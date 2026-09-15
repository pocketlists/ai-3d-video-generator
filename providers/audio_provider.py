"""
Audio providers — music and SFX generation.

MusicProvider: Generates background music (procedural or API-based)
SFXProvider: Generates sound effects (procedural or library-based)
"""
import math
import os
import struct
import wave
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from utils.logger import PipelineLogger


class MusicProvider(ABC):
    """Abstract base for music providers."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = PipelineLogger("music_provider")

    @abstractmethod
    def generate(self, duration_sec: int, mood: str = "ambient") -> Optional[str]:
        ...

    @abstractmethod
    def is_available(self) -> bool:
        ...


class ProceduralMusicProvider(MusicProvider):
    """Generates simple procedural ambient music using WAV synthesis."""

    def is_available(self) -> bool:
        return True

    def generate(self, duration_sec: int, mood: str = "ambient") -> Optional[str]:
        out_dir = self.config.get("artifact_dir", "/tmp/pipeline_artifacts")
        audio_dir = os.path.join(out_dir, "audio")
        os.makedirs(audio_dir, exist_ok=True)
        filepath = os.path.join(audio_dir, "background_music.wav")

        sample_rate = 22050
        total_samples = duration_sec * sample_rate

        # Chord progression based on mood
        if mood == "happy":
            chords = [(261.63, 329.63, 392.00), (293.66, 369.99, 440.00),
                      (349.23, 440.00, 523.25), (392.00, 493.88, 587.33)]
        elif mood == "sad":
            chords = [(220.00, 261.63, 329.63), (196.00, 233.08, 293.66),
                      (174.61, 220.00, 261.63), (164.81, 196.00, 246.94)]
        else:  # ambient
            chords = [(261.63, 329.63, 392.00), (220.00, 261.63, 329.63),
                      (174.61, 220.00, 261.63), (196.00, 246.94, 293.66)]

        chord_duration = total_samples // len(chords)
        samples = []
        for chord_idx, chord in enumerate(chords):
            for i in range(chord_duration):
                t = i / sample_rate
                envelope = min(1.0, i / (sample_rate * 0.5)) * \
                           min(1.0, (chord_duration - i) / (sample_rate * 0.5))
                value = sum(math.sin(2 * math.pi * freq * t) for freq in chord) / len(chord)
                value *= 0.15 * envelope
                samples.append(int(value * 32767))

        with wave.open(filepath, "w") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(struct.pack(f"{len(samples)}h", *samples))

        self.logger.info(f"Music generated: {filepath} ({duration_sec}s, {mood})")
        return filepath


class SFXProvider(ABC):
    """Abstract base for SFX providers."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = PipelineLogger("sfx_provider")

    @abstractmethod
    def generate(self, sfx_type: str, duration_sec: float = 0.5) -> Optional[str]:
        ...

    @abstractmethod
    def is_available(self) -> bool:
        ...


class ProceduralSFXProvider(SFXProvider):
    """Generates simple procedural sound effects."""

    def is_available(self) -> bool:
        return True

    def generate(self, sfx_type: str, duration_sec: float = 0.5) -> Optional[str]:
        out_dir = self.config.get("artifact_dir", "/tmp/pipeline_artifacts")
        audio_dir = os.path.join(out_dir, "audio")
        os.makedirs(audio_dir, exist_ok=True)
        filepath = os.path.join(audio_dir, f"sfx_{sfx_type}_{int(duration_sec*1000)}ms.wav")

        sample_rate = 22050
        total_samples = int(duration_sec * sample_rate)
        samples = []

        if sfx_type == "footstep":
            for i in range(total_samples):
                t = i / sample_rate
                envelope = math.exp(-t * 30)
                value = (math.sin(2 * math.pi * 80 * t) + 0.5 * math.sin(2 * math.pi * 120 * t))
                value *= envelope * 0.3
                samples.append(int(value * 32767))
        elif sfx_type == "ambient":
            for i in range(total_samples):
                t = i / sample_rate
                value = 0.05 * math.sin(2 * math.pi * 0.5 * t) + 0.02 * math.sin(2 * math.pi * 0.3 * t)
                samples.append(int(value * 32767))
        elif sfx_type == "whoosh":
            for i in range(total_samples):
                t = i / sample_rate
                progress = i / total_samples
                envelope = math.sin(progress * math.pi)
                freq = 200 + progress * 800
                value = math.sin(2 * math.pi * freq * t) * envelope * 0.2
                samples.append(int(value * 32767))
        else:
            # Generic beep
            for i in range(total_samples):
                t = i / sample_rate
                envelope = math.exp(-t * 5)
                value = math.sin(2 * math.pi * 440 * t) * envelope * 0.2
                samples.append(int(value * 32767))

        with wave.open(filepath, "w") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(struct.pack(f"{len(samples)}h", *samples))

        return filepath


def get_music_provider(config: Dict[str, Any]) -> MusicProvider:
    return ProceduralMusicProvider(config)


def get_sfx_provider(config: Dict[str, Any]) -> SFXProvider:
    return ProceduralSFXProvider(config)
