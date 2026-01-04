from __future__ import annotations

import random
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

import numpy as np
import trimesh

Mode = Literal["emboss", "engrave"]


# -----------------------------
# Config
# -----------------------------
@dataclass
class EmbedConfig:
    mode: Mode
    depth_percent: float  # percent of min(bbox)

    # sampling / fitting
    tries: int = 200
    margin: float = 0.85
    patch_radius_percent: float = 12.0
    ray_steps: int = 40
    lift_percent: float = 1.0

    # Blender (required)
    blender_exe: str = r"C:\Program Files\Blender Foundation\Blender 5.0\blender.exe"

    # Voxel fallback (recommended)
    voxel_fallback: bool = True
    voxel_pitch_percent: float = 3.0  # try 3~6 for heavy meshes

    # small push along normal for boolean stability
    eps_percent: float = 0.2  # 0.2% of min(bbox)


# -----------------------------
# Cleanup helpers
# -----------------------------
def _remove_duplicate_faces_compat(mesh: trimesh.Trimesh) -> None:
    faces = np.asarray(getattr(mesh, "faces", None))
    if faces is None or len(faces) == 0:
        return
    fs = np.sort(faces, axis=1)
    _, idx = np.unique(fs, axis=0, return_index=True)
    mask = np.zeros(len(faces), dtype=bool)
    mask[idx] = True
    mesh.update_faces(mask)


def _cleanup_mesh(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    m = mesh.copy()
    _remove_duplicate_faces_compat(m)
    if hasattr(m, "remove_degenerate_faces"):
        m.remove_degenerate_faces()
    if hasattr(m, "remove_unreferenced_vertices"):
        m.remove_unreferenced_vertices()
    if hasattr(m, "process"):
        m.process(validate=False)
    return m


def _load_glb_as_mesh(path: str | Path) -> trimesh.Trimesh:
    obj = trimesh.load(str(path), force="scene")
    if isinstance(obj, trimesh.Scene):
        dumped = obj.dump(concatenate=True)
        if isinstance(dumped, list):
            mesh = trimesh.util.concatenate(dumped)
        else:
            mesh = dumped
    elif isinstance(obj, trimesh.Trimesh):
        mesh = obj
    else:
        raise TypeError(f"Unsupported GLB load result: {type(obj)}")
    return _cleanup_mesh(mesh)


def _min_bbox_size(mesh: trimesh.Trimesh) -> float:
    ext = mesh.bounds[1] - mesh.bounds[0]
    return float(np.min(ext))


# -----------------------------
# Voxel solid fallback
# -----------------------------
def _voxel_solid_boxes(mesh: trimesh.Trimesh, pitch: float) -> trimesh.Trimesh:
    """
    Make a very robust solid by voxelizing + fill + as_boxes.
    as_boxes is blocky but tends to be manifold/solid.
    """
    m = mesh.copy()
    vg = m.voxelized(pitch).fill()
    out = vg.as_boxes()
    out = _cleanup_mesh(out)
    try:
        out.merge_vertices()
    except Exception:
        pass
    return out


# -----------------------------
# Geometry helpers
# -----------------------------
def _random_tangent_frame(n: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    n = n / (np.linalg.norm(n) + 1e-12)
    for _ in range(20):
        v = np.random.randn(3)
        v = v - np.dot(v, n) * n
        nv = np.linalg.norm(v)
        if nv > 1e-6:
            t = v / nv
            b = np.cross(n, t)
            b = b / (np.linalg.norm(b) + 1e-12)
            return t, b
    a = np.array([1.0, 0.0, 0.0])
    if abs(np.dot(a, n)) > 0.9:
        a = np.array([0.0, 1.0, 0.0])
    t = np.cross(n, a)
    t = t / (np.linalg.norm(t) + 1e-12)
    b = np.cross(n, t)
    b = b / (np.linalg.norm(b) + 1e-12)
    return t, b


def _ray_hit(mesh: trimesh.Trimesh, origin: np.ndarray, direction: np.ndarray) -> Optional[np.ndarray]:
    loc, _, _ = mesh.ray.intersects_location(
        ray_origins=np.asarray([origin], dtype=np.float64),
        ray_directions=np.asarray([direction], dtype=np.float64),
        multiple_hits=False,
    )
    if loc is None or len(loc) == 0:
        return None
    return loc[0]


def _probe_available_extent(
    mesh: trimesh.Trimesh,
    p: np.ndarray,
    n: np.ndarray,
    dir_tan: np.ndarray,
    R: float,
    steps: int,
    lift: float,
) -> float:
    step = R / max(steps, 1)
    best = 0.0
    for i in range(1, steps + 1):
        d = i * step
        q = p + dir_tan * d
        origin = q + n * lift
        hit = _ray_hit(mesh, origin, -n)
        if hit is None:
            break
        best = d
    return best


def estimate_patch_wh(
    mesh: trimesh.Trimesh,
    p: np.ndarray,
    n: np.ndarray,
    t: np.ndarray,
    b: np.ndarray,
    R: float,
    steps: int,
    lift: float,
) -> tuple[float, float]:
    tp = _probe_available_extent(mesh, p, n, t, R, steps, lift)
    tm = _probe_available_extent(mesh, p, n, -t, R, steps, lift)
    bp = _probe_available_extent(mesh, p, n, b, R, steps, lift)
    bm = _probe_available_extent(mesh, p, n, -b, R, steps, lift)
    return (tp + tm), (bp + bm)


def _center_mesh_xy_and_zero_z(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    m = mesh.copy()
    bounds = m.bounds
    center_xy = 0.5 * (bounds[0] + bounds[1])
    center_xy[2] = 0.0
    m.apply_translation(-center_xy)
    zmin = float(m.bounds[0][2])
    m.apply_translation([0.0, 0.0, -zmin])
    return m


def _scale_mesh_xy_z(mesh: trimesh.Trimesh, s_xy: float, s_z: float) -> trimesh.Trimesh:
    m = mesh.copy()
    M = np.eye(4)
    M[0, 0] = s_xy
    M[1, 1] = s_xy
    M[2, 2] = s_z
    m.apply_transform(M)
    return m


def deform_text_mesh_to_surface(
    base_mesh: trimesh.Trimesh,
    text_mesh_local: trimesh.Trimesh,
    p: np.ndarray,
    n: np.ndarray,
    t: np.ndarray,
    b: np.ndarray,
    lift: float,
    mode: Mode,
) -> trimesh.Trimesh:
    m = text_mesh_local.copy()
    v = np.asarray(m.vertices, dtype=np.float64)
    out = np.zeros_like(v)

    sign = 1.0 if mode == "emboss" else -1.0
    for i in range(len(v)):
        x, y, z = v[i]
        base = p + t * x + b * y
        origin = base + n * lift
        hit = _ray_hit(base_mesh, origin, -n)
        if hit is None:
            hit = base
        out[i] = hit + n * (sign * z)

    m.vertices = out
    return _cleanup_mesh(m)


# -----------------------------
# Boolean via Blender subprocess (GLB import/export)
# -----------------------------
_BLENDER_BOOL_SCRIPT = r"""
import bpy
import sys

def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)

def enable_addon(module_name):
    # In background factory-startup, addons may be disabled. Enable importer/exporter explicitly.
    try:
        bpy.ops.preferences.addon_enable(module=module_name)
    except Exception:
        pass

def import_glb(path):
    # glTF addon name is io_scene_gltf2
    enable_addon("io_scene_gltf2")
    bpy.ops.import_scene.gltf(filepath=path)

    meshes = [o for o in bpy.context.selected_objects if o.type == 'MESH']
    if not meshes:
        meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    if not meshes:
        raise RuntimeError("No mesh objects imported from GLB")

    # join to single mesh object
    bpy.ops.object.select_all(action='DESELECT')
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()

    obj = bpy.context.view_layer.objects.active
    return obj

def make_active(obj):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

def apply_scale(obj):
    make_active(obj)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

def recalc_normals(obj):
    make_active(obj)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode='OBJECT')

def boolean_apply(base, tool, op):
    make_active(base)
    mod = base.modifiers.new(name="Boolean", type='BOOLEAN')
    mod.operation = op  # 'UNION' or 'DIFFERENCE'
    try:
        mod.solver = 'EXACT'
    except Exception:
        pass
    mod.object = tool
    bpy.ops.object.modifier_apply(modifier=mod.name)

def export_glb(obj, path):
    enable_addon("io_scene_gltf2")
    make_active(obj)
    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format='GLB',
        use_selection=True
    )

def main():
    argv = sys.argv
    if "--" not in argv:
        raise SystemExit("Missing -- args: base.glb tool.glb out.glb OP")
    idx = argv.index("--")
    args = argv[idx+1:]
    base_path, tool_path, out_path, op = args[0], args[1], args[2], args[3]

    clear_scene()

    base = import_glb(base_path)
    tool = import_glb(tool_path)

    apply_scale(base)
    apply_scale(tool)

    recalc_normals(base)
    recalc_normals(tool)

    boolean_apply(base, tool, op)

    # cleanup tool
    try:
        bpy.data.objects.remove(tool, do_unlink=True)
    except Exception:
        pass

    export_glb(base, out_path)

if __name__ == "__main__":
    main()
"""


def _run_blender_boolean(cfg: EmbedConfig, base: trimesh.Trimesh, tool: trimesh.Trimesh, mode: Mode) -> trimesh.Trimesh:
    blender_exe = Path(cfg.blender_exe)
    if not blender_exe.exists():
        raise FileNotFoundError(f"blender.exe not found: {cfg.blender_exe}")

    op = "UNION" if mode == "emboss" else "DIFFERENCE"

    with tempfile.TemporaryDirectory(prefix="text3d_blender_bool_") as td:
        td = Path(td)
        base_glb = td / "base.glb"
        tool_glb = td / "tool.glb"
        out_glb = td / "out.glb"
        script_py = td / "bool.py"

        # export base/tool as GLB (single mesh scene)
        trimesh.Scene(base).export(base_glb)
        trimesh.Scene(tool).export(tool_glb)

        script_py.write_text(_BLENDER_BOOL_SCRIPT, encoding="utf-8")

        cmd = [
            str(blender_exe),
            "--background",
            "--factory-startup",
            "--python",
            str(script_py),
            "--",
            str(base_glb),
            str(tool_glb),
            str(out_glb),
            op,
        ]

        proc = subprocess.run(cmd, capture_output=True, text=True)
        if (proc.returncode != 0) or (not out_glb.exists()):
            raise RuntimeError(
                "Blender boolean subprocess failed.\n"
                f"Return code: {proc.returncode}\n"
                f"STDOUT:\n{proc.stdout}\n"
                f"STDERR:\n{proc.stderr}\n"
            )

        out = trimesh.load(out_glb, force="scene")
        if isinstance(out, trimesh.Scene):
            dumped = out.dump(concatenate=True)
            if isinstance(dumped, list):
                out_mesh = trimesh.util.concatenate(dumped)
            else:
                out_mesh = dumped
        elif isinstance(out, trimesh.Trimesh):
            out_mesh = out
        else:
            raise RuntimeError(f"Unexpected blender output type: {type(out)}")

        return _cleanup_mesh(out_mesh)


# -----------------------------
# Main API
# -----------------------------
def embed_text_on_glb(
    *,
    base_glb_path: str | Path,
    text_mesh_generator,
    text: str,
    font_path: str,
    cfg: EmbedConfig,
    seed: Optional[int] = None,
) -> Path:
    if seed is not None:
        random.seed(seed)
        np.random.seed(seed)

    base = _load_glb_as_mesh(base_glb_path)

    L = _min_bbox_size(base)
    depth_world = (cfg.depth_percent / 100.0) * L
    R = (cfg.patch_radius_percent / 100.0) * L
    lift = (cfg.lift_percent / 100.0) * L
    eps = (cfg.eps_percent / 100.0) * L

    # Build planar text mesh (one line)
    text_mesh = text_mesh_generator(
        text=text,
        font_path=font_path,
        extrude_depth=1.0,
        target_height=1.0,
    )
    text_mesh = _cleanup_mesh(_center_mesh_xy_and_zero_z(text_mesh))

    bnd = text_mesh.bounds
    w2d = float(bnd[1][0] - bnd[0][0])
    h2d = float(bnd[1][1] - bnd[0][1])
    if w2d < 1e-9 or h2d < 1e-9:
        raise ValueError("Text mesh has near-zero size; check font/text.")

    for _attempt in range(cfg.tries):
        pts, face_idx = trimesh.sample.sample_surface(base, 1)
        p = pts[0]
        fi = int(face_idx[0])
        n = base.face_normals[fi]
        n = n / (np.linalg.norm(n) + 1e-12)

        t, bvec = _random_tangent_frame(n)
        W, H = estimate_patch_wh(base, p, n, t, bvec, R=R, steps=cfg.ray_steps, lift=lift)

        s_xy = cfg.margin * min(W / w2d, H / h2d)
        if not np.isfinite(s_xy) or s_xy <= 1e-6:
            continue

        text_scaled = _scale_mesh_xy_z(text_mesh, s_xy=s_xy, s_z=depth_world)

        tool = deform_text_mesh_to_surface(
            base_mesh=base,
            text_mesh_local=text_scaled,
            p=p,
            n=n,
            t=t,
            b=bvec,
            lift=lift,
            mode=cfg.mode,
        )

        # tiny push for stability
        tool = tool.copy()
        tool.apply_translation(n * (eps if cfg.mode == "emboss" else -eps))

        # 1) Try blender boolean directly
        try:
            result = _run_blender_boolean(cfg, base, tool, cfg.mode)
        except Exception as e1:
            if not cfg.voxel_fallback:
                raise RuntimeError(f"Blender boolean failed (no voxel fallback). Error:\n{e1}") from e1

            # 2) Voxel solid fallback (as_boxes) then blender boolean again
            pitch = (cfg.voxel_pitch_percent / 100.0) * L
            base_v = _voxel_solid_boxes(base, pitch)
            tool_v = _voxel_solid_boxes(tool, pitch)

            try:
                result = _run_blender_boolean(cfg, base_v, tool_v, cfg.mode)
            except Exception as e2:
                raise RuntimeError(
                    "Blender boolean failed even after voxel solid fallback.\n"
                    f"- direct error:\n{e1}\n"
                    f"- voxel error:\n{e2}\n"
                    f"Try increasing voxel_pitch_percent (e.g. 4.0, 5.0, 6.0)."
                ) from e2

        out_dir = Path("outputs") / "engrave_emboss"
        out_dir.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^0-9a-zA-Zก-ฮะ-๙一-龯ぁ-んァ-ンー]+", "_", text).strip("_")
        out_path = out_dir / f"{Path(base_glb_path).stem}_{cfg.mode}_{cfg.depth_percent:g}pct_{safe}.glb"
        result.export(out_path, file_type="glb")
        return out_path

    raise RuntimeError(f"Failed to find a placement that fits after {cfg.tries} tries.")
