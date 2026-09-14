"""
Low-poly mesh generator — creates procedural low-poly geometry.

Generates characters, environments, and props as low-poly meshes
suitable for fast CPU rendering while maintaining visual appeal.
"""
import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class MeshData:
    """Simple mesh representation (vertices, faces)."""
    vertices: List[Tuple[float, float, float]] = field(default_factory=list)
    faces: List[List[int]] = field(default_factory=list)
    name: str = "mesh"

    def vertex_count(self) -> int:
        return len(self.vertices)

    def face_count(self) -> int:
        return len(self.faces)

    def to_dict(self) -> dict:
        return {"name": self.name, "vertices": self.vertices, "faces": self.faces}

class LowPolyGenerator:
    """Generate low-poly meshes for the pipeline."""

    def __init__(self, seed: Optional[int] = None, max_vertices: int = 500):
        self.rng = random.Random(seed)
        self.max_vertices = max_vertices

    def generate_character(self, name: str = "character") -> MeshData:
        """Generate a simple low-poly humanoid character."""
        verts: List[Tuple[float, float, float]] = []
        faces: List[List[int]] = []

        # Head (icosphere-like, very simplified)
        head_center = (0, 0, 1.6)
        r = 0.25
        head_verts = []
        for i in range(6):
            theta = self.rng.uniform(0, 2 * math.pi)
            phi = self.rng.uniform(0, math.pi)
            v = (
                head_center[0] + r * math.sin(phi) * math.cos(theta),
                head_center[1] + r * math.sin(phi) * math.sin(theta),
                head_center[2] + r * math.cos(phi),
            )
            head_verts.append(len(verts))
            verts.append(v)
        # simple face fan
        for i in range(1, len(head_verts) - 1):
            faces.append([head_verts[0], head_verts[i], head_verts[i + 1]])

        # Body (box)
        body_h, body_w, body_d = 0.7, 0.35, 0.2
        body_center = (0, 0, 0.9)
        bv = []
        for dx in [-body_w, body_w]:
            for dy in [-body_d, body_d]:
                for dz in [-body_h / 2, body_h / 2]:
                    bv.append(len(verts))
                    verts.append((body_center[0] + dx, body_center[1] + dy, body_center[2] + dz))
        # box faces (quads)
        faces.append([bv[0], bv[1], bv[3], bv[2]])
        faces.append([bv[4], bv[5], bv[7], bv[6]])
        faces.append([bv[0], bv[1], bv[5], bv[4]])
        faces.append([bv[2], bv[3], bv[7], bv[6]])
        faces.append([bv[0], bv[2], bv[6], bv[4]])
        faces.append([bv[1], bv[3], bv[7], bv[5]])

        # Legs (two boxes)
        for offset_x in [-0.12, 0.12]:
            for dz in [0, 0.45]:
                pass  # simplified
            leg_center = (offset_x, 0, 0.3)
            lv = []
            for dx in [-0.08, 0.08]:
                for dy in [-0.08, 0.08]:
                    for dz in [-0.3, 0.0]:
                        lv.append(len(verts))
                        verts.append((leg_center[0] + dx, leg_center[1] + dy, leg_center[2] + dz))
            faces.append([lv[0], lv[1], lv[3], lv[2]])
            faces.append([lv[4], lv[5], lv[7], lv[6]])

        return MeshData(vertices=verts, faces=faces, name=name)

    def generate_environment(self, env_type: str = "outdoor") -> MeshData:
        """Generate a low-poly environment ground plane with features."""
        verts: List[Tuple[float, float, float]] = []
        faces: List[List[int]] = []

        # Ground plane with slight variation
        grid_size = 10
        cell = 1.0
        grid = {}
        for x in range(grid_size):
            for y in range(grid_size):
                z = self.rng.uniform(-0.05, 0.05)  # gentle terrain variation
                grid[(x, y)] = len(verts)
                verts.append((x * cell - grid_size * cell / 2,
                              y * cell - grid_size * cell / 2, z))

        # Create quads
        for x in range(grid_size - 1):
            for y in range(grid_size - 1):
                faces.append([
                    grid[(x, y)], grid[(x + 1, y)],
                    grid[(x + 1, y + 1)], grid[(x, y + 1)]
                ])

        # Add a few low-poly trees
        for _ in range(5):
            tx = self.rng.uniform(-4, 4)
            ty = self.rng.uniform(-4, 4)
            # trunk
            trunk_base = len(verts)
            verts.extend([(tx - 0.05, ty - 0.05, 0), (tx + 0.05, ty - 0.05, 0),
                          (tx + 0.05, ty + 0.05, 0), (tx - 0.05, ty + 0.05, 0),
                          (tx - 0.05, ty - 0.05, 0.5), (tx + 0.05, ty - 0.05, 0.5),
                          (tx + 0.05, ty + 0.05, 0.5), (tx - 0.05, ty + 0.05, 0.5)])
            faces.append([trunk_base, trunk_base + 1, trunk_base + 5, trunk_base + 4])
            faces.append([trunk_base + 2, trunk_base + 3, trunk_base + 7, trunk_base + 6])
            # foliage (cone-like)
            foliage_base = len(verts)
            h = 1.2
            for i in range(5):
                theta = i * 2 * math.pi / 5
                verts.append((tx + 0.3 * math.cos(theta), ty + 0.3 * math.sin(theta), 0.5 + h * 0.3))
            verts.append((tx, ty, 0.5 + h))
            top = len(verts) - 1
            for i in range(5):
                faces.append([foliage_base + i, foliage_base + (i + 1) % 5, top])

        return MeshData(vertices=verts, faces=faces, name=f"env_{env_type}")

    def generate_prop(self, prop_type: str = "box") -> MeshData:
        """Generate a simple low-poly prop."""
        verts: List[Tuple[float, float, float]] = []
        faces: List[List[int]] = []

        if prop_type == "box":
            s = 0.2
            for dx in [-s, s]:
                for dy in [-s, s]:
                    for dz in [-s, s]:
                        verts.append((dx, dy, dz))
            faces = [
                [0, 1, 3, 2], [4, 5, 7, 6], [0, 1, 5, 4],
                [2, 3, 7, 6], [0, 2, 6, 4], [1, 3, 7, 5]
            ]
        elif prop_type == "cylinder":
            r, h, segments = 0.15, 0.3, 8
            for dz in [0, h]:
                for i in range(segments):
                    theta = i * 2 * math.pi / segments
                    verts.append((r * math.cos(theta), r * math.sin(theta), dz))
            for i in range(segments):
                ni = (i + 1) % segments
                faces.append([i, ni, ni + segments, i + segments])
            faces.append(list(range(segments)))
            faces.append(list(range(segments, 2 * segments))[::-1])
        elif prop_type == "sphere":
            r, segments, rings = 0.2, 8, 6
            for ring in range(1, rings):
                phi = ring * math.pi / rings
                for seg in range(segments):
                    theta = seg * 2 * math.pi / segments
                    verts.append((r * math.sin(phi) * math.cos(theta),
                                  r * math.sin(phi) * math.sin(theta),
                                  r * math.cos(phi)))
            verts.append((0, 0, r))  # top
            verts.append((0, 0, -r))  # bottom
            top_idx = len(verts) - 2
            bot_idx = len(verts) - 1
            for ring in range(rings - 2):
                for seg in range(segments):
                    ni = (seg + 1) % segments
                    faces.append([ring * segments + seg, ring * segments + ni,
                                  (ring + 1) * segments + ni, (ring + 1) * segments + seg])
            for seg in range(segments):
                ni = (seg + 1) % segments
                faces.append([top_idx, seg, ni])
                faces.append([bot_idx, (rings - 2) * segments + ni, (rings - 2) * segments + seg])

        return MeshData(vertices=verts, faces=faces, name=f"prop_{prop_type}")

    def optimize(self, mesh: MeshData, target_faces: int = 200) -> MeshData:
        """Simple mesh decimation — reduces face count if above target."""
        if mesh.face_count() <= target_faces:
            return mesh
        # Calculate step to get close to target, then slice
        step = max(1, (mesh.face_count() + target_faces - 1) // target_faces)
        mesh.faces = mesh.faces[::step]
        # If still above target, take first N
        if len(mesh.faces) > target_faces:
            mesh.faces = mesh.faces[:target_faces]
        return mesh
