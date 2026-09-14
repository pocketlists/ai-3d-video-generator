"""
Render manager — manages parallel rendering of Blender frames/clips.

Splits a scene's frame range across N workers, each rendering a subset
of frames, then collects all output for FFmpeg assembly.
"""
import json
import os
import math
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from utils.logger import PipelineLogger
from utils.file_validator import validate_directory


@dataclass
class RenderTask:
    """A single rendering task for one worker."""
    worker_id: int
    blend_file: str
    output_dir: str
    frame_start: int
    frame_end: int
    resolution: Tuple[int, int] = (1280, 720)
    samples: int = 64
    engine: str = "BLENDER_EEVEE"

    def frame_count(self) -> int:
        return self.frame_end - self.frame_start + 1

    def to_dict(self) -> dict:
        return {
            "worker_id": self.worker_id,
            "blend_file": self.blend_file,
            "output_dir": self.output_dir,
            "frame_start": self.frame_start,
            "frame_end": self.frame_end,
            "resolution": list(self.resolution),
            "samples": self.samples,
            "engine": self.engine,
        }


@dataclass
class RenderResult:
    """Result of a single render task."""
    worker_id: int
    success: bool
    frames_rendered: int
    elapsed_sec: float
    output_files: List[str] = field(default_factory=list)
    error: Optional[str] = None

class RenderManager:
    """Manages distributed rendering across multiple workers."""

    def __init__(self, blend_file: str, output_dir: str,
                 total_frames: int = 1440, num_workers: int = 4):
        self.blend_file = blend_file
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.total_frames = total_frames
        self.num_workers = num_workers
        self.logger = PipelineLogger("render_manager")

    def create_tasks(self, frame_start: int = 1, frame_end: Optional[int] = None,
                     resolution: Tuple[int, int] = (1280, 720),
                     samples: int = 64, engine: str = "BLENDER_EEVEE") -> List[RenderTask]:
        """Split the frame range into tasks for each worker."""
        end = frame_end or (frame_start + self.total_frames - 1)
        total = end - frame_start + 1
        frames_per_worker = math.ceil(total / self.num_workers)

        tasks = []
        for i in range(self.num_workers):
            start = frame_start + i * frames_per_worker
            task_end = min(start + frames_per_worker - 1, end)
            if start > end:
                break
            task = RenderTask(
                worker_id=i,
                blend_file=self.blend_file,
                output_dir=str(self.output_dir / f"worker_{i}"),
                frame_start=start,
                frame_end=task_end,
                resolution=resolution,
                samples=samples,
                engine=engine,
            )
            os.makedirs(task.output_dir, exist_ok=True)
            tasks.append(task)

        self.logger.info(f"Created {len(tasks)} render tasks for {total} frames",
                         data={"frames_per_worker": frames_per_worker})
        return tasks

    def render_single_task(self, task: RenderTask, blender_path: str = "blender") -> RenderResult:
        """Render a single task using Blender's command-line interface."""
        start_time = time.time()
        self.logger.info(f"Worker {task.worker_id}: rendering frames {task.frame_start}-{task.frame_end}")

        output_pattern = os.path.join(task.output_dir, f"frame_####.png")

        cmd = [
            blender_path,
            "--background",
            task.blend_file,
            "--render-output", output_pattern,
            "--render-format", "PNG",
            "--render-frame", f"{task.frame_start}..{task.frame_end}",
            "--",
            "-E", task.engine,
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            elapsed = time.time() - start_time

            if result.returncode != 0:
                error_msg = result.stderr[:500] if result.stderr else "Unknown Blender error"
                self.logger.error(f"Worker {task.worker_id}: render failed", data={"error": error_msg})
                return RenderResult(
                    worker_id=task.worker_id, success=False,
                    frames_rendered=0, elapsed_sec=elapsed, error=error_msg
                )

            # Collect output files
            output_files = sorted([
                str(f) for f in Path(task.output_dir).glob("frame_*.png")
            ])

            self.logger.info(f"Worker {task.worker_id}: rendered {len(output_files)} frames in {elapsed:.1f}s")
            return RenderResult(
                worker_id=task.worker_id, success=True,
                frames_rendered=len(output_files), elapsed_sec=elapsed,
                output_files=output_files
            )

        except subprocess.TimeoutExpired:
            elapsed = time.time() - start_time
            error = f"Render timed out after {elapsed:.0f}s"
            self.logger.error(f"Worker {task.worker_id}: {error}")
            return RenderResult(
                worker_id=task.worker_id, success=False,
                frames_rendered=0, elapsed_sec=elapsed, error=error
            )
        except FileNotFoundError:
            elapsed = time.time() - start_time
            error = f"Blender binary not found at: {blender_path}"
            self.logger.error(f"Worker {task.worker_id}: {error}")
            return RenderResult(
                worker_id=task.worker_id, success=False,
                frames_rendered=0, elapsed_sec=elapsed, error=error
            )

    def collect_all_frames(self, worker_results: List[RenderResult]) -> List[str]:
        """Collect all rendered frame files in order."""
        all_frames = []
        for result in sorted(worker_results, key=lambda r: r.worker_id):
            if result.success:
                all_frames.extend(result.output_files)
        return all_frames

    def get_render_summary(self, results: List[RenderResult]) -> Dict:
        """Get summary statistics from render results."""
        total_frames = sum(r.frames_rendered for r in results)
        total_time = sum(r.elapsed_sec for r in results)
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        return {
            "total_workers": len(results),
            "successful_workers": len(successful),
            "failed_workers": len(failed),
            "total_frames_rendered": total_frames,
            "total_render_time_sec": round(total_time, 2),
            "avg_frame_time_sec": round(total_time / max(total_frames, 1), 3),
            "failed_worker_ids": [r.worker_id for r in failed],
            "errors": [{"worker": r.worker_id, "error": r.error} for r in failed],
        }

    def save_task_manifest(self, tasks: List[RenderTask], path: Optional[str] = None) -> str:
        """Save the task list as JSON for GitHub Actions matrix."""
        manifest = {
            "blend_file": self.blend_file,
            "total_frames": self.total_frames,
            "num_workers": len(tasks),
            "tasks": [t.to_dict() for t in tasks],
        }
        out_path = path or str(self.output_dir / "render_tasks.json")
        with open(out_path, "w") as f:
            json.dump(manifest, f, indent=2)
        return out_path
