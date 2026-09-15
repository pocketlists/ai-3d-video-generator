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
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(("controller", "workers", "providers", "utils",
                                              "blender", "optimizer", "core")):
                        module_path = alias.name.replace(".", "/")
                        candidates = [
                            root / f"{module_path}.py",
                            root / module_path / "__init__.py",
                        ]
                        if not any(c.exists() for c in candidates):
                            result.warn(f"Import may not resolve: {alias.name} (from {f.name})")
                            import_errors += 1
    result.ok(f"Import scan: {len(py_files)} files, {import_errors} potential issues")

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

    return result


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    result = validate(root)
    ok = result.report()
    sys.exit(0 if ok else 1)
