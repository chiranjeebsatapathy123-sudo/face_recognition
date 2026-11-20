import cv2
import numpy as np
import time
from .effects import (
    draw_3d_perspective_box,
    draw_rotating_reticle,
    draw_corner_brackets,
    draw_laser_scan,
    draw_synthetic_face_mesh
)

class CyberHUDRenderer:
    # Color palette (BGR format for OpenCV)
    CYAN = (245, 220, 0)       # Searching / Scanning
    GREEN = (60, 255, 120)     # Verified / Attendance Marked
    AMBER = (0, 185, 255)      # Cooldown / Monitored
    RED = (50, 50, 255)        # Unknown / Alert / Banned
    GOLD = (0, 215, 255)       # VIP Priority Executive
    WHITE = (240, 240, 240)
    DARK_BG = (20, 25, 30)

    def __init__(self, show_3d_cube=True, show_mesh=True, show_reticle=True, show_laser=True):
        self.show_3d_cube = show_3d_cube
        self.show_mesh = show_mesh
        self.show_reticle = show_reticle
        self.show_laser = show_laser
        self.fps = 0.0
        self._fps_time = time.time()
        self._frame_count = 0
        self.theme = "cyan"
        self.accent_color = self.CYAN

    def set_theme(self, theme_name):
        t = str(theme_name).lower()
        if t == "matrix":
            self.theme = "matrix"
            self.accent_color = (40, 255, 60)
        elif t == "synthwave":
            self.theme = "synthwave"
            self.accent_color = (220, 50, 255)
        elif t == "amber":
            self.theme = "amber"
            self.accent_color = (0, 185, 255)
        else:
            self.theme = "cyan"
            self.accent_color = self.CYAN
        return self.theme

    def _update_fps(self):
        self._frame_count += 1
        now = time.time()
        diff = now - self._fps_time
        if diff >= 0.5:
            self.fps = round(self._frame_count / diff, 1)
            self._frame_count = 0
            self._fps_time = now

    def render(self, frame, tracked_faces, latest_log=None, qr_info=None):
        """
        Renders the entire futuristic 3D HUD on the camera frame.
        """
        self._update_fps()
        h, w = frame.shape[:2]

        # 1. Global Viewport Border & Sci-Fi Elements
        self._draw_viewport_hud(frame, w, h, len(tracked_faces), latest_log)

        # 2. Render 2-Factor QR Badge overlay if detected
        if qr_info and qr_info.get("bbox") is not None:
            self._draw_qr_hud(frame, qr_info)

        # 3. Render each tracked face
        for face in tracked_faces:
            self._draw_face_hud(frame, face)

        return frame

    def _draw_qr_hud(self, frame, qr_info):
        pts = qr_info.get("bbox")
        if pts is not None and len(pts) > 0:
            pts_int = pts.reshape((-1, 1, 2)).astype(np.int32)
            is_match = qr_info.get("is_2fa_match", False)
            is_mismatch = qr_info.get("is_mismatch", False)
            color = self.GREEN if is_match else (self.RED if is_mismatch else self.CYAN)
            cv2.polylines(frame, [pts_int], True, color, 2)
            
            top_pt = pts_int[0][0]
            name = qr_info.get("name", "BADGE")
            if is_match:
                tag = f"2FA VERIFIED // {name}"
            elif is_mismatch:
                tag = f"2FA FRAUD ALERT // MISMATCH {name}"
            else:
                tag = f"QR BADGE // {name}"

            cv2.putText(frame, tag, (int(top_pt[0]), max(25, int(top_pt[1]) - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

    def _draw_viewport_hud(self, frame, w, h, target_count, latest_log):
        # Frame Outer Brackets
        margin = 15
        bracket_size = 35
        # Top-Left
        cv2.line(frame, (margin, margin), (margin + bracket_size, margin), self.accent_color, 2)
        cv2.line(frame, (margin, margin), (margin, margin + bracket_size), self.accent_color, 2)
        # Top-Right
        cv2.line(frame, (w - margin, margin), (w - margin - bracket_size, margin), self.accent_color, 2)
        cv2.line(frame, (w - margin, margin), (w - margin, margin + bracket_size), self.accent_color, 2)
        # Bottom-Left
        cv2.line(frame, (margin, h - margin), (margin + bracket_size, h - margin), self.accent_color, 2)
        cv2.line(frame, (margin, h - margin), (margin, h - margin - bracket_size), self.accent_color, 2)
        # Bottom-Right
        cv2.line(frame, (w - margin, h - margin), (w - margin - bracket_size, h - margin), self.accent_color, 2)
        cv2.line(frame, (w - margin, h - margin), (w - margin, h - margin - bracket_size), self.accent_color, 2)

        # Top Header Banner
        header_h = 32
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, header_h), self.DARK_BG, -1)
        cv2.addWeighted(overlay, 0.70, frame, 0.30, 0, frame)

        # Header Text
        cv2.putText(frame, f"BIOMETRIC ATTENDANCE AI 3D [{self.theme.upper()}]", (25, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.52, self.accent_color, 2)
        cv2.putText(frame, f"FPS: {self.fps}", (w - 110, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.GREEN, 1)
        cv2.putText(frame, f"TARGETS: {target_count}", (w - 240, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.WHITE, 1)
        cv2.line(frame, (0, header_h), (w, header_h), self.accent_color, 1)

        # Bottom Footer Ticker
        footer_y = h - 28
        overlay_foot = frame.copy()
        cv2.rectangle(overlay_foot, (0, footer_y), (w, h), self.DARK_BG, -1)
        cv2.addWeighted(overlay_foot, 0.75, frame, 0.25, 0, frame)

        msg = "SYSTEM ACTIVE // REAL-TIME 3D FACIAL MOTION TRACKING"
        if latest_log:
            name = latest_log.get('user_name', 'Unknown')
            t = latest_log.get('time', '')
            msg = f"RECENT ATTENDANCE: {name.upper()} AT {t} // STATUS: VERIFIED"

        cv2.putText(frame, msg, (25, h - 9), cv2.FONT_HERSHEY_SIMPLEX, 0.45, self.accent_color, 1)
        cv2.line(frame, (0, footer_y), (w, footer_y), self.accent_color, 1)

    def _draw_face_hud(self, frame, face):
        x, y, w, h = [int(v) for v in face.smooth_bbox]
        cx, cy = x + w // 2, y + h // 2

        clearance = getattr(face, 'clearance', 'STANDARD').upper()

        # Pick accent color based on status and clearance
        if clearance == "BANNED" or face.status == "BANNED":
            color = self.RED
        elif clearance == "VIP":
            color = self.GOLD if face.status in ("VERIFIED", "TRACKED", "COOLDOWN") else self.CYAN
        elif clearance == "MONITORED":
            color = self.AMBER
        elif face.status == "SPOOF":
            color = self.RED
        elif face.status == "VERIFIED":
            color = self.GREEN
        elif face.status == "COOLDOWN":
            color = self.AMBER
        elif face.status == "UNKNOWN":
            color = self.RED
        else:
            color = self.CYAN

        # 1. 3D Wireframe Perspective Box
        if self.show_3d_cube:
            draw_3d_perspective_box(frame, x, y, w, h, color, depth_ratio=0.20, thickness=2)
        else:
            draw_corner_brackets(frame, (x, y), (x + w, y + h), color, length=int(w * 0.2), thickness=2)

        # 2. Dual Rotating Reticle
        if self.show_reticle:
            radius = max(w, h) // 2 + 10
            draw_rotating_reticle(frame, (cx, cy), radius, face.reticle_angle, color)

        # 3. Biometric Synthetic Face Mesh
        if self.show_mesh:
            draw_synthetic_face_mesh(frame, x, y, w, h, color)

        # 4. Animated Laser Scan
        if self.show_laser:
            draw_laser_scan(frame, x, y, w, h, face.scan_line_y, color)

        # 5. Sliding Holographic Identity Card
        self._draw_identity_badge(frame, face, x, y, w, h, color)

    def _draw_identity_badge(self, frame, face, x, y, w, h, color):
        slide = face.badge_slide
        if slide <= 0.05:
            return

        # Target badge dimensions
        badge_w = 230
        badge_h = 96
        badge_x = int(x + w + 15 * slide)
        badge_y = max(35, y)

        # Prevent badge from drawing outside right boundary
        if badge_x + badge_w > frame.shape[1] - 10:
            badge_x = max(10, x - badge_w - 15)

        # Glassmorphic semi-transparent background
        overlay = frame.copy()
        cv2.rectangle(overlay, (badge_x, badge_y), (badge_x + badge_w, badge_y + badge_h), self.DARK_BG, -1)
        cv2.addWeighted(overlay, 0.75 * slide, frame, 1.0 - (0.75 * slide), 0, frame)

        # Cyber border and left accent bar
        cv2.rectangle(frame, (badge_x, badge_y), (badge_x + badge_w, badge_y + badge_h), color, 1)
        cv2.line(frame, (badge_x, badge_y), (badge_x, badge_y + badge_h), color, 4)

        # Connecting cyber line from face box to badge
        conn_x_face = x + w if badge_x > x else x
        cv2.line(frame, (conn_x_face, y + 20), (badge_x, badge_y + 20), color, 1)

        # Texts
        name_str = face.label.upper()
        cv2.putText(frame, name_str, (badge_x + 10, badge_y + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.60, self.WHITE, 2)

        # Match confidence & Liveness bar
        conf_pct = int(face.confidence * 100)
        live_pct = int(getattr(face, 'liveness_score', 0.9) * 100)
        telemetry_str = f"MATCH: {conf_pct}% // LIVE: {live_pct}%"
        cv2.putText(frame, telemetry_str, (badge_x + 10, badge_y + 42), cv2.FONT_HERSHEY_SIMPLEX, 0.38, color, 1)

        # Mood / Emotion telemetry
        emotion_str = f"MOOD: [{getattr(face, 'emotion', 'FOCUSED')}]"
        cv2.putText(frame, emotion_str, (badge_x + 10, badge_y + 60), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (200, 240, 255), 1)

        # Status line & Clearance banner
        clearance = getattr(face, 'clearance', 'STANDARD').upper()
        if clearance == "BANNED" or face.status == "BANNED":
            status_text = "⚠ ACCESS REVOKED: BANNED ⚠"
        elif clearance == "VIP" and face.status in ("VERIFIED", "COOLDOWN"):
            status_text = "★ VIP CLEARANCE: GRANTED ★"
        elif clearance == "MONITORED":
            status_text = "👁 MONITORED: AUDIT LOGGED"
        elif face.status == "SPOOF":
            status_text = "ALERT: SPOOF DETECTED"
        elif face.status == "VERIFIED":
            status_text = "ATTENDANCE: RECORDED"
        elif face.status == "COOLDOWN":
            status_text = "STATUS: PRESENT (COOLDOWN)"
        elif face.status == "UNKNOWN":
            status_text = "STATUS: UNREGISTERED"
        else:
            status_text = "STATUS: SCANNING..."

        cv2.putText(frame, status_text, (badge_x + 10, badge_y + 82), cv2.FONT_HERSHEY_SIMPLEX, 0.36, color, 1)
