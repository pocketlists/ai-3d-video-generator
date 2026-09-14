"""
SFX worker — generates sound effects.

Stage 13: Creates sound effects (footsteps, ambient, whoosh, etc.)
using procedural audio generation.
"""
import json
import os
import math
import struct
import wave
from typing import Any, Dict, List

from workers.base_worker import BaseWorker


class SFXWorker(BaseWorker):
    stage_name = "sfx"

    def run(self) -> Dict[str, Any]:
        breakdown = self._load_breakdown()
        if not breakdown:
            return {"status": "error", "error": "No breakdown found"}

        sfx_files = self._generate_sfx(breakdown)
        path = self._save_sfx_manifest(sfx_files)
        return {
            "status": "success",
            "sfx_manifest_path": path,
            "sfx_count": len(sfx_files),
        }

    def _load_breakdown(self) -> Dict:
        artifact_dir = os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts")
        path = os.path.join(artifact_dir, "script_breakdown.json")
        if not os.path.exists(path):
            return {}
        with open(path) as f:
            return json.load(f)

    def _generate_sfx(self, breakdown: Dict) -> List[Dict]:
        out_dir = os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts/audio")
        os.makedirs(out_dir, exist_ok=True)
        sfx_files = []
        sample_rate = 22050

        for shot in breakdown.get("shots", []):
            # Footstep sounds
            for char in shot.get("characters", []):
                for step_idx in range(3):
                    filename = f"sfx_footstep_{shot['scene_id']}_{step_idx}.wav"
                    filepath = os.path.join(out_dir, filename)
                    self._generate_footstep(filepath, sample_rate)
                    sfx_files.append({
                        "type": "footstep",
                        "scene_id": shot["scene_id"],
                        "character": char["name"],
                        "filepath": filepath,
                        "frame_offset": int(step_idx * shot.get("duration_sec", 15) / 3 * shot.get("fps", 24)),
                    })

            # Ambient sound
            filename = f"sfx_ambient_{shot['scene_id']}.wav"
            filepath = os.path.join(out_dir, filename)
            self._generate_ambient(filepath, sample_rate, int(shot.get("duration_sec", 15)))
            sfx_files.append({
                "type": "ambient",
                "scene_id": shot["scene_id"],
                "filepath": filepath,
                "frame_start": shot["frame_start"],
                "frame_end": shot["frame_end"],
            })

        return sfx_files

    def _generate_footstep(self, filepath: str, sample_rate: int) -> None:
        """Generate a simple footstep sound."""
        duration = 0.15
        samples = []
        for i in range(int(duration * sample_rate)):
            t = i / sample_rate
            envelope = math.exp(-t * 30)
            noise = (math.sin(2 * math.pi * 80 * t) + 0.5 * math.sin(2 * math.pi * 120 * t))
            value = noise * envelope * 0.3
            samples.append(int(value * 32767))

        with wave.open(filepath, "w") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(struct.pack(f"{len(samples)}h", *samples))

    def _generate_ambient(self, filepath: str, sample_rate: int, duration: int) -> None:
        """Generate ambient wind sound."""
        total_samples = duration * sample_rate
        samples = []
        for i in range(total_samples):
            t = i / sample_rate
            # Low frequency wind with random variation
            value = 0.05 * math.sin(2 * math.pi * 0.5 * t) + 0.02 * math.sin(2 * math.pi * 0.3 * t)
            samples.append(int(value * 32767))

        with wave.open(filepath, "w") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(struct.pack(f"{len(samples)}h", *samples))

    def _save_sfx_manifest(self, sfx_files: List[Dict]) -> str:
        out_dir = os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts")
        path = os.path.join(out_dir, "sfx_manifest.json")
        with open(path, "w") as f:
            json.dump(sfx_files, f, indent=2)
        return path
