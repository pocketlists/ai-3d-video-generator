"""
Orchestrator — top-level entry point for local and CI pipeline execution.

Can be invoked from the command line to run individual stages or the
entire pipeline locally (for testing), or from GitHub Actions workflows
to run a specific job.
"""
import argparse
import json
import sys
import time
from typing import Optional

from controller.config_loader import ConfigLoader, ConfigError
from controller.state_manager import StateManager
from controller.pipeline import Pipeline


class Orchestrator:
    """Coordinates pipeline execution, state management, and error recovery."""

    def __init__(self, config_path: Optional[str] = None):
        self.config = ConfigLoader(config_path)
        self.pipeline = Pipeline()
        self.state = StateManager()

    def run_stage(self, stage_name: str) -> bool:
        """Run a single pipeline stage. Returns True on success."""
        stage = self.pipeline.get_stage(stage_name)
        if not stage:
            print("Unknown stage: " + stage_name)
            return False

        # Check dependencies
        for dep in stage.depends_on:
            if not self.state.is_stage_complete(dep):
                print("Dependency '" + dep + "' not complete for stage '" + stage_name + "'")
                return False

        self.state.set_stage_status(stage_name, "running")
        print("> Running stage: " + stage_name + " — " + stage.description)
        start = time.time()

        try:
            result = self._execute_stage(stage_name)
            elapsed = time.time() - start
            self.state.set_stage_status(stage_name, "completed",
                                        data={"elapsed": elapsed, "result": result})
            self.state.record_metric(stage_name + "_elapsed", round(elapsed, 2))
            print("[OK] Stage '" + stage_name + "' completed in " + str(round(elapsed, 1)) + "s")
            return True
        except Exception as e:
            elapsed = time.time() - start
            self.state.record_error(stage_name, str(e), recoverable=False)
            self.state.set_stage_status(stage_name, "failed", data={"error": str(e)})
            print("[FAIL] Stage '" + stage_name + "' failed after " + str(round(elapsed, 1)) + "s: " + str(e))
            return False

    def _execute_stage(self, stage_name: str) -> dict:
        """Execute the actual work for a stage via its worker."""
        from workers import WORKER_REGISTRY
        worker_cls = WORKER_REGISTRY.get(stage_name)
        if not worker_cls:
            raise ValueError("No worker registered for stage: " + stage_name)
        worker = worker_cls(self.config.config, self.state)
        return worker.run()

    def run_pipeline(self) -> bool:
        """Run the entire pipeline (for local testing)."""
        print("Starting pipeline with " + str(self.pipeline.total_stages()) + " stages")
        if not self.pipeline.validate_dependencies():
            print("Invalid pipeline dependencies")
            return False

        layers = self.pipeline.get_execution_order()
        for i, layer in enumerate(layers):
            print("\n=== Layer " + str(i+1) + ": " + ", ".join(layer) + " ===")
            for stage_name in layer:
                success = self.run_stage(stage_name)
                if not success:
                    print("\nPipeline halted at stage: " + stage_name)
                    return False

        print("\n[OK] Pipeline completed successfully!")
        self._print_summary()
        return True

    def _print_summary(self) -> None:
        metrics = self.state.get_metrics()
        total_time = sum(v for v in metrics.values() if isinstance(v, (int, float)))
        print("\n--- Pipeline Summary ---")
        print("Total stages: " + str(self.pipeline.total_stages()))
        print("Total time: " + str(round(total_time, 1)) + "s")
        print("Errors: " + str(len(self.state.get_full_state().get("errors", []))))
        print("\nStage times:")
        for key, val in sorted(metrics.items()):
            if key.endswith("_elapsed"):
                print("  " + key + ": " + str(val) + "s")

    def export_state(self) -> str:
        return self.state.export_json()


def main():
    parser = argparse.ArgumentParser(description="AI 3D Video Generation Pipeline")
    parser.add_argument("--stage", type=str, help="Run a specific stage")
    parser.add_argument("--all", action="store_true", help="Run the entire pipeline")
    parser.add_argument("--export-state", action="store_true", help="Export pipeline state as JSON")
    parser.add_argument("--config", type=str, help="Path to config file")
    args = parser.parse_args()

    orchestrator = Orchestrator(config_path=args.config)

    if args.all:
        success = orchestrator.run_pipeline()
        sys.exit(0 if success else 1)
    elif args.stage:
        success = orchestrator.run_stage(args.stage)
        sys.exit(0 if success else 1)
    elif args.export_state:
        print(orchestrator.export_state())
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
