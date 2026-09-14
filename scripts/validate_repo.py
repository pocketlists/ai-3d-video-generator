#!/usr/bin/env python3
"""
Repository validator — checks that all manifest files exist and are non-empty.

Runs as part of CI/CD to verify repository completeness.
"""
import os
import sys
import json
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def load_manifest():
    manifest_path = REPO_ROOT / "FILE_MANIFEST.md"
    if not manifest_path.exists():
        print("ERROR: FILE_MANIFEST.md not found!")
        return []
    with open(manifest_path) as f:
        content = f.read()
    files = []
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("- `"):
            # Extract path between backticks
            start = line.index("`") + 1
            end = line.index("`", start)
            files.append(line[start:end])
    return files


def validate_file(filepath):
    full_path = REPO_ROOT / filepath
    if not full_path.exists():
        return False, "MISSING"
    if full_path.is_file():
        if full_path.stat().st_size == 0:
            return False, "EMPTY"
        # Check for placeholder content
        with open(full_path) as f:
            content = f.read(100)
        for placeholder in ["TODO", "IMPLEMENT LATER", "PLACEHOLDER", "coming soon"]:
            if placeholder in content:
                return False, f"PLACEHOLDER: {placeholder}"
    return True, "OK"


def main():
    manifest_files = load_manifest()
    if not manifest_files:
        print("No files found in manifest!")
        return 1

    print(f"Validating {len(manifest_files)} files from FILE_MANIFEST.md...")
    print()

    all_good = True
    missing = []
    empty = []
    placeholders = []

    for filepath in manifest_files:
        ok, status = validate_file(filepath)
        icon = "✓" if ok else "✗"
        print(f"  {icon} {filepath} — {status}")
        if not ok:
            all_good = False
            if status == "MISSING":
                missing.append(filepath)
            elif status == "EMPTY":
                empty.append(filepath)
            elif status.startswith("PLACEHOLDER"):
                placeholders.append(filepath)

    print()
    print(f"{'=' * 60}")
    print(f"Results: {len(manifest_files)} files checked")
    print(f"  ✓ Valid: {len(manifest_files) - len(missing) - len(empty) - len(placeholders)}")
    print(f"  ✗ Missing: {len(missing)}")
    print(f"  ✗ Empty: {len(empty)}")
    print(f"  ✗ Placeholders: {len(placeholders)}")

    if missing:
        print(f"\nMissing files:")
        for f in missing:
            print(f"  - {f}")
    if empty:
        print(f"\nEmpty files:")
        for f in empty:
            print(f"  - {f}")
    if placeholders:
        print(f"\nPlaceholder files:")
        for f in placeholders:
            print(f"  - {f}")

    if all_good:
        print("\n✓ All files valid!")
        return 0
    else:
        print("\n✗ Repository validation failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
