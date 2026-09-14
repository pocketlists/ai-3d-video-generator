"""Base worker class — shared interface for all pipeline workers.

Every worker inherits from BaseWorker and implements the run() method.
Workers receive config and state, execute their stage, and return results.
"""
import abc
import time
from typing import Any, Dict, Optional

from controller.state_manager import StateManager
from utils.logger import PipelineLogger
from utils.telemetry import TelemetryCollector


class BaseWorker(abc.ABC):
    """Abstract base class for all pipeline workers."""

    stage_name: str = "base"

    def __init__(self, config: Dict[str, Any], state: Optional[StateManager] = None):
        self.config = config
        self.state = state
        self.logger = PipelineLogger(self.stage_name)
        self.telemetry = TelemetryCollector()

    @abc.abstractmethod
    def run(self) -> Dict[str, Any]:
        """Execute the worker's task. Returns result dict."""
        ...

    def pre_run(self) -> bool:
        """Validate prerequisites before running. Override for custom checks."""
        self.logger.info(f"Starting stage: {self.stage_name}")
        return True

    def post_run(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Post-processing after run completes."""
        self.logger.info(f"Completed stage: {self.stage_name}")
        return result

    def execute(self) -> Dict[str, Any]:
        """Full execution lifecycle: pre_run -> run -> post_run."""
        if not self.pre_run():
            return {"status": "skipped", "stage": self.stage_name}

        start = time.time()
        try:
            result = self.run()
            elapsed = time.time() - start
            result["elapsed_sec"] = round(elapsed, 2)
            result["stage"] = self.stage_name
            result["status"] = "success"

            if self.state:
                self.state.set_stage_status(self.stage_name, "completed", result)
            self.telemetry.record_stage_metrics(self.stage_name, elapsed, True, result)

            return self.post_run(result)
        except Exception as e:
            elapsed = time.time() - start
            self.logger.error(f"Stage {self.stage_name} failed: {e}")
            if self.state:
                self.state.record_error(self.stage_name, str(e), recoverable=False)
                self.state.set_stage_status(self.stage_name, "failed", {"error": str(e)})
            self.telemetry.record_stage_metrics(self.stage_name, elapsed, False, {"error": str(e)})
            return {"status": "error", "stage": self.stage_name, "error": str(e),
                    "elapsed_sec": round(elapsed, 2)}
