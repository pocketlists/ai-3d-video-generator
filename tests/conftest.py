"""Pytest configuration — the test suite runs in PIPELINE_MODE=test.

Production-mode guards (low-poly generator blocking, template fallback
blocking, placeholder frame blocking) are verified explicitly by
tests/test_v4.py::TestProductionModeGuards using monkeypatch.
"""
import os

# Tests are TEST mode by definition — production guards verified via monkeypatch
os.environ.setdefault("PIPELINE_MODE", "test")
