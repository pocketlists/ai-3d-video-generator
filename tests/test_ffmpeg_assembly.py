"""Tests for FFmpeg assembly worker."""
import json
import os
import tempfile
import pytest

from workers.ffmpeg_worker import FFmpegWorker


def test_ffmpeg_worker_init():
    worker = FFmpegWorker({"prompt": "test"})
    assert worker.stage_name == "ffmpeg_assembly"


def test_ffmpeg_collect_frames(tmp_path):
    worker = FFmpegWorker({"prompt": "test"})
    # Create fake render frames
    renders_dir = tmp_path / "renders" / "worker_0"
    renders_dir.mkdir(parents=True)
    for i in range(5):
        (renders_dir / f"frame_{i:04d}.png").write_bytes(b"\x00" * 100)

    frames = worker._collect_frames(str(tmp_path / "renders"))
    assert len(frames) == 5


def test_ffmpeg_collect_frames_empty(tmp_path):
    worker = FFmpegWorker({"prompt": "test"})
    frames = worker._collect_frames(str(tmp_path / "nonexistent"))
    assert frames == []


def test_ffmpeg_collect_audio(tmp_path):
    worker = FFmpegWorker({"prompt": "test"})
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    (audio_dir / "voice_shot_1.mp3").write_bytes(b"\x00" * 100)
    (audio_dir / "voice_shot_2.mp3").write_bytes(b"\x00" * 100)
    (audio_dir / "sfx_ambient_1.wav").write_bytes(b"\x00" * 100)

    voice_files = worker._collect_audio(str(audio_dir), "voice")
    assert len(voice_files) == 2

    sfx_files = worker._collect_audio(str(audio_dir), "sfx")
    assert len(sfx_files) == 1


def test_ffmpeg_available():
    worker = FFmpegWorker({"prompt": "test"})
    # Should return True or False without raising
    result = worker._ffmpeg_available()
    assert isinstance(result, bool)


def test_ffmpeg_get_duration(tmp_path):
    worker = FFmpegWorker({"prompt": "test"})
    # Test with nonexistent file (should return default)
    duration = worker._get_duration("/nonexistent/video.mp4")
    assert duration == 60.0


def test_ffmpeg_placeholder_audio(tmp_path):
    worker = FFmpegWorker({"prompt": "test"})
    audio_path = str(tmp_path / "silent.wav")
    worker._create_placeholder_audio(audio_path, frame_count=240)
    assert os.path.exists(audio_path)
    assert os.path.getsize(audio_path) > 0
