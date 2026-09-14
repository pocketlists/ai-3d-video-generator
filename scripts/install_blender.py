#!/usr/bin/env python3
"""
Install Blender — downloads and installs Blender for CI environments.

Used by GitHub Actions runners or local development to install a
specific Blender version.
"""
import os
import subprocess
import sys
import urllib.request
import tarfile


BLENDER_VERSION = "4.2.1"
BLENDER_URL = f"https://download.blender.org/release/Blender{BLENDER_VERSION.split('.')[0]}.{BLENDER_VERSION.split('.')[1]}/blender-{BLENDER_VERSION}-linux-x64.tar.xz"


def install_blender():
    """Download and install Blender."""
    install_dir = os.environ.get("BLENDER_INSTALL_DIR", "/tmp/blender")
    blender_binary = os.path.join(install_dir, "blender")

    if os.path.exists(blender_binary):
        print(f"Blender already installed at: {blender_binary}")
        result = subprocess.run([blender_binary, "--version"], capture_output=True, text=True)
        print(result.stdout)
        return blender_binary

    print(f"Installing Blender {BLENDER_VERSION}...")
    os.makedirs(install_dir, exist_ok=True)

    # Download
    archive_path = os.path.join(install_dir, "blender.tar.xz")
    print(f"Downloading from: {BLENDER_URL}")
    urllib.request.urlretrieve(BLENDER_URL, archive_path)

    # Extract
    print("Extracting...")
    subprocess.run(["tar", "xf", archive_path, "-C", install_dir,
                    "--strip-components=1"], check=True)
    os.remove(archive_path)

    # Verify
    result = subprocess.run([blender_binary, "--version"], capture_output=True, text=True)
    print(result.stdout)

    # Set environment
    print(f"\nBlender installed at: {blender_binary}")
    print(f"Add to PATH or set BLENDER_PATH={blender_binary}")

    return blender_binary


if __name__ == "__main__":
    try:
        blender_path = install_blender()
        print(f"\n✓ Blender installed successfully: {blender_path}")
    except Exception as e:
        print(f"\n✗ Failed to install Blender: {e}")
        sys.exit(1)
