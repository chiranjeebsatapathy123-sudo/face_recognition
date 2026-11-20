import time
import numpy as np
from .liveness import LivenessDetector
from .emotion import EmotionDetector

class TrackedFace:
    def __init__(self, face_id, bbox, label="Scanning...", confidence=0.0, landmarks=None):
        self.face_id = face_id
        # Raw box
        self.bbox = np.array(bbox, dtype=np.float32) # [x, y, w, h]
        # Smoothed box for buttery animations
        self.smooth_bbox = np.array(bbox, dtype=np.float32)
        self.landmarks = landmarks or []
        self.label = label
        self.confidence = confidence
        self.is_known = False

        self.last_seen = time.time()
        self.first_seen = time.time()
        self.frames_tracked = 1

        # Liveness & Emotion Telemetry
        self.is_live = True
        self.liveness_score = 0.85
        self.liveness_msg = "LIVENESS: VERIFIED"
        self.emotion = "FOCUSED"

        # Animation states: SEARCHING, SCANNING, VERIFIED, COOLDOWN, UNKNOWN, SPOOF
        self.status = "SCANNING"
        self.badge_slide = 0.0 # 0.0 to 1.0 for slide-in animation
        self.scan_line_y = 0.0 # 0.0 to 1.0 for laser sweep
        self.scan_direction = 1.0
        self.reticle_angle = 0.0 # Degrees
        self.target_locked = False
        self.lock_progress = 0.0 # 0.0 to 1.0
        self.attendance_msg = ""
        self.attendance_marked = False

    def update(self, bbox, label, confidence, is_known, landmarks=None, is_live=True, liveness_score=0.9, emotion="FOCUSED", alpha=0.35):
        self.last_seen = time.time()
        self.frames_tracked += 1
        if landmarks:
            self.landmarks = landmarks

        self.is_live = is_live
        self.liveness_score = liveness_score
        self.liveness_msg = "LIVE HUMAN" if is_live else "SPOOF DETECTED"
        self.emotion = emotion

        # Smooth bbox lerp (Linear Interpolation)
        raw = np.array(bbox, dtype=np.float32)
        self.bbox = raw
        self.smooth_bbox = self.smooth_bbox * (1.0 - alpha) + raw * alpha

        if not is_live:
            self.status = "SPOOF"
            return

        # Update label with hysteresis
        if is_known:
            self.label = label
            self.confidence = 0.7 * self.confidence + 0.3 * confidence
            self.is_known = True
            self.lock_progress = min(1.0, self.lock_progress + 0.15)
            if self.lock_progress >= 0.8:
                self.target_locked = True
                self.status = "VERIFIED" if not self.attendance_marked else "COOLDOWN"
        else:
            if not self.target_locked:
                self.label = "Analyzing..." if confidence > 0.4 else "Unknown"
                self.confidence = confidence
                self.is_known = False
                self.status = "UNKNOWN" if self.frames_tracked > 10 else "SCANNING"

    def advance_animation(self, dt=0.033):
        # Rotate HUD targeting reticle
        self.reticle_angle = (self.reticle_angle + 120.0 * dt) % 360.0

        # Laser sweep animation
        self.scan_line_y += self.scan_direction * 1.5 * dt
        if self.scan_line_y > 1.0:
            self.scan_line_y = 1.0
            self.scan_direction = -1.0
        elif self.scan_line_y < 0.0:
            self.scan_line_y = 0.0
            self.scan_direction = 1.0

        # Badge slide-in smooth animation
        target_slide = 1.0 if (self.is_known or self.status == "UNKNOWN") else 0.0
        self.badge_slide += (target_slide - self.badge_slide) * min(1.0, 10.0 * dt)


class FaceTracker:
    def __init__(self, max_missing_time=1.2, iou_threshold=0.25):
        self.max_missing_time = max_missing_time
        self.iou_threshold = iou_threshold
        self.faces = {} # face_id -> TrackedFace
        self.next_id = 1
        self.last_tick = time.time()
        self.liveness_detector = LivenessDetector()
        self.emotion_detector = EmotionDetector()

    def _calc_iou(self, boxA, boxB):
        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])
        xB = min(boxA[0] + boxA[2], boxB[0] + boxB[2])
        yB = min(boxA[1] + boxA[3], boxB[1] + boxB[3])

        interArea = max(0, xB - xA) * max(0, yB - yA)
        boxAArea = boxA[2] * boxA[3]
        boxBArea = boxB[2] * boxB[3]
        unionArea = boxAArea + boxBArea - interArea
        return interArea / float(unionArea) if unionArea > 0 else 0

    def update(self, detected_bboxes, recognitions, landmarks_list=None):
        """
        detected_bboxes: list of [x, y, w, h]
        recognitions: list of (label, confidence, is_known)
        landmarks_list: optional list of 5 landmark coordinates
        """
        now = time.time()
        dt = max(0.001, min(0.1, now - self.last_tick))
        self.last_tick = now

        matched_tracks = set()
        matched_detections = set()

        if landmarks_list is None:
            landmarks_list = [None] * len(detected_bboxes)

        # Match existing faces
        for d_idx, bbox in enumerate(detected_bboxes):
            best_iou = 0.0
            best_id = None
            for f_id, face in self.faces.items():
                if f_id in matched_tracks:
                    continue
                iou = self._calc_iou(bbox, face.bbox)
                if iou > best_iou:
                    best_iou = iou
                    best_id = f_id

            if best_iou >= self.iou_threshold and best_id is not None:
                lbl, conf, is_k = recognitions[d_idx]
                lm = landmarks_list[d_idx] if d_idx < len(landmarks_list) else None
                is_live, live_score, live_reason = self.liveness_detector.update(best_id, bbox, lm)
                emotion, _ = self.emotion_detector.analyze(lm, bbox)
                self.faces[best_id].update(bbox, lbl, conf, is_k, landmarks=lm, is_live=is_live, liveness_score=live_score, emotion=emotion)
                matched_tracks.add(best_id)
                matched_detections.add(d_idx)

        # Create new tracks for unmatched detections
        for d_idx, bbox in enumerate(detected_bboxes):
            if d_idx not in matched_detections:
                lbl, conf, is_k = recognitions[d_idx]
                lm = landmarks_list[d_idx] if d_idx < len(landmarks_list) else None
                face = TrackedFace(self.next_id, bbox, lbl, conf, landmarks=lm)
                face.is_known = is_k
                is_live, live_score, live_reason = self.liveness_detector.update(self.next_id, bbox, lm)
                emotion, _ = self.emotion_detector.analyze(lm, bbox)
                face.is_live = is_live
                face.liveness_score = live_score
                face.emotion = emotion
                self.faces[self.next_id] = face
                matched_tracks.add(self.next_id)
                self.next_id += 1

        # Purge stale tracks and advance animations
        to_del = []
        for f_id, face in self.faces.items():
            if now - face.last_seen > self.max_missing_time:
                to_del.append(f_id)
            else:
                face.advance_animation(dt)

        for f_id in to_del:
            del self.faces[f_id]

        self.liveness_detector.cleanup(list(self.faces.keys()))
        return list(self.faces.values())
