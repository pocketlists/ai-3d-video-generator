"""
Render worker — renders frames using Blender in parallel.

Stage 16: Each worker instance renders a subset of frames from the
assembled Blender scene. Workers run in parallel via GitHub Actions matrix.
"""
import json
import os
import subprocess
import time
from typing import Any, Dict, List

from workers.base_worker import BaseWorker
from blender.render_manager import RenderManager, RenderTask, RenderResult
from utils.file_validator import validate_file_exists
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

        # If blend file exists, render with Blender
        if blend_file and os.path.exists(blend_file):
            self.logger.info(f"Worker {worker_id}: rendering {blend_file} frames {frame_start}-{frame_end}")
            task = RenderTask(
                worker_id=worker_id,
                blend_file=blend_file,
                output_dir=output_dir,
                frame_start=frame_start,
                frame_end=frame_end,
                resolution=(int(resolution[0]), int(resolution[1])),
                samples=samples,
                engine=engine,
            )
            manager = RenderManager(blend_file, os.path.join(artifact_dir, "renders"))
            result = manager.render_single_task(task, blender_path)

            # Record metrics
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
            }
        else:
            # No blend file — generate placeholder frames for pipeline testing
            self.logger.warning(f"Worker {worker_id}: no blend file, generating placeholder frames")
            frames = self._generate_placeholder_frames(output_dir, frame_start, frame_end,
                                                       int(resolution[0]), int(resolution[1]))
            return {
                "status": "success",
                "worker_id": worker_id,
                "frames_rendered": len(frames),
                "output_files": frames,
                "note": "placeholder frames (no Blender available)",
            }

    def _generate_placeholder_frames(self, output_dir: str, frame_start: int, frame_end: int,
                                      width: int, height: int) -> List[str]:
        """Generate simple PNG placeholder frames when Blender is not available."""
        try:
            from PIL import Image
        except ImportError:
            self.logger.error("PIL not available for placeholder frames")
            return []

        frames = []
        for frame in range(frame_start, frame_end + 1):
            img = Image.new("RGB", (width, height), color=(20 + frame % 50, 30, 50))
            # Add frame number text
            from PIL import ImageDraw
            draw = ImageDraw.Draw(img)
            draw.text((10, 10), f"Frame {frame}", fill=(255, 255, 255))
            filepath = os.path.join(output_dir, f"frame_{frame:04d}.png")
            img.save(filepath)
            frames.append(filepath)

        self.logger.info(f"Generated {len(frames)} placeholder frames")
        return frames
