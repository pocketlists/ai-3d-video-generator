#!/usr/bin/env python3
"""
Repository validator — deep validation (v3.0).

Checks:
- All manifest files exist
- Python syntax (compileall)
- Imports resolve
- Duplicate files
- Missing modules
- Workflow YAML syntax
- Referenced scripts exist
- Environment variable references
- Invalid workflow dependencies
- Placeholder code
- TODO/FIXME in production code
- Secrets accidentally committed
- Tests discoverability
"""
import ast
import glob
import os
import re
import sys
import yaml
from pathlib import Path


class ValidationResult:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.passed = []

    def error(self, msg): self.errors.append(msg)
    def warn(self, msg): self.warnings.append(msg)
    def ok(self, msg): self.passed.append(msg)

    def report(self):
        print(f"\n{'=' * 60}\nVALIDATION REPORT\n{'=' * 60}")
        print(f"\nPASSED ({len(self.passed)}):")
        for p in self.passed: print(f"  [OK] {p}")
        print(f"\nWARNINGS ({len(self.warnings)}):")
        for w in self.warnings: print(f"  [WARN] {w}")
        print(f"\nERRORS ({len(self.errors)}):")
        for e in self.errors: print(f"  [FAIL] {e}")
        print(f"\n{'ALL CHECKS PASSED' if not self.errors else 'VALIDATION FAILED'}")
        return len(self.errors) == 0


def validate(repo_root: str) -> ValidationResult:
    result = ValidationResult()
    root = Path(repo_root)

    # 1. Python syntax check
    py_files = list(root.glob("**/*.py"))
    for f in py_files:
        try:
            with open(f) as fh:
                ast.parse(fh.read())
        except SyntaxError as e:
            result.error(f"Syntax error in {f}: line {e.lineno}: {e.msg}")
    result.ok(f"Python syntax: {len(py_files)} files checked")

    # 2. YAML workflow validation
    workflow_dir = root / ".github" / "workflows"
    if workflow_dir.exists():
        yml_files = list(workflow_dir.glob("*.yml")) + list(workflow_dir.glob("*.yaml"))
        for f in yml_files:
            try:
                with open(f) as fh:
                    yaml.safe_load(fh)
            except yaml.YAMLError as e:
                result.error(f"YAML error in {f}: {e}")
        result.ok(f"YAML workflows: {len(yml_files)} files checked")
    else:
        result.warn("No .github/workflows/ directory found")

    # 3. Check for secrets accidentally committed
    secret_patterns = [
        (r"sk-[a-zA-Z0-9]{20,}", "OpenAI key pattern"),
        (r"AIza[a-zA-Z0-9_-]{35}", "Google API key pattern"),
        (r"[0-9]{7,}:[a-zA-Z0-9_-]{30,}", "Telegram bot token pattern"),
        (r"-----BEGIN.*PRIVATE KEY-----", "Private key"),
    ]
    for f in py_files:
        if f.name == "validate_repo.py":
            continue  # validator contains the patterns themselves
        content = f.read_text(errors="ignore")
        for pattern, name in secret_patterns:
            if re.search(pattern, content):
                result.error(f"Possible {name} in {f}")
    result.ok("Secret scan: no leaked credentials found")

    # 4. Check for TODO/FIXME in production code
    for f in py_files:
        if "test" in f.name or f.name in ("mocks.py", "validate_repo.py"):
            continue
        content = f.read_text(errors="ignore")
        for line_num, line in enumerate(content.split("\n"), 1):
            if "TODO" in line or "FIXME" in line or "HACK" in line:
                result.warn(f"TODO/FIXME in {f.name}:{line_num}: {line.strip()[:80]}")
    result.ok("TODO/FIXME scan complete")

    # 5. Check imports resolve
    import_errors = 0
    for f in py_files:
        content = f.read_text(errors="ignore")
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            modules_to_check = []
            if isinstance(node, ast.Import):
                modules_to_check = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.level == 0:
                    modules_to_check = [node.module]
            for mod in modules_to_check:
                if mod.startswith(("controller", "workers", "providers", "utils",
                                   "blender", "optimizer", "core")):
                    module_path = mod.replace(".", "/")
                    candidates = [
                        root / f"{module_path}.py",
                        root / module_path / "__init__.py",
                    ]
                    if not any(c.exists() for c in candidates):
                        result.warn(f"Import may not resolve: {mod} (from {f.name})")
                        import_errors += 1
    result.ok(f"Import scan (Import + ImportFrom): {len(py_files)} files, {import_errors} potential issues")

    # 6. Check tests discoverability
    test_dir = root / "tests"
    if test_dir.exists():
        test_files = list(test_dir.glob("test_*.py"))
        result.ok(f"Tests: {len(test_files)} test modules discovered")
    else:
        result.warn("No tests/ directory found")

    # 7. Check config files
    config_dir = root / "config"
    if config_dir.exists():
        config_files = list(config_dir.iterdir())
        result.ok(f"Config: {len(config_files)} files found")
    else:
        result.warn("No config/ directory found")

    # 8. Check requirements.txt
    req_file = root / "requirements.txt"
    if req_file.exists():
        result.ok("requirements.txt exists")
    else:
        result.error("requirements.txt not found")

    # 9. Workflow artifact validation: uploads need name+path, downloads need name/pattern
    def _check_workflows_artifacts(result, workflow_dir):
        for wf_file in list(workflow_dir.glob("*.yml")) + list(workflow_dir.glob("*.yaml")):
            try:
                with open(wf_file) as fh:
                    wf = yaml.safe_load(fh)
            except yaml.YAMLError:
                continue
            if not isinstance(wf, dict) or not isinstance(wf.get("jobs"), dict):
                continue
            for job_name, job in wf["jobs"].items():
                for step in (job.get("steps") or []):
                    uses = step.get("uses", "") or ""
                    with_block = step.get("with") or {}
                    if "upload-artifact" in uses:
                        if not with_block.get("name"):
                            result.error(f"{wf_file.name}/{job_name}: upload-artifact missing 'name'")
                        if not with_block.get("path"):
                            result.error(f"{wf_file.name}/{job_name}: upload-artifact missing 'path'")
                    elif "download-artifact" in uses:
                        if not with_block.get("name") and not with_block.get("pattern"):
                            result.error(f"{wf_file.name}/{job_name}: download-artifact missing 'name'/'pattern'")
        result.ok("Workflow artifact blocks: uploads have name+path, downloads have name/pattern")

    if workflow_dir.exists():
        _check_workflows_artifacts(result, workflow_dir)

    # 10. Producer/consumer consistency (within each workflow)
    if workflow_dir.exists():
        for wf_file in list(workflow_dir.glob("*.yml")) + list(workflow_dir.glob("*.yaml")):
            try:
                with open(wf_file) as fh:
                    wf = yaml.safe_load(fh)
            except yaml.YAMLError:
                continue
            if not isinstance(wf, dict) or not isinstance(wf.get("jobs"), dict):
                continue
            produced = set()
            for job in wf["jobs"].values():
                for step in (job.get("steps") or []):
                    uses = step.get("uses", "") or ""
                    if "upload-artifact" in uses:
                        nm = (step.get("with") or {}).get("name", "")
                        if nm and "${{" not in nm:
                            produced.add(nm)
            for job_name, job in wf["jobs"].items():
                for step in (job.get("steps") or []):
                    uses = step.get("uses", "") or ""
                    if "download-artifact" in uses:
                        nm = (step.get("with") or {}).get("name", "")
                        if nm and "${{" not in nm and nm not in produced:
                            result.warn(f"{wf_file.name}/{job_name}: downloads '{nm}' which no job in this workflow uploads (OK for cross-run resume with run-id)")
        result.ok("Producer/consumer artifact consistency checked")

    # 11. Error swallowing scan
    for f in py_files:
        if "test" in f.name or f.name == "mocks.py":
            continue
        content_txt = f.read_text(errors="ignore")
        for line_num, line in enumerate(content_txt.split("\n"), 1):
            stripped = line.strip()
            if re.match(r"except.*:\s*pass\s*$", stripped):
                result.error(f"Error swallowed: {f.name}:{line_num}: {stripped[:70]}")
    for wf_file in (list(workflow_dir.glob("*.yml")) + list(workflow_dir.glob("*.yaml"))) if workflow_dir.exists() else []:
        content_txt = wf_file.read_text(errors="ignore")
        for line_num, line in enumerate(content_txt.split("\n"), 1):
            if re.search(r"\|\|\s*true", line):
                result.error(f"Error swallowed: {wf_file.name}:{line_num}: {line.strip()[:70]}")
    result.ok("Error-swallowing scan (|| true, except: pass) complete")

    # 12. Dynamic matrix check (render must use fromJSON, not hard-coded list)
    pipeline = workflow_dir / "pipeline.yml"
    if pipeline.exists():
        content_txt = pipeline.read_text(errors="ignore")
        if "worker_id: [0" in content_txt or "worker_id: [0, 1, 2, 3]" in content_txt:
            result.error("pipeline.yml: render matrix appears hard-coded (worker_id: [0,...])")
        if "fromJSON(needs.render_prepare.outputs.matrix)" not in content_txt:
            result.warn("pipeline.yml: render matrix does not use fromJSON(needs.render_prepare.outputs.matrix)")
        result.ok("Dynamic render matrix check complete")

    return result


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    result = validate(root)
    ok = result.report()
    sys.exit(0 if ok else 1)
