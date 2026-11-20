import cv2
import time
import argparse
import numpy as np

from attendance_engine.db import AttendanceDB
from attendance_engine.recognizer import HybridFaceRecognizer
from attendance_engine.tracker import FaceTracker
from attendance_engine.voice import announce_attendance
from hud_renderer.cyber_hud import CyberHUDRenderer

def run_hud(source=0):
    print("==================================================================")
    print(" 🚀 3D CYBER BIOMETRIC ATTENDANCE SYSTEM - DESKTOP HUD")
    print(" Controls:")
    print("   [C] Toggle 3D Perspective Box")
    print("   [M] Toggle 3D Biometric Facial Mesh")
    print("   [R] Toggle Rotating Reticles")
    print("   [L] Toggle Laser Scan")
    print("   [S] Save Snapshot")
    print("   [Q] Quit")
    print("==================================================================")

    db = AttendanceDB()
    recognizer = HybridFaceRecognizer()
    tracker = FaceTracker()
    hud = CyberHUDRenderer()

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(f"Warning: Could not open video source {source}. Attempting simulation mode...")
        simulated = True
    else:
        simulated = False

    latest_event = None
    tick = 0.0

    cv2.namedWindow("3D Cyber Biometric Attendance System", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("3D Cyber Biometric Attendance System", 1024, 768)

    while True:
        tick += 0.03
        if simulated or not cap.isOpened():
            # Simulated tech feed
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            for gx in range(0, 640, 40):
                cv2.line(frame, (gx, 0), (gx, 480), (25, 25, 30), 1)
            for gy in range(0, 480, 40):
                cv2.line(frame, (0, gy), (640, gy), (25, 25, 30), 1)

            cx = int(320 + 90 * np.sin(tick * 0.8))
            cy = int(240 + 50 * np.cos(tick * 0.6))
            w, h = 130, 130
            x, y = cx - w // 2, cy - h // 2
            cv2.ellipse(frame, (cx, cy), (55, 65), 0, 0, 360, (70, 70, 75), -1)
            detected_bboxes = [(x, y, w, h)]
            recognitions = [("Chiru", 0.98, True)]
        else:
            ret, frame = cap.read()
            if not ret:
                print("Failed to grab frame.")
                break

            detected_bboxes, landmarks_list = recognizer.detect_faces_with_landmarks(frame)
            recognitions = []
            for (x, y, w, h) in detected_bboxes:
                pad = 10
                fx = max(0, x - pad)
                fy = max(0, y - pad)
                fw = min(frame.shape[1] - fx, w + 2 * pad)
                fh = min(frame.shape[0] - fy, h + 2 * pad)
                face_crop = frame[fy:fy+fh, fx:fx+fw]

                label, conf, is_known = recognizer.predict(face_crop)
                recognitions.append((label, conf, is_known))

        tracked_faces = tracker.update(detected_bboxes, recognitions, landmarks_list=landmarks_list if 'landmarks_list' in locals() else None)

        # Handle Attendance Logic
        for face in tracked_faces:
            if face.is_known and face.confidence >= 0.70 and face.is_live and not face.attendance_marked:
                success, msg, record = db.mark_attendance(face.label, confidence=face.confidence, cooldown_minutes=5)
                face.attendance_msg = msg
                if success and record:
                    face.attendance_marked = True
                    face.status = "VERIFIED"
                    latest_event = record
                    print(f"✅ Attendance Recorded: {face.label} ({int(face.confidence*100)}%)")
                    announce_attendance(face.label)
                else:
                    face.status = "COOLDOWN"

        # Render 3D HUD
        rendered = hud.render(frame, tracked_faces, latest_log=latest_event)

        cv2.imshow("3D Cyber Biometric Attendance System", rendered)
        key = cv2.waitKey(1) & 0xFF

        if key == ord('q') or key == 27:
            break
        elif key == ord('c'):
            hud.show_3d_cube = not hud.show_3d_cube
            print(f"3D Perspective Cube: {'ON' if hud.show_3d_cube else 'OFF'}")
        elif key == ord('m'):
            hud.show_mesh = not hud.show_mesh
            print(f"3D Facial Mesh: {'ON' if hud.show_mesh else 'OFF'}")
        elif key == ord('r'):
            hud.show_reticle = not hud.show_reticle
            print(f"Rotating Reticle: {'ON' if hud.show_reticle else 'OFF'}")
        elif key == ord('l'):
            hud.show_laser = not hud.show_laser
            print(f"Laser Scan: {'ON' if hud.show_laser else 'OFF'}")
        elif key == ord('s'):
            filename = f"snapshot_{int(time.time())}.jpg"
            cv2.imwrite(filename, rendered)
            print(f"Snapshot saved: {filename}")

    if cap.isOpened():
        cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="3D Cyber Biometric Attendance Desktop HUD")
    parser.add_argument("--source", default=0, help="Webcam index (0) or IP Camera Stream URL")
    args = parser.parse_args()

    src = int(args.source) if str(args.source).isdigit() else args.source
    run_hud(src)
