"""
Metrics collector — gathers metrics from all pipeline stages.

Collects render times, system utilization, Blender settings, asset
processing times, FFmpeg metrics, failures, and quality-check results.
"""
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class MetricsCollector:
    """Collect and persist pipeline run metrics for optimization."""

    def __init__(self, run_id: Optional[str] = None, storage_dir: Optional[str] = None):
        self.run_id = run_id or os.environ.get("GITHUB_RUN_ID", f"run_{int(time.time())}")
        self.storage_dir = Path(storage_dir or os.environ.get("METRICS_DIR", "/tmp/pipeline_metrics"))
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.metrics: Dict[str, Any] = {
            "run_id": self.run_id,
            "timestamp": time.time(),
            "stages": {},
            "render": {},
            "system": {},
            "blender": {},
            "ffmpeg": {},
            "errors": [],
            "quality_check": {},
            "optimizations_applied": [],
        }

    def record_stage(self, name: str, elapsed: float, success: bool,
                     metadata: Optional[Dict] = None) -> None:
        self.metrics["stages"][name] = {
            "elapsed_sec": round(elapsed, 2),
            "success": success,
            "metadata": metadata or {},
        }

    def record_render(self, worker_id: int, frame_start: int, frame_end: int,
                      elapsed: float, samples: int, resolution: str,
                      engine: str, frame_count: int, success: bool,
                      error: Optional[str] = None) -> None:
        key = f"worker_{worker_id}"
        self.metrics["render"][key] = {
            "frame_start": frame_start,
            "frame_end": frame_end,
            "frame_count": frame_count,
            "elapsed_sec": round(elapsed, 2),
            "per_frame_sec": round(elapsed / max(frame_count, 1), 3),
            "samples": samples,
            "resolution": resolution,
            "engine": engine,
            "success": success,
            "error": error,
        }

    def record_system(self, cpu_percent: float, ram_used_mb: float,
                      ram_total_mb: float, disk_used_gb: float,
                      disk_total_gb: float) -> None:
        self.metrics["system"] = {
            "cpu_percent": cpu_percent,
            "ram_used_mb": round(ram_used_mb, 1),
            "ram_total_mb": round(ram_total_mb, 1),
            "ram_percent": round(ram_used_mb / ram_total_mb * 100, 1) if ram_total_mb else 0,
            "disk_used_gb": round(disk_used_gb, 1),
            "disk_total_gb": round(disk_total_gb, 1),
            "disk_percent": round(disk_used_gb / disk_total_gb * 100, 1) if disk_total_gb else 0,
        }

    def record_blender_settings(self, samples: int, resolution: list, engine: str,
                                 fps: int, modifiers: int, texture_sizes: list,
                                 complexity_score: float, complexity_label: str) -> None:
        self.metrics["blender"] = {
            "samples": samples,
            "resolution": resolution,
            "engine": engine,
            "fps": fps,
            "modifier_count": modifiers,
            "texture_sizes": texture_sizes,
            "complexity_score": complexity_score,
            "complexity_label": complexity_label,
        }

    def record_ffmpeg(self, input_count: int, output_duration: float,
                      processing_time: float, output_size: int,
                      codec: str, input_formats: list) -> None:
        self.metrics["ffmpeg"] = {
            "input_count": input_count,
            "output_duration_sec": round(output_duration, 2),
            "processing_time_sec": round(processing_time, 2),
            "output_size_bytes": output_size,
            "codec": codec,
            "input_formats": input_formats,
        }

    def record_error(self, stage: str, error: str, recoverable: bool = True,
                     retried: bool = False, resolved: bool = False) -> None:
        self.metrics["errors"].append({
            "stage": stage,
            "error": error,
            "recoverable": recoverable,
            "retried": retried,
            "resolved": resolved,
            "timestamp": time.time(),
        })

    def record_quality_check(self, passed: bool, checks: Dict[str, bool],
                              duration_sec: float, issues: List[str]) -> None:
        self.metrics["quality_check"] = {
            "passed": passed,
            "checks": checks,
            "video_duration_sec": round(duration_sec, 2),
            "issues": issues,
        }

    def record_optimization(self, name: str, description: str,
                            before: Any, after: Any, safe: bool = True) -> None:
        self.metrics["optimizations_applied"].append({
            "name": name,
            "description": description,
            "before": before,
            "after": after,
            "safe": safe,
            "timestamp": time.time(),
        })

    def save(self) -> str:
        """Save metrics to a JSON file. Returns the path."""
        self.metrics["completed_at"] = time.time()
        path = self.storage_dir / f"run_{self.run_id}.json"
        with open(path, "w") as f:
            json.dump(self.metrics, f, indent=2)
        return str(path)

    def to_dict(self) -> Dict[str, Any]:
        return self.metrics.copy()

    def load_previous_runs(self, limit: int = 20) -> List[Dict]:
        """Load metrics from previous runs for analysis."""
        runs = []
        files = sorted(self.storage_dir.glob("run_*.json"), reverse=True)
        for f in files[:limit]:
            try:
                with open(f) as fh:
                    runs.append(json.load(fh))
            except (json.JSONDecodeError, IOError):
                continue
        return runs
