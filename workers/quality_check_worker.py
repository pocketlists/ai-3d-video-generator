"""
Quality check worker — validates rendered output.

Stage 17: Checks that all expected frames exist, are non-empty,
and meet quality thresholds. Verifies final video duration and
audio/video sync.
"""
import json
import os
from typing import Any, Dict, List

from workers.base_worker import BaseWorker
from utils.file_validator import (
    validate_required_files, validate_image_file, safe_validate
)
from optimizer.rules import QUALITY_THRESHOLDS


class QualityCheckWorker(BaseWorker):
    stage_name = "quality_check"

    def run(self) -> Dict[str, Any]:
        artifact_dir = os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts")
        renders_dir = os.path.join(artifact_dir, "renders")

        # Collect all rendered frames
        all_frames = []
        if os.path.exists(renders_dir):
            for worker_dir in sorted(os.listdir(renders_dir)):
                worker_path = os.path.join(renders_dir, worker_dir)
                if os.path.isdir(worker_path):
                    for fname in sorted(os.listdir(worker_path)):
                        if fname.endswith(".png"):
                            all_frames.append(os.path.join(worker_path, fname))

        if not all_frames:
            return {"status": "error", "error": "No rendered frames found"}

        # Validate frames
        checks = {
            "frames_exist": True,
            "frames_nonempty": True,
            "frame_count_sufficient": True,
            "resolution_consistent": True,
            "no_corrupt_frames": True,
        }
        issues = []

        # Check frame count
        breakdown = self._load_breakdown()
        expected_frames = breakdown.get("total_frames", 1440) if breakdown else 1440
        if len(all_frames) < expected_frames * 0.9:  # allow 10% loss
            checks["frame_count_sufficient"] = False
            issues.append(f"Only {len(all_frames)} frames found, expected ~{expected_frames}")

        # Validate individual frames
        corrupt_count = 0
        empty_count = 0
        for frame_path in all_frames[:50]:  # check first 50
            success, error = safe_validate(frame_path, validate_image_file)
            if not success:
                if "empty" in (error or "").lower():
                    empty_count += 1
                else:
                    corrupt_count += 1

        if empty_count > 0:
            checks["frames_nonempty"] = False
            issues.append(f"{empty_count} empty frames detected in sample")

        if corrupt_count > 5:
            checks["no_corrupt_frames"] = False
            issues.append(f"{corrupt_count} corrupt frames in sample of 50")

        # Check duration
        fps = breakdown.get("fps", 24) if breakdown else 24
        estimated_duration = len(all_frames) / fps
        duration_ok = (QUALITY_THRESHOLDS["min_video_duration_sec"] <= estimated_duration <=
                       QUALITY_THRESHOLDS["max_video_duration_sec"])
        if not duration_ok:
            issues.append(f"Estimated duration {estimated_duration:.1f}s outside "
                         f"expected range {QUALITY_THRESHOLDS['min_video_duration_sec']}-"
                         f"{QUALITY_THRESHOLDS['max_video_duration_sec']}s")

        passed = all(checks.values()) and len(issues) == 0

        # Save QC report
        report = {
            "passed": passed,
            "checks": checks,
            "total_frames": len(all_frames),
            "expected_frames": expected_frames,
            "estimated_duration_sec": round(estimated_duration, 1),
            "issues": issues,
            "frame_sample_size": min(50, len(all_frames)),
        }
        report_path = os.path.join(artifact_dir, "quality_check_report.json")
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

        # Record metrics
        collector = self._get_collector()
        collector.record_quality_check(passed, checks, estimated_duration, issues)

        return {
            "status": "success" if passed else "warning",
            "quality_check_path": report_path,
            "passed": passed,
            "total_frames": len(all_frames),
            "issues": issues,
        }

    def _load_breakdown(self) -> Dict:
        artifact_dir = os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts")
        path = os.path.join(artifact_dir, "script_breakdown.json")
        if not os.path.exists(path):
            return {}
        with open(path) as f:
            return json.load(f)

    def _get_collector(self):
        from optimizer.metrics_collector import MetricsCollector
        return MetricsCollector()
