@echo off
title NEXUS 3D Biometric Attendance Server
color 0b
echo ============================================================
echo   NEXUS 3D: BIOMETRIC ATTENDANCE SYSTEM
echo   Starting Web Dashboard on http://127.0.0.1:5000 ...
echo ============================================================
start "" "http://127.0.0.1:5000"
python app.py
pause
