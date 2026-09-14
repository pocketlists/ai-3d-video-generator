"""
Optimizer analyzer — analyzes historical metrics and identifies optimizations.

Identifies bottlenecks, unnecessary expensive operations, inefficient
settings, and repeated failures, then recommends safe optimizations.
"""
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict

from optimizer.metrics_collector import MetricsCollector
from optimizer.rules import OptimizationRule, SAFE_RULES


class OptimizationAnalyzer:
    """Analyze pipeline metrics and generate optimization recommendations."""

    def __init__(self, collector: Optional[MetricsCollector] = None):
        self.collector = collector or MetricsCollector()
        self.rules: List[OptimizationRule] = list(SAFE_RULES)

    def analyze(self, runs: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """
        Analyze historical runs and return findings + recommendations.
        """
        historical = runs or self.collector.load_previous_runs()
        if not historical:
            return {
                "summary": {"total_runs_analyzed": 0},
                "bottlenecks": [],
                "recommendations": [],
                "warnings": ["No historical data available yet"],
            }

        bottlenecks = self._identify_bottlenecks(historical)
        inefficient = self._identify_inefficiencies(historical)
        failures = self._identify_repeated_failures(historical)
        wasted = self._identify_wasted_resources(historical)

        recommendations = self._generate_recommendations(
            bottlenecks, inefficient, failures, wasted
        )

        warnings = self._generate_warnings(historical)

        total_render_time = sum(
            r.get("render", {}).get("total_time", 0) for r in historical
        )
        avg_pipeline_time = sum(
            sum(s.get("elapsed_sec", 0) for s in r.get("stages", {}).values())
            for r in historical
        ) / len(historical)

        return {
            "summary": {
                "total_runs_analyzed": len(historical),
                "total_render_time_sec": round(total_render_time, 1),
                "avg_pipeline_time_sec": round(avg_pipeline_time, 1),
                "total_errors": sum(len(r.get("errors", [])) for r in historical),
            },
            "bottlenecks": bottlenecks,
            "inefficiencies": inefficient,
            "failures": failures,
            "wasted_resources": wasted,
            "recommendations": recommendations,
            "warnings": warnings,
        }

    def _identify_bottlenecks(self, runs: List[Dict]) -> List[Dict]:
        """Identify the slowest stages across runs."""
        stage_times = defaultdict(list)
        for run in runs:
            for stage_name, stage_data in run.get("stages", {}).items():
                stage_times[stage_name].append(stage_data.get("elapsed_sec", 0))

        bottlenecks = []
        for stage, times in sorted(stage_times.items(), key=lambda x: sum(x[1]), reverse=True):
            avg_time = sum(times) / len(times)
            if avg_time > 30:
                bottlenecks.append({
                    "stage": stage,
                    "avg_time_sec": round(avg_time, 1),
                    "runs": len(times),
                    "max_time_sec": round(max(times), 1),
                })

        return bottlenecks[:5]

    def _identify_inefficiencies(self, runs: List[Dict]) -> List[Dict]:
        """Identify inefficient settings or operations."""
        inefficiencies = []

        for run in runs:
            blender = run.get("blender", {})
            render = run.get("render", {})
            ffmpeg = run.get("ffmpeg", {})

            samples = blender.get("samples", 0)
            complexity = blender.get("complexity_label", "")
            if samples > 64 and complexity in ("low", "medium"):
                inefficiencies.append({
                    "type": "high_samples_low_complexity",
                    "description": "Using " + str(samples) + " samples for " + complexity + " complexity scene",
                    "recommendation": "Reduce to 32-48 samples for " + complexity + " scenes",
                })

            for worker_key, worker_data in render.items():
                per_frame = worker_data.get("per_frame_sec", 0)
                if per_frame > 5.0:
                    inefficiencies.append({
                        "type": "slow_per_frame",
                        "description": worker_key + ": " + str(round(per_frame, 1)) + "s per frame",
                        "recommendation": "Consider reducing samples or resolution",
                    })

            if ffmpeg:
                proc_time = ffmpeg.get("processing_time_sec", 0)
                out_dur = ffmpeg.get("output_duration_sec", 0)
                if proc_time > out_dur * 3 and out_dur > 0:
                    inefficiencies.append({
                        "type": "slow_ffmpeg",
                        "description": "FFmpeg took " + str(round(proc_time, 1)) + "s for " + str(round(out_dur, 1)) + "s video",
                        "recommendation": "Use hardware encoding or faster codec preset",
                    })

        return inefficiencies

    def _identify_repeated_failures(self, runs: List[Dict]) -> List[Dict]:
        """Identify stages that fail repeatedly."""
        failure_counts = defaultdict(list)
        for run in runs:
            for error in run.get("errors", []):
                failure_counts[error.get("stage", "unknown")].append(error)

        repeated = []
        for stage, errors in failure_counts.items():
            if len(errors) >= 2:
                repeated.append({
                    "stage": stage,
                    "failure_count": len(errors),
                    "errors": list(set(e.get("error", "")[:200] for e in errors)),
                })

        return repeated

    def _identify_wasted_resources(self, runs: List[Dict]) -> List[Dict]:
        """Identify wasted CPU time, unnecessary transfers, etc."""
        wasted = []

        for run in runs:
            render = run.get("render", {})
            if len(render) > 1:
                times = [w.get("elapsed_sec", 0) for w in render.values()]
                if times:
                    max_t, min_t = max(times), min(times)
                    if max_t > 0 and (max_t - min_t) / max_t > 0.5:
                        wasted.append({
                            "type": "uneven_worker_load",
                            "description": "Worker time variance: " + str(round(min_t)) + "s - " + str(round(max_t)) + "s",
                            "recommendation": "Better distribute frames across workers",
                        })

            blender = run.get("blender", {})
            texture_sizes = blender.get("texture_sizes", [])
            if any(ts > 2048 for ts in texture_sizes):
                wasted.append({
                    "type": "oversized_textures",
                    "description": "Texture sizes: " + str(texture_sizes),
                    "recommendation": "Use 1024x1024 max for low-poly scenes",
                })

        return wasted

    def _generate_recommendations(self, bottlenecks: List, inefficiencies: List,
                                    failures: List, wasted: List) -> List[Dict]:
        """Generate actionable optimization recommendations."""
        recs = []

        all_issues = inefficiencies + wasted
        for rule in self.rules:
            matches = rule.check(all_issues)
            for match in matches:
                recs.append({
                    "rule": rule.name,
                    "description": rule.description,
                    "action": rule.action,
                    "safe": rule.safe,
                    "priority": rule.priority,
                    "matched_issue": match,
                })

        for b in bottlenecks:
            if b["stage"] == "render_workers":
                recs.append({
                    "rule": "render_bottleneck",
                    "description": "Rendering is the bottleneck (" + str(b["avg_time_sec"]) + "s avg)",
                    "action": "Increase worker count or reduce samples if above minimum",
                    "safe": True,
                    "priority": "high",
                })
            elif b["stage"] == "blender_assembly":
                recs.append({
                    "rule": "assembly_bottleneck",
                    "description": "Scene assembly is slow (" + str(b["avg_time_sec"]) + "s avg)",
                    "action": "Simplify scene or pre-compute static elements",
                    "safe": True,
                    "priority": "medium",
                })

        for f in failures:
            recs.append({
                "rule": "failure_pattern",
                "description": f["stage"] + " failed " + str(f["failure_count"]) + " times",
                "action": "Add retry logic or investigate root cause",
                "safe": True,
                "priority": "high",
            })

        priority_order = {"high": 0, "medium": 1, "low": 2}
        recs.sort(key=lambda r: priority_order.get(r.get("priority", "low"), 2))

        return recs

    def _generate_warnings(self, runs: List[Dict]) -> List[str]:
        warnings = []

        recent = runs[:3]
        for run in recent:
            blender = run.get("blender", {})
            if blender.get("samples", 64) < 32:
                warnings.append(
                    "Run " + str(run.get("run_id")) + ": samples below recommended minimum (" + str(blender["samples"]) + ")"
                )

            qc = run.get("quality_check", {})
            if qc and not qc.get("passed"):
                warnings.append(
                    "Run " + str(run.get("run_id")) + ": quality check failed - " + str(qc.get("issues", []))
                )

        if len(runs) >= 5:
            error_rate = sum(len(r.get("errors", [])) for r in runs) / len(runs)
            if error_rate > 2:
                warnings.append("High error rate: " + str(round(error_rate, 1)) + " errors/run average")

        return warnings

    def generate_report(self, analysis: Optional[Dict] = None) -> str:
        """Generate a human-readable optimization report."""
        a = analysis or self.analyze()
        lines = ["=" * 60, "PIPELINE OPTIMIZATION REPORT", "=" * 60]

        s = a.get("summary", {})
        lines.append("\nRuns analyzed: " + str(s.get("total_runs_analyzed", 0)))
        lines.append("Total render time: " + str(s.get("total_render_time_sec", 0)) + "s")
        lines.append("Avg pipeline time: " + str(s.get("avg_pipeline_time_sec", 0)) + "s")
        lines.append("Total errors: " + str(s.get("total_errors", 0)))

        if a.get("bottlenecks"):
            lines.append("\n--- Bottlenecks ---")
            for b in a["bottlenecks"]:
                lines.append("  " + b["stage"] + ": avg " + str(b["avg_time_sec"]) + "s (" + str(b["runs"]) + " runs)")

        if a.get("recommendations"):
            lines.append("\n--- Recommendations ---")
            for r in a["recommendations"]:
                lines.append("  [" + r["priority"].upper() + "] " + r["description"])
                lines.append("    Action: " + r["action"])

        if a.get("warnings"):
            lines.append("\n--- Warnings ---")
            for w in a["warnings"]:
                lines.append("  [!] " + w)

        return "\n".join(lines)
