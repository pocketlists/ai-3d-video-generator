"""
Voice TTS worker — uses Google free TTS provider.

Stage 11: Converts narration text to speech using configurable TTS provider.
Supports Hindi, Hinglish, and English. Uses caching.
"""
import json
import os
from typing import Any, Dict, List

from workers.base_worker import BaseWorker
from providers.tts_provider import get_tts_provider


class VoiceTTSWorker(BaseWorker):
    stage_name = "voice_tts"

    def run(self) -> Dict[str, Any]:
        breakdown = self._load_breakdown()
        if not breakdown:
            return {"status": "error", "error": "No breakdown found"}

        tts = get_tts_provider(self.config)
        self.logger.info(f"Using TTS provider: {tts.__class__.__name__}")

        audio_files = []
        for shot in breakdown.get("shots", []):
            narration = shot.get("narration", "").strip()
            if not narration:
                continue

            # Determine language from narration or config
            language = self.config.get("tts_language", "en")

            # Handle long narration
            audio_paths = tts.synthesize_long(narration, language=language)
            if audio_paths:
                filepath = audio_paths[0] if len(audio_paths) == 1 else self._merge_audio(audio_paths)
                audio_files.append({
                    "scene_id": shot["scene_id"],
                    "text": narration,
                    "filepath": filepath,
                    "source": tts.__class__.__name__,
                    "frame_start": shot["frame_start"],
                    "frame_end": shot["frame_end"],
                })
                self.logger.info(f"Voice generated for shot {shot['scene_id']} via {tts.__class__.__name__}")

        path = self._save_voice_manifest(audio_files)
        return {
            "status": "success",
            "voice_manifest_path": path,
            "audio_count": len(audio_files),
            "tts_provider": tts.__class__.__name__,
        }

    def _merge_audio(self, paths: List[str]) -> str:
        """Merge multiple audio files into one using FFmpeg."""
        out_dir = os.path.dirname(paths[0])
        output = os.path.join(out_dir, f"merged_{int(__import__('time').time())}.mp3")
        import subprocess
        try:
            cmd = ["ffmpeg", "-y"]
            for p in paths:
                cmd.extend(["-i", p])
            cmd.extend(["-filter_complex", f"concat=n={len(paths)}:v=0:a=1", output])
            subprocess.run(cmd, capture_output=True, timeout=60, check=True)
            return output
        except Exception:
            return paths[0]  # Fallback to first file

    def _load_breakdown(self) -> Dict:
        artifact_dir = os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts")
        path = os.path.join(artifact_dir, "script_breakdown.json")
        if not os.path.exists(path):
            return {}
        with open(path) as f:
            return json.load(f)

    def _save_voice_manifest(self, audio_files: List[Dict]) -> str:
        out_dir = os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts")
        path = os.path.join(out_dir, "voice_manifest.json")
        with open(path, "w") as f:
            json.dump(audio_files, f, indent=2)
        return path
