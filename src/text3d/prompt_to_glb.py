"""
prompt_to_glb.py

Input examples:

1) PowerShell-friendly (text in quotes; attrs split as extra argv):
   text3d "สวัสดีครับ konnichiwa こんにちは" สีเหลือง หนา 8

2) One single string (quotes included as characters):
   text3d "\"สวัสดีครับ konnichiwa こんにちは\" สีเหลือง หนา 8"

3) With embed (engrave/emboss) into a target .glb:
   text3d "cookie" นูน ลึก 3% .\hse_tiger_shark.glb
   text3d "HELLO" จม ลึก 2% .\hse_tiger_shark.glb

NLP via Ollama (optional):
- Enable:
    $env:TEXT3D_USE_OLLAMA="1"
    $env:TEXT3D_OLLAMA_MODEL="qwen2.5:7b-instruct"
    # optional:
    $env:TEXT3D_OLLAMA_HOST="http://127.0.0.1:11434"

- Blender path (optional for embed pipeline):
    $env:TEXT3D_BLENDER_EXE="C:\Program Files\Blender Foundation\Blender 5.0\blender.exe"

Rule:
  - Text inside quotes ("...") -> 3D text
  - Outside quotes -> options (color, thickness/extrude, mode/depth/target)

Output:
  - Standalone text: outputs/meshes/<name>.glb
  - Embed result:    outputs/engrave_emboss/<name>.glb
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

from .text_to_mesh import text_to_mesh
from .embed_text_glb import EmbedConfig, embed_text_on_glb


# -------------------------------
# 1) Parse: quoted text
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
    attrs = (prompt[: m.start()] + " " + prompt[m.end() :]).strip()
    return text.strip(), attrs.strip()


# -------------------------------
# 2) Font selection (Thai / EN / JP)
# -------------------------------

def choose_font_for_text(text: str) -> str:
    win_fonts = Path(r"C:\Windows\Fonts")
    project_fonts = Path("assets") / "fonts"

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

    mixed_best = try_paths(
        [
            "NotoSansCJKjp-Regular.otf",
            "NotoSansJP-Regular.otf",
            "NotoSansThai-Regular.ttf",
        ]
    )
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

    p = try_paths(["BERNHC.TTF", "arial.ttf", "calibri.ttf"])
    if p:
        return p

    raise FileNotFoundError("No suitable font found in assets/fonts or C:\\Windows\\Fonts")


# -------------------------------
# 3) Options parsing (color + thickness + embed params)
# -------------------------------

_COLOR_MAP = {
    "สีแดง": (220, 30, 30, 255),
    "สีเขียว": (30, 200, 80, 255),
    "สีน้ำเงิน": (0, 80, 255, 255),
    "สีฟ้า": (80, 170, 255, 255),
    "สีดำ": (20, 20, 20, 255),
    "สีขาว": (240, 240, 240, 255),
    "สีเหลือง": (255, 220, 60, 255),
}


def _clamp255(x: int) -> int:
    return max(0, min(255, int(x)))


def parse_options(attrs: str) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "color_rgba": (200, 200, 200, 255),
        "extrude_depth": 2.0,
        "target_height": 1.0,
        "mode": None,          # "emboss" | "engrave"
        "depth_percent": None, # float (percent of min(bbox))
        "target_glb": None,    # path to .glb
    }

    a = attrs.strip()
    if not a:
        return opts

    low = a.lower()

    # mode
    if ("นูน" in a) or ("emboss" in low):
        opts["mode"] = "emboss"
    if ("จม" in a) or ("engrave" in low):
        opts["mode"] = "engrave"

    # depth percent: "ลึก 2%" or "depth 2%"
    m = re.search(r"(?:ลึก|depth)\s*([0-9]+(?:\.[0-9]+)?)\s*%", a, flags=re.IGNORECASE)
    if m:
        opts["depth_percent"] = float(m.group(1))

    # target glb path: any token containing .glb
    tokens = a.split()
    for tok in tokens[::-1]:
        if ".glb" in tok.lower():
            opts["target_glb"] = tok.strip('"')
            break

    # RGB:(r,g,b)
    m_rgb = re.search(
        r"rgb\s*[:=]?\s*\(?\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)?",
        a,
        flags=re.IGNORECASE,
    )
    if m_rgb:
        r = _clamp255(int(m_rgb.group(1)))
        g = _clamp255(int(m_rgb.group(2)))
        b = _clamp255(int(m_rgb.group(3)))
        opts["color_rgba"] = (r, g, b, 255)

    # HEX color #RRGGBB
    m_hex = re.search(r"(#?[0-9a-fA-F]{6})", a)
    if m_hex:
        hx = m_hex.group(1)
        if not hx.startswith("#"):
            hx = "#" + hx
        r = int(hx[1:3], 16)
        g = int(hx[3:5], 16)
        b = int(hx[5:7], 16)
        opts["color_rgba"] = (r, g, b, 255)

    # Thai named colors (fallback)
    for k, rgba in _COLOR_MAP.items():
        if k in a:
            opts["color_rgba"] = rgba
            break

    # thickness/extrude for standalone text: "หนา 8"
    m2 = re.search(r"(หนา|ความหนา)\s*([0-9]+(?:\.[0-9]+)?)", a)
    if m2:
        opts["extrude_depth"] = float(m2.group(2))

    return opts


# -------------------------------
# 3.5) Ollama NLP (optional)
# -------------------------------

def _ollama_chat_json(prompt: str) -> dict[str, Any] | None:
    """
    Call local Ollama and ask it to output STRICT JSON for text3d parsing.

    Enable via env:
      TEXT3D_USE_OLLAMA=1
      TEXT3D_OLLAMA_HOST=http://127.0.0.1:11434
      TEXT3D_OLLAMA_MODEL=qwen2.5:7b-instruct
    """
    use = os.environ.get("TEXT3D_USE_OLLAMA", "0")
    if use not in ("1", "true", "TRUE", "yes", "YES"):
        return None

    host = os.environ.get("TEXT3D_OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    model = os.environ.get("TEXT3D_OLLAMA_MODEL", "qwen2.5:7b-instruct")

    system = (
        "You are a strict JSON parser for a CLI tool named text3d.\n"
        "Return STRICT JSON only (no markdown, no explanation).\n"
        "Extract fields from the user's command (Thai/English allowed).\n"
        "Schema:\n"
        "{\n"
        '  "text": string,\n'
        '  "mode": "emboss"|"engrave"|null,\n'
        '  "depth_percent": number|null,\n'
        '  "target_glb": string|null,\n'
        '  "color_rgba": [r,g,b,a]|null,\n'
        '  "color_hex": string|null,\n'
        '  "extrude_depth": number|null,\n'
        '  "target_height": number|null\n'
        "}\n"
        "Rules:\n"
        "- If quoted text exists, use it as text.\n"
        "- If multiple .glb paths exist, pick the last one.\n"
        "- If user says RGB:(r,g,b) or hex color, parse it.\n"
        "- If user says นูน/จม -> emboss/engrave.\n"
        "- Always output a JSON object.\n"
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }

    req = urllib.request.Request(
        url=f"{host}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None

    content = (data.get("message") or {}).get("content", "")
    if not content:
        return None

    try:
        obj = json.loads(content)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", content, flags=re.DOTALL)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None


def parse_prompt_and_options(prompt: str) -> tuple[str, dict[str, Any], str]:
    """
    Returns: (text, opts, attrs)
    Tries Ollama first (if enabled), fallback to regex parsing.
    """
    obj = _ollama_chat_json(prompt)
    if isinstance(obj, dict):
        text = str(obj.get("text") or "").strip()
        if text:
            opts = parse_options("")  # start from defaults

            mode = obj.get("mode")
            if mode in ("emboss", "engrave"):
                opts["mode"] = mode

            dp = obj.get("depth_percent")
            if dp is not None:
                try:
                    opts["depth_percent"] = float(dp)
                except Exception:
                    pass

            tg = obj.get("target_glb")
            if isinstance(tg, str) and ".glb" in tg.lower():
                opts["target_glb"] = tg.strip()

            rgba = obj.get("color_rgba")
            if isinstance(rgba, list) and len(rgba) == 4:
                try:
                    opts["color_rgba"] = tuple(_clamp255(int(x)) for x in rgba)
                except Exception:
                    pass
            else:
                hx = obj.get("color_hex")
                if isinstance(hx, str) and re.fullmatch(r"#?[0-9a-fA-F]{6}", hx.strip()):
                    hx = hx.strip()
                    if not hx.startswith("#"):
                        hx = "#" + hx
                    r = int(hx[1:3], 16)
                    g = int(hx[3:5], 16)
                    b = int(hx[5:7], 16)
                    opts["color_rgba"] = (r, g, b, 255)

            ex = obj.get("extrude_depth")
            if ex is not None:
                try:
                    opts["extrude_depth"] = float(ex)
                except Exception:
                    pass

            th = obj.get("target_height")
            if th is not None:
                try:
                    opts["target_height"] = float(th)
                except Exception:
                    pass

            return text, opts, ""  # attrs empty because structured

    # fallback old behavior
    text, attrs = parse_prompt(prompt)
    opts = parse_options(attrs)
    return text, opts, attrs


# -------------------------------
# 4) Main: prompt -> GLB
# -------------------------------

def auto_font_size(base: int, text: str, min_scale: float = 0.6, max_scale: float = 1.4) -> int:
    n = max(len(text), 1)
    scale = 8.0 / n
    scale = max(min_scale, min(max_scale, scale))
    return int(base * scale)


def prompt_to_glb(prompt: str) -> Path:
    text, opts, attrs = parse_prompt_and_options(prompt)

    print(f"[INFO] Parsed text: {text!r}")
    print(f"[INFO] Attrs: {attrs!r}")
    print(f"[INFO] Options: {opts}")

    font_path = choose_font_for_text(text)
    print(f"[INFO] Using font: {font_path}")

    base_font = 900
    fs = auto_font_size(base_font, text)
    print(f"[INFO] auto font_size = {fs} (from base {base_font})")

    # -------- Embed mode (engrave/emboss) --------
    if opts.get("target_glb") and opts.get("mode") and (opts.get("depth_percent") is not None):
        blender_exe = os.environ.get("TEXT3D_BLENDER_EXE")
        if blender_exe:
            cfg = EmbedConfig(
                mode=opts["mode"],
                depth_percent=float(opts["depth_percent"]),
                blender_exe=blender_exe,
            )
        else:
            cfg = EmbedConfig(
                mode=opts["mode"],
                depth_percent=float(opts["depth_percent"]),
            )

        def _make_text_mesh(text: str, font_path: str, extrude_depth: float, target_height: float):
            return text_to_mesh(
                text=text,
                font_path=font_path,
                output_path=None,
                font_size=fs,
                image_size=(4096, 4096),
                extrude_depth=float(extrude_depth),
                simplify_tol=0.3,
                target_height=float(target_height),
            )

        out_path = embed_text_on_glb(
            base_glb_path=opts["target_glb"],
            text_mesh_generator=_make_text_mesh,
            text=text,
            font_path=font_path,
            cfg=cfg,
            seed=None,
        )
        print(f"[DONE] Embedded ({cfg.mode}) into: {out_path.resolve()}")
        return out_path

    # -------- Standalone text GLB --------
    mesh = text_to_mesh(
        text=text,
        font_path=font_path,
        output_path=None,
        font_size=fs,
        image_size=(4096, 4096),
        extrude_depth=float(opts["extrude_depth"]),
        simplify_tol=0.3,
        target_height=float(opts["target_height"]),
    )

    r, g, b, a = opts["color_rgba"]
    mat = trimesh.visual.material.PBRMaterial(
        baseColorFactor=(r / 255.0, g / 255.0, b / 255.0, a / 255.0),
        metallicFactor=0.0,
        roughnessFactor=0.6,
    )
    mesh.visual.material = mat

    safe = re.sub(r"[^0-9a-zA-Zก-ฮะ-๙一-龯ぁ-んァ-ンー]+", "_", text).strip("_")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path("outputs") / "meshes"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"text_{safe}_{ts}.glb"

    mesh.export(out_path, file_type="glb")
    print(f"[DONE] Exported GLB to: {out_path.resolve()}")
    return out_path


def main() -> None:
    if len(sys.argv) < 2:
        print('Usage: text3d "สวัสดีครับ konnichiwa こんにちは" สีเหลือง หนา 8')
        print('   or: text3d "\\"สวัสดีครับ konnichiwa こんにちは\\" สีเหลือง หนา 8"')
        raise SystemExit(1)

    # Case A: one big string is passed (may contain quotes as characters)
    if len(sys.argv) == 2:
        prompt = sys.argv[1]
    else:
        # Case B: PowerShell splits args:
        # text3d "TEXT ..." สีเหลือง หนา 8
        text_arg = sys.argv[1]
        attrs = " ".join(sys.argv[2:]).strip()

        if _QUOTE_RE.search(text_arg):
            prompt = f"{text_arg} {attrs}".strip()
        else:
            prompt = f"\"{text_arg}\" {attrs}".strip()

    prompt_to_glb(prompt)


if __name__ == "__main__":
    main()
