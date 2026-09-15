"""
Lip Sync Provider — generates viseme data from voice audio.

BasicLipSyncProvider: Analyzes audio amplitude to generate mouth shapes.
Fails gracefully if dependencies are missing.
"""
import json
import math
import os
import wave
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from utils.logger import PipelineLogger


class LipSyncProvider(ABC):
    """Abstract base for lip-sync providers."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = PipelineLogger("lip_sync_provider")

    @abstractmethod
    def generate_visemes(self, audio_path: str, fps: int = 24) -> List[Dict]:
        ...

    @abstractmethod
    def is_available(self) -> bool:
        ...


class BasicLipSyncProvider(LipSyncProvider):
    """Basic lip-sync using audio amplitude analysis."""

    def is_available(self) -> bool:
        return True

    def generate_visemes(self, audio_path: str, fps: int = 24) -> List[Dict]:
        if not os.path.exists(audio_path):
            self.logger.error(f"Audio file not found: {audio_path}")
            return []

        visemes = []
        viseme_types = ["A", "E", "I", "O", "U", "M", "F", "rest"]

        try:
            with wave.open(audio_path, "r") as wav:
                n_frames = wav.getnframes()
                framerate = wav.getframerate()
                audio_data = wav.readframes(n_frames)

            import struct
            samples = struct.unpack(f"<{n_frames}h", audio_data) if n_frames > 0 else []
            duration = n_frames / framerate if framerate > 0 else 0
            total_frames = int(duration * fps)

            for frame in range(total_frames):
                # Sample audio at this frame position
                sample_start = int(frame * framerate / fps)
                sample_end = int((frame + 1) * framerate / fps)
                frame_samples = samples[sample_start:sample_end] if sample_end < len(samples) else []

                if frame_samples:
                    amplitude = sum(abs(s) for s in frame_samples) / len(frame_samples) / 32768.0
                else:
                    amplitude = 0.0

                # Map amplitude to viseme
                if amplitude < 0.05:
                    viseme = "rest"
                elif amplitude < 0.2:
                    viseme = "M"
                elif amplitude < 0.4:
                    viseme = "A"
                elif amplitude < 0.6:
                    viseme = "O"
                else:
                    viseme = "E"

                visemes.append({
                    "frame": frame,
                    "viseme": viseme,
                    "intensity": round(amplitude, 2),
                })

            self.logger.info(f"Generated {len(visemes)} visemes from {audio_path}")
            return visemes

        except Exception as e:
            self.logger.error(f"Lip-sync generation failed: {e}")
            # Fail gracefully — return empty visemes
            return []


def get_lip_sync_provider(config: Dict[str, Any]) -> LipSyncProvider:
    return BasicLipSyncProvider(config)
