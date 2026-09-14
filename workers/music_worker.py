"""
Music worker — generates or selects background music.

Stage 12: Creates background music tracks. Can use AI music generation
or procedural music generation as fallback.
"""
import json
import os
import math
import struct
import wave
from typing import Any, Dict

from workers.base_worker import BaseWorker


class MusicWorker(BaseWorker):
    stage_name = "music"

    def run(self) -> Dict[str, Any]:
        breakdown = self._load_breakdown()
        if not breakdown:
            return {"status": "error", "error": "No breakdown found"}

        music_path = self._generate_music(breakdown)
        return {
            "status": "success",
            "music_path": music_path,
            "duration_sec": breakdown.get("total_duration_sec", 60),
        }

    def _load_breakdown(self) -> Dict:
        artifact_dir = os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts")
        path = os.path.join(artifact_dir, "script_breakdown.json")
        if not os.path.exists(path):
            return {}
        with open(path) as f:
            return json.load(f)

    def _generate_music(self, breakdown: Dict) -> str:
        """Generate a simple procedural ambient music track."""
        duration = int(breakdown.get("total_duration_sec", 60))
        sample_rate = 22050
        out_dir = os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts/audio")
        os.makedirs(out_dir, exist_ok=True)
        filepath = os.path.join(out_dir, "background_music.wav")

        # Generate simple chord progression as WAV
        total_samples = duration * sample_rate
        # C major - A minor - F major - G major progression
        chords = [
            (261.63, 329.63, 392.00),  # C major
            (220.00, 261.63, 329.63),  # A minor
            (174.61, 220.00, 261.63),  # F major
            (196.00, 246.94, 293.66),  # G major
        ]
        chord_duration = total_samples // len(chords)

        samples = []
        for chord_idx, chord in enumerate(chords):
            start = chord_idx * chord_duration
            for i in range(chord_duration):
                t = i / sample_rate
                # Add gentle envelope
                envelope = min(1.0, i / (sample_rate * 0.5)) * min(1.0, (chord_duration - i) / (sample_rate * 0.5))
                value = sum(math.sin(2 * math.pi * freq * t) for freq in chord) / len(chord)
                value *= 0.15 * envelope  # low volume
                samples.append(int(value * 32767))

        with wave.open(filepath, "w") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(struct.pack(f"{len(samples)}h", *samples))

        self.logger.info(f"Generated music: {filepath} ({duration}s)")
        return filepath
