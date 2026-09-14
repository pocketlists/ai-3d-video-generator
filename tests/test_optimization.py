"""Tests for optimization system, metrics, and rules."""
import json
import os
import tempfile
import pytest

from optimizer.metrics_collector import MetricsCollector
from optimizer.analyzer import OptimizationAnalyzer
from optimizer.rules import OptimizationRule, SAFE_RULES, QUALITY_THRESHOLDS, validate_quality_thresholds
from blender.optimization import BlenderOptimizer, SceneComplexity


def test_metrics_collector_init():
    with tempfile.TemporaryDirectory() as tmpdir:
        collector = MetricsCollector(storage_dir=tmpdir)
        assert collector.run_id is not None
        assert "stages" in collector.metrics


def test_metrics_record_stage():
    with tempfile.TemporaryDirectory() as tmpdir:
        collector = MetricsCollector(storage_dir=tmpdir)
        collector.record_stage("render", 120.0, True, {"frames": 360})
        assert "render" in collector.metrics["stages"]
        assert collector.metrics["stages"]["render"]["elapsed_sec"] == 120.0


def test_metrics_record_render():
    with tempfile.TemporaryDirectory() as tmpdir:
        collector = MetricsCollector(storage_dir=tmpdir)
        collector.record_render(0, 1, 360, 120.0, 64, "1280x720", "BLENDER_EEVEE", 360, True)
        assert "worker_0" in collector.metrics["render"]
        assert collector.metrics["render"]["worker_0"]["per_frame_sec"] > 0


def test_metrics_save_and_load():
    with tempfile.TemporaryDirectory() as tmpdir:
        collector = MetricsCollector(storage_dir=tmpdir, run_id="test_run")
        collector.record_stage("planning", 5.0, True)
        path = collector.save()
        assert os.path.exists(path)

        # Load previous runs
        runs = collector.load_previous_runs()
        assert len(runs) == 1
        assert "planning" in runs[0]["stages"]


def test_analyzer_no_history():
    with tempfile.TemporaryDirectory() as tmpdir:
        collector = MetricsCollector(storage_dir=tmpdir)
        analyzer = OptimizationAnalyzer(collector=collector)
        result = analyzer.analyze()
        assert result["summary"]["total_runs_analyzed"] == 0
        assert "No historical data" in result["warnings"][0]


def test_analyzer_with_history():
    with tempfile.TemporaryDirectory() as tmpdir:
        collector = MetricsCollector(storage_dir=tmpdir, run_id="run1")
        collector.record_stage("render_workers", 300.0, True)
        collector.record_render(0, 1, 360, 300.0, 64, "1280x720", "BLENDER_EEVEE", 360, True)
        collector.record_blender_settings(64, [1280, 720], "BLENDER_EEVEE", 24, 0, [1024], 45.0, "medium")
        collector.save()

        analyzer = OptimizationAnalyzer(collector=collector)
        result = analyzer.analyze(runs=collector.load_previous_runs())
        assert result["summary"]["total_runs_analyzed"] == 1
        assert len(result.get("bottlenecks", [])) > 0


def test_quality_thresholds():
    violations = validate_quality_thresholds({"samples": 16, "resolution": [640, 360], "fps": 24})
    assert len(violations) >= 2  # samples and resolution too low


def test_quality_thresholds_ok():
    violations = validate_quality_thresholds({"samples": 64, "resolution": [1280, 720], "fps": 24})
    assert len(violations) == 0


def test_safe_rules_exist():
    assert len(SAFE_RULES) >= 5


def test_optimization_rule_check():
    rule = SAFE_RULES[0]
    issues = [{"type": rule.issue_types[0], "description": "test"}]
    matches = rule.check(issues)
    assert len(matches) == 1


def test_scene_complexity_low():
    c = SceneComplexity(object_count=5, total_vertices=500, total_faces=300, light_count=2)
    assert c.complexity_label == "low"
    assert c.complexity_score < 25


def test_scene_complexity_high():
    c = SceneComplexity(object_count=40, total_vertices=30000, total_faces=15000, light_count=5)
    assert c.complexity_label in ("high", "very_high")


def test_blender_optimizer_init():
    optimizer = BlenderOptimizer()
    assert optimizer.MIN_SAMPLES == 32


def test_blender_optimizer_low_complexity():
    optimizer = BlenderOptimizer()
    c = SceneComplexity(object_count=5, total_vertices=500, total_faces=300)
    settings = optimizer.optimize_settings(c)
    assert settings["samples"] >= 32
    assert settings["samples"] <= 64


def test_blender_optimizer_never_below_min():
    optimizer = BlenderOptimizer()
    c = SceneComplexity(object_count=50, total_vertices=50000, total_faces=25000)
    settings = optimizer.optimize_settings(c, requested_samples=16)
    assert settings["samples"] >= optimizer.MIN_SAMPLES


def test_blender_optimizer_estimate_time():
    optimizer = BlenderOptimizer()
    c = SceneComplexity(object_count=10, total_vertices=2000, total_faces=1000)
    settings = optimizer.optimize_settings(c)
    est = optimizer.estimate_render_time(c, settings, 1440)
    assert est > 0


def test_blender_optimizer_report():
    optimizer = BlenderOptimizer()
    c = SceneComplexity(object_count=10, total_vertices=2000, total_faces=1000)
    settings = optimizer.optimize_settings(c)
    report = optimizer.get_optimization_report(settings)
    assert "Optimization Report" in report
    assert "Samples" in report
