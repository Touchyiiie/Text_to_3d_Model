"""
prompt_to_obj.py

Input:
  python src/prompt_to_obj.py "\"สวัสดี konnichiwa こんにちは\" สีน้ำเงิน หนา 2"

Rule:
  - Text inside quotes ("...") -> 3D text
  - Outside quotes -> options (color, thickness/extrude)
Output:
  outputs/meshes/<name>.glb  (GLB only)
"""

from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import trimesh

from text3d import text_to_mesh


# -------------------------------
# 1) Parse
# -------------------------------

_QUOTE_RE = re.compile(r'"(.+?)"|“(.+?)”|\'(.+?)\'')

def parse_prompt(prompt: str) -> tuple[str, str]:
    """
    Returns: (text_in_quotes, attrs_outside)
    If no quotes -> use whole prompt as text, attrs=""
    """
    m = _QUOTE_RE.search(prompt)
    if not m:
        return prompt.strip(), ""

    text = next(g for g in m.groups() if g is not None)
    attrs = (prompt[:m.start()] + " " + prompt[m.end():]).strip()
    return text.strip(), attrs.strip()


# -------------------------------
# 2) Font selection (Thai / EN / JP)
#    NOTE: For best mixed TH/EN/JP in one sentence,
#          recommend installing/bundling a font that supports all (e.g. Noto Sans CJK).
# -------------------------------

def choose_font_for_text(text: str) -> str:
    win_fonts = Path(r"C:\Windows\Fonts")
    project_fonts = Path("assets") / "fonts"

    # helper: try project fonts first
    def try_paths(names: list[str]) -> str | None:
        for base in (project_fonts, win_fonts):
            for n in names:
                p = base / n
                if p.exists():
                    return str(p)
        return None

    has_thai = any("\u0E00" <= ch <= "\u0E7F" for ch in text)
    has_hira = any("\u3040" <= ch <= "\u309F" for ch in text)
    has_kata = any("\u30A0" <= ch <= "\u30FF" for ch in text)
    has_kanji = any("\u4E00" <= ch <= "\u9FFF" for ch in text)
    has_jp = has_hira or has_kata or has_kanji

    # Best case for mixed TH/JP/EN: Noto CJK / Noto Sans (if you place in assets/fonts)
    mixed_best = try_paths([
        "NotoSansCJKjp-Regular.otf",
        "NotoSansJP-Regular.otf",
        "NotoSansThai-Regular.ttf",
    ])
    # If contains both Thai and Japanese, prefer a CJK-capable font if available
    if has_thai and has_jp and mixed_best:
        return mixed_best

    if has_thai:
        p = try_paths(["THSarabunNew.ttf", "LeelawUI.ttf", "Leelawad.ttf"])
        if p:
            return p

    if has_jp:
        p = try_paths(["YuGothM.ttc", "YuGothR.ttc", "meiryo.ttc", "MSGOTHIC.TTC", "MSMINCHO.TTC"])
        if p:
            return p

    # fallback Latin
    p = try_paths(["BERNHC.TTF", "arial.ttf", "calibri.ttf"])
    if p:
        return p

    raise FileNotFoundError("No suitable font found in assets/fonts or C:\\Windows\\Fonts")


# -------------------------------
# 3) Options parsing (color + thickness)
# -------------------------------

_COLOR_MAP = {
    "สีแดง":   (220, 30, 30, 255),
    "สีเขียว": (30, 200, 80, 255),
    "สีน้ำเงิน": (0, 80, 255, 255),
    "สีฟ้า":   (80, 170, 255, 255),
    "สีดำ":    (20, 20, 20, 255),
    "สีขาว":   (240, 240, 240, 255),
    "สีเหลือง": (255, 220, 60, 255),
}

def parse_options(attrs: str) -> dict:
    """
    Supported:
      - color keywords: สีฟ้า / สีน้ำเงิน / ...
      - thickness: "หนา 2" -> extrude_depth=2.0
    """
    opts = {
        "color_rgba": (200, 200, 200, 255),  # default gray
        "extrude_depth": 2.0,
        "target_height": 1.0,
    }

    a = attrs.strip()
    if not a:
        return opts

    # color
    for k, rgba in _COLOR_MAP.items():
        if k in a:
            opts["color_rgba"] = rgba
            break

    # thickness
    m = re.search(r"(หนา|ความหนา)\s*([0-9]+(?:\.[0-9]+)?)", a)
    if m:
        opts["extrude_depth"] = float(m.group(2))

    return opts


# -------------------------------
# 4) Main: prompt -> GLB
# -------------------------------

def auto_font_size(base: int, text: str, min_scale: float = 0.6, max_scale: float = 1.4) -> int:
    n = max(len(text), 1)
    scale = 8.0 / n
    scale = max(min_scale, min(max_scale, scale))
    return int(base * scale)


def prompt_to_obj(prompt: str) -> Path:
    text, attrs = parse_prompt(prompt)
    print(f"[INFO] Parsed text: {text!r}")
    print(f"[INFO] Attrs: {attrs!r}")

    opts = parse_options(attrs)
    print(f"[INFO] Options: {opts}")

    font_path = choose_font_for_text(text)
    print(f"[INFO] Using font: {font_path}")

    base_font = 900
    fs = auto_font_size(base_font, text)
    print(f"[INFO] auto font_size = {fs} (from base {base_font})")

    # build mesh (do NOT export inside text_to_mesh; we export GLB here)
    mesh = text_to_mesh(
        text=text,
        font_path=font_path,
        output_path=None,
        font_size=fs,
        image_size=(4096, 4096),          # higher for smooth edges
        extrude_depth=float(opts["extrude_depth"]),
        simplify_tol=0.3,                 # keep curves nicer
        target_height=float(opts["target_height"]),
    )

    # Apply color as a PBR material (GLB-friendly)
    r, g, b, a = opts["color_rgba"]
    mat = trimesh.visual.material.PBRMaterial(
        baseColorFactor=(r / 255.0, g / 255.0, b / 255.0, a / 255.0),
        metallicFactor=0.0,
        roughnessFactor=0.6,
    )
    mesh.visual.material = mat

    # output path (GLB only)
    safe = re.sub(r"[^0-9a-zA-Zก-ฮะ-๙一-龯ぁ-んァ-ンー]+", "_", text).strip("_")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path("outputs") / "meshes"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"text_{safe}_{ts}.glb"

    mesh.export(out_path, file_type="glb")
    print(f"[DONE] Exported GLB to: {out_path.resolve()}")

    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage: python src/prompt_to_obj.py "\\"สวัสดี konnichiwa こんにちは\\" สีน้ำเงิน หนา 2"')
        sys.exit(1)

    prompt = sys.argv[1]
    prompt_to_obj(prompt)

def main():
    if len(sys.argv) < 2:
        print('Usage: text3d "\\"สวัสดี konnichiwa こんにちは\\" สีน้ำเงิน หนา 8"')
        raise SystemExit(1)
    prompt_to_obj(sys.argv[1])

if __name__ == "__main__":
    main()
