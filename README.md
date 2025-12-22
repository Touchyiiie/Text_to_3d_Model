⚡⚡⚡ Description
A lightweight, platform-independent system that converts any input text
(Thai, English, Japanese, or any language supported by the selected font)
into a clean 3D text model (.OBJ) using a bitmap-based pipeline.

This project focuses on robust text-to-3D geometry generation without relying on
platform-specific text engines or heavy dependencies, making it suitable for
research, prototyping, and future AI-based extensions.

🔍 Overview

The system transforms text into a 3D mesh through a deterministic pipeline:

Text
 ↓
Bitmap Rendering
 ↓
Contour Detection
 ↓
Polygon Reconstruction
 ↓
3D Extrusion
 ↓
Export (.OBJ)


By converting text into a bitmap first, the pipeline avoids common issues with
multi-language text rendering and ensures consistent results across platforms.

✨ Key Features

✅ Convert any text into a 3D model (.OBJ)

🌏 Supports Thai, English, Japanese, and multilingual fonts

🧱 Bitmap → Contour → Polygon → Extruded Mesh pipeline

📐 Automatic font scaling (no missing or clipped characters)

📏 Height-normalized 3D output for consistent sizing

💻 Works on any machine (no FreeType or OS-specific dependencies)

🔗 Easy to integrate into AI pipelines, scripts, or 3D workflows

🧠 Designed for gradual extension toward full Text-to-3D systems

🧪 Why Bitmap-Based?

Traditional text-to-geometry pipelines rely on font vector parsing
(e.g., FreeType), which can be platform-dependent and error-prone
for multilingual text.

This project uses a bitmap-first approach, which offers:

Stable multi-language rendering

Predictable geometry extraction

Simpler debugging and visualization

Easier integration with image-based AI models in the future

🛠 Requirements

Python 3.10.x (recommended)

Libraries:

numpy

pillow

opencv-python

shapely

trimesh

🚀 How to Use
STEP 1 — Create Virtual Environment
python -m venv .venv
.\.venv\Scripts\activate
python --version


Make sure you are using Python 3.10.x

STEP 2 — Install Dependencies
pip install numpy pillow opencv-python shapely trimesh


Verify installation:

python -c "import numpy, PIL, cv2, shapely, trimesh; print('OK')"

STEP 3 — Run the Program
python src/prompt_to_obj.py "こんにちは"


or

python src/prompt_to_obj.py "สวัสดีโลก"


The output .OBJ file will be saved to:

outputs/meshes/

STEP 4 — Open in Blender

Open Blender

File → Import → Wavefront (.obj)

Load the generated file

Adjust scale/material as needed

📁 Project Structure
PROJECT_TEXT3D
│
├─ src/
│  ├─ text2mesh/
│  │  └─ text_to_mesh.py
│  └─ prompt_to_obj.py
│
├─ assets/
│  └─ fonts/
│
├─ outputs/
│  └─ meshes/
│
├─ debug_bitmap.png
├─ debug_contours.png
├─ requirements.txt
├─ README.md
└─ LICENSE

🔮 Future Extensions (Planned)

This project is intentionally scoped to text-only 3D generation, but designed
to be extended into more advanced pipelines, such as:

Text → Image → 3D

AI-based font or style generation

Web-based text-to-3D interfaces

Integration with LLM-based prompt parsers

Export to .GLB / .USD formats

⚡ Thai Description (คำอธิบายภาษาไทย)

โปรเจ็กต์นี้เป็นระบบที่สามารถแปลง ข้อความ (Text)
ไม่ว่าจะเป็นภาษาไทย อังกฤษ ญี่ปุ่น หรือภาษาใด ๆ ที่ฟอนต์รองรับ
ให้กลายเป็น โมเดลสามมิติ (.OBJ) ได้โดยอัตโนมัติ

ระบบใช้แนวคิด
Bitmap → Contour → Polygon → 3D Mesh
เพื่อให้รองรับหลายภาษาได้อย่างเสถียร ไม่ผูกกับแพลตฟอร์มหรือไลบรารีเฉพาะทาง

เหมาะสำหรับ:

งานโลโก้ 3D

ป้ายข้อความ

โมเดลพิมพ์ 3D

งาน AR / VR

ระบบ AI ที่ต้องการความสามารถ text-to-3D

📌 Scope (ขอบเขตโปรเจ็กต์)

✔ โฟกัสเฉพาะ 3D Text Geometry
✔ ไม่สร้างโมเดลคน / สัตว์ / สิ่งของในเวอร์ชันนี้
✔ ออกแบบเพื่อการต่อยอดในอนาคตอย่างเป็นระบบ

👋 Final Note

This project is designed to be:

Technically solid

Bachelor-level appropriate

Extendable without overengineering

“Start simple. Build correctly. Extend intelligently.”

🙏🙏🙏
bye bye