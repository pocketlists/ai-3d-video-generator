"""
Render worker — renders frames with real CPU/RAM monitoring.

Stage 16: Each worker renders a subset of frames. Supports up to 20 parallel workers.
Uses CPU monitor for real-time metrics. Falls back to placeholder frames if Blender unavailable.
"""
import json
import os
import subprocess
import time
from typing import Any, Dict, List

from workers.base_worker import BaseWorker
from blender.render_manager import RenderManager, RenderTask, RenderResult
from utils.cpu_monitor import CPUMonitor
from optimizer.metrics_collector import MetricsCollector


class RenderWorker(BaseWorker):
    stage_name = "render_workers"

    def run(self) -> Dict[str, Any]:
        worker_id = int(os.environ.get("WORKER_ID", "0"))
        blend_file = os.environ.get("BLEND_FILE", "")
        frame_start = int(os.environ.get("FRAME_START", "1"))
        frame_end = int(os.environ.get("FRAME_END", "360"))
        resolution = os.environ.get("RESOLUTION", "1280x720").split("x")
        samples = int(os.environ.get("RENDER_SAMPLES", "64"))
        engine = os.environ.get("RENDER_ENGINE", "BLENDER_EEVEE")
        blender_path = os.environ.get("BLENDER_PATH", "blender")

        artifact_dir = os.environ.get("ARTIFACT_DIR", "/tmp/pipeline_artifacts")
        output_dir = os.path.join(artifact_dir, "renders", f"worker_{worker_id}")
        os.makedirs(output_dir, exist_ok=True)

        # Initialize CPU monitor
        monitor = CPUMonitor(worker_id=worker_id)
        self.logger.info(f"Worker {worker_id} system: {monitor.get_system_info()}")

        if blend_file and os.path.exists(blend_file):
            # Real Blender rendering
            task = RenderTask(
                worker_id=worker_id, blend_file=blend_file, output_dir=output_dir,
                frame_start=frame_start, frame_end=frame_end,
                resolution=(int(resolution[0]), int(resolution[1])),
                samples=samples, engine=engine,
            )
            manager = RenderManager(blend_file, os.path.join(artifact_dir, "renders"))
            result = manager.render_single_task(task, blender_path)

            # Record metrics with CPU monitoring
            collector = MetricsCollector()
            collector.record_render(
                worker_id, frame_start, frame_end,
                result.elapsed_sec, samples, f"{resolution[0]}x{resolution[1]}",
                engine, result.frames_rendered, result.success, result.error
            )
            collector.save()

            return {
                "status": "success" if result.success else "error",
                "worker_id": worker_id,
                "frames_rendered": result.frames_rendered,
                "elapsed_sec": result.elapsed_sec,
                "output_files": result.output_files,
                "error": result.error,
                "system_info": monitor.get_system_info(),
            }
        else:
            # Placeholder frames for pipeline testing
            self.logger.warning(f"Worker {worker_id}: no blend file, generating placeholder frames")
            frames = self._generate_placeholder_frames(
                output_dir, frame_start, frame_end,
                int(resolution[0]), int(resolution[1]), monitor
            )
            summary = monitor.get_summary()
            return {
                "status": "success",
                "worker_id": worker_id,
                "frames_rendered": len(frames),
                "output_files": frames,
                "note": "placeholder frames (no Blender available)",
                "system_info": monitor.get_system_info(),
                "render_summary": summary,
            }

    def _generate_placeholder_frames(self, output_dir: str, frame_start: int, frame_end: int,
                                      width: int, height: int, monitor: CPUMonitor) -> List[str]:
        """Generate placeholder PNG frames with CPU monitoring."""
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.logger.error("PIL not available for placeholder frames")
            return []

        frames = []
        total = frame_end - frame_start + 1
        for i, frame in enumerate(range(frame_start, frame_end + 1)):
            start = time.time()
            img = Image.new("RGB", (width, height), color=(20 + frame % 50, 30, 50))
            draw = ImageDraw.Draw(img)
            draw.text((10, 10), f"Frame {frame}", fill=(255, 255, 255))
            filepath = os.path.join(output_dir, f"frame_{frame:04d}.png")
            img.save(filepath)
            frames.append(filepath)

            frame_time = time.time() - start
            metrics = monitor.record_frame(i + 1, total, frame_time,
                                           "placeholder", f"{width}x{height}")

        self.logger.info(f"Generated {len(frames)} placeholder frames\n{metrics.format_report()}")
        return frames
