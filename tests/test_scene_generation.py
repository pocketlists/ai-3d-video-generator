"""Tests for low-poly mesh and scene generation."""
import pytest

from blender.low_poly_generator import LowPolyGenerator, MeshData
from blender.scene_builder import SceneBuilder


def test_low_poly_generator_init():
    gen = LowPolyGenerator(seed=42)
    assert gen.rng is not None


def test_generate_character():
    gen = LowPolyGenerator(seed=42)
    mesh = gen.generate_character("hero")
    assert mesh.name == "hero"
    assert mesh.vertex_count() > 0
    assert mesh.face_count() > 0


def test_generate_environment():
    gen = LowPolyGenerator(seed=123)
    mesh = gen.generate_environment("outdoor")
    assert mesh.name == "env_outdoor"
    assert mesh.vertex_count() > 0
    assert mesh.face_count() > 0


def test_generate_prop_box():
    gen = LowPolyGenerator(seed=789)
    mesh = gen.generate_prop("box")
    assert mesh.name == "prop_box"
    assert mesh.vertex_count() == 8
    assert mesh.face_count() == 6


def test_generate_prop_cylinder():
    gen = LowPolyGenerator(seed=789)
    mesh = gen.generate_prop("cylinder")
    assert mesh.vertex_count() > 0
    assert mesh.face_count() > 0


def test_generate_prop_sphere():
    gen = LowPolyGenerator(seed=789)
    mesh = gen.generate_prop("sphere")
    assert mesh.vertex_count() > 0
    assert mesh.face_count() > 0


def test_mesh_to_dict():
    mesh = MeshData(vertices=[(0, 0, 0), (1, 0, 0)], faces=[[0, 1]], name="test")
    d = mesh.to_dict()
    assert d["name"] == "test"
    assert len(d["vertices"]) == 2
    assert len(d["faces"]) == 1


def test_optimize_mesh():
    gen = LowPolyGenerator(seed=42)
    mesh = gen.generate_character("hero")
    original_faces = mesh.face_count()
    optimized = gen.optimize(mesh, target_faces=10)
    assert optimized.face_count() <= 10 or original_faces <= 10


def test_scene_builder_init():
    builder = SceneBuilder()
    assert builder.output_dir.exists()


def test_scene_builder_build_script(tmp_path):
    builder = SceneBuilder(output_dir=str(tmp_path))
    plan = {
        "characters": [{"name": "hero", "position": [0, 0, 0]}],
        "environment": {"type": "outdoor"},
        "props": [{"name": "crate", "type": "box", "position": [1, 1, 0]}],
        "camera": {"type": "static", "location": [5, -5, 3], "target": [0, 0, 1]},
        "lighting": {"type": "sun", "energy": 3.0, "location": [5, 5, 10]},
        "animation": {"fps": 24, "total_frames": 1440},
        "render": {"engine": "BLENDER_EEVEE", "resolution": [1280, 720], "samples": 64},
        "output_blend": str(tmp_path / "scene.blend"),
    }
    script_path = builder.build_scene_script(plan)
    assert script_path is not None
    with open(script_path) as f:
        content = f.read()
    assert "bpy" in content
    assert "hero" in content
    assert "save_as_mainfile" in content


def test_scene_builder_validate():
    builder = SceneBuilder()
    issues = builder.validate_scene_plan({
        "characters": [],
        "environment": {},
        "camera": {},
        "render": {"samples": 1024},
    })
    # Should have issues: no chars/env, no camera, high samples
    assert len(issues) >= 1


def test_scene_builder_valid_plan():
    builder = SceneBuilder()
    issues = builder.validate_scene_plan({
        "characters": [{"name": "hero"}],
        "environment": {"type": "outdoor"},
        "camera": {"type": "static"},
        "render": {"samples": 64},
    })
    assert len(issues) == 0
