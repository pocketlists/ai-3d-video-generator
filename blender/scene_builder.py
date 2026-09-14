"""
Scene builder — assembles a complete Blender scene from pipeline assets.

Takes character meshes, environments, props, camera paths, lighting rigs,
and animation data, then writes a Python script that Blender can execute
headlessly to build and save the .blend file.
"""
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from blender.low_poly_generator import LowPolyGenerator, MeshData


class SceneBuilder:
    """Build a Blender scene assembly script from pipeline assets."""

    def __init__(self, output_dir: str = "/tmp/pipeline_artifacts/scene"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.generator = LowPolyGenerator()

    def build_scene_script(self, scene_plan: Dict[str, Any]) -> str:
        """
        Generate a Python script that Blender runs headlessly to build the scene.

        scene_plan contains:
          - characters: list of character specs
          - environment: environment spec
          - props: list of prop specs
          - camera: camera path spec
          - lighting: lighting rig spec
          - animation: animation keyframes
          - output_blend: path to save .blend file
        """
        lines = [
            '"""Auto-generated Blender scene assembly script."""',
            "import bpy",
            "import bmesh",
            "import math",
            "import os",
            "",
            "# Clear default scene",
            "bpy.ops.wm.read_factory_settings(use_empty=True)",
            "",
        ]

        # Environment
        env = scene_plan.get("environment", {})
        lines.extend(self._build_environment_script(env))

        # Characters
        for i, char in enumerate(scene_plan.get("characters", [])):
            lines.extend(self._build_character_script(char, i))

        # Props
        for i, prop in enumerate(scene_plan.get("props", [])):
            lines.extend(self._build_prop_script(prop, i))

        # Camera
        cam = scene_plan.get("camera", {})
        lines.extend(self._build_camera_script(cam))

        # Lighting
        light = scene_plan.get("lighting", {})
        lines.extend(self._build_lighting_script(light))

        # Animation keyframes
        anim = scene_plan.get("animation", {})
        lines.extend(self._build_animation_script(anim))

        # Render settings
        render = scene_plan.get("render", {})
        lines.extend(self._build_render_settings_script(render))

        # Save blend file
        output_blend = scene_plan.get("output_blend", str(self.output_dir / "scene.blend"))
        lines.extend([
            f"output_blend = {repr(output_blend)}",
            "os.makedirs(os.path.dirname(output_blend), exist_ok=True)",
            "bpy.ops.wm.save_as_mainfile(filepath=output_blend)",
            f"print('Scene saved to: {output_blend}')",
        ])

        script = "\n".join(lines)
        script_path = self.output_dir / "build_scene.py"
        with open(script_path, "w") as f:
            f.write(script)

        # Also save the scene plan
        plan_path = self.output_dir / "scene_plan.json"
        with open(plan_path, "w") as f:
            json.dump(scene_plan, f, indent=2)

        return str(script_path)

    def _build_environment_script(self, env: Dict) -> List[str]:
        env_type = env.get("type", "outdoor")
        return [
            "# --- Environment ---",
            "ground = bpy.data.meshes.new('Ground')",
            f"ground_obj = bpy.data.objects.new('Ground', ground)",
            "bpy.context.collection.objects.link(ground_obj)",
            f"print('Environment type: {env_type}')",
        ]

    def _build_character_script(self, char: Dict, index: int) -> List[str]:
        name = char.get("name", f"character_{index}")
        x, y, z = char.get("position", [0, 0, 0])
        return [
            f"# --- Character: {name} ---",
            f"bpy.ops.mesh.primitive_cube_add(location=({x}, {y}, {z}))",
            f"bpy.context.object.name = '{name}'",
            f"bpy.context.object.scale = (0.3, 0.3, 0.8)",
        ]

    def _build_prop_script(self, prop: Dict, index: int) -> List[str]:
        name = prop.get("name", f"prop_{index}")
        prop_type = prop.get("type", "box")
        x, y, z = prop.get("position", [0, 0, 0])
        ops = {
            "box": "primitive_cube_add",
            "cylinder": "primitive_cylinder_add",
            "sphere": "primitive_uv_sphere_add",
            "cone": "primitive_cone_add",
        }
        op = ops.get(prop_type, "primitive_cube_add")
        return [
            f"# --- Prop: {name} ({prop_type}) ---",
            f"bpy.ops.mesh.{op}(location=({x}, {y}, {z}))",
            f"bpy.context.object.name = '{name}'",
            f"bpy.context.object.scale = (0.2, 0.2, 0.2)",
        ]

    def _build_camera_script(self, cam: Dict) -> List[str]:
        cam_type = cam.get("type", "static")
        loc = cam.get("location", [5, -5, 3])
        target = cam.get("target", [0, 0, 1])
        return [
            "# --- Camera ---",
            "cam_data = bpy.data.cameras.new('Camera')",
            f"cam_obj = bpy.data.objects.new('Camera', cam_data)",
            "bpy.context.collection.objects.link(cam_obj)",
            f"cam_obj.location = {tuple(loc)}",
            "# Point camera at target",
            f"target_loc = {tuple(target)}",
            "import mathutils",
            "direction = mathutils.Vector(target_loc) - cam_obj.location",
            "rot_quat = direction.to_track_quat('-Z', 'Y')",
            "cam_obj.rotation_euler = rot_quat.to_euler()",
            "bpy.context.scene.camera = cam_obj",
            f"# Camera type: {cam_type}",
        ]

    def _build_lighting_script(self, light: Dict) -> List[str]:
        light_type = light.get("type", "sun")
        energy = light.get("energy", 3.0)
        loc = light.get("location", [5, 5, 10])
        return [
            "# --- Lighting ---",
            f"light_data = bpy.data.lights.new(name='KeyLight', type='{light_type.upper()}')",
            f"light_data.energy = {energy}",
            f"light_obj = bpy.data.objects.new('KeyLight', light_data)",
            "bpy.context.collection.objects.link(light_obj)",
            f"light_obj.location = {tuple(loc)}",
            "# Fill light",
            "fill_data = bpy.data.lights.new(name='FillLight', type='AREA')",
            "fill_data.energy = 1.5",
            "fill_data.size = 3.0",
            "fill_obj = bpy.data.objects.new('FillLight', fill_data)",
            "bpy.context.collection.objects.link(fill_obj)",
            "fill_obj.location = (-5, -3, 5)",
        ]

    def _build_animation_script(self, anim: Dict) -> List[str]:
        fps = anim.get("fps", 24)
        total_frames = anim.get("total_frames", 1440)  # ~60 seconds at 24fps
        return [
            "# --- Animation ---",
            f"bpy.context.scene.render.fps = {fps}",
            f"bpy.context.scene.frame_start = 1",
            f"bpy.context.scene.frame_end = {total_frames}",
            "# Keyframes would be inserted here based on animation data",
        ]

    def _build_render_settings_script(self, render: Dict) -> List[str]:
        engine = render.get("engine", "BLENDER_EEVEE")
        resolution = render.get("resolution", [1280, 720])
        samples = render.get("samples", 64)
        return [
            "# --- Render Settings ---",
            f"bpy.context.scene.render.engine = '{engine}'",
            f"bpy.context.scene.render.resolution_x = {resolution[0]}",
            f"bpy.context.scene.render.resolution_y = {resolution[1]}",
            f"bpy.context.scene.render.resolution_percentage = 100",
            f"bpy.context.scene.eevee.taa_render_samples = {samples}",
            "bpy.context.scene.render.image_settings.file_format = 'PNG'",
            "bpy.context.scene.render.image_settings.color_mode = 'RGBA'",
            "bpy.context.scene.render.image_settings.color_depth = '8'",
            "# Optimization: disable unnecessary features",
            "bpy.context.scene.eevee.use_ssr = False",
            "bpy.context.scene.eevee.use_ssr_refraction = False",
            "bpy.context.scene.eevee.use_gtao = True",
            "bpy.context.scene.eevee.gtao_distance = 0.2",
        ]

    def validate_scene_plan(self, plan: Dict) -> List[str]:
        """Validate a scene plan. Returns list of issues (empty = valid)."""
        issues = []
        if not plan.get("characters") and not plan.get("environment"):
            issues.append("Scene has no characters or environment")
        if not plan.get("camera"):
            issues.append("Scene has no camera")
        render = plan.get("render", {})
        if render.get("samples", 0) > 512:
            issues.append(f"High sample count ({render['samples']}) may be slow on CPU")
        return issues
