"""
prompt_to_obj.py

ใช้ฟังก์ชัน text_to_mesh ที่เราทำไว้แล้ว
แปลง "ประโยคธรรมชาติ" → ไฟล์ .obj 3D text

วิธีใช้:
    python src/prompt_to_obj.py "ผู้ชายใส่เสื้อเชิ๊ตสีฟ้าเขียนว่า \"konnichiwa\""
"""

import os
import re
import sys
from datetime import datetime
from pathlib import Path

from text2mesh.text_to_mesh import text_to_mesh


# -------------------------------
# 1) ฟังก์ชันแยกข้อความจาก prompt
# -------------------------------

def parse_prompt(prompt: str):
    """
    ดึงข้อความที่อยู่ในเครื่องหมาย quote ออกมา
    เช่น:
        'ผู้ชายใส่เสื้อเชิ๊ตสีฟ้าเขียนว่า "konnichiwa"'
        → text = "konnichiwa"

    ถ้าไม่มี quote เลย → ใช้ทั้ง prompt เป็น text
    """
    # รองรับ "..." หรือ '...' หรือ “...”
    m = re.search(r'"(.+?)"|“(.+?)”|\'(.+?)\'', prompt)
    if m:
        # เลือก group ที่ไม่ใช่ None
        text = next(g for g in m.groups() if g is not None)
    else:
        text = prompt.strip()

    return text


# -------------------------------
# 2) เลือกฟอนต์ให้เหมาะกับภาษา
# -------------------------------
def auto_font_size(base: int, text: str, min_scale: float = 0.6, max_scale: float = 1.4) -> int:
    """
    ปรับ font_size อัตโนมัติให้สัมพันธ์กับความยาวคำ
    - คำสั้น → scale สูง (ตัวใหญ่)
    - คำยาว → scale ลดลง (ตัวไม่เละจากการล้น bitmap)
    """
    n = max(len(text), 1)
    # heuristic ง่าย ๆ: ยิ่งตัวอักษรน้อย → scale ใกล้ max_scale
    scale = 8.0 / n        # ปรับเลข 8.0 ได้ตามที่ชอบ
    scale = max(min_scale, min(max_scale, scale))
    return int(base * scale)


def choose_font_for_text(text: str) -> str:
    """
    เลือกฟอนต์ตามประเภทตัวอักษรแบบง่าย ๆ
    - ถ้ามีอักษรไทย → TH Sarabun
    - ถ้ามีญี่ปุ่น → Noto Sans JP (ถ้าคุณติดตั้ง)
    - ถ้าเป็นอังกฤษล้วน → Bernard MT (หรือฟอนต์อื่นของคุณ)
    *** แก้ path ฟอนต์ให้ตรงกับเครื่องคุณ ***
    """
    win_fonts = Path(r"C:\Windows\Fonts")

    has_thai = any('\u0E00' <= ch <= '\u0E7F' for ch in text)
    has_jp = any('\u3040' <= ch <= '\u30FF' for ch in text)  # hiragana + katakana

    if has_thai:
        # เปลี่ยนชื่อไฟล์ตามฟอนต์ไทยที่คุณมี
        cand = win_fonts / "THSarabunNew.ttf"
        if cand.exists():
            return str(cand)

    if has_jp:
        # ต้องลง Noto Sans JP ก่อน หรือใช้ฟอนต์ญี่ปุ่นอื่นแทน
        cand = win_fonts / "NotoSansJP-Regular.otf"
        if cand.exists():
            return str(cand)

    # fallback: Bernard MT (ภาษาอังกฤษ/เลข)
    bern = win_fonts / "BERNHC.TTF"
    if bern.exists():
        return str(bern)

    # สุดท้ายจริง ๆ: Arial
    arial = win_fonts / "arial.ttf"
    if arial.exists():
        return str(arial)

    raise FileNotFoundError("ไม่พบฟอนต์ที่เหมาะสมใน C:\\Windows\\Fonts")


# -------------------------------
# 3) main: prompt → .obj
# -------------------------------

def prompt_to_obj(prompt: str):
    text = parse_prompt(prompt)
    print(f"[INFO] Parsed text from prompt: {text!r}")

    font_path = choose_font_for_text(text)
    print(f"[INFO] Using font: {font_path}")

    # ตั้งชื่อไฟล์ output
    safe_text = re.sub(r"[^0-9a-zA-Zก-ฮะ-๙一-龯ぁ-んァ-ンー]+", "_", text)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"text_{safe_text}_{timestamp}.obj"

    out_dir = Path("outputs") / "meshes"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / filename

    # เรียกฟังก์ชัน text_to_mesh ที่คุณทำไว้แล้ว
    base_font = 900
    fs = auto_font_size(base_font, text)
    print(f"[INFO] auto font_size = {fs} (from base {base_font})")

    mesh = text_to_mesh(
        text=text,
        font_path=str(font_path),
        output_path=str(out_path),
        font_size=fs,
        image_size=(2048, 2048),
        extrude_depth=2.0,
        simplify_tol=0.5,
    )


    print(f"[DONE] Exported OBJ to: {out_path.resolve()}")
    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python src/prompt_to_obj.py \"ผู้ชายใส่เสื้อเชิ๊ตสีฟ้าเขียนว่า \\\"konnichiwa\\\"\"")
        sys.exit(1)

    prompt = sys.argv[1]
    prompt_to_obj(prompt)
