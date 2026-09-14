"""
Blender assembly worker — assembles the complete Blender scene.

Stage 15: Combines characters, environments, props, camera, lighting,
animation, and lip-sync data into a single Blender scene script.
"""
import json
import os
from typing import Any, Dict

from workers.base_worker import BaseWorker
from blender.scene_builder import SceneBuilder
from blender.optimization import BlenderOptimizer, SceneComplexity
from optimizer.metrics_collector import MetricsCollector


class BlenderAssemblyWorker(BaseWorker):
    stage_name = "blender_assembly"

    def run(self) -> Dict[str, Any]:
        artifact_dir = os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts")

        # Load all artifacts
        breakdown = self._load_json(os.path.join(artifact_dir, "script_breakdown.json"))
        characters = self._load_json(os.path.join(artifact_dir, "characters.json"))
        environments = self._load_json(os.path.join(artifact_dir, "environments.json"))
        props = self._load_json(os.path.join(artifact_dir, "props.json"))
        camera_data = self._load_json(os.path.join(artifact_dir, "camera_data.json"))
        lighting_data = self._load_json(os.path.join(artifact_dir, "lighting_data.json"))
        animations = self._load_json(os.path.join(artifact_dir, "animations.json"))

        if not breakdown:
            return {"status": "error", "error": "No breakdown found"}

        # Estimate scene complexity
        total_verts = sum(c.get("vertex_count", 0) for c in characters)
        total_verts += sum(e.get("vertex_count", 0) for e in environments)
        total_verts += sum(p.get("vertex_count", 0) for p in props)
        total_faces = sum(c.get("face_count", 0) for c in characters)
        total_faces += sum(e.get("face_count", 0) for e in environments)
        total_faces += sum(p.get("face_count", 0) for p in props)

        complexity = SceneComplexity(
            object_count=len(characters) + len(environments) + len(props),
            total_vertices=total_verts,
            total_faces=total_faces,
            light_count=3,
        )

        # Optimize settings
        optimizer = BlenderOptimizer(previous_runs=self._load_previous_metrics())
        render_config = breakdown.get("render_config", {})
        settings = optimizer.optimize_settings(
            complexity,
            requested_resolution=tuple(render_config.get("resolution", [1280, 720])),
            requested_samples=render_config.get("samples", 64),
        )

        self.logger.info(optimizer.get_optimization_report(settings))

        # Build scene plan
        scene_plan = {
            "characters": self._extract_char_specs(characters, breakdown),
            "environment": {"type": "outdoor"},
            "props": self._extract_prop_specs(props, breakdown),
            "camera": self._extract_camera_spec(camera_data, breakdown),
            "lighting": self._extract_lighting_spec(lighting_data, breakdown),
            "animation": {
                "fps": breakdown.get("fps", 24),
                "total_frames": breakdown.get("total_frames", 1440),
                "data": animations,
            },
            "render": settings,
            "output_blend": os.path.join(artifact_dir, "scene", "scene.blend"),
        }

        # Validate
        builder = SceneBuilder()
        issues = builder.validate_scene_plan(scene_plan)
        for issue in issues:
            self.logger.warning(f"Scene plan issue: {issue}")

        # Generate scene script
        script_path = builder.build_scene_script(scene_plan)

        return {
            "status": "success",
            "scene_script_path": script_path,
            "scene_plan_path": os.path.join(artifact_dir, "scene", "scene_plan.json"),
            "complexity_score": settings.get("complexity_score", 0),
            "complexity_label": settings.get("complexity_label", "unknown"),
            "render_settings": settings,
        }

    def _load_json(self, path: str) -> Any:
        if not os.path.exists(path):
            return {}
        with open(path) as f:
            return json.load(f)

    def _load_previous_metrics(self) -> list:
        collector = MetricsCollector()
        return collector.load_previous_runs(limit=10)

    def _extract_char_specs(self, characters: list, breakdown: dict) -> list:
        specs = []
        for shot in breakdown.get("shots", []):
            for char in shot.get("characters", []):
                specs.append({
                    "name": char["name"],
                    "position": char.get("position", [0, 0, 0]),
                })
        return specs or [{"name": "hero", "position": [0, 0, 0]}]

    def _extract_prop_specs(self, props: list, breakdown: dict) -> list:
        specs = []
        for shot in breakdown.get("shots", []):
            for prop in shot.get("props", []):
                specs.append({
                    "name": prop["name"],
                    "type": prop.get("type", "box"),
                    "position": prop.get("position", [0, 0, 0]),
                })
        return specs

    def _extract_camera_spec(self, camera_data: dict, breakdown: dict) -> dict:
        shots = camera_data.get("shots", [])
        if shots:
            first = shots[0]
            cam = first.get("keyframes", [{}])[0]
            return {
                "type": first.get("cam_type", "static"),
                "location": cam.get("location", [5, -5, 3]),
                "target": cam.get("target", [0, 0, 1]),
            }
        return {"type": "static", "location": [5, -5, 3], "target": [0, 0, 1]}

    def _extract_lighting_spec(self, lighting_data: dict, breakdown: dict) -> dict:
        shots = lighting_data.get("shots", [])
        if shots:
            lights = shots[0].get("lights", [])
            key = next((l for l in lights if l["name"] == "key_light"), {})
            return {
                "type": key.get("type", "sun"),
                "energy": key.get("energy", 3.0),
                "location": key.get("location", [5, 5, 10]),
            }
        return {"type": "sun", "energy": 3.0, "location": [5, 5, 10]}
