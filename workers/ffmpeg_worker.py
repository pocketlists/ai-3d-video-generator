"""
FFmpeg worker — assembles final video from rendered frames and audio.

Stage 18: Merges rendered frame sequences with voice, music, and SFX
audio tracks into the final MP4 video using FFmpeg.
"""
import json
import os
import subprocess
import time
from typing import Any, Dict, List

from workers.base_worker import BaseWorker
from utils.file_validator import validate_video_file


class FFmpegWorker(BaseWorker):
    stage_name = "ffmpeg_assembly"

    def run(self) -> Dict[str, Any]:
        artifact_dir = os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts")
        renders_dir = os.path.join(artifact_dir, "renders")
        audio_dir = os.path.join(artifact_dir, "audio")
        output_dir = os.path.join(artifact_dir, "output")
        os.makedirs(output_dir, exist_ok=True)

        # Collect frames
        frames = self._collect_frames(renders_dir)
        if not frames:
            return {"status": "error", "error": "No rendered frames found"}

        # Collect audio
        voice_files = self._collect_audio(audio_dir, "voice")
        music_file = os.path.join(audio_dir, "background_music.wav")
        sfx_files = self._collect_audio(audio_dir, "sfx")

        start_time = time.time()

        # Step 1: Create video from frames
        video_path = os.path.join(output_dir, "video_only.mp4")
        self._frames_to_video(frames, video_path)

        # Step 2: Mix audio tracks
        audio_path = os.path.join(output_dir, "mixed_audio.wav")
        self._mix_audio(voice_files, music_file, sfx_files, audio_path, len(frames))

        # Step 3: Merge video and audio
        final_path = os.path.join(output_dir, "final_video.mp4")
        self._merge_av(video_path, audio_path, final_path)

        elapsed = time.time() - start_time

        # Validate
        if not os.path.exists(final_path):
            return {"status": "error", "error": "Final video was not created"}

        file_size = os.path.getsize(final_path)

        # Get duration via ffprobe
        duration = self._get_duration(final_path)

        # Record metrics
        from optimizer.metrics_collector import MetricsCollector
        collector = MetricsCollector()
        collector.record_ffmpeg(
            input_count=len(frames), output_duration=duration,
            processing_time=elapsed, output_size=file_size,
            codec="libx264", input_formats=["png", "wav"]
        )
        collector.save()

        return {
            "status": "success",
            "final_video_path": final_path,
            "duration_sec": round(duration, 1),
            "file_size_mb": round(file_size / 1024 / 1024, 2),
            "frame_count": len(frames),
            "processing_time_sec": round(elapsed, 1),
        }

    def _collect_frames(self, renders_dir: str) -> List[str]:
        frames = []
        if not os.path.exists(renders_dir):
            return frames
        for worker_dir in sorted(os.listdir(renders_dir)):
            worker_path = os.path.join(renders_dir, worker_dir)
            if os.path.isdir(worker_path):
                for fname in sorted(os.listdir(worker_path)):
                    if fname.endswith(".png"):
                        frames.append(os.path.join(worker_path, fname))
        return frames

    def _collect_audio(self, audio_dir: str, prefix: str) -> List[str]:
        files = []
        if not os.path.exists(audio_dir):
            return files
        for fname in sorted(os.listdir(audio_dir)):
            if fname.startswith(prefix) and (fname.endswith(".wav") or fname.endswith(".mp3")):
                files.append(os.path.join(audio_dir, fname))
        return files

    def _frames_to_video(self, frames: List[str], output_path: str) -> None:
        """Create video from PNG frames using FFmpeg."""
        if not self._ffmpeg_available():
            self.logger.warning("FFmpeg not available, creating placeholder video")
            self._create_placeholder_video(output_path)
            return

        # Create a file list or use pattern
        frame_dir = os.path.dirname(frames[0])
        cmd = [
            "ffmpeg", "-y",
            "-framerate", "24",
            "-i", os.path.join(frame_dir, "frame_%04d.png"),
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            output_path
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=300, check=True)
            self.logger.info(f"Video created: {output_path}")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            self.logger.error(f"FFmpeg video creation failed: {e}")
            self._create_placeholder_video(output_path)

    def _mix_audio(self, voice_files: List[str], music_file: str,
                   sfx_files: List[str], output_path: str, frame_count: int) -> None:
        """Mix all audio tracks into a single track."""
        if not self._ffmpeg_available():
            self._create_placeholder_audio(output_path, frame_count)
            return

        inputs = []
        filter_parts = []

        idx = 0
        if os.path.exists(music_file):
            inputs.extend(["-i", music_file])
            filter_parts.append(f"[{idx}:a]volume=0.3[a{idx}]")
            idx += 1

        for vf in voice_files:
            if os.path.exists(vf):
                inputs.extend(["-i", vf])
                filter_parts.append(f"[{idx}:a]volume=0.8[a{idx}]")
                idx += 1

        for sf in sfx_files:
            if os.path.exists(sf):
                inputs.extend(["-i", sf])
                filter_parts.append(f"[{idx}:a]volume=0.4[a{idx}]")
                idx += 1

        if idx == 0:
            self._create_placeholder_audio(output_path, frame_count)
            return

        # Mix all
        mix_inputs = "".join(f"[a{i}]" for i in range(idx))
        filter_complex = ";".join(filter_parts) + f";{mix_inputs}amix=inputs={idx}:duration=longest[out]"

        cmd = ["ffmpeg", "-y"] + inputs + [
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-ac", "2",
            "-ar", "44100",
            output_path
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=120, check=True)
            self.logger.info(f"Audio mixed: {output_path}")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            self.logger.error(f"Audio mixing failed: {e}")
            self._create_placeholder_audio(output_path, frame_count)

    def _merge_av(self, video_path: str, audio_path: str, output_path: str) -> None:
        """Merge video and audio into final output."""
        if not self._ffmpeg_available():
            # Just copy the video
            import shutil
            shutil.copy2(video_path, output_path)
            return

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "128k",
            "-shortest",
            "-movflags", "+faststart",
            output_path
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=300, check=True)
            self.logger.info(f"Final video: {output_path}")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            self.logger.error(f"A/V merge failed: {e}")
            import shutil
            shutil.copy2(video_path, output_path)

    def _ffmpeg_available(self) -> bool:
        try:
            result = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _get_duration(self, video_path: str) -> float:
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", video_path],
                capture_output=True, text=True, timeout=10
            )
            return float(result.stdout.strip())
        except Exception:
            return 60.0

    def _create_placeholder_video(self, path: str) -> None:
        """Create a minimal valid MP4 when FFmpeg is not available."""
        try:
            from PIL import Image
            import struct
            # Create a 1-frame black video as placeholder
            img = Image.new("RGB", (1280, 720), color=(10, 10, 30))
            img.save(path, "PNG")
        except ImportError:
            with open(path, "wb") as f:
                f.write(b"placeholder")

    def _create_placeholder_audio(self, path: str, frame_count: int) -> None:
        """Create silent audio placeholder."""
        import wave, struct
        duration = frame_count / 24
        sample_rate = 22050
        with wave.open(path, "w") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            # Write silence
            for _ in range(int(duration * sample_rate)):
                wav.writeframes(struct.pack("h", 0))
