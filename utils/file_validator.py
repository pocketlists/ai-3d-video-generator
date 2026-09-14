"""
File validator — validates that pipeline output files exist and are non-empty.

Provides functions to check file existence, size, format, and integrity
before dependent stages consume them.
"""
import json
import os
from pathlib import Path
from typing import List, Optional, Tuple


class ValidationError(Exception):
    """Raised when a file fails validation."""


def validate_file_exists(path: str) -> bool:
    """Check that a file exists."""
    if not os.path.exists(path):
        raise ValidationError(f"File does not exist: {path}")
    return True


def validate_file_nonempty(path: str) -> bool:
    """Check that a file exists and is non-empty."""
    validate_file_exists(path)
    if os.path.getsize(path) == 0:
        raise ValidationError(f"File is empty: {path}")
    return True


def validate_file_extension(path: str, extensions: List[str]) -> bool:
    """Check that a file has one of the allowed extensions."""
    ext = Path(path).suffix.lower()
    if ext not in [e.lower() for e in extensions]:
        raise ValidationError(f"File '{path}' has extension '{ext}', expected one of {extensions}")
    return True


def validate_json_file(path: str) -> bool:
    """Validate that a file is valid, non-empty JSON."""
    validate_file_nonempty(path)
    try:
        with open(path, "r") as f:
            json.load(f)
    except json.JSONDecodeError as e:
        raise ValidationError(f"Invalid JSON in {path}: {e}")
    return True


def validate_video_file(path: str, min_size_bytes: int = 1000) -> bool:
    """Validate a video file exists, is non-empty, and has a video extension."""
    validate_file_extension(path, [".mp4", ".avi", ".mov", ".mkv", ".webm"])
    validate_file_exists(path)
    if os.path.getsize(path) < min_size_bytes:
        raise ValidationError(f"Video file too small ({os.path.getsize(path)} bytes): {path}")
    return True


def validate_audio_file(path: str) -> bool:
    """Validate an audio file."""
    validate_file_extension(path, [".wav", ".mp3", ".aac", ".ogg", ".flac"])
    validate_file_nonempty(path)
    return True


def validate_image_file(path: str) -> bool:
    """Validate an image file."""
    validate_file_extension(path, [".png", ".jpg", ".jpeg", ".webp", ".tga"])
    validate_file_nonempty(path)
    return True


def validate_blender_file(path: str) -> bool:
    """Validate a Blender file."""
    validate_file_extension(path, [".blend", ".blend1"])
    validate_file_nonempty(path)
    return True


def validate_directory(path: str, min_files: int = 0) -> bool:
    """Validate a directory exists and optionally has minimum files."""
    if not os.path.isdir(path):
        raise ValidationError(f"Directory does not exist: {path}")
    files = os.listdir(path)
    if len(files) < min_files:
        raise ValidationError(f"Directory '{path}' has {len(files)} files, needs {min_files}")
    return True


def validate_required_files(paths: List[str]) -> Tuple[bool, List[str]]:
    """Validate multiple files exist and are non-empty. Returns (success, missing)."""
    missing = []
    for path in paths:
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            missing.append(path)
    return (len(missing) == 0, missing)


def safe_validate(path: str, validator_func) -> Tuple[bool, Optional[str]]:
    """Run a validator, catching exceptions. Returns (success, error_message)."""
    try:
        validator_func(path)
        return (True, None)
    except ValidationError as e:
        return (False, str(e))
