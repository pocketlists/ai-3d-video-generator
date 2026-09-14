"""
Blender optimization — intelligent scene optimization for CPU rendering.

Analyzes scene complexity and adjusts Blender settings to balance
quality and render time WITHOUT blindly lowering quality.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class SceneComplexity:
    """Estimated complexity of a scene."""
    object_count: int = 0
    total_vertices: int = 0
    total_faces: int = 0
    light_count: int = 0
    texture_count: int = 0
    has_particles: bool = False
    has_volumetrics: bool = False
    has_sss: bool = False  # subsurface scattering

    @property
    def complexity_score(self) -> float:
        """0-100 score, higher = more complex."""
        score = 0.0
        score += min(self.object_count * 0.5, 20)
        score += min(self.total_vertices / 1000, 30)
        score += min(self.total_faces / 2000, 20)
        score += min(self.light_count * 2, 10)
        score += min(self.texture_count * 1.5, 10)
        if self.has_particles:
            score += 5
        if self.has_volumetrics:
            score += 5
        if self.has_sss:
            score += 5
        return min(score, 100.0)

    @property
    def complexity_label(self) -> str:
        s = self.complexity_score
        if s < 25:
            return "low"
        elif s < 50:
            return "medium"
        elif s < 75:
            return "high"
        return "very_high"

class BlenderOptimizer:
    """Optimize Blender render settings based on scene complexity."""

    # Safe optimization rules — never lower below these
    MIN_SAMPLES = 32
    MIN_RESOLUTION = (960, 540)

    # Default settings by complexity
    SETTINGS_BY_COMPLEXITY: Dict[str, Dict] = {
        "low": {
            "samples": 64,
            "resolution": (1280, 720),
            "use_ssr": False,
            "use_gtao": True,
            "use_bloom": False,
            "shadow_cube_size": 512,
        },
        "medium": {
            "samples": 48,
            "resolution": (1280, 720),
            "use_ssr": False,
            "use_gtao": True,
            "use_bloom": False,
            "shadow_cube_size": 512,
        },
        "high": {
            "samples": 32,
            "resolution": (1280, 720),
            "use_ssr": False,
            "use_gtao": True,
            "use_bloom": False,
            "shadow_cube_size": 256,
        },
        "very_high": {
            "samples": 32,
            "resolution": (960, 540),
            "use_ssr": False,
            "use_gtao": True,
            "use_bloom": False,
            "shadow_cube_size": 256,
        },
    }

    def __init__(self, previous_runs: Optional[List[Dict]] = None):
        """Initialize with historical run data for learning."""
        self.previous_runs = previous_runs or []

    def optimize_settings(self, complexity: SceneComplexity,
                          requested_resolution: Optional[Tuple[int, int]] = None,
                          requested_samples: Optional[int] = None) -> Dict:
        """
        Get optimized render settings for a scene.

        NEVER goes below MIN_SAMPLES or MIN_RESOLUTION.
        Learns from previous runs to avoid repeating slow configurations.
        """
        label = complexity.complexity_label
        base = self.SETTINGS_BY_COMPLEXITY[label].copy()

        # Apply user requests if safe
        if requested_resolution:
            if requested_resolution[0] >= self.MIN_RESOLUTION[0]:
                base["resolution"] = requested_resolution

        if requested_samples and requested_samples >= self.MIN_SAMPLES:
            base["samples"] = requested_samples

        # Learn from previous runs
        optimizations = self._learn_from_history(base, complexity)
        base.update(optimizations)

        base["complexity_score"] = round(complexity.complexity_score, 1)
        base["complexity_label"] = label
        base["min_samples_enforced"] = self.MIN_SAMPLES
        base["min_resolution_enforced"] = list(self.MIN_RESOLUTION)

        return base

    def _learn_from_history(self, settings: Dict, complexity: SceneComplexity) -> Dict:
        """Analyze previous runs and apply safe optimizations."""
        adjustments = {}

        if not self.previous_runs:
            return adjustments

        # Find similar past runs
        similar = [
            r for r in self.previous_runs
            if r.get("complexity_label") == complexity.complexity_label
        ]

        if not similar:
            return adjustments

        # Check if previous runs with these settings were slow
        avg_time = sum(r.get("render_time_sec", 0) for r in similar) / len(similar)
        avg_frames = sum(r.get("frame_count", 1) for r in similar) / len(similar)
        per_frame_time = avg_time / max(avg_frames, 1)

        # If per-frame time was very high, apply conservative optimizations
        if per_frame_time > 5.0:  # > 5 sec per frame is slow
            current_samples = settings.get("samples", 64)
            if current_samples > self.MIN_SAMPLES:
                adjustments["samples"] = max(current_samples - 16, self.MIN_SAMPLES)
                adjustments["optimization_reason"] = (
                    f"Reduced samples from {current_samples} to {adjustments['samples']} "
                    f"based on slow per-frame time ({per_frame_time:.1f}s) in {len(similar)} past runs"
                )

        # Check for repeated failures with certain settings
        failures = [r for r in similar if not r.get("success", True)]
        if len(failures) > len(similar) * 0.5:
            adjustments["use_bloom"] = False
            adjustments["use_ssr"] = False
            adjustments["optimization_reason"] = (
                f"Disabled expensive effects due to {len(failures)} failures "
                f"in {len(similar)} similar past runs"
            )

        return adjustments

    def get_optimization_report(self, settings: Dict) -> str:
        """Generate a human-readable optimization report."""
        lines = [
            "=== Blender Optimization Report ===",
            f"Complexity: {settings.get('complexity_label', 'unknown')} "
            f"(score: {settings.get('complexity_score', 'N/A')})",
            f"Render engine: EEVEE (CPU-optimized)",
            f"Samples: {settings.get('samples', 'N/A')}",
            f"Resolution: {settings.get('resolution', 'N/A')}",
            f"SSR: {settings.get('use_ssr', False)}",
            f"Ambient Occlusion: {settings.get('use_gtao', False)}",
            f"Bloom: {settings.get('use_bloom', False)}",
            f"Shadow cube size: {settings.get('shadow_cube_size', 'N/A')}",
        ]
        if settings.get("optimization_reason"):
            lines.append(f"Optimization: {settings['optimization_reason']}")
        lines.append(f"Min samples enforced: {self.MIN_SAMPLES}")
        lines.append(f"Min resolution enforced: {self.MIN_RESOLUTION}")
        return "\n".join(lines)

    def estimate_render_time(self, complexity: SceneComplexity,
                              settings: Dict, frame_count: int) -> float:
        """Estimate total render time in seconds."""
        label = complexity.complexity_label
        base_time_per_frame = {
            "low": 0.5,
            "medium": 1.0,
            "high": 2.0,
            "very_high": 4.0,
        }
        base = base_time_per_frame.get(label, 2.0)

        # Adjust for samples (relative to 64)
        samples = settings.get("samples", 64)
        sample_factor = samples / 64.0

        # Adjust for resolution (relative to 1280x720)
        res = settings.get("resolution", (1280, 720))
        pixel_count = res[0] * res[1]
        base_pixels = 1280 * 720
        res_factor = pixel_count / base_pixels

        estimated_per_frame = base * sample_factor * res_factor
        total = estimated_per_frame * frame_count

        return round(total, 1)
