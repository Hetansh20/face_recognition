# Automatic Attendance using Face Recognition and Multiclassification

An enterprise-grade, high-accuracy contactless attendance system powered by advanced deep learning techniques (InsightFace + YOLOv8) and presented through a beautifully responsive web dashboard built in Flask.

## 📖 Overview

The "Automatic Attendance using Face Recognition and Multiclassification" project provides an end-to-end automated pipeline to replace manual roll-calls. Institutions and administrative faculties setup scheduling logic upfront. When a scheduled session begins, faculties initiate a secure live-feed streaming session or a group photo analysis. State-of-the-art multi-classification object detection engines pinpoint faces which are then dynamically mapped against an enrolled student database using L2-normalized deep embeddings.

## ✨ Key Features

- **Live Camera MJPEG Streaming**: Ultra-low-latency computer vision live streaming delivered cleanly into the web UI using asynchronous OpenCV threading.
- **Multiclassification Engine**: 
  - Uses **InsightFace (ArcFace `buffalo_l` model)** to extract 512-dimensional facial feature vectors.
  - Optionally utilizes **YOLOv8** (`yolov8n-face.pt`) for ultra-fast bounding box multi-face detection, significantly reducing overhead for group analytics and heavy crowd scenarios.
- **Twin-Interface Portal**:
  - **Admin Dashboard**: Manage users, students, timetable scheduling, database configurations, and global insight reporting.
  - **Faculty Portal**: Session initiation, live video monitoring, one-click Group Photo capture, forced exits, and raw data extraction.
- **Intelligent Analytics**: Immediate breakdown of class attendance including "Total Faces Detected", "Present", and "Unknown" identifiers.
- **Instant CSV Export**: Generates categorized `{Class}_Present_{timestamp}.csv` and `{Class}_Absent.csv` immediately on session termination.
- **Database Driven**: Clean SQLite implementation safely tying user metadata, login passcodes (encrypted via bcrypt), and timetable rules.

## ⚙️ Architecture & Flow Description

1. **Environment Setup & Bootstrapping**:
   The `app.py` Flask server starts up establishing SQL connections via `database.py`. The `FaceEngine` securely buffers registered JSON (`face_database.json`) logic and deserializes compiled feature vectors (`face_embeddings_insightface.pkl`).
   
2. **Setup Phase (Admin)**:
   - Admin logs into the portal to inject Student data (IDs, names) and Faculty details.
   - Admin utilizes the camera portal to register multiple facial angles for users. The system compiles and caches facial embeddings.
   - Admin maps Faculties to class Timetables.
   
3. **Session Initiation (Faculty)**:
   - Faculty logs in with their passcode.
   - System checks if there is an **active class** based on the global timetable settings and the current server timestamp.
   - Once confirmed, the system mounts the `FaceEngine` asynchronously.

4. **Inference Pipeline**:
   - `cv2.VideoCapture` streams continuous frames.
   - *Live Video*: `FaceEngine` downsizes frames to infer using `InsightFace` backend. Distances (`np.dot` between live vector and cached vectors) under a specific strict margin vote over a rolling frame window to declare a user "Present".
   - *Group Photo / Image Upload*: Falls back to the YOLOv8 face detector for strict grouping. Multi-classification determines box overlap, matching against InsightFace extracts.
   
5. **Session Termination**:
   - The instance performs a diff between registered students for that class against the tracked `session_marked` variable.
   - The generator builds separated `Present` / `Absent` CSVs and dumps them in the `attendance_reports/` directory while ending the SQL session globally.

## 🚀 How to Run the Project

### 1. Prerequisites / Requirements
The application leverages robust Python data-science frameworks. Check the `requirements.txt` included in the root folder. You will require Python `3.9`+.

```bash
# Core web architecture
flask
gunicorn

# Recognition libraries
insightface
onnxruntime
opencv-python-headless

# YOLO multi-face detector
ultralytics

# Database & Utilities
bcrypt
python-dotenv
requests
numpy
scipy
Pillow
```

### 2. Environment Installation

Ensure you operate inside an isolated virtual environment (`venv`) to avoid package conflicts.

```bash
# Clone the repository
git clone <repository_url>
cd face_recognition

# Create a clean virtual environment
python3 -m venv venv
source venv/bin/activate  # (On Windows use: venv\Scripts\activate)

# Install required modules
pip install -r requirements.txt
```

### 3. Run the Backend Application

```bash
# Execute the main Flask wrapper
python3 app.py
```
> Note: Upon the first boot, InsightFace and YOLOv8 will automatically attempt to download the `buffalo_l` and `yolov8n-face.pt` network weights (approx 350MB). Make sure your machine is connected to the internet on the first cold start.

### 4. Viewing the Application
Open a Chromium-base / modern browser of your choice and navigate to:
```text
http://127.0.0.1:5000/
```

- **Admin Account**: Configure the admin directly during initial setup or use the default seeder.
- **Faculty Accounts**: Auto-generated by Admin. Faculty accesses classes dynamically when their `Timetable` aligns perfectly with current time conditions.

---
### 🖥️ Hardware Note
The inference application gracefully degrades and performs operations on CPU if `onnxruntime-gpu` and CUDA accelerators aren't detected. However, for large group classrooms (30+ students), it is highly recommended to run this project on an Nvidia CUDA-compatible GPU.
