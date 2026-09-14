"""Tests for asset collection and manifest management."""
import json
import os
import tempfile
import pytest

from workers.asset_worker import AssetWorker


def test_asset_worker_initialization():
    worker = AssetWorker({"prompt": "test"})
    assert worker.stage_name == "asset_collection"


def test_asset_worker_build_manifest():
    worker = AssetWorker({"prompt": "test"})
    breakdown = {
        "shots": [
            {
                "scene_id": 1,
                "characters": [{"name": "hero"}],
                "environment": {"type": "outdoor"},
                "props": [{"name": "crate", "type": "box"}],
            }
        ]
    }
    manifest = worker._build_manifest(breakdown)
    assert manifest["summary"]["characters"] == 1
    assert manifest["summary"]["environments"] == 1
    assert manifest["summary"]["props"] == 1
    assert manifest["characters"][0]["name"] == "hero"


def test_asset_worker_empty_breakdown():
    worker = AssetWorker({"prompt": "test"})
    manifest = worker._build_manifest({"shots": []})
    assert manifest["summary"]["total"] == 3  # just audio


def test_artifact_store():
    from utils.artifact_store import ArtifactStore
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ArtifactStore(tmpdir)
        # Create a test file
        test_file = os.path.join(tmpdir, "test.txt")
        with open(test_file, "w") as f:
            f.write("test content")

        stored_path = store.store("my_artifact", test_file)
        assert os.path.exists(stored_path)
        assert store.has_artifact("my_artifact")

        retrieved = store.retrieve("my_artifact")
        assert retrieved == stored_path

        assert "my_artifact" in store.list_artifacts()

        info = store.get_artifact_info("my_artifact")
        assert info is not None
        assert info["size_bytes"] > 0
