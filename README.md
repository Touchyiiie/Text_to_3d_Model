⚡⚡⚡ Description
This project provides a lightweight and flexible system that converts any input text—Thai, English, Japanese, or any language supported by your font—into a fully-generated 3D model (.OBJ).
The pipeline uses a bitmap-based approach to ensure high compatibility without relying on heavy libraries or platform-specific text rendering engines.

Users simply input text, and the program outputs a clean, extruded 3D mesh that preserves the shape of the selected font.
This is ideal for creating 3D titles, logos, printable text objects, AR/VR assets, or integrating into AI systems that need text-to-3D capabilities.

⭐⭐⭐ Key Features

● Convert any text into a 3D model (.OBJ)

● Supports Thai, English, Japanese, and multi-language fonts

● Bitmap → Contour → Polygon → 3D Mesh pipeline

● Automatic font scaling to ensure all characters fit

● Height-normalized 3D output for consistent sizing

● Works on any machine (no FreeType or platform dependencies)

● Ready for integration with AI pipelines, web apps, or 3D editors

⚡⚡⚡คำอธิบาย (Description)
โปรเจ็กต์นี้สร้างระบบที่สามารถแปลงข้อความ (Text) ไม่ว่าจะเป็นภาษาไทย อังกฤษ ญี่ปุ่น หรือภาษาใด ๆ ที่ฟอนต์รองรับ ให้กลายเป็นโมเดลสามมิติ (.OBJ) ได้ทันที เพียงแค่ผู้ใช้กรอกข้อความ ระบบก็จะประมวลผลตัวอักษรทั้งหมดและสร้างโมเดล 3D ที่มีรูปทรงตรงกับฟอนต์จริงอย่างแม่นยำ

โปรแกรมใช้วิธีแปลงข้อความเป็นภาพ bitmap → หาเส้นขอบ (contour) → สร้าง polygon → สร้างโมเดล 3D ทำให้รองรับได้ทุกภาษา ไม่ติดปัญหาแพลตฟอร์มหรือไลบรารีเฉพาะทาง เช่น FreeType

เหมาะสำหรับงานสร้างโลโก้ 3D, ป้ายข้อความ, โมเดลพิมพ์ 3D, โปรเจ็กต์ AR/VR, งานออกแบบ หรือระบบ AI ที่ต้องการฟังก์ชัน “text-to-3D”

⭐⭐⭐คุณสมบัติเด่น

แปลงข้อความเป็นโมเดล 3 มิติ (.OBJ) ได้ทันที

รองรับภาษาไทยและหลายภาษาอย่างสมบูรณ์

Pipeline: Bitmap → Contour → Polygon → Extruded Mesh

ปรับขนาดฟอนต์อัตโนมัติ ตัวอักษรไม่ล้นหรือหาย

ทำให้ความสูงของโมเดลคงที่เสมอ เพื่อให้สัดส่วนสวยงาม

ทำงานได้ทุกเครื่อง ติดตั้งง่าย ไม่พึ่งไลบรารีเฉพาะแพลตฟอร์ม

รองรับการต่อยอดเข้ากับระบบ AI, Web UI หรือโปรแกรม 3D อื่น ๆ

How to use this Program
STEP 1 — Create Virtual Environment
python -m venv .venv
.\.venv\Scripts\activate
check----
python --version
(You should choose Python 3.10.x)

STEP 2 — install dependency
pip install numpy pillow opencv-python shapely trimesh
check----
python -c "import numpy, PIL, cv2, shapely, trimesh; print('OK')"

STEP 3 — Run Program 
<img width="873" height="43" alt="image" src="https://github.com/user-attachments/assets/a6ce66ae-a7e0-4cc9-8d8f-b5893bee354a" />
open output in blender
<img width="1912" height="921" alt="image" src="https://github.com/user-attachments/assets/5fd72f20-0ec9-445a-9643-3f4af926827b" />

-bye bye 🙏🙏🙏
