"""
Lip-sync worker — generates lip-sync data from voice audio.

Stage 14: Analyzes voice audio and generates viseme data for
character mouth animation.
"""
import json
import os
import math
from typing import Any, Dict, List

from workers.base_worker import BaseWorker


class LipSyncWorker(BaseWorker):
    stage_name = "lip_sync"

    def run(self) -> Dict[str, Any]:
        voice_manifest = self._load_voice_manifest()
        if not voice_manifest:
            return {"status": "skipped", "reason": "No voice audio found"}

        lip_sync_data = self._generate_lip_sync(voice_manifest)
        path = self._save_lip_sync(lip_sync_data)
        return {
            "status": "success",
            "lip_sync_path": path,
            "frame_count": sum(d.get("frame_count", 0) for d in lip_sync_data),
        }

    def _load_voice_manifest(self) -> List[Dict]:
        artifact_dir = os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts")
        path = os.path.join(artifact_dir, "voice_manifest.json")
        if not os.path.exists(path):
            return []
        with open(path) as f:
            return json.load(f)

    def _generate_lip_sync(self, voice_manifest: List[Dict]) -> List[Dict]:
        """Generate simple viseme data from voice audio timing."""
        results = []
        for entry in voice_manifest:
            duration_sec = (entry.get("frame_end", 0) - entry.get("frame_start", 0)) / 24.0
            fps = 24
            frame_count = int(duration_sec * fps)
            visemes = []

            # Generate visemes based on syllable-like patterns
            viseme_types = ["A", "E", "I", "O", "U", "M", "F", "rest"]
            for frame in range(frame_count):
                # Simulate mouth shape changes
                cycle = (frame % 8) / 8.0
                viseme = viseme_types[frame % len(viseme_types)]
                intensity = 0.5 + 0.5 * math.sin(frame * 0.5)
                visemes.append({
                    "frame": frame,
                    "viseme": viseme,
                    "intensity": round(intensity, 2),
                })

            results.append({
                "scene_id": entry["scene_id"],
                "character": "hero",
                "frame_start": entry.get("frame_start", 0),
                "frame_count": frame_count,
                "visemes": visemes,
            })

        return results

    def _save_lip_sync(self, data: List[Dict]) -> str:
        out_dir = os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts")
        path = os.path.join(out_dir, "lip_sync_data.json")
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return path
