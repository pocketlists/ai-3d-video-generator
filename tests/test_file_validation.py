"""Tests for file validation utilities."""
import json
import os
import tempfile
import pytest

from utils.file_validator import (
    validate_file_exists, validate_file_nonempty, validate_file_extension,
    validate_json_file, validate_video_file, validate_audio_file,
    validate_image_file, validate_blender_file, validate_directory,
    validate_required_files, safe_validate, ValidationError,
)


def test_validate_file_exists(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("hello")
    assert validate_file_exists(str(f))


def test_validate_file_exists_missing():
    with pytest.raises(ValidationError):
        validate_file_exists("/nonexistent/path/file.txt")


def test_validate_file_nonempty(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("content")
    assert validate_file_nonempty(str(f))


def test_validate_file_nonempty_empty(tmp_path):
    f = tmp_path / "empty.txt"
    f.write_text("")
    with pytest.raises(ValidationError):
        validate_file_nonempty(str(f))


def test_validate_file_extension():
    assert validate_file_extension("video.mp4", [".mp4", ".avi"])
    assert validate_file_extension("image.PNG", [".png"])


def test_validate_file_extension_wrong():
    with pytest.raises(ValidationError):
        validate_file_extension("video.txt", [".mp4"])


def test_validate_json_file(tmp_path):
    f = tmp_path / "data.json"
    f.write_text('{"key": "value"}')
    assert validate_json_file(str(f))


def test_validate_json_file_invalid(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text("not json")
    with pytest.raises(ValidationError):
        validate_json_file(str(f))


def test_validate_video_file(tmp_path):
    f = tmp_path / "video.mp4"
    f.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 1000)
    assert validate_video_file(str(f))


def test_validate_video_file_too_small(tmp_path):
    f = tmp_path / "small.mp4"
    f.write_bytes(b"\x00")
    with pytest.raises(ValidationError):
        validate_video_file(str(f))


def test_validate_audio_file(tmp_path):
    f = tmp_path / "audio.wav"
    f.write_bytes(b"\x00" * 100)
    assert validate_audio_file(str(f))


def test_validate_image_file(tmp_path):
    f = tmp_path / "image.png"
    f.write_bytes(b"\x89PNG" + b"\x00" * 100)
    assert validate_image_file(str(f))


def test_validate_blender_file(tmp_path):
    f = tmp_path / "scene.blend"
    f.write_bytes(b"\x00" * 100)
    assert validate_blender_file(str(f))


def test_validate_directory(tmp_path):
    assert validate_directory(str(tmp_path))
    f = tmp_path / "file.txt"
    f.write_text("x")
    assert validate_directory(str(tmp_path), min_files=1)


def test_validate_required_files_all_exist(tmp_path):
    f1 = tmp_path / "a.txt"
    f2 = tmp_path / "b.txt"
    f1.write_text("a")
    f2.write_text("b")
    success, missing = validate_required_files([str(f1), str(f2)])
    assert success
    assert len(missing) == 0


def test_validate_required_files_some_missing(tmp_path):
    f1 = tmp_path / "a.txt"
    f1.write_text("a")
    success, missing = validate_required_files([str(f1), "/nonexistent/b.txt"])
    assert not success
    assert len(missing) == 1


def test_safe_validate_success(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("content")
    success, error = safe_validate(str(f), validate_file_nonempty)
    assert success
    assert error is None


def test_safe_validate_failure():
    success, error = safe_validate("/nonexistent", validate_file_exists)
    assert not success
    assert error is not None
