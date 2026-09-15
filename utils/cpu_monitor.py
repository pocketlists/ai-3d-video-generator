"""
CPU/RAM monitor — real-time system resource monitoring for render workers.

Every render worker logs:
- CPU cores available
- CPU model
- RAM available/used
- CPU utilization (measured, not faked)
- Render engine
- Blender version
- Resolution
- Frame number / total
- Frame time / average frame time
- ETA
- Scene complexity metrics

Example output:
  CPU cores: 4
  CPU utilization: 96%
  RAM: 5.2 / 15.0 GB
  Frame: 37/120
  Frame time: 1.82 sec
  Average: 1.94 sec/frame
  ETA: 2m 45s
"""
import os
import platform
import socket
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from utils.logger import PipelineLogger


@dataclass
class RenderMetrics:
    """Metrics for a single render frame."""
    worker_id: int
    frame_number: int
    total_frames: int
    frame_time_sec: float
    cpu_percent: float
    ram_used_mb: float
    ram_total_mb: float
    cpu_cores: int
    cpu_model: str
    render_engine: str
    blender_version: str
    resolution: str
    timestamp: float = 0.0
    avg_frame_time: float = 0.0
    eta_sec: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "frame_number": self.frame_number,
            "total_frames": self.total_frames,
            "frame_time_sec": round(self.frame_time_sec, 2),
            "cpu_percent": round(self.cpu_percent, 1),
            "ram_used_mb": round(self.ram_used_mb, 1),
            "ram_total_mb": round(self.ram_total_mb, 1),
            "cpu_cores": self.cpu_cores,
            "cpu_model": self.cpu_model,
            "render_engine": self.render_engine,
            "blender_version": self.blender_version,
            "resolution": self.resolution,
            "avg_frame_time": round(self.avg_frame_time, 2),
            "eta_sec": round(self.eta_sec, 1),
            "timestamp": self.timestamp,
        }

    def format_report(self) -> str:
        """Human-readable metrics report."""
        eta_min = int(self.eta_sec // 60)
        eta_s = int(self.eta_sec % 60)
        return (
            f"CPU cores: {self.cpu_cores}\n"
            f"CPU: {self.cpu_model}\n"
            f"CPU utilization: {self.cpu_percent:.0f}%\n"
            f"RAM: {self.ram_used_mb:.1f} / {self.ram_total_mb:.1f} GB\n"
            f"Frame: {self.frame_number}/{self.total_frames}\n"
            f"Frame time: {self.frame_time_sec:.2f} sec\n"
            f"Average: {self.avg_frame_time:.2f} sec/frame\n"
            f"ETA: {eta_min}m {eta_s}s\n"
            f"Engine: {self.render_engine}\n"
            f"Resolution: {self.resolution}\n"
            f"Blender: {self.blender_version}"
        )


class CPUMonitor:
    """Monitor CPU/RAM usage during rendering."""

    def __init__(self, worker_id: int = 0):
        self.worker_id = worker_id
        self.logger = PipelineLogger(f"cpu_monitor_w{worker_id}")
        self._frame_times: List[float] = []
        self._start_time = time.time()

        # Cache system info
        self._cpu_cores = self._get_cpu_cores()
        self._cpu_model = self._get_cpu_model()
        self._ram_total = self._get_ram_total()
        self._blender_version = self._get_blender_version()

    def _get_cpu_cores(self) -> int:
        try:
            import psutil
            return psutil.cpu_count(logical=True) or 1
        except ImportError:
            return os.cpu_count() or 1

    def _get_cpu_model(self) -> str:
        try:
            return platform.processor() or "unknown"
        except Exception:
            return "unknown"

    def _get_ram_total(self) -> float:
        try:
            import psutil
            return psutil.virtual_memory().total / 1024 / 1024 / 1024
        except ImportError:
            return 0.0

    def _get_blender_version(self) -> str:
        import subprocess
        try:
            result = subprocess.run(
                ["blender", "--version"], capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return result.stdout.strip().split("\n")[0]
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return "not_installed"

    def measure_cpu_percent(self) -> float:
        """Measure real CPU utilization (NOT faked)."""
        try:
            import psutil
            return psutil.cpu_percent(interval=0.5)
        except ImportError:
            return 0.0

    def measure_ram_used(self) -> float:
        """Measure real RAM usage in GB."""
        try:
            import psutil
            return psutil.virtual_memory().used / 1024 / 1024 / 1024
        except ImportError:
            return 0.0

    def record_frame(self, frame_number: int, total_frames: int, frame_time: float,
                     render_engine: str = "BLENDER_EEVEE", resolution: str = "1280x720") -> RenderMetrics:
        """Record metrics for a rendered frame."""
        self._frame_times.append(frame_time)
        avg_time = sum(self._frame_times) / len(self._frame_times)
        frames_remaining = total_frames - frame_number
        eta = avg_time * frames_remaining

        metrics = RenderMetrics(
            worker_id=self.worker_id,
            frame_number=frame_number,
            total_frames=total_frames,
            frame_time_sec=frame_time,
            cpu_percent=self.measure_cpu_percent(),
            ram_used_mb=self.measure_ram_used() * 1024,
            ram_total_mb=self._ram_total * 1024,
            cpu_cores=self._cpu_cores,
            cpu_model=self._cpu_model,
            render_engine=render_engine,
            blender_version=self._blender_version,
            resolution=resolution,
            timestamp=time.time(),
            avg_frame_time=avg_time,
            eta_sec=eta,
        )

        self.logger.info(f"Frame {frame_number}/{total_frames}: {frame_time:.2f}s, "
                         f"CPU {metrics.cpu_percent:.0f}%, RAM {metrics.ram_used_mb/1024:.1f}GB, "
                         f"ETA {int(eta//60)}m{int(eta%60)}s")
        return metrics

    def get_system_info(self) -> Dict[str, Any]:
        """Get static system information."""
        return {
            "cpu_cores": self._cpu_cores,
            "cpu_model": self._cpu_model,
            "ram_total_gb": round(self._ram_total, 1),
            "blender_version": self._blender_version,
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
        }

    def get_summary(self) -> Dict[str, Any]:
        """Get render session summary."""
        if not self._frame_times:
            return {"frames_rendered": 0}
        return {
            "frames_rendered": len(self._frame_times),
            "total_render_time_sec": round(sum(self._frame_times), 2),
            "avg_frame_time_sec": round(sum(self._frame_times) / len(self._frame_times), 2),
            "min_frame_time_sec": round(min(self._frame_times), 2),
            "max_frame_time_sec": round(max(self._frame_times), 2),
            "total_elapsed_sec": round(time.time() - self._start_time, 2),
            "system_info": self.get_system_info(),
        }
