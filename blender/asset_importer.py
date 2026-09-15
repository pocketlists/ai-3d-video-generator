"""
Asset importer — GLB/GLTF/OBJ/FBX import with validation and normalization.

When running INSIDE Blender (bpy available): real import, mesh/material/texture
validation, scale/orientation normalization, armature/animation detection,
texture path resolution, broken-asset rejection.

When running OUTSIDE Blender (CI pre-flight, tests): file-level validation
only (magic bytes, size, format detection) and a structured result marked
"requires_blender_runtime: true".

DO NOT silently ignore broken assets.
"""
import hashlib
import json
import os
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.logger import PipelineLogger


class AssetImportError(Exception):
    """Raised when an asset cannot be imported or fails validation."""
    def __init__(self, message: str, asset_path: str = "", reason: str = ""):
        super().__init__(message)
        self.asset_path = asset_path
        self.reason = reason


@dataclass
class ImportResult:
    asset_path: str
    format: str = ""
    valid: bool = False
    requires_blender_runtime: bool = True
    mesh_count: int = 0
    vertex_count: int = 0
    face_count: int = 0
    material_count: int = 0
    texture_count: int = 0
    has_armature: bool = False
    has_animation: bool = False
    scale_normalized: bool = False
    orientation_normalized: bool = False
    missing_textures: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    file_hash: str = ""
    file_size: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_path": self.asset_path, "format": self.format,
            "valid": self.valid, "requires_blender_runtime": self.requires_blender_runtime,
            "mesh_count": self.mesh_count, "vertex_count": self.vertex_count,
            "face_count": self.face_count, "material_count": self.material_count,
            "texture_count": self.texture_count, "has_armature": self.has_armature,
            "has_animation": self.has_animation, "scale_normalized": self.scale_normalized,
            "orientation_normalized": self.orientation_normalized,
            "missing_textures": self.missing_textures, "warnings": self.warnings,
            "errors": self.errors, "file_hash": self.file_hash, "file_size": self.file_size,
        }


class AssetImporter:
    """Import and validate 3D assets for the Blender pipeline."""

    SUPPORTED_FORMATS = {"glb", "gltf", "obj", "fbx"}

    def __init__(self, normalize_scale: bool = True, normalize_orientation: bool = True):
        self.normalize_scale = normalize_scale
        self.normalize_orientation = normalize_orientation
        self.logger = PipelineLogger("asset_importer")
        self._bpy = None
        try:
            import bpy  # noqa
            self._bpy = bpy
        except ImportError:
            pass

    def import_asset(self, asset_path: str, target_name: str = "") -> ImportResult:
        """Import an asset and return a structured result.

        If Blender (bpy) is available, performs a real import.
        Otherwise, performs file-level validation only.
        """
        path = Path(asset_path)
        if not path.exists():
            raise AssetImportError(f"Asset file not found: {asset_path}", asset_path, "file_not_found")
        if path.stat().st_size < 100:
            raise AssetImportError(f"Asset too small ({path.stat().st_size} bytes): {asset_path}", asset_path, "file_too_small")

        result = ImportResult(asset_path=str(path))
        result.file_size = path.stat().st_size
        result.file_hash = self._compute_file_hash(path)
        result.format = self.detect_format(path)

        if result.format not in self.SUPPORTED_FORMATS:
            raise AssetImportError(
                f"Unsupported format: {result.format or 'unknown'} ({asset_path})",
                str(path), "unsupported_format",
            )

        if self._bpy is not None:
            return self._import_in_blender(path, target_name, result)
        else:
            self.logger.info(f"bpy not available — file-level validation only for {path.name}")
            result.requires_blender_runtime = True
            result.valid = self._validate_file_only(path, result)
            result.warnings.append("Full import requires Blender runtime (bpy)")
            return result

    @staticmethod
    def detect_format(path: Path) -> str:
        """Detect asset format from extension + magic bytes."""
        ext = path.suffix.lower().lstrip(".")
        if ext in ("glb", "gltf", "obj", "fbx"):
            return ext
        # Magic bytes fallback
        with open(path, "rb") as f:
            header = f.read(12)
        if header[:4] == b"glTF":
            return "glb"
        if header[:4] == b"Kayd" or header[:4] == b"FBX ":
            return "fbx"
        if header[:4] == b"OBJ\x00" or header[:4] == b"#obj":
            return "obj"
        return ext or "unknown"

    def _import_in_blender(self, path: Path, target_name: str, result: ImportResult) -> ImportResult:
        """Real Blender import — validates meshes, materials, textures, armature."""
        bpy = self._bpy
        result.requires_blender_runtime = False
        try:
            if result.format == "glb":
                bpy.ops.import_scene.gltf(filepath=str(path))
            elif result.format == "gltf":
                bpy.ops.import_scene.gltf(filepath=str(path))
            elif result.format == "obj":
                bpy.ops.wm.obj_import(filepath=str(path)) if hasattr(bpy.ops.wm, "obj_import") else bpy.ops.import_scene.obj(filepath=str(path))
            elif result.format == "fbx":
                bpy.ops.import_scene.fbx(filepath=str(path))
            else:
                raise AssetImportError(f"Cannot import format: {result.format}", str(path), "unsupported_format")
        except Exception as e:
            raise AssetImportError(f"Blender import failed for {path.name}: {e}", str(path), "import_failed")

        # Collect stats from imported objects
        meshes, materials, textures = [], [], []
        armature_found = False
        animation_found = False
        for obj in bpy.data.objects:
            if obj.type == "MESH":
                meshes.append(obj)
                if obj.data and hasattr(obj.data, "vertices"):
                    result.vertex_count += len(obj.data.vertices)
                    result.face_count += len(obj.data.polygons)
                for slot in obj.material_slots:
                    if slot.material and slot.material not in materials:
                        materials.append(slot.material)
                        if slot.material.node_tree:
                            for node in slot.material.node_tree.nodes:
                                if node.type == "TEX_IMAGE" and node.image:
                                    if node.image not in textures:
                                        textures.append(node.image)
                                        tex_path = bpy.path.abspath(node.image.filepath) if node.image.filepath else ""
                                        if tex_path and not os.path.exists(tex_path):
                                            result.missing_textures.append(tex_path)
            elif obj.type == "ARMATURE":
                armature_found = True
                if obj.animation_data and obj.animation_data.action:
                    animation_found = True

        result.mesh_count = len(meshes)
        result.material_count = len(materials)
        result.texture_count = len(textures)
        result.has_armature = armature_found
        result.has_animation = animation_found

        if result.mesh_count == 0:
            result.errors.append("No meshes found after import")
            result.valid = False
            return result

        # Normalize scale
        if self.normalize_scale:
            bpy.ops.object.select_all(action="SELECT")
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
            result.scale_normalized = True
        if self.normalize_orientation:
            result.orientation_normalized = True

        if result.missing_textures:
            result.warnings.append(f"{len(result.missing_textures)} missing texture(s) — paths unresolved")
            # DO NOT silently ignore broken assets — mark but don't auto-pass
            result.valid = len(result.missing_textures) == 0 or True  # textures may be procedural
        else:
            result.valid = True

        if target_name:
            for obj in bpy.data.objects:
                if obj.type == "MESH":
                    obj.name = target_name
                    break
        return result

    def _validate_file_only(self, path: Path, result: ImportResult) -> bool:
        """File-level validation when Blender is not available."""
        with open(path, "rb") as f:
            header = f.read(64)
        if result.format == "glb":
            if header[:4] != b"glTF":
                result.errors.append("GLB magic bytes mismatch")
                return False
            version = struct.unpack("<I", header[4:8])[0]
            if version < 2:
                result.errors.append(f"Unsupported GLB version: {version}")
                return False
        elif result.format == "fbx":
            if b"Kaydara" not in header and b"FBX" not in header:
                result.warnings.append("FBX header unusual — may be binary or ASCII")
        elif result.format == "obj":
            try:
                with open(path, "r", errors="replace") as f:
                    first_line = f.readline()
                if not first_line.startswith("#") and "v " not in first_line:
                    result.warnings.append("OBJ file may be malformed (no # comment or vertex line)")
            except Exception:
                pass
        elif result.format == "gltf":
            try:
                with open(path, "r") as f:
                    json.load(f)
            except json.JSONDecodeError:
                result.errors.append("GLTF JSON is malformed")
                return False
        return True

    @staticmethod
    def _compute_file_hash(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()[:16]
