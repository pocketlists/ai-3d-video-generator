"""
Telemetry collector — gathers system metrics during pipeline execution.

Collects CPU, RAM, disk usage, timing, and Blender render statistics
for the self-optimization system to analyze.
"""
import json
import os
import psutil
import socket
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class TelemetryCollector:
    """Collects and stores system telemetry metrics."""

    def __init__(self, run_id: Optional[str] = None, output_dir: Optional[str] = None):
        self.run_id = run_id or os.environ.get("GITHUB_RUN_ID", "local")
        self.output_dir = Path(output_dir or os.environ.get("METRICS_DIR", "/tmp/pipeline_metrics"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.metrics: List[Dict[str, Any]] = []
        self._start_time = time.time()

    def collect_system_metrics(self) -> Dict[str, Any]:
        """Collect current system resource usage."""
        cpu_percent = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        return {
            "timestamp": time.time(),
            "cpu_percent": cpu_percent,
            "cpu_count": psutil.cpu_count(),
            "ram_total_mb": round(ram.total / 1024 / 1024, 1),
            "ram_used_mb": round(ram.used / 1024 / 1024, 1),
            "ram_percent": ram.percent,
            "disk_total_gb": round(disk.total / 1024 / 1024 / 1024, 1),
            "disk_used_gb": round(disk.used / 1024 / 1024 / 1024, 1),
            "disk_percent": disk.percent,
            "hostname": socket.gethostname(),
        }

    def record_render_metrics(self, stage: str, frame: int, render_time: float,
                               samples: int, resolution: str, engine: str,
                               file_size: int = 0) -> None:
        """Record per-frame render metrics."""
        entry = {
            "type": "render",
            "stage": stage,
            "frame": frame,
            "render_time_sec": round(render_time, 2),
            "samples": samples,
            "resolution": resolution,
            "engine": engine,
            "file_size_bytes": file_size,
            "timestamp": time.time(),
        }
        self.metrics.append(entry)

    def record_stage_metrics(self, stage: str, elapsed: float, success: bool,
                              metadata: Optional[Dict] = None) -> None:
        """Record overall stage execution metrics."""
        entry = {
            "type": "stage",
            "stage": stage,
            "elapsed_sec": round(elapsed, 2),
            "success": success,
            "metadata": metadata or {},
            "timestamp": time.time(),
        }
        self.metrics.append(entry)

    def record_ffmpeg_metrics(self, input_count: int, output_duration: float,
                               processing_time: float, output_size: int,
                               codec: str = "libx264") -> None:
        """Record FFmpeg assembly metrics."""
        entry = {
            "type": "ffmpeg",
            "input_count": input_count,
            "output_duration_sec": round(output_duration, 2),
            "processing_time_sec": round(processing_time, 2),
            "output_size_bytes": output_size,
            "codec": codec,
            "timestamp": time.time(),
        }
        self.metrics.append(entry)

    def save(self) -> str:
        """Save all collected metrics to a JSON file. Returns the file path."""
        output = {
            "run_id": self.run_id,
            "total_elapsed": round(time.time() - self._start_time, 2),
            "metrics_count": len(self.metrics),
            "final_system_snapshot": self.collect_system_metrics(),
            "metrics": self.metrics,
        }
        path = self.output_dir / f"metrics_{self.run_id}.json"
        with open(path, "w") as f:
            json.dump(output, f, indent=2)
        return str(path)

    def get_summary(self) -> Dict[str, Any]:
        """Return a summary of collected metrics."""
        render_metrics = [m for m in self.metrics if m.get("type") == "render"]
        stage_metrics = [m for m in self.metrics if m.get("type") == "stage"]
        total_render_time = sum(m.get("render_time_sec", 0) for m in render_metrics)
        total_stage_time = sum(m.get("elapsed_sec", 0) for m in stage_metrics)
        failures = [m for m in stage_metrics if not m.get("success")]

        return {
            "total_metrics": len(self.metrics),
            "total_render_time_sec": round(total_render_time, 2),
            "total_stage_time_sec": round(total_stage_time, 2),
            "render_frame_count": len(render_metrics),
            "stage_count": len(stage_metrics),
            "failure_count": len(failures),
            "failed_stages": [m["stage"] for m in failures],
        }
