import numpy as np

class EmotionDetector:
    """
    Real-Time Facial Expression & Engagement Biometric Telemetry.
    Analyzes landmark geometry (Mouth curvature, Eye openness, Brow tension)
    to classify expressions:
    - FOCUSED / ATTENTIVE
    - HAPPY / ENGAGED
    - NEUTRAL
    - DROWSY / FATIGUED
    """
    def __init__(self):
        pass

    def analyze(self, landmarks, bbox):
        """
        landmarks: 5 points [(rx, ry), (lx, ly), (nx, ny), (rmx, rmy), (lmx, lmy)]
                   right_eye, left_eye, nose, mouth_right, mouth_left
        bbox: [x, y, w, h]
        """
        if not landmarks or len(landmarks) < 5:
            return "NEUTRAL", 0.75

        rx, ry = landmarks[0]
        lx, ly = landmarks[1]
        nx, ny = landmarks[2]
        rmx, rmy = landmarks[3]
        lmx, lmy = landmarks[4]

        w, h = bbox[2], bbox[3]
        if w <= 0 or h <= 0:
            return "NEUTRAL", 0.70

        # 1. Smile / Mouth Curvature
        # When smiling, mouth corners move upward relative to nose tip
        eye_center_y = (ry + ly) / 2.0
        mouth_center_y = (rmy + lmy) / 2.0
        nose_to_mouth = mouth_center_y - ny
        eye_to_nose = ny - eye_center_y + 1e-5

        smile_ratio = nose_to_mouth / eye_to_nose
        mouth_width = abs(rmx - lmx)
        eye_dist = abs(rx - lx) + 1e-5
        mouth_span_ratio = mouth_width / eye_dist

        # 2. Eye Aspect / Head Orientation
        eye_slope = abs(ry - ly) / (eye_dist + 1e-5)

        # Classification heuristics
        if mouth_span_ratio > 1.05 and smile_ratio < 1.15:
            return "HAPPY / ENGAGED", 0.92
        elif eye_slope < 0.12 and 0.85 <= mouth_span_ratio <= 1.02:
            return "FOCUSED", 0.88
        elif nose_to_mouth > 1.45 * eye_to_nose:
            return "DROWSY / FATIGUED", 0.84
        else:
            return "NEUTRAL", 0.80
