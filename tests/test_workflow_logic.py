"""Tests for pipeline workflow and dependency logic."""
import pytest

from controller.pipeline import Pipeline, PipelineStage, PIPELINE_STAGES


def test_pipeline_has_20_stages():
    """Pipeline should have exactly 20 stages."""
    assert len(PIPELINE_STAGES) == 20


def test_pipeline_stage_names_unique():
    """All stage names should be unique."""
    names = [s.name for s in PIPELINE_STAGES]
    assert len(names) == len(set(names))


def test_pipeline_get_stage():
    p = Pipeline()
    stage = p.get_stage("ai_planning")
    assert stage is not None
    assert stage.name == "ai_planning"


def test_pipeline_get_stage_missing():
    p = Pipeline()
    assert p.get_stage("nonexistent") is None


def test_pipeline_validate_dependencies():
    """All dependencies should reference existing stages."""
    p = Pipeline()
    assert p.validate_dependencies()


def test_pipeline_execution_order():
    """Execution order should be valid topological sort."""
    p = Pipeline()
    layers = p.get_execution_order()
    assert len(layers) > 0
    # First layer should be receive_request
    assert "receive_request" in layers[0]
    # Last layer should include self_optimize
    assert "self_optimize" in layers[-1]


def test_parallel_stages():
    """Some stages should be parallelizable."""
    p = Pipeline()
    parallel = p.get_parallel_stages()
    assert len(parallel) > 0
    names = [s.name for s in parallel]
    assert "characters" in names
    assert "environments" in names
    assert "voice_tts" in names


def test_dependency_chain():
    """blender_assembly depends on animation, camera, lighting."""
    p = Pipeline()
    stage = p.get_stage("blender_assembly")
    assert "animation" in stage.depends_on
    assert "camera" in stage.depends_on
    assert "lighting" in stage.depends_on


def test_render_workers_depends_on_assembly():
    """render_workers depends on blender_assembly."""
    p = Pipeline()
    stage = p.get_stage("render_workers")
    assert "blender_assembly" in stage.depends_on


def test_ffmpeg_depends_on_quality_and_audio():
    """ffmpeg_assembly depends on quality_check and audio stages."""
    p = Pipeline()
    stage = p.get_stage("ffmpeg_assembly")
    assert "quality_check" in stage.depends_on
    assert "voice_tts" in stage.depends_on
    assert "music" in stage.depends_on
    assert "sfx" in stage.depends_on


def test_telegram_delivery_last():
    """telegram_delivery should be near the end."""
    p = Pipeline()
    layers = p.get_execution_order()
    tg_layer = None
    for i, layer in enumerate(layers):
        if "telegram_delivery" in layer:
            tg_layer = i
    assert tg_layer is not None
    assert tg_layer >= len(layers) - 3  # near the end


def test_no_circular_dependencies():
    """Pipeline should not have circular dependencies."""
    p = Pipeline()
    # Should not raise
    layers = p.get_execution_order()
    all_stages = set()
    for layer in layers:
        all_stages.update(layer)
    assert len(all_stages) == 20


def test_total_stages():
    p = Pipeline()
    assert p.total_stages() == 20


def test_stages_after():
    """get_stages_after should find dependents."""
    p = Pipeline()
    dependents = p.get_stages_after("receive_request")
    dependent_names = [s.name for s in dependents]
    assert "ai_planning" in dependent_names
