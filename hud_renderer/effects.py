import cv2
import numpy as np
import math

def draw_corner_brackets(img, pt1, pt2, color, length=20, thickness=2):
    """
    Draws sci-fi angled corner brackets around a rectangular bounding box.
    """
    x1, y1 = pt1
    x2, y2 = pt2

    length = min(length, (x2 - x1) // 3, (y2 - y1) // 3)
    if length <= 0:
        return

    # Top-Left
    cv2.line(img, (x1, y1), (x1 + length, y1), color, thickness)
    cv2.line(img, (x1, y1), (x1, y1 + length), color, thickness)

    # Top-Right
    cv2.line(img, (x2, y1), (x2 - length, y1), color, thickness)
    cv2.line(img, (x2, y1), (x2, y1 + length), color, thickness)

    # Bottom-Left
    cv2.line(img, (x1, y2), (x1 + length, y2), color, thickness)
    cv2.line(img, (x1, y2), (x1, y2 - length), color, thickness)

    # Bottom-Right
    cv2.line(img, (x2, y2), (x2 - length, y2), color, thickness)
    cv2.line(img, (x2, y2), (x2, y2 - length), color, thickness)

def draw_rotating_reticle(img, center, radius, angle_deg, color, thickness=1):
    """
    Draws dual rotating concentric targeting rings with segmented ticks.
    """
    cx, cy = int(center[0]), int(center[1])
    rad = int(radius)
    if rad <= 5:
        return

    # Outer segmented arc
    rad_outer = rad + 12
    for offset in [0, 90, 180, 270]:
        start_a = angle_deg + offset
        end_a = start_a + 55
        cv2.ellipse(img, (cx, cy), (rad_outer, rad_outer), 0, start_a, end_a, color, thickness)

    # Inner dashed counter-rotating circle
    rad_inner = max(10, rad - 8)
    for offset in range(0, 360, 30):
        tick_a = math.radians(-angle_deg * 1.5 + offset)
        p1 = (int(cx + (rad_inner - 4) * math.cos(tick_a)), int(cy + (rad_inner - 4) * math.sin(tick_a)))
        p2 = (int(cx + (rad_inner + 4) * math.cos(tick_a)), int(cy + (rad_inner + 4) * math.sin(tick_a)))
        cv2.line(img, p1, p2, color, 1)

    # Crosshair pointers
    ch_len = 8
    cv2.line(img, (cx - rad - ch_len, cy), (cx - rad + 2, cy), color, 1)
    cv2.line(img, (cx + rad - 2, cy), (cx + rad + ch_len, cy), color, 1)
    cv2.line(img, (cx, cy - rad - ch_len), (cx, cy - rad + 2), color, 1)
    cv2.line(img, (cx, cy + rad - 2), (cx, cy + rad + ch_len), color, 1)

def draw_3d_perspective_box(img, x, y, w, h, color, depth_ratio=0.22, thickness=2):
    """
    Draws a 3D isometric perspective wireframe cube around the face.
    """
    dx = int(w * depth_ratio * 0.7)
    dy = int(-h * depth_ratio * 0.5)

    # Front plane
    f_p1 = (x, y)
    f_p2 = (x + w, y)
    f_p3 = (x + w, y + h)
    f_p4 = (x, y + h)

    # Back plane
    b_p1 = (x + dx, y + dy)
    b_p2 = (x + w + dx, y + dy)
    b_p3 = (x + w + dx, y + h + dy)
    b_p4 = (x + dx, y + h + dy)

    # Semi-transparent back lines
    overlay = img.copy()
    cv2.polylines(overlay, [np.array([b_p1, b_p2, b_p3, b_p4], np.int32)], True, color, 1)
    cv2.line(overlay, f_p1, b_p1, color, 1)
    cv2.line(overlay, f_p2, b_p2, color, 1)
    cv2.line(overlay, f_p3, b_p3, color, 1)
    cv2.line(overlay, f_p4, b_p4, color, 1)

    # Blend rear box
    cv2.addWeighted(overlay, 0.45, img, 0.55, 0, img)

    # Front plane with solid glow
    draw_corner_brackets(img, f_p1, f_p3, color, length=int(w * 0.25), thickness=thickness)

def draw_laser_scan(img, x, y, w, h, progress, color):
    """
    Draws an animated horizontal laser sweep line with gradient glow across the face.
    """
    scan_y = int(y + h * progress)
    if scan_y < 0 or scan_y >= img.shape[0]:
        return

    # Glow strip
    glow_h = 6
    y_min = max(0, scan_y - glow_h)
    y_max = min(img.shape[0], scan_y + glow_h)
    x_min = max(0, x - 5)
    x_max = min(img.shape[1], x + w + 5)

    overlay = img.copy()
    cv2.rectangle(overlay, (x_min, y_min), (x_max, y_max), color, -1)
    cv2.addWeighted(overlay, 0.35, img, 0.65, 0, img)

    # Solid center laser line
    cv2.line(img, (x_min, scan_y), (x_max, scan_y), (255, 255, 255), 1)

def draw_synthetic_face_mesh(img, x, y, w, h, color):
    """
    Draws a synthetic 3D biometric landmark mesh over the face box.
    """
    # Relative landmark nodes based on canonical facial geometry
    landmarks = [
        # Jawline / Chin
        (x + w * 0.15, y + h * 0.70),
        (x + w * 0.30, y + h * 0.88),
        (x + w * 0.50, y + h * 0.96), # Chin point
        (x + w * 0.70, y + h * 0.88),
        (x + w * 0.85, y + h * 0.70),
        # Eyebrows
        (x + w * 0.22, y + h * 0.28),
        (x + w * 0.38, y + h * 0.25),
        (x + w * 0.62, y + h * 0.25),
        (x + w * 0.78, y + h * 0.28),
        # Eyes
        (x + w * 0.30, y + h * 0.36), # Left eye
        (x + w * 0.70, y + h * 0.36), # Right eye
        # Nose bridge and tip
        (x + w * 0.50, y + h * 0.32),
        (x + w * 0.50, y + h * 0.50),
        (x + w * 0.42, y + h * 0.58),
        (x + w * 0.58, y + h * 0.58),
        # Mouth
        (x + w * 0.35, y + h * 0.74),
        (x + w * 0.50, y + h * 0.71),
        (x + w * 0.65, y + h * 0.74),
        (x + w * 0.50, y + h * 0.79)
    ]

    pts = [(int(px), int(py)) for px, py in landmarks]

    # Connections for wireframe polygon mesh
    mesh_edges = [
        (0, 1), (1, 2), (2, 3), (3, 4), # Chin arc
        (5, 6), (7, 8),                 # Brows
        (5, 9), (6, 9), (7, 10), (8, 10),# Eye-Brow
        (9, 11), (10, 11),              # Eye-Nose top
        (11, 12), (12, 13), (12, 14), (13, 14), # Nose
        (13, 15), (14, 17), (12, 16),   # Nose to mouth
        (15, 16), (16, 17), (17, 18), (18, 15), # Mouth
        (18, 2), (15, 1), (17, 3)        # Mouth to jaw
    ]

    overlay = img.copy()
    for e1, e2 in mesh_edges:
        if 0 <= e1 < len(pts) and 0 <= e2 < len(pts):
            cv2.line(overlay, pts[e1], pts[e2], color, 1)

    for p in pts:
        cv2.circle(overlay, p, 2, (255, 255, 255), -1)

    cv2.addWeighted(overlay, 0.40, img, 0.60, 0, img)
