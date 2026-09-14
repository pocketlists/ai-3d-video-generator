"""Tests for render manager and task distribution."""
import pytest

from blender.render_manager import RenderManager, RenderTask, RenderResult


def test_render_task_creation():
    task = RenderTask(
        worker_id=0,
        blend_file="scene.blend",
        output_dir="/tmp/renders/worker_0",
        frame_start=1,
        frame_end=360,
    )
    assert task.worker_id == 0
    assert task.frame_count() == 360


def test_render_manager_create_tasks(tmp_path):
    manager = RenderManager(
        blend_file="scene.blend",
        output_dir=str(tmp_path / "renders"),
        total_frames=1440,
        num_workers=4,
    )
    tasks = manager.create_tasks(frame_start=1, frame_end=1440)
    assert len(tasks) == 4
    # Check frame coverage
    total_frames = sum(t.frame_count() for t in tasks)
    assert total_frames == 1440
    # Check no overlap
    for i in range(len(tasks) - 1):
        assert tasks[i].frame_end < tasks[i + 1].frame_start


def test_render_manager_task_distribution(tmp_path):
    manager = RenderManager(
        blend_file="scene.blend",
        output_dir=str(tmp_path / "renders"),
        total_frames=100,
        num_workers=3,
    )
    tasks = manager.create_tasks(frame_start=1, frame_end=100)
    assert len(tasks) == 3
    # First worker gets 34, others get 33
    assert tasks[0].frame_count() >= 33
    assert tasks[2].frame_count() >= 32


def test_render_result_success():
    result = RenderResult(
        worker_id=0, success=True,
        frames_rendered=360, elapsed_sec=120.0,
        output_files=["frame_0001.png"],
    )
    assert result.success
    assert result.frames_rendered == 360


def test_render_result_failure():
    result = RenderResult(
        worker_id=1, success=False,
        frames_rendered=0, elapsed_sec=10.0,
        error="Blender not found",
    )
    assert not result.success
    assert result.error == "Blender not found"


def test_render_manager_collect_frames(tmp_path):
    manager = RenderManager(
        blend_file="scene.blend",
        output_dir=str(tmp_path / "renders"),
        total_frames=10,
        num_workers=2,
    )
    results = [
        RenderResult(0, True, 5, 10.0, ["frame_0001.png", "frame_0002.png"]),
        RenderResult(1, True, 5, 12.0, ["frame_0003.png", "frame_0004.png"]),
    ]
    frames = manager.collect_all_frames(results)
    assert len(frames) == 4


def test_render_manager_summary(tmp_path):
    manager = RenderManager(
        blend_file="scene.blend",
        output_dir=str(tmp_path / "renders"),
        total_frames=10,
        num_workers=2,
    )
    results = [
        RenderResult(0, True, 5, 10.0, ["f1.png"]),
        RenderResult(1, False, 0, 5.0, error="timeout"),
    ]
    summary = manager.get_render_summary(results)
    assert summary["total_workers"] == 2
    assert summary["successful_workers"] == 1
    assert summary["failed_workers"] == 1
    assert summary["total_frames_rendered"] == 5
    assert 1 in summary["failed_worker_ids"]


def test_render_task_to_dict():
    task = RenderTask(
        worker_id=0,
        blend_file="scene.blend",
        output_dir="/tmp/renders/w0",
        frame_start=1,
        frame_end=360,
        resolution=(1280, 720),
        samples=64,
    )
    d = task.to_dict()
    assert d["worker_id"] == 0
    assert d["frame_start"] == 1
    assert d["frame_end"] == 360
    assert d["resolution"] == [1280, 720]


def test_render_manager_save_manifest(tmp_path):
    manager = RenderManager(
        blend_file="scene.blend",
        output_dir=str(tmp_path / "renders"),
        total_frames=100,
        num_workers=2,
    )
    tasks = manager.create_tasks(frame_start=1, frame_end=100)
    path = manager.save_task_manifest(tasks)
    assert path is not None
    import json
    with open(path) as f:
        manifest = json.load(f)
    assert manifest["num_workers"] == 2
    assert len(manifest["tasks"]) == 2
