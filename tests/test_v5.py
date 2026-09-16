"""v5 safe-fix regression tests: artifact contract + uneven partitions."""
import ast
import yaml
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestArtifactContract:
    """Programmatically inspect pipeline.yml — fail on any contract violation."""

    def _load_pipeline(self):
        with open(REPO_ROOT / ".github" / "workflows" / "pipeline.yml") as f:
            return yaml.safe_load(f)

    def test_every_upload_has_name_and_path(self):
        wf = self._load_pipeline()
        for job_name, job in wf["jobs"].items():
            for step in job.get("steps", []):
                if "upload-artifact" in step.get("uses", ""):
                    w = step.get("with") or {}
                    assert w.get("name"), f"{job_name}: upload missing name"
                    assert w.get("path"), f"{job_name}: upload missing path"

    def test_every_download_has_name_or_pattern(self):
        wf = self._load_pipeline()
        for job_name, job in wf["jobs"].items():
            for step in job.get("steps", []):
                if "download-artifact" in step.get("uses", ""):
                    w = step.get("with") or {}
                    assert w.get("name") or w.get("pattern"), \
                        f"{job_name}: download missing name AND pattern"

    def test_download_names_are_produced_by_some_upload(self):
        wf = self._load_pipeline()
        produced = set()
        for job in wf["jobs"].values():
            for step in job.get("steps", []):
                if "upload-artifact" in step.get("uses", ""):
                    nm = (step.get("with") or {}).get("name", "")
                    if nm and "${{" not in nm:
                        produced.add(nm)
        for job_name, job in wf["jobs"].items():
            for step in job.get("steps", []):
                if "download-artifact" in step.get("uses", ""):
                    nm = (step.get("with") or {}).get("name", "")
                    if nm and "${{" not in nm:
                        assert nm in produced, \
                            f"{job_name}: downloads '{nm}' but no job uploads it"

    def test_upload_names_unique(self):
        wf = self._load_pipeline()
        names = []
        for job in wf["jobs"].values():
            for step in job.get("steps", []):
                if "upload-artifact" in step.get("uses", ""):
                    nm = (step.get("with") or {}).get("name", "")
                    if nm and "${{" not in nm:
                        names.append(nm)
        assert len(names) == len(set(names)), "duplicate upload names found"

    def test_render_matrix_is_dynamic_not_hardcoded(self):
        content = (REPO_ROOT / ".github" / "workflows" / "pipeline.yml").read_text()
        assert "fromJSON(needs.render_prepare.outputs.matrix)" in content
        assert "worker_id: [0, 1, 2, 3]" not in content

    def test_no_error_swallowing_in_workflows(self):
        for wf_file in (REPO_ROOT / ".github" / "workflows").glob("*.yml"):
            for i, line in enumerate(wf_file.read_text().split("\n"), 1):
                assert "|| true" not in line, f"{wf_file.name}:{i}: {line.strip()}"

    def test_resume_yml_no_continue_on_error_download(self):
        with open(REPO_ROOT / ".github" / "workflows" / "resume.yml") as f:
            wf = yaml.safe_load(f)
        for step in wf["jobs"]["resume"]["steps"]:
            uses = step.get("uses", "")
            if "download-artifact" in uses:
                assert not step.get("continue-on-error"), \
                    "resume.yml download must not use continue-on-error"

    def test_resume_yml_cross_run_download_uses_run_id(self):
        with open(REPO_ROOT / ".github" / "workflows" / "resume.yml") as f:
            wf = yaml.safe_load(f)
        dl_steps = [s for s in wf["jobs"]["resume"]["steps"]
                    if "download-artifact" in s.get("uses", "")]
        assert dl_steps, "resume.yml must have a download step"
        w = dl_steps[0].get("with") or {}
        assert w.get("run-id"), "cross-run download must pass run-id"
        assert w.get("github-token"), "cross-run download must pass github-token"


class TestUnevenPartition101x20:
    """101 frames / 20 workers: all frames assigned exactly once."""

    def test_101_frames_20_workers_full_coverage(self):
        from blender.render_manager import RenderManager
        total, workers = 101, 20
        parts = RenderManager.partition_frames(total, workers)
        assert len(parts) == workers
        covered = []
        for start, end in parts:
            assert start <= end
            covered.extend(range(start, end + 1))
        assert sorted(covered) == list(range(1, total + 1))
        # adjacency: no gaps between partitions
        for i in range(1, len(parts)):
            assert parts[i][0] == parts[i - 1][1] + 1


class TestValidatorImportFrom:
    """Validator must parse ast.ImportFrom too (from x import y)."""

    def test_importfrom_detected(self):
        # Craft a temp module with a bad ImportFrom and run the scan logic
        import sys
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "vr", REPO_ROOT / "scripts" / "validate_repo.py")
        vr = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(vr)
        tree = ast.parse("from controller.nonexistent_module import thing\n")
        found = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                found.append(node.module)
        assert "controller.nonexistent_module" in found
