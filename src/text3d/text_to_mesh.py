"""
text_to_mesh.py  (Bitmap → Contour(+holes) → Polygon → Mesh)

Pipeline:
  1) Render text to bitmap (Pillow)
  2) Find contours WITH holes (OpenCV RETR_CCOMP)
  3) Build shapely Polygon/MultiPolygon with interior rings
  4) Extrude to 3D mesh (trimesh)
  5) Planar UV (x,y -> u,v in [0,1])
  6) Normalize height (Y axis) for consistent sizing

Deps:
  pip install numpy pillow opencv-python shapely trimesh mapbox-earcut
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Tuple

import numpy as np
import cv2
import trimesh
from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union


# ---------------------------------------------------------
# Config
# ---------------------------------------------------------

@dataclass
class TextToMeshConfig:
    font_path: str
    font_size: int = 256
    image_size: Tuple[int, int] = (1024, 1024)  # (W, H)
    extrude_depth: float = 1.0
    threshold: int = 128
    simplify_tol: float = 0.5
    invert_y: bool = True  # convert image coords -> cartesian


# ---------------------------------------------------------
# 1) Text -> Bitmap (auto-fit to frame)
# ---------------------------------------------------------
from pathlib import Path

def _char_script(ch: str) -> str:
    o = ord(ch)
    if 0x0E00 <= o <= 0x0E7F:
        return "thai"
    if (0x3040 <= o <= 0x309F) or (0x30A0 <= o <= 0x30FF) or (0x4E00 <= o <= 0x9FFF):
        return "jp"
    return "latin"

def _pick_font_path_for_char(ch: str, primary_font_path: str) -> str:
    """
    เลือก font ต่อ 1 ตัวอักษร (ชัวร์สุด)
    - ใช้ primary_font_path ก่อน
    - ถ้าเป็น JP/TH ให้ลองฟอนต์ของภาษา (Windows Fonts)
    """
    win = Path(r"C:\Windows\Fonts")
    script = _char_script(ch)

    # เรียงลำดับความชัวร์: primary ก่อน แล้วค่อย fallback ตามภาษา
    candidates = [primary_font_path]

    if script == "jp":
        candidates += [
            str(win / "YuGothM.ttc"),
            str(win / "YuGothR.ttc"),
            str(win / "meiryo.ttc"),
            str(win / "MSGOTHIC.TTC"),
        ]
    elif script == "thai":
        candidates += [
            str(win / "LeelawUI.ttf"),
            str(win / "Leelawad.ttf"),
            str(win / "THSarabunNew.ttf"),
            str(win / "AngsanaUPC.ttf"),
        ]
    else:
        candidates += [
            str(win / "arial.ttf"),
            str(win / "calibri.ttf"),
        ]

    # เอาอันที่มีอยู่จริงตัวแรก
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return primary_font_path

def _measure_mixed_text(draw: ImageDraw.ImageDraw, text: str, font_size: int, primary_font_path: str):
    """
    วัดขนาดข้อความแบบ mixed fonts (ต่อ 1 ตัวอักษร)
    คืนค่า (total_w, total_h, min_y, max_y, runs)
    runs = list[(ch, font_obj, advance)]
    """
    font_cache = {}
    def get_font(path: str):
        key = (path, font_size)
        if key not in font_cache:
            font_cache[key] = ImageFont.truetype(path, font_size)
        return font_cache[key]

    x = 0.0
    min_y = 0.0
    max_y = 0.0
    runs = []

    for ch in text:
        if ch == "\n":
            # (โค้ดนี้ยังไม่รองรับหลายบรรทัด — ถ้าต้องการค่อยเพิ่ม)
            ch = " "
        fp = _pick_font_path_for_char(ch, primary_font_path)
        f = get_font(fp)

        # bbox ของ glyph (relative)
        bbox = f.getbbox(ch)
        # bbox: (x0, y0, x1, y1)
        if bbox:
            min_y = min(min_y, bbox[1])
            max_y = max(max_y, bbox[3])

        # advance (ความกว้างที่ควรเลื่อน)
        try:
            adv = float(f.getlength(ch))
        except Exception:
            adv = float(draw.textlength(ch, font=f))

        runs.append((ch, f, adv))
        x += adv

    total_w = x
    total_h = max_y - min_y
    return total_w, total_h, min_y, max_y, runs

import hashlib
from PIL import Image, ImageDraw, ImageFont

def _font_notdef_hash(font: ImageFont.FreeTypeFont, size: int = 64) -> str:
    """
    สร้าง signature ของ glyph .notdef (ตัวที่ใช้แทนตอน font ไม่มี glyph)
    ใช้ตรวจว่า char นั้นๆ เป็น "กล่อง" เพราะไม่มี glyph หรือเปล่า
    """
    # ใช้ private-use char ที่แทบไม่มีฟอนต์ไหนมีจริง → จะได้ .notdef แน่นอน
    ch = "\uE000"
    img = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(img)
    d.text((0, 0), ch, fill=255, font=font)
    return hashlib.md5(img.tobytes()).hexdigest()

def _char_supported(font: ImageFont.FreeTypeFont, notdef_hash: str, ch: str) -> bool:
    """
    เรนเดอร์ตัวอักษรลงภาพเล็กๆ แล้วเทียบกับ .notdef
    ถ้าเหมือนกัน → ไม่มี glyph จริง (มักเป็นกล่อง)
    """
    img = Image.new("L", (64, 64), 0)
    d = ImageDraw.Draw(img)
    d.text((0, 0), ch, fill=255, font=font)
    h = hashlib.md5(img.tobytes()).hexdigest()
    return h != notdef_hash

def _is_thai(ch: str) -> bool:
    return "\u0E00" <= ch <= "\u0E7F"


def _is_japanese(ch: str) -> bool:
    # Hiragana, Katakana, CJK Unified Ideographs (Kanji)
    return (
        ("\u3040" <= ch <= "\u309F")
        or ("\u30A0" <= ch <= "\u30FF")
        or ("\u4E00" <= ch <= "\u9FFF")
    )


def _pick_existing_font(candidates: list[str]) -> str | None:
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def text_to_bitmap(text: str, cfg: TextToMeshConfig) -> np.ndarray:
    """
    Multi-font per-character fallback (Thai/English/Japanese) + shared baseline.
    - แก้ปัญหา ญี่ปุ่นเป็นกล่อง (เลือก YuGothM.ttc ต่อ “ตัวอักษร”)
    - แก้ปัญหา ไทย/อังกฤษ/ญี่ปุ่น สูงไม่เท่ากัน (ใช้ baseline เดียว)
    - ย่อ font_size อัตโนมัติถ้าข้อความล้นภาพ
    """
    W, H = cfg.image_size

    win_fonts = r"C:\Windows\Fonts"
    jp_font_path = _pick_existing_font([
        os.path.join(win_fonts, "YuGothM.ttc"),
        os.path.join(win_fonts, "YuGothR.ttc"),
        os.path.join(win_fonts, "meiryo.ttc"),
        os.path.join(win_fonts, "MSGOTHIC.TTC"),
    ])
    thai_font_path = _pick_existing_font([
        os.path.join(win_fonts, "LeelawUI.ttf"),
        os.path.join(win_fonts, "THSarabunNew.ttf"),
        os.path.join(win_fonts, "AngsanaUPC.ttf"),
    ])

    # latin = cfg.font_path (ของเดิม) เป็น default
    latin_font_path = cfg.font_path

    # ---------- helper: layout metrics ----------
    def build_fonts(size: int):
        latin = ImageFont.truetype(latin_font_path, size)

        # ถ้าเครื่องไม่มีฟอนต์ fallback ก็ใช้ latin ไปก่อน (ยังไม่พัง)
        thai = ImageFont.truetype(thai_font_path, size) if thai_font_path else latin
        jp = ImageFont.truetype(jp_font_path, size) if jp_font_path else latin

        return latin, thai, jp

    def font_for_char(ch: str, latin, thai, jp):
        if _is_japanese(ch):
            return jp
        if _is_thai(ch):
            return thai
        return latin

    def measure(text_: str, latin, thai, jp):
        # วัด width แบบต่อ char + หาค่าสูงแบบ baseline รวม
        total_w = 0.0
        max_ascent = 0
        max_descent = 0

        for ch in text_:
            f = font_for_char(ch, latin, thai, jp)
            a, d = f.getmetrics()
            max_ascent = max(max_ascent, a)
            max_descent = max(max_descent, d)

            # ความกว้าง: ใช้ getlength ถ้ามี (Pillow ใหม่) ไม่งั้น fallback bbox
            if hasattr(f, "getlength"):
                total_w += float(f.getlength(ch))
            else:
                bx = f.getbbox(ch)
                total_w += float((bx[2] - bx[0]) if bx else 0)

        total_h = max_ascent + max_descent
        return total_w, total_h, max_ascent, max_descent

    # ---------- auto-fit font size ----------
    font_size = cfg.font_size
    max_w = W * 0.90
    max_h = H * 0.90

    while True:
        latin, thai, jp = build_fonts(font_size)
        text_w, text_h, max_ascent, max_descent = measure(text, latin, thai, jp)

        if text_w <= max_w and text_h <= max_h:
            break

        # scale down
        scale_w = max_w / text_w if text_w > 1e-6 else 1.0
        scale_h = max_h / text_h if text_h > 1e-6 else 1.0
        scale = min(scale_w, scale_h)

        new_size = int(font_size * scale)
        if new_size >= font_size:
            new_size = font_size - 1

        if new_size < 10:
            font_size = 10
            latin, thai, jp = build_fonts(font_size)
            text_w, text_h, max_ascent, max_descent = measure(text, latin, thai, jp)
            break

        font_size = new_size

    # ---------- render ----------
    img = Image.new("L", (W, H), color=0)
    draw = ImageDraw.Draw(img)

    # baseline-centered:
    # top = yb - max_ascent, bottom = yb + max_descent
    # center -> (top+bottom)/2 = H/2
    yb = (H + max_ascent - max_descent) / 2.0

    x = (W - text_w) / 2.0

    for ch in text:
        f = font_for_char(ch, latin, thai, jp)
        a, _ = f.getmetrics()

        # วาดด้วย “top-left” => y_top = baseline - ascent
        draw.text((x, yb - a), ch, fill=255, font=f)

        if hasattr(f, "getlength"):
            x += float(f.getlength(ch))
        else:
            bx = f.getbbox(ch)
            x += float((bx[2] - bx[0]) if bx else 0)

    return np.array(img)

# ---------------------------------------------------------
# 2) Bitmap -> Polygon/MultiPolygon (WITH holes)
# ---------------------------------------------------------

def _cnt_to_xy(cnt: np.ndarray, H: int, invert_y: bool) -> list[tuple[float, float]]:
    pts = cnt.reshape(-1, 2).astype(float)
    if invert_y:
        pts[:, 1] = H - pts[:, 1]
    return [(float(x), float(y)) for x, y in pts]


def _cnt_to_xy(cnt: np.ndarray, H: int) -> list[tuple[float, float]]:
    pts = cnt.reshape(-1, 2).astype(float)
    pts[:, 1] = H - pts[:, 1]  # flip Y
    return [(float(x), float(y)) for x, y in pts]


def bitmap_to_polygon(bitmap: np.ndarray, cfg: TextToMeshConfig):
    """
    Convert bitmap (white text on black) -> Polygon/MultiPolygon with holes.
    """
    mask = (bitmap > cfg.threshold).astype(np.uint8) * 255

    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    cv2.imwrite("debug_contours.png", mask)

    contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None or len(contours) == 0:
        raise ValueError("No contours found. Check bitmap/font.")

    H = bitmap.shape[0]
    hierarchy = hierarchy[0]  # (n,4): next, prev, child, parent

    polygons: list[Polygon] = []

    for idx, h in enumerate(hierarchy):
        parent = h[3]
        if parent != -1:
            continue  # only outer contours

        outer = contours[idx]
        if len(outer) < 3:
            continue

        eps = 0.005 * cv2.arcLength(outer, True)
        outer = cv2.approxPolyDP(outer, eps, True)
        shell = _cnt_to_xy(outer, H)

        holes: list[list[tuple[float, float]]] = []
        child = h[2]
        while child != -1:
            hole_cnt = contours[child]
            if len(hole_cnt) >= 3:
                eps_h = 0.005 * cv2.arcLength(hole_cnt, True)
                hole_cnt = cv2.approxPolyDP(hole_cnt, eps_h, True)
                holes.append(_cnt_to_xy(hole_cnt, H))
            child = hierarchy[child][0]  # next sibling

        poly = Polygon(shell, holes)
        if not poly.is_valid:
            poly = poly.buffer(0)

        if not poly.is_empty and poly.area > 50:
            polygons.append(poly)

    if not polygons:
        raise ValueError("No valid polygons built from contours.")

    geom = unary_union(polygons)

    if cfg.simplify_tol and cfg.simplify_tol > 0:
        geom = geom.simplify(cfg.simplify_tol, preserve_topology=True)

    return geom


# ---------------------------------------------------------
# 3) Polygon -> Mesh
# ---------------------------------------------------------

def polygon_to_extruded_mesh(poly, extrude_depth: float) -> trimesh.Trimesh:
    if poly.is_empty:
        raise ValueError("Empty polygon")

    if isinstance(poly, Polygon):
        polys = [poly]
    elif isinstance(poly, MultiPolygon):
        polys = list(poly.geoms)
    else:
        raise TypeError(f"Unsupported geometry type: {type(poly)}")

    meshes: list[trimesh.Trimesh] = []
    for p in polys:
        if p.is_empty or p.area <= 0:
            continue
        meshes.append(trimesh.creation.extrude_polygon(p, extrude_depth))

    if not meshes:
        raise ValueError("No valid polygon to extrude")

    mesh = trimesh.util.concatenate(meshes)
    mesh.vertices -= mesh.center_mass
    return mesh


def normalize_height(mesh: trimesh.Trimesh, target_height: float = 1.0) -> trimesh.Trimesh:
    ext = mesh.extents  # [x,y,z]
    h = float(ext[1])
    if h > 0:
        mesh.apply_scale(target_height / h)
    return mesh


def add_planar_uv(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    xy = mesh.vertices[:, :2]
    mn = xy.min(axis=0)
    mx = xy.max(axis=0)
    size = np.maximum(mx - mn, 1e-6)
    uv = (xy - mn) / size
    mesh.visual.uv = uv
    return mesh


# ---------------------------------------------------------
# 4) main API
# ---------------------------------------------------------

def text_to_mesh(
    text: str,
    font_path: str,
    output_path: str | None = None,
    font_size: int = 256,
    image_size: Tuple[int, int] = (1024, 1024),
    extrude_depth: float = 1.0,
    simplify_tol: float = 0.5,
    target_height: float = 1.0,
) -> trimesh.Trimesh:
    cfg = TextToMeshConfig(
        font_path=font_path,
        font_size=font_size,
        image_size=image_size,
        extrude_depth=extrude_depth,
        simplify_tol=simplify_tol,
    )

    bitmap = text_to_bitmap(text, cfg)
    Image.fromarray(bitmap).save("debug_bitmap.png")

    poly = bitmap_to_polygon(bitmap, cfg)
    mesh = polygon_to_extruded_mesh(poly, extrude_depth)

    mesh = normalize_height(mesh, target_height=target_height)
    mesh = add_planar_uv(mesh)

    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        mesh.export(output_path)
        print(f"Exported mesh to: {os.path.abspath(output_path)}")

    return mesh
