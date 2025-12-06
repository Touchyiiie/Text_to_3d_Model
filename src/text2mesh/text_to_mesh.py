"""
text_to_mesh.py  (Bitmap → Contour → Mesh)

Pipeline:
    1) วาดข้อความลงบน bitmap (Pillow)
    2) ใช้ OpenCV หา contour จากภาพขาวดำ
    3) แปลง contour เป็น shapely Polygon
    4) extrude เป็น 3D mesh ด้วย trimesh
    5) ใส่ planar UV ง่าย ๆ (x,y -> u,v ∈ [0,1])

Dependencies (ติดตั้งใน venv แล้ว):
    pip install numpy pillow opencv-python shapely trimesh mapbox-earcut
"""

import os
from dataclasses import dataclass
from typing import Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import cv2
from shapely.geometry import Polygon
from shapely.ops import unary_union
import trimesh


# ---------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------

@dataclass
class TextToMeshConfig:
    font_path: str
    font_size: int = 256                  # ขนาดฟอนต์ (ยิ่งใหญ่ รายละเอียดยิ่งดี)
    image_size: Tuple[int, int] = (1024, 1024)   # ขนาด bitmap (W, H)
    extrude_depth: float = 1.0            # ความหนาในแกน Z
    threshold: int = 128                  # เกณฑ์แยกดำ/ขาว
    simplify_tol: float = 1.0             # tolerance ของ simplify polygon


# ---------------------------------------------------------
# 1) Text → Bitmap
# ---------------------------------------------------------

def text_to_bitmap(text: str, cfg: TextToMeshConfig) -> np.ndarray:
    """
    วาดข้อความลงบน bitmap mode 'L' (grayscale, 0-255)
    และถ้าตัวอักษรล้นกรอบภาพ → ย่อ font_size ลงอัตโนมัติ
    ให้ข้อความทั้งคำอยู่ในภาพเสมอ
    """
    W, H = cfg.image_size
    img = Image.new("L", (W, H), color=0)  # พื้นหลังดำ
    draw = ImageDraw.Draw(img)

    # เริ่มด้วย font_size ตาม config
    font_size = cfg.font_size

    while True:
        font = ImageFont.truetype(cfg.font_path, font_size)

        # ดูขนาดจริงของข้อความ
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        # ให้มี margin รอบ ๆ ประมาณ 90% ของภาพ
        max_w = W * 0.9
        max_h = H * 0.9

        if text_w <= max_w and text_h <= max_h:
            # ขนาดโอเคแล้ว
            break

        # ถ้ายังล้น → ย่อฟอนต์ลงตามสัดส่วน
        scale_w = max_w / text_w if text_w > 0 else 1.0
        scale_h = max_h / text_h if text_h > 0 else 1.0
        scale = min(scale_w, scale_h)

        new_size = int(font_size * scale)

        if new_size >= font_size:   # กัน loop แปลก ๆ
            new_size = font_size - 1

        if new_size < 10:
            # เล็กสุดละ พอแค่นี้
            font_size = 10
            font = ImageFont.truetype(cfg.font_path, font_size)
            bbox = draw.textbbox((0, 0), text, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            break

        font_size = new_size

    # center ข้อความ
    x = (W - text_w) // 2
    y = (H - text_h) // 2

    draw.text((x, y), text, fill=255, font=font)

    return np.array(img)


# ---------------------------------------------------------
# 2) Bitmap → Polygon (ผ่าน contour)
# ---------------------------------------------------------

def bitmap_to_polygon(bitmap: np.ndarray, cfg: TextToMeshConfig):
    """
    แปลง bitmap (ตัวอักษรสีขาวบนพื้นดำ) → shapely Polygon / MultiPolygon
    """
    # ทำให้เป็นภาพ binary 0/255: ตัวอักษร = 255, พื้นหลัง = 0
    img = (bitmap > cfg.threshold).astype(np.uint8) * 255

    # closing เล็กน้อยให้เส้นต่อกัน (กันรูรั่วเล็ก ๆ)
    kernel = np.ones((3, 3), np.uint8)
    img = cv2.morphologyEx(img, cv2.MORPH_CLOSE, kernel)

    # debug: เซฟ mask ที่ใช้หา contour
    cv2.imwrite("debug_contours.png", img)

    # หา contour เฉพาะด้านนอก (แต่ละตัวอักษรเป็น blob แยกกัน)
    contours, hierarchy = cv2.findContours(
        img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    polygons = []

    for cnt in contours:
        if len(cnt) < 3:
            continue

        # ลดจุดนิดหน่อยไม่ให้ละเอียดเกินไป
        epsilon = 0.01 * cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, epsilon, True)

        pts = approx.reshape(-1, 2).astype(float)

        # กลับแกน y: จากภาพ (origin มุมบนซ้าย) → พิกัดคาร์ทีเซียน (origin ล่างซ้าย)
        H = bitmap.shape[0]
        pts[:, 1] = H - pts[:, 1]

        poly = Polygon(pts)
        if poly.is_valid and not poly.is_empty and poly.area > 50:
            polygons.append(poly)

    if not polygons:
        raise ValueError("No valid polygons from text bitmap.")

    union_poly = unary_union(polygons)

    # simplify เพื่อลดจำนวนจุด
    if cfg.simplify_tol > 0:
        union_poly = union_poly.simplify(cfg.simplify_tol)

    # union_poly อาจเป็น Polygon เดี่ยว หรือ MultiPolygon
    return union_poly


# ---------------------------------------------------------
# 3) Polygon → Mesh + UV
# ---------------------------------------------------------
from shapely.geometry import Polygon, MultiPolygon

def polygon_to_extruded_mesh(poly, extrude_depth: float) -> trimesh.Trimesh:
    """
    รองรับทั้ง Polygon เดี่ยว และ MultiPolygon (หลายตัวอักษร)
    extrude ทีละชิ้น แล้วรวม mesh เข้าด้วยกัน
    """
    if poly.is_empty:
        raise ValueError("Empty polygon")

    # แปลงเป็น list ของ Polygon เสมอ
    if isinstance(poly, Polygon):
        polygons = [poly]
    elif isinstance(poly, MultiPolygon):
        polygons = list(poly.geoms)
    else:
        raise TypeError(f"Unsupported geometry type: {type(poly)}")

    meshes = []
    for p in polygons:
        if p.is_empty or p.area <= 0:
            continue
        m = trimesh.creation.extrude_polygon(p, extrude_depth)
        meshes.append(m)

    if not meshes:
        raise ValueError("No valid polygon to extrude")

    mesh = trimesh.util.concatenate(meshes)
    mesh.vertices -= mesh.center_mass
    return mesh

def normalize_height(mesh: trimesh.Trimesh, target_height: float = 1.0) -> trimesh.Trimesh:
    """
    ปรับ scale ให้ 'ความสูง' (แกน Y) ของ mesh = target_height
    ความกว้าง X จะเปลี่ยนตาม (คำยาวกว่าก็กิน X มากกว่า)
    """
    extents = mesh.extents  # [size_x, size_y, size_z]
    current_height = float(extents[1])   # แกน Y = ความสูงตัวอักษร
    if current_height > 0:
        scale = target_height / current_height
        mesh.apply_scale(scale)
    return mesh

def add_planar_uv(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """
    ใส่ planar UV mapping จากพิกัด x,y → u,v ∈ [0,1]
    เหมาะกับโลโก้/ตัวอักษรในระนาบ XY
    """
    xy = mesh.vertices[:, :2]
    min_xy = xy.min(axis=0)
    max_xy = xy.max(axis=0)
    size = np.maximum(max_xy - min_xy, 1e-6)

    uv = (xy - min_xy) / size  # scale to [0,1]
    mesh.visual.uv = uv
    return mesh


# ---------------------------------------------------------
# 4) ฟังก์ชันหลัก: text_to_mesh(...)
# ---------------------------------------------------------

def text_to_mesh(
    text: str,
    font_path: str,
    output_path: str | None = None,
    font_size: int = 256,
    image_size: Tuple[int, int] = (1024, 1024),
    extrude_depth: float = 1.0,
    simplify_tol: float = 1.0,
) -> trimesh.Trimesh:
    """
    ฟังก์ชันหลัก: แปลง text + font → 3D mesh (และ .obj ถ้าระบุ output_path)

    Args:
        text: ข้อความ (ไทย/ญี่ปุ่น/อังกฤษ ฯลฯ)
        font_path: path ฟอนต์ (.ttf, .otf)
        output_path: path สำหรับเซฟไฟล์ mesh (.obj, .glb ฯลฯ)
        font_size: ขนาดฟอนต์ตอนวาด
        image_size: ขนาด bitmap (ยิ่งใหญ่ ขอบยิ่งเนียน)
        extrude_depth: ความหนาในแกน z
        simplify_tol: tolerance สำหรับ simplify polygon

    Returns:
        mesh: trimesh.Trimesh
    """
    cfg = TextToMeshConfig(
        font_path=font_path,
        font_size=font_size,
        image_size=image_size,
        extrude_depth=extrude_depth,
        simplify_tol=simplify_tol,
    )

    bitmap = text_to_bitmap(text, cfg)
    # debug: เซฟ bitmap ต้นฉบับ
    Image.fromarray(bitmap).save("debug_bitmap.png")

    poly = bitmap_to_polygon(bitmap, cfg)
    mesh = polygon_to_extruded_mesh(poly, extrude_depth)

    # 🔁 ใช้ normalize_height แทน: ให้ความสูงเท่ากันทุกคำ
    mesh = normalize_height(mesh, target_height=1.0)   # เปลี่ยนให้สูง 1 หน่วย (ปรับได้)

    mesh = add_planar_uv(mesh)


    if output_path is not None:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        mesh.export(output_path)
        print(f"Exported mesh to: {os.path.abspath(output_path)}")

    return mesh


# ---------------------------------------------------------
# 5) ตัวอย่างการใช้งาน (รันไฟล์นี้ตรง ๆ)
# ---------------------------------------------------------

if __name__ == "__main__":
    # แก้ path ฟอนต์ให้ตรงกับเครื่องคุณก่อนรันนะ
    SAMPLE_TEXT = "こんにちは"
    SAMPLE_FONT = r"C:\Windows\Fonts\YuGothM.ttc"  # YuGothM.ttc
    OUTPUT_PATH = r"outputs\meshes\konichiwa_uubernard.obj"

    if not os.path.exists(SAMPLE_FONT):
        raise FileNotFoundError(f"Font not found: {SAMPLE_FONT}")

    text_to_mesh(
        text=SAMPLE_TEXT,
        font_path=SAMPLE_FONT,
        output_path=OUTPUT_PATH,
        image_size = (4096, 4096),
        font_size = 800,
        extrude_depth=2.0,
        simplify_tol=0.5,
    )
    print("Done.")