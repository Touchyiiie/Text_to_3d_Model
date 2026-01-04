⚡⚡⚡ Description
This project provides a lightweight and flexible system that converts any input text
— Thai, English, Japanese, or any language supported by your font — into a fully-generated
3D text model (.GLB).

The pipeline uses a bitmap-based approach to ensure high compatibility without relying on
platform-specific text engines or heavy font parsing libraries.

Users simply input a prompt, and the program outputs a clean, extruded 3D mesh that preserves
the shape of the selected font. Ideal for 3D titles, logos, printable text objects, AR/VR assets,
or integrating into AI systems that need text-to-3D capabilities.


⭐⭐⭐ Key Features
● Convert any text into a 3D model (.GLB)  
● Supports Thai / English / Japanese (font-based)  
● Bitmap → Contour → Polygon (with holes) → 3D Extruded Mesh  
● Automatic font scaling to ensure all characters fit (no cut-off)  
● Height-normalized output (Y-axis fixed) for consistent sizing  
● Works on any machine (no FreeType dependency)  
● Ready for extension (prompt parser / AI pipeline)


⚡⚡⚡คำอธิบาย (Description)
โปรเจ็กต์นี้เป็นระบบแปลง “ข้อความ (Text)” ให้กลายเป็นโมเดลสามมิติ (.GLB) แบบอัตโนมัติ
รองรับภาษาไทย/อังกฤษ/ญี่ปุ่น (และภาษาอื่น ๆ ถ้าฟอนต์รองรับ)

ระบบใช้แนวคิด:
Bitmap → Contour → Polygon (มีรู) → Extruded Mesh
ทำให้รองรับหลายภาษาได้เสถียร ไม่ผูกกับแพลตฟอร์มหรือไลบรารีเฉพาะทาง


🧪 Input Format (สำคัญมาก)
Rule:
- Text inside quotes ("...") = ข้อความที่ต้องการทำเป็น 3D
- Text outside quotes = options เช่น สี / ความหนา

Example:
text3d "\"สวัสดี konnichiwa こんにちは\" สีเหลือง หนา 8"


------------------------------------------------------------
⚡ (1) QUICK START — Clone → Run (copy/paste ชุดเดียว)
------------------------------------------------------------

Windows PowerShell:

git clone https://github.com/Touchyiiie/Text_to_3d_Model.git
cd Text_to_3d_Model
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt

# Run
python src/prompt_to_obj.py "\"สวัสดี konnichiwa こんにちは\" สีเหลือง หนา 8"


✅ Output:
outputs/meshes/<name>.glb


------------------------------------------------------------
🧩 Optional: Run as a command (text3d)
------------------------------------------------------------
If your repo includes a console entry point, you can run:

text3d "\"สวัสดี konnichiwa こんにちは\" สีเหลือง หนา 8"


------------------------------------------------------------
🛠 Dependencies
------------------------------------------------------------
Always install `mapbox-earcut` (required for triangulation):
pip install -r requirements.txt


------------------------------------------------------------
🧠 Fonts (TH/EN/JP on EVERY machine)
------------------------------------------------------------
If you want Thai/English/Japanese to work reliably on ANY machine (even if the OS has no JP fonts),
bundle open fonts in this folder:

assets/fonts/

Recommended (free / stable / best for mixed TH+EN+JP in one sentence):
- NotoSansThai-Regular.ttf
- NotoSansJP-Regular.otf (or .ttf)
- NotoSansCJK-Regular.ttc (best “one font covers all”)

⚠️ Note:
- Avoid shipping proprietary fonts (e.g., Yu Gothic from Windows).
- Noto fonts are great for distribution (OFL license).


------------------------------------------------------------
🎨 Blender: “GLB has color but I can’t see it”
------------------------------------------------------------
If you open .glb and color doesn’t show, switch viewport shading:
Viewport Shading → Material Preview (icon: sphere)
(Solid mode may look gray even when material exists)


------------------------------------------------------------
👋 Final Note
------------------------------------------------------------
This project is designed to be:
- Technically solid
- Bachelor-level appropriate
- Extendable without overengineering

“Start simple. Build correctly. Extend intelligently.”

🙏🙏🙏
bye bye
