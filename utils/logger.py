"""
Structured logger — writes JSON logs to stdout and files.

Each log entry includes timestamp, stage, level, message, and optional
context data for downstream metric collection and debugging.
"""
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional


class PipelineLogger:
    """Structured JSON logger for the pipeline."""

    def __init__(self, stage: str = "pipeline", log_dir: Optional[str] = None):
        self.stage = stage
        self.log_dir = Path(log_dir or os.environ.get("LOG_DIR", "/tmp/pipeline_logs"))
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / f"{stage}_{int(time.time())}.log"
        self._console = logging.getLogger(stage)
        self._console.setLevel(logging.DEBUG)
        if not self._console.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
            self._console.addHandler(handler)

    def _log(self, level: str, message: str, data: Optional[Dict[str, Any]] = None) -> None:
        entry = {
            "timestamp": time.time(),
            "stage": self.stage,
            "level": level,
            "message": message,
            "data": data or {},
        }
        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

        getattr(self._console, level.lower(), self._console.info)(message)
        if data:
            self._console.debug(f"  context: {json.dumps(data)}")

    def info(self, message: str, data: Optional[Dict] = None) -> None:
        self._log("info", message, data)

    def warning(self, message: str, data: Optional[Dict] = None) -> None:
        self._log("warning", message, data)

    def error(self, message: str, data: Optional[Dict] = None) -> None:
        self._log("error", message, data)

    def debug(self, message: str, data: Optional[Dict] = None) -> None:
        self._log("debug", message, data)

    def critical(self, message: str, data: Optional[Dict] = None) -> None:
        self._log("critical", message, data)

    def get_log_path(self) -> str:
        return str(self.log_file)
