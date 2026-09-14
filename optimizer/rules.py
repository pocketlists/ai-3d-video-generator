"""
Optimization rules — safe rules for optimizing the pipeline.

Each rule checks for specific inefficiency patterns and recommends
a safe optimization. Quality is NEVER automatically lowered below
minimum thresholds.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class OptimizationRule:
    """A single optimization rule."""
    name: str
    description: str
    action: str
    safe: bool = True
    priority: str = "medium"  # high, medium, low
    issue_types: List[str] = field(default_factory=list)

    def check(self, issues: List[Dict]) -> List[Dict]:
        """Check if this rule applies to any issues. Returns matching issues."""
        matches = []
        for issue in issues:
            if issue.get("type") in self.issue_types:
                matches.append(issue)
        return matches


# Safe optimization rules — these NEVER reduce quality below minimum
SAFE_RULES: List[OptimizationRule] = [
    OptimizationRule(
        name="reduce_samples_low_complexity",
        description="Reduce render samples for low-complexity scenes",
        action="Set samples to 32 for low complexity, 48 for medium (never below 32)",
        priority="high",
        issue_types=["high_samples_low_complexity"],
    ),
    OptimizationRule(
        name="optimize_slow_frames",
        description="Optimize settings for slow per-frame renders",
        action="Reduce samples by 16 (if above 48) or use lower shadow resolution",
        priority="high",
        issue_types=["slow_per_frame"],
    ),
    OptimizationRule(
        name="fast_ffmpeg_preset",
        description="Use faster FFmpeg encoding preset",
        action="Use 'ultrafast' or 'veryfast' x264 preset for intermediate encoding",
        priority="medium",
        issue_types=["slow_ffmpeg"],
    ),
    OptimizationRule(
        name="balance_worker_load",
        description="Balance frame distribution across render workers",
        action="Use dynamic frame splitting based on estimated render time per frame",
        priority="medium",
        issue_types=["uneven_worker_load"],
    ),
    OptimizationRule(
        name="limit_texture_sizes",
        description="Limit texture sizes for low-poly scenes",
        action="Downscale textures to max 1024x1024 for low-poly assets",
        priority="low",
        issue_types=["oversized_textures"],
    ),
    OptimizationRule(
        name="disable_expensive_effects",
        description="Disable expensive rendering effects on CPU",
        action="Disable SSR, volumetrics, and bloom for CPU rendering",
        priority="medium",
        issue_types=["slow_per_frame", "high_samples_low_complexity"],
    ),
]


# Minimum quality thresholds — NEVER go below these
QUALITY_THRESHOLDS = {
    "min_samples": 32,
    "min_resolution": [960, 540],
    "min_fps": 24,
    "min_bitrate_kbps": 1000,
    "min_video_duration_sec": 50,  # ~1 minute target
    "max_video_duration_sec": 75,
}


def validate_quality_thresholds(settings: Dict) -> List[str]:
    """Validate that settings don't violate quality thresholds. Returns violations."""
    violations = []

    if settings.get("samples", 64) < QUALITY_THRESHOLDS["min_samples"]:
        violations.append(
            f"Samples ({settings['samples']}) below minimum ({QUALITY_THRESHOLDS['min_samples']})"
        )

    res = settings.get("resolution", [1280, 720])
    if res[0] < QUALITY_THRESHOLDS["min_resolution"][0] or res[1] < QUALITY_THRESHOLDS["min_resolution"][1]:
        violations.append(
            f"Resolution ({res}) below minimum ({QUALITY_THRESHOLDS['min_resolution']})"
        )

    fps = settings.get("fps", 24)
    if fps < QUALITY_THRESHOLDS["min_fps"]:
        violations.append(f"FPS ({fps}) below minimum ({QUALITY_THRESHOLDS['min_fps']})")

    return violations


def is_optimization_safe(optimization: Dict, current_settings: Dict) -> bool:
    """Check if an optimization would violate quality thresholds."""
    proposed = current_settings.copy()
    proposed.update(optimization.get("changes", {}))
    violations = validate_quality_thresholds(proposed)
    return len(violations) == 0
