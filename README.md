# 🚀 NEXUS 3D: Biometric Attendance System & Motion HUD

An AI-driven **Attendance System** featuring **Real-time 3D Motion Animation HUD**, **PyTorch Face Recognition**, **SQLite Database Logging**, and an **Interactive Three.js 3D Holographic Web Dashboard**.

---

## ✨ Key Features

### 1. 📋 Automated Attendance Management System
- **Real-Time Attendance Marking**: Automatically identifies individuals (`Chiru`, `Rahul`, `Sourav`, etc.) with confidence scoring.
- **Smart Cooldown Engine**: Prevents duplicate attendance entries (configurable 5-minute cooldown timer with visual on-screen countdown).
- **SQLite Database (`attendance.db`) & CSV Backup**: Full audit trail storing names, timestamps, dates, confidence scores, and attendance statuses.
- **Voice / Audio Feedback**: Native Windows text-to-speech audio confirmation ("Attendance confirmed for Chiru. Welcome!") + Web Audio chimes.
- **Daily Analytics**: Live metrics for Total Registered Profiles, Present Today, Absent Count, Attendance Rate %, and Daily Logs.

### 2. 🥽 3D Motion Animation & Cyber HUD Overlay
- **3D Isometric Perspective Bounding Box**: Depth-projected wireframe cube that dynamically reacts to face position and motion.
- **Dual Rotating Targeting Reticles**: Concentric sci-fi HUD rings rotating with segmented ticks and angle velocity.
- **Animated Laser Sweep**: Vertical laser beam oscillating with gradient glow and edge sparks.
- **3D Biometric Facial Mesh**: Wireframe polygon landmark overlay connecting estimated facial nodes (brows, eyes, nose, mouth, chin).
- **Motion-Smoothed Face Tracking**: Continuous linear interpolation and spring damping to eliminate bounding box jitter.
- **Sliding Holographic Identity Badges**: Slides in with easing curves displaying name, match %, and verification badge.

### 3. 🌐 Interactive 3D Web Dashboard & Control Center
- **Interactive Three.js 3D Hologram**: Parametric 3D particle cyber-face with mouse parallax rotation, holographic sweep plane, and green verification pulse.
- **Live Video Streaming**: High-framerate MJPEG stream with dynamic HUD overlays.
- **Real-time HUD Toggles**: Turn on/off 3D Cube, Facial Mesh, Reticles, and Laser Scan on the fly.
- **Face Enrollment Studio**: Register new faces via webcam snapshot or image upload with instant KNN dynamic training.
- **1-Click CSV Export**: Download attendance reports anytime.

---

## 🛠️ Quick Start

### 1. Launch the 3D Web Dashboard (Recommended)
```bash
python app.py
```
Open your browser and navigate to:
```
http://127.0.0.1:5000
```
- **Live Monitor**: Live camera feed with 3D HUD + interactive Three.js 3D hologram.
- **Attendance Logs**: Table of all attendance records with live search and CSV export.
- **Enroll Profile**: Add new employees/students with camera snapshot or file upload.

### 2. Run the Desktop OpenCV Cyber HUD
For full-screen or native windowed camera mode:
```bash
python run_attendance_hud.py
```
**Interactive Hotkeys:**
- `[C]` - Toggle 3D Perspective Cube
- `[M]` - Toggle 3D Biometric Facial Mesh
- `[R]` - Toggle Rotating Reticles
- `[L]` - Toggle Laser Scan Sweep
- `[S]` - Capture & Save Snapshot
- `[Q]` - Quit

### 3. Export Attendance Records to CSV
```bash
python export_records.py --out daily_attendance.csv
```

---

## 📁 Project Architecture
```
face_recognition/
├── attendance_engine/
│   ├── db.py               # SQLite database & CSV logger, user management, metrics
│   ├── recognizer.py       # YuNet Face Detector + PyTorch CNN + KNN Hybrid Recognizer
│   ├── tracker.py          # Multi-face tracking with exponential smoothing & animations
│   └── voice.py            # Asynchronous Windows TTS audio announcement
├── hud_renderer/
│   ├── effects.py          # 3D isometric projection, rotating reticles, laser scan, mesh
│   └── cyber_hud.py        # Cyberpunk HUD compositor & sliding holographic identity cards
├── models/
│   ├── face_detection_yunet_2023mar.onnx # High-speed YuNet face detection model
│   ├── face_cnn.pt         # Trained PyTorch CNN model (100% accuracy on dataset)
│   ├── knn_model.pkl       # Dynamic classifier for real-time enrolled faces
│   └── label_map.json      # Class index mapping
├── templates/
│   ├── index.html          # Main 3D futuristic dashboard with Three.js
│   ├── records.html        # Historical attendance audit logs & filter
│   └── enroll.html         # Live webcam face enrollment & registration
├── static/
│   ├── css/style.css       # Cyberpunk glassmorphism design & animations
│   └── js/
│       ├── three_hologram.js # Three.js 3D particle face visualizer
│       └── app.js          # Live polling, telemetry updates, audio chimes
├── app.py                  # Flask Web Server with live video streaming
├── run_attendance_hud.py   # Standalone Desktop OpenCV HUD application
├── export_records.py       # Standalone CSV attendance exporter
└── attendance.db           # SQLite database
```
