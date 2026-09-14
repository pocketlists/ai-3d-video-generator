"""
Optimization worker — collects metrics and optimizes for future runs.

Stage 20: The final stage collects all run metrics, analyzes them,
generates optimization recommendations, and saves them for future
pipeline executions to learn from.
"""
import json
import os
import time
from typing import Any, Dict

from workers.base_worker import BaseWorker
from optimizer.metrics_collector import MetricsCollector
from optimizer.analyzer import OptimizationAnalyzer
from optimizer.rules import validate_quality_thresholds


class OptimizationWorker(BaseWorker):
    stage_name = "self_optimize"

    def run(self) -> Dict[str, Any]:
        artifact_dir = os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts")
        metrics_dir = os.environ.get("METRICS_DIR", "/tmp/pipeline_metrics")

        # Collect final system metrics
        collector = MetricsCollector(storage_dir=metrics_dir)
        try:
            import psutil
            collector.record_system(
                cpu_percent=psutil.cpu_percent(interval=0.5),
                ram_used_mb=psutil.virtual_memory().used / 1024 / 1024,
                ram_total_mb=psutil.virtual_memory().total / 1024 / 1024,
                disk_used_gb=psutil.disk_usage("/").used / 1024 / 1024 / 1024,
                disk_total_gb=psutil.disk_usage("/").total / 1024 / 1024 / 1024,
            )
        except ImportError:
            collector.record_system(0, 0, 0, 0, 0)

        # Load and record Blender settings from scene plan
        scene_plan_path = os.path.join(artifact_dir, "scene", "scene_plan.json")
        if os.path.exists(scene_plan_path):
            with open(scene_plan_path) as f:
                scene_plan = json.load(f)
            render_settings = scene_plan.get("render", {})
            collector.record_blender_settings(
                samples=render_settings.get("samples", 64),
                resolution=render_settings.get("resolution", [1280, 720]),
                engine=render_settings.get("engine", "BLENDER_EEVEE"),
                fps=scene_plan.get("animation", {}).get("fps", 24),
                modifiers=0,
                texture_sizes=[1024],
                complexity_score=render_settings.get("complexity_score", 0),
                complexity_label=render_settings.get("complexity_label", "unknown"),
            )

        # Record FFmpeg metrics
        # (loaded from the ffmpeg worker's saved metrics)
        ffmpeg_metrics_path = os.path.join(metrics_dir, "metrics_local.json")
        if os.path.exists(ffmpeg_metrics_path):
            with open(ffmpeg_metrics_path) as f:
                ffmpeg_data = json.load(f)
            ffmpeg = ffmpeg_data.get("metrics", {}).get("ffmpeg", {})
            if ffmpeg:
                collector.record_ffmpeg(
                    input_count=ffmpeg.get("input_count", 0),
                    output_duration=ffmpeg.get("output_duration_sec", 0),
                    processing_time=ffmpeg.get("processing_time_sec", 0),
                    output_size=ffmpeg.get("output_size_bytes", 0),
                    codec=ffmpeg.get("codec", "libx264"),
                    input_formats=ffmpeg.get("input_formats", []),
                )

        # Save metrics
        metrics_path = collector.save()

        # Analyze
        analyzer = OptimizationAnalyzer(collector=collector)
        analysis = analyzer.analyze()
        report = analyzer.generate_report(analysis)

        # Save analysis
        analysis_path = os.path.join(metrics_dir, "optimization_analysis.json")
        with open(analysis_path, "w") as f:
            json.dump(analysis, f, indent=2)

        # Save report
        report_path = os.path.join(metrics_dir, "optimization_report.txt")
        with open(report_path, "w") as f:
            f.write(report)

        # Validate quality thresholds
        blender = collector.metrics.get("blender", {})
        violations = validate_quality_thresholds({
            "samples": blender.get("samples", 64),
            "resolution": blender.get("resolution", [1280, 720]),
            "fps": blender.get("fps", 24),
        })

        self.logger.info(report)

        return {
            "status": "success",
            "metrics_path": metrics_path,
            "analysis_path": analysis_path,
            "report_path": report_path,
            "recommendations_count": len(analysis.get("recommendations", [])),
            "bottlenecks_count": len(analysis.get("bottlenecks", [])),
            "quality_violations": violations,
            "summary": analysis.get("summary", {}),
        }
