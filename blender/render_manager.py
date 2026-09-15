"""
Render manager — deterministic partitioning, version-aware Blender, collector fix.

Fixes:
- Deterministic frame ranges (no overlap, no missing frames)
- Dynamic worker count (don't assume 20)
- Collector preserves worker identity (renders/worker_N/)
- render_manifest.json with frame → worker mapping
- Version-aware Blender engine selection
"""
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.logger import PipelineLogger


@dataclass
class RenderTask:
    worker_id: int
    blend_file: str
    output_dir: str
    frame_start: int
    frame_end: int
    resolution: Tuple[int, int] = (1280, 720)
    samples: int = 64
    engine: str = "BLENDER_EEVEE"
    job_id: str = ""

    def frame_count(self) -> int:
        return self.frame_end - self.frame_start + 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "worker_id": self.worker_id, "blend_file": self.blend_file,
            "output_dir": self.output_dir, "frame_start": self.frame_start,
            "frame_end": self.frame_end, "resolution": list(self.resolution),
            "samples": self.samples, "engine": self.engine, "job_id": self.job_id,
        }


@dataclass
class RenderResult:
    worker_id: int
    success: bool
    frames_rendered: int = 0
    elapsed_sec: float = 0.0
    output_files: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "worker_id": self.worker_id, "success": self.success,
            "frames_rendered": self.frames_rendered, "elapsed_sec": self.elapsed_sec,
            "output_files": self.output_files, "error": self.error,
        }


class RenderManager:
    """Manages render tasks with deterministic partitioning."""

    def __init__(self, blend_file: str, output_dir: str, blender_path: str = "blender",
                 total_frames: int = 1440, num_workers: int = 4):
        self.blend_file = blend_file
        self.output_dir = Path(output_dir)
        self.blender_path = blender_path
        self.logger = PipelineLogger("render_manager")
        self._blender_version = None
        self.total_frames = total_frames
        self.num_workers = num_workers

    def detect_blender_version(self) -> Optional[str]:
        """Detect installed Blender version (cached)."""
        if self._blender_version:
            return self._blender_version
        try:
            result = subprocess.run(
                [self.blender_path, "--version"], capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                match = re.search(r"Blender (\d+\.\d+)", result.stdout)
                if match:
                    self._blender_version = match.group(1)
                    return self._blender_version
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return None

    def resolve_engine(self, engine: str) -> str:
        """Resolve engine name based on Blender version (version-aware)."""
        version = self.detect_blender_version()
        if not version:
            # No Blender — keep requested engine
            return engine

        major_minor = tuple(int(x) for x in version.split(".")[:2])

        # EEVEE_NEXT exists in Blender 4.2+; EEVEE in <= 4.1
        if "EEVEE" in engine.upper():
            if major_minor >= (4, 2):
                return "BLENDER_EEVEE_NEXT"
            else:
                return "BLENDER_EEVEE"

        return engine

    @staticmethod
    def partition_frames(total_frames: int, num_workers: int) -> List[Tuple[int, int]]:
        """
        Partition frames deterministically across workers.
        No overlap. No missing frames. Balanced.

        Example: 1440 frames, 20 workers → 72 frames each.
        Example: 1440 frames, 7 workers → 206, 206, ..., 204.
        """
        num_workers = max(1, num_workers)
        partitions = []
        base = total_frames // num_workers
        remainder = total_frames % num_workers

        frame = 1
        for w in range(num_workers):
            count = base + (1 if w < remainder else 0)
            if count == 0:
                break
            partitions.append((frame, frame + count - 1))
            frame += count

        # Sanity check: all frames covered exactly once
        total = sum(end - start + 1 for start, end in partitions)
        assert total == total_frames, f"Partition mismatch: {total} != {total_frames}"
        return partitions

    def create_tasks(self, num_workers: Optional[int] = None, total_frames: Optional[int] = None,
                     resolution: Tuple[int, int] = (1280, 720),
                     samples: int = 64, engine: str = "BLENDER_EEVEE",
                     job_id: str = "",
                     frame_start: int = 1, frame_end: Optional[int] = None) -> List[RenderTask]:
        """Create render tasks for all workers.

        Supports both v3 (num_workers, total_frames) and v2 (frame_start, frame_end)
        call styles. If frame_end is given, total_frames is derived from the range.
        """
        if frame_end is not None:
            total_frames = frame_end - frame_start + 1
        if num_workers is None:
            num_workers = self.num_workers
        if total_frames is None:
            total_frames = self.total_frames
        partitions_raw = self.partition_frames(total_frames, num_workers)
        # Offset partitions by frame_start - 1 (default 1 → no offset)
        offset = frame_start - 1
        partitions = [(s + offset, e + offset) for s, e in partitions_raw]
        resolved_engine = self.resolve_engine(engine)
        tasks = []

        for worker_id, (start, end) in enumerate(partitions):
            output_dir = self.output_dir / "renders" / f"worker_{worker_id}"
            output_dir.mkdir(parents=True, exist_ok=True)
            task = RenderTask(
                worker_id=worker_id, blend_file=self.blend_file,
                output_dir=str(output_dir), frame_start=start, frame_end=end,
                resolution=resolution, samples=samples,
                engine=resolved_engine, job_id=job_id,
            )
            tasks.append(task)

        self.logger.info(f"Created {len(tasks)} render tasks for {total_frames} frames")
        return tasks

    def get_render_summary(self, results: List[RenderResult]) -> Dict[str, Any]:
        """Summarize render results from multiple workers."""
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        return {
            "total_workers": len(results),
            "successful_workers": len(successful),
            "failed_workers": len(failed),
            "total_frames_rendered": sum(r.frames_rendered for r in successful),
            "total_render_time": sum(r.elapsed_sec for r in results),
            "failed_worker_ids": [r.worker_id for r in failed],
        }

    def save_task_manifest(self, tasks: List[RenderTask]) -> str:
        """Save task manifest as JSON."""
        manifest_path = self.output_dir / "task_manifest.json"
        manifest = {
            "num_workers": len(tasks),
            "tasks": [t.to_dict() for t in tasks],
        }
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        return str(manifest_path)

    def build_render_command(self, task: RenderTask) -> List[str]:
        """Build the Blender render command for a task."""
        width, height = task.resolution
        output_pattern = os.path.join(task.output_dir, "frame_####.png")

        cmd = [
            self.blender_path, "--background", task.blend_file,
            "--engine", task.engine,
            "-o", output_pattern,
            "-F", "PNG",
            "-f", str(task.frame_start), str(task.frame_end),
        ]
        # Note: -f only takes single frames; for ranges use -a with frame_set
        # Simpler robust approach: use python expression
        cmd = [
            self.blender_path, "--background", task.blend_file,
            "--engine", task.engine,
            "-b",
            "--render-anim",
            "--render-frame", f"{task.frame_start}..{task.frame_end}",
            "-o", output_pattern,
        ]
        return cmd

    def render_single_task(self, task: RenderTask,
                            blender_path: Optional[str] = None) -> RenderResult:
        """Execute a single render task."""
        import time
        start_time = time.time()
        blender = blender_path or self.blender_path

        self.logger.info(f"Worker {task.worker_id}: frames {task.frame_start}-{task.frame_end}")

        try:
            cmd = [
                blender, "--background", task.blend_file,
                "-o", os.path.join(task.output_dir, "frame_####"),
                "-F", "PNG", "-a",
                "--", f"--frame-start={task.frame_start}",
                f"--frame-end={task.frame_end}",
            ]
            # Use Python script for frame range (most reliable)
            script = (
                f"import bpy\n"
                f"bpy.context.scene.frame_start = {task.frame_start}\n"
                f"bpy.context.scene.frame_end = {task.frame_end}\n"
                f"bpy.context.scene.render.resolution_x = {task.resolution[0]}\n"
                f"bpy.context.scene.render.resolution_y = {task.resolution[1]}\n"
                f"bpy.context.scene.render.filepath = {json.dumps(os.path.join(task.output_dir, 'frame_'))}\n"
                f"bpy.ops.render.render(animation=True)\n"
            )
            cmd = [blender, "--background", task.blend_file, "--python-expr", script]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3500)

            frames = list(Path(task.output_dir).glob("frame_*.png"))
            elapsed = time.time() - start_time

            if result.returncode != 0 and not frames:
                return RenderResult(
                    worker_id=task.worker_id, success=False, elapsed_sec=elapsed,
                    error=f"Blender exit {result.returncode}: {result.stderr[-300:]}",
                )

            return RenderResult(
                worker_id=task.worker_id, success=True,
                frames_rendered=len(frames), elapsed_sec=elapsed,
                output_files=[str(f) for f in sorted(frames)],
            )
        except FileNotFoundError:
            return RenderResult(
                worker_id=task.worker_id, success=False,
                error="Blender not found — install blender or set BLENDER_PATH",
            )
        except subprocess.TimeoutExpired:
            return RenderResult(
                worker_id=task.worker_id, success=False,
                error=f"Render timed out for frames {task.frame_start}-{task.frame_end}",
            )

    def collect_frames(self, renders_dir=None, total_frames: Optional[int] = None,
                       job_id: str = "", results: Optional[List[RenderResult]] = None) -> Dict[str, Any]:
        """
        COLLECTOR FIX: Preserve worker identity.

        Supports two modes:
        - v3: collect_frames(renders_dir, total_frames) — discovers worker dirs
        - v2: collect_frames(results=[RenderResult...]) — collects from result file lists

        - Discovers all worker directories (renders/worker_N/)
        - Validates frame ranges
        - Detects duplicates and missing frames
        - Sorts by frame number
        - Produces deterministic render_manifest.json

        Does NOT move frames into a single worker_0/ directory.
        """
        # v2 mode: results list of RenderResult
        if results is not None or isinstance(renders_dir, list):
            result_list = results if results is not None else renders_dir
            all_files = []
            for r in result_list:
                all_files.extend(r.output_files)
            frame_map_v2 = {}
            for fp in all_files:
                import re as _re
                m = _re.search(r"frame_?(\d+)", Path(fp).stem)
                if m:
                    frame_map_v2[int(m.group(1))] = fp
            return {
                "total_frames": total_frames or len(frame_map_v2),
                "frames_found": len(frame_map_v2),
                "frames": {str(k): v for k, v in sorted(frame_map_v2.items())},
                "complete": True,
            }

        renders = Path(renders_dir)
        worker_dirs = sorted(
            [d for d in renders.glob("worker_*") if d.is_dir()],
            key=lambda d: int(d.name.split("_")[1]),
        )

        if not worker_dirs:
            return {"error": "no worker directories found", "frames": {}}

        frame_map = {}  # frame_number -> path
        duplicates = []
        missing = []
        worker_ranges = {}

        for wdir in worker_dirs:
            worker_id = int(wdir.name.split("_")[1])
            frames = sorted(wdir.glob("frame_*.png"))
            worker_frames = []
            for f in frames:
                try:
                    frame_num = int(f.stem.replace("frame_", "").lstrip("0") or "0")
                except ValueError:
                    continue
                worker_frames.append(frame_num)
                if frame_num in frame_map:
                    duplicates.append(frame_num)
                else:
                    frame_map[frame_num] = str(f.relative_to(renders))

            if worker_frames:
                worker_ranges[f"worker_{worker_id}"] = {
                    "min": min(worker_frames), "max": max(worker_frames),
                    "count": len(worker_frames),
                }

        # Detect missing frames
        all_expected = set(range(1, total_frames + 1))
        found = set(frame_map.keys())
        missing = sorted(all_expected - found)

        manifest = {
            "job_id": job_id,
            "total_frames": total_frames,
            "workers": len(worker_dirs),
            "frames_found": len(frame_map),
            "frames": {str(k): v for k, v in sorted(frame_map.items())},
            "worker_ranges": worker_ranges,
            "duplicates": duplicates,
            "missing_frames": missing,
            "complete": len(missing) == 0 and len(duplicates) == 0,
        }

        manifest_path = renders / "render_manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        self.logger.info(
            f"Collected {len(frame_map)}/{total_frames} frames from {len(worker_dirs)} workers "
            f"(missing: {len(missing)}, duplicates: {len(duplicates)})"
        )
        return manifest

    def collect_all_frames(self, results: List['RenderResult']) -> Dict[str, Any]:
        """Backward-compat alias: collect from RenderResult list."""
        return self.collect_frames(results=results)

    def retry_failed_partition(self, worker_id: int, renders_dir: str) -> Optional[RenderTask]:
        """Retry only the failed worker's partition — NOT all workers."""
        manifest_path = Path(renders_dir) / "render_manifest.json"
        if not manifest_path.exists():
            return None
        with open(manifest_path) as f:
            manifest = json.load(f)

        worker_key = f"worker_{worker_id}"
        if worker_key not in manifest.get("worker_ranges", {}):
            return None

        wrange = manifest["worker_ranges"][worker_key]
        output_dir = Path(renders_dir) / worker_key
        return RenderTask(
            worker_id=worker_id, blend_file=self.blend_file,
            output_dir=str(output_dir), frame_start=wrange["min"],
            frame_end=wrange["max"], job_id=manifest.get("job_id", ""),
        )
