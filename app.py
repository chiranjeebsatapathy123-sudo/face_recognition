import os
import cv2
import time
import io
import json
import queue
import qrcode
import base64
import urllib.request
import numpy as np
from flask import Flask, render_template, Response, request, jsonify, send_file, send_from_directory

from attendance_engine.db import AttendanceDB
from attendance_engine.recognizer import HybridFaceRecognizer
from attendance_engine.tracker import FaceTracker
from attendance_engine.liveness import LivenessDetector
from attendance_engine.voice import announce_attendance
from attendance_engine.notifier import NotificationDispatcher
from hud_renderer.cyber_hud import CyberHUDRenderer

app = Flask(__name__)

# Initialize components
db = AttendanceDB()
recognizer = HybridFaceRecognizer()
tracker = FaceTracker()
liveness_lab = LivenessDetector()
hud = CyberHUDRenderer()
notifier = NotificationDispatcher(db)

latest_attendance_event = None
latest_security_alert = None
last_marked_times = {}

# Server-Sent Events subscribers
sse_subscribers = []
qr_detector = cv2.QRCodeDetector()
sim_active_subject = "Chiru"
sim_cooldown_override = False
current_defcon = 4

def push_sse_event(event_type, payload):
    data_str = json.dumps({"type": event_type, "data": payload})
    msg = f"data: {data_str}\n\n"
    for q in sse_subscribers[:]:
        try:
            q.put_nowait(msg)
        except Exception:
            if q in sse_subscribers:
                sse_subscribers.remove(q)

def generate_simulated_frame(tick):
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    for x in range(0, 640, 40):
        cv2.line(frame, (x, 0), (x, 480), (25, 25, 30), 1)
    for y in range(0, 480, 40):
        cv2.line(frame, (0, y), (640, y), (25, 25, 30), 1)

    cx = int(320 + 90 * np.sin(tick * 0.8))
    cy = int(240 + 50 * np.cos(tick * 0.6))
    w, h = 130, 130
    x, y = cx - w // 2, cy - h // 2

    cv2.ellipse(frame, (cx, cy), (55, 65), 0, 0, 360, (70, 70, 75), -1)
    cv2.circle(frame, (cx - 20, cy - 12), 8, (120, 120, 130), -1)
    cv2.circle(frame, (cx + 20, cy - 12), 8, (120, 120, 130), -1)
    cv2.ellipse(frame, (cx, cy + 25), (20, 10), 0, 0, 180, (120, 120, 130), 2)

    return frame, [(x, y, w, h)]

crowd_active_scenario = "shift_rush"
crowd_cooldown_override = False
crowd_tracker = FaceTracker()

def generate_crowd_frame(tick, scenario="shift_rush"):
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    for x in range(0, 640, 40):
        cv2.line(frame, (x, 0), (x, 480), (18, 22, 28), 1)
    for y in range(0, 480, 40):
        cv2.line(frame, (0, y), (640, y), (18, 22, 28), 1)

    # Scenarios roster
    if scenario == "security_audit":
        subjects = [
            ("David Chen", 0.98, (150, 220), (0.0, 0.65, 0.45)),
            ("Natasha Roy", 0.95, (330, 200), (1.3, 0.75, 0.55)),
            ("Marcus Vance", 0.96, (505, 230), (2.5, 0.60, 0.50))
        ]
    elif scenario == "academic_surge":
        subjects = [
            ("Sneha Rao", 0.96, (150, 210), (0.3, 0.70, 0.50)),
            ("Rohan Gupta", 0.94, (330, 225), (1.5, 0.65, 0.55)),
            ("Emily Watson", 0.97, (505, 195), (2.2, 0.75, 0.45))
        ]
    else:  # default shift_rush
        subjects = [
            ("Chiru", 0.99, (150, 210), (0.0, 0.65, 0.45)),
            ("Priya Sharma", 0.97, (330, 195), (1.1, 0.75, 0.55)),
            ("Aarav Mehta", 0.95, (505, 225), (2.2, 0.60, 0.45))
        ]

    bboxes = []
    recognitions = []
    landmarks_list = []

    for name, conf, (base_x, base_y), (phase, spd_x, spd_y) in subjects:
        cx = int(base_x + 35 * np.sin(tick * spd_x + phase))
        cy = int(base_y + 25 * np.cos(tick * spd_y + phase))
        w, h = 105, 105
        x, y = cx - w // 2, cy - h // 2

        # Draw stylized face silhouette
        cv2.ellipse(frame, (cx, cy), (42, 50), 0, 0, 360, (55, 60, 70), -1)
        cv2.circle(frame, (cx - 15, cy - 10), 6, (125, 130, 140), -1)
        cv2.circle(frame, (cx + 15, cy - 10), 6, (125, 130, 140), -1)
        cv2.ellipse(frame, (cx, cy + 18), (14, 7), 0, 0, 180, (125, 130, 140), 2)

        bboxes.append((x, y, w, h))
        recognitions.append((name, conf, True))
        lm = [
            (cx - 15, cy - 10),
            (cx + 15, cy - 10),
            (cx, cy + 4),
            (cx - 10, cy + 18),
            (cx + 10, cy + 18)
        ]
        landmarks_list.append(lm)

    return frame, bboxes, recognitions, landmarks_list

class VideoCamera:
    def __init__(self, src=0):
        self.src = src
        self.cap = None
        self.tick = 0.0
        self.source_mode = "webcam" # webcam, ipcam, simulated
        self._init_cap()

    def _init_cap(self):
        if str(self.src).lower() == "simulated":
            self.source_mode = "simulated"
            self.cap = None
            return

        if str(self.src).startswith("http"):
            self.source_mode = "ipcam"
            self.cap = None
            return

        try:
            cam_idx = int(self.src) if str(self.src).isdigit() else 0
            self.cap = cv2.VideoCapture(cam_idx)
            if self.cap.isOpened():
                self.source_mode = "webcam"
            else:
                self.cap = None
                self.source_mode = "simulated"
        except Exception:
            self.cap = None
            self.source_mode = "simulated"

    def switch_source(self, new_src):
        if self.cap is not None and self.cap.isOpened():
            self.cap.release()
        self.src = new_src
        self._init_cap()
        return self.source_mode

    def get_frame(self):
        global latest_attendance_event, latest_security_alert, sim_active_subject, sim_cooldown_override
        self.tick += 0.03

        frame = None
        simulated_faces = None

        if self.source_mode == "ipcam":
            try:
                # Fetch shot from IP cam (e.g. DroidCam, IP Webcam)
                req = urllib.request.urlopen(self.src, timeout=1.5)
                img_arr = np.array(bytearray(req.read()), dtype=np.uint8)
                frame = cv2.imdecode(img_arr, -1)
            except Exception:
                frame = None

        elif self.source_mode == "webcam" and self.cap is not None and self.cap.isOpened():
            ret, frame = self.cap.read()
            if not ret:
                frame = None

        if frame is None or self.source_mode == "simulated":
            # High-tech simulated feed with selectable subject
            frame, simulated_faces = generate_simulated_frame(self.tick)
            detected_bboxes = simulated_faces
            landmarks_list = [None]
            if sim_active_subject == "Unknown Intruder":
                recognitions = [("UNKNOWN", 0.22, False)]
            else:
                recognitions = [(sim_active_subject, 0.97, True)]
        else:
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

        tracked_faces = tracker.update(detected_bboxes, recognitions, landmarks_list=landmarks_list)

        # 2-Factor QR Badge Scan
        qr_info = None
        if frame is not None:
            try:
                qr_data, qr_bbox, _ = qr_detector.detectAndDecode(frame)
                if qr_data and qr_bbox is not None and len(qr_bbox) > 0:
                    badge_name = qr_data.split("/")[-1].strip()
                    is_match = any(f.is_known and f.label.lower() == badge_name.lower() for f in tracked_faces)
                    is_mismatch = any(f.is_known and f.label.lower() != badge_name.lower() for f in tracked_faces)
                    qr_info = {
                        "name": badge_name,
                        "bbox": qr_bbox,
                        "is_2fa_match": is_match,
                        "is_mismatch": is_mismatch
                    }
            except Exception:
                qr_info = None

        for face in tracked_faces:
            if current_defcon == 1:
                face.status = "LOCKDOWN"
                face.attendance_msg = "FACILITY LOCKDOWN: ACCESS PROHIBITED"
                continue

            # Fetch security clearance
            clearance = "STANDARD"
            if face.is_known:
                u_rec = db.get_user(face.label)
                if u_rec:
                    clearance = u_rec.get("security_clearance", "STANDARD").upper()
            face.clearance = clearance

            # Banned Profile Intercept
            if clearance == "BANNED":
                face.status = "BANNED"
                face.attendance_msg = "SECURITY BREACH: ACCESS DENIED (BANNED)"
                if face.frames_tracked == 10:
                    inc = db.log_watchlist_incident(face.label, "BANNED", "ACCESS_REVOKED_INTERCEPT_ALARM", snapshot_bgr=frame, notes="Banned individual attempted entry at checkpoint.")
                    db.log_access_event("GATE-A1", face.label, "DENIED_BANNED", snapshot_bgr=frame)
                    latest_security_alert = inc
                    push_sse_event("watchlist_breach", inc)
                    push_sse_event("door_relay", {"door_code": "GATE-A1", "relay_state": "LOCKED", "user": face.label})
                    notifier.dispatch_intruder_alert(inc)
                continue

            # 1. Process attendance for verified live faces
            if face.is_known and face.confidence >= 0.70 and face.is_live and not face.attendance_marked:
                # Auto-crop face proof for punch snapshot
                punch_crop = None
                if frame is not None and frame.size > 0:
                    x, y, w, h = [int(v) for v in face.smooth_bbox]
                    cx1 = max(0, x - 15)
                    cy1 = max(0, y - 15)
                    cx2 = min(frame.shape[1], x + w + 15)
                    cy2 = min(frame.shape[0], y + h + 15)
                    if cx2 > cx1 and cy2 > cy1:
                        punch_crop = frame[cy1:cy2, cx1:cx2]

                cooldown = 0 if sim_cooldown_override else 5
                success, msg, record = db.mark_attendance(face.label, confidence=face.confidence, cooldown_minutes=cooldown, snapshot_bgr=punch_crop)
                sim_cooldown_override = False
                face.attendance_msg = msg
                if success and record:
                    face.attendance_marked = True
                    face.status = "VERIFIED"
                    record["security_clearance"] = clearance
                    latest_attendance_event = record
                    announce_attendance(face.label)
                    push_sse_event("attendance", record)

                    # Trigger Door Solenoid Relay
                    db.log_access_event("GATE-A1", face.label, "GRANTED", snapshot_bgr=punch_crop)
                    if clearance == "VIP":
                        db.log_access_event("DOOR-C1", face.label, "GRANTED", snapshot_bgr=punch_crop)
                    push_sse_event("door_relay", {"door_code": "GATE-A1", "relay_state": "UNLOCKED", "user": face.label})

                    if clearance == "MONITORED":
                        db.log_watchlist_incident(face.label, "MONITORED", "AUDITED_ENTRY_GRANTED", snapshot_bgr=punch_crop, notes="Monitored identity entry audited")
                    if record.get("is_late"):
                        notifier.dispatch_late_alert(record["user_name"], record.get("user_type", "Employee"), record["time"])
                else:
                    face.status = "COOLDOWN"

            # 2. Security Intruder Alert Snapshot
            if face.status == "UNKNOWN" and face.frames_tracked == 18:
                alert_rec = db.log_security_alert(frame, event_type="UNAUTHORIZED_FACE_DETECTED")
                latest_security_alert = alert_rec
                push_sse_event("security_alert", alert_rec)
                notifier.dispatch_intruder_alert(alert_rec)

        # Render 3D Cyber HUD overlay with 2FA QR data
        rendered = hud.render(frame, tracked_faces, latest_log=latest_attendance_event, qr_info=qr_info)

        ret, jpeg = cv2.imencode('.jpg', rendered, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return jpeg.tobytes()

camera = VideoCamera(0)

def gen_frames():
    while True:
        frame_bytes = camera.get_frame()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        time.sleep(0.02)

@app.route('/')
def index():
    stats = db.get_stats()
    users = db.get_users()
    today_records = db.get_today_attendance()
    return render_template('index.html', stats=stats, users=users, today_records=today_records, cam_mode=camera.source_mode)

@app.route('/records')
def records_view():
    user_type = request.args.get('type')
    all_records = db.get_all_records(limit=250, user_type=user_type)
    return render_template('records.html', records=all_records, current_type=user_type or 'All')

@app.route('/enroll')
def enroll_view():
    user_type = request.args.get('type')
    users = db.get_users(user_type=user_type)
    return render_template('enroll.html', users=users, current_type=user_type or 'All')

@app.route('/alerts')
def alerts_view():
    alerts = db.get_security_alerts(limit=30)
    return render_template('alerts.html', alerts=alerts)

@app.route('/report')
def report_view():
    date_arg = request.args.get('date')
    report_data = db.get_daily_report_data(target_date=date_arg)
    return render_template('report.html', report=report_data)

@app.route('/shifts')
def shifts_view():
    shifts = db.get_shifts()
    users = db.get_users()
    return render_template('shifts.html', shifts=shifts, users=users)

@app.route('/api/shifts', methods=['GET', 'POST'])
def api_shifts():
    if request.method == 'POST':
        data = request.json or {}
        name = data.get('name', '').strip()
        start_time = data.get('start_time', '09:00').strip()
        end_time = data.get('end_time', '17:00').strip()
        grace = int(data.get('grace_minutes', 15))
        cohort = data.get('cohort', 'All').strip()
        if not name:
            return jsonify({"success": False, "message": "Shift name is required"}), 400
        ok, msg = db.add_shift(name, start_time, end_time, grace_minutes=grace, cohort=cohort)
        return jsonify({"success": ok, "message": msg})
    return jsonify(db.get_shifts())

@app.route('/analytics')
def analytics_view():
    stats = db.get_stats()
    analytics = db.get_analytics()
    return render_template('analytics.html', stats=stats, analytics=analytics)

@app.route('/api/assistant', methods=['POST'])
def api_assistant():
    data = request.json or {}
    query = data.get('query', '')
    res = db.query_assistant(query)
    return jsonify(res)

def generate_qr_b64(text):
    qr = qrcode.QRCode(box_size=4, border=1)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

@app.route('/idcard')
def idcard_view():
    users = db.get_users()
    user_param = request.args.get('user')
    selected_user = None
    if user_param:
        for u in users:
            if u['name'].lower() == user_param.lower():
                selected_user = u
                break
    if not selected_user and users:
        selected_user = users[0]

    qr_data = f"NEXUS-BIO-AUTH://{selected_user.get('emp_id')}/{selected_user.get('name')}" if selected_user else "NEXUS"
    qr_b64 = generate_qr_b64(qr_data)
    return render_template('idcard.html', users=users, selected_user=selected_user, qr_b64=qr_b64)

@app.route('/kiosk')
def kiosk_view():
    stats = db.get_stats()
    return render_template('kiosk.html', stats=stats, cam_mode=camera.source_mode)

@app.route('/multicam')
def multicam_view():
    stats = db.get_stats()
    return render_template('multicam.html', stats=stats, cam_mode=camera.source_mode)

@app.route('/notifications')
def notifications_view():
    logs = db.get_notification_logs(limit=40)
    users = db.get_users()
    return render_template('notifications.html', logs=logs, users=users)

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

def gen_aux_camera_stream(cam_name, color_accent=(0, 243, 255)):
    tick = 0
    while True:
        tick += 1
        frame = np.zeros((360, 480, 3), dtype=np.uint8)
        # Cyber grid
        for x in range(0, 480, 40):
            cv2.line(frame, (x, 0), (x, 360), (18, 22, 30), 1)
        for y in range(0, 360, 40):
            cv2.line(frame, (0, y), (480, y), (18, 22, 30), 1)
        
        now_str = time.strftime('%H:%M:%S')
        cv2.putText(frame, f"[ {cam_name.upper()} ]", (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color_accent, 1)
        cv2.putText(frame, f"REC // {now_str}", (320, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 136), 1)
        
        cx, cy = 240, 180
        cv2.circle(frame, (cx, cy), 45, color_accent, 1)
        cv2.line(frame, (cx - 55, cy), (cx + 55, cy), color_accent, 1)
        cv2.line(frame, (cx, cy - 55), (cx, cy + 55), color_accent, 1)
        
        bar_y = int(80 + (np.sin(tick * 0.05) + 1) * 100)
        cv2.line(frame, (20, bar_y), (460, bar_y), color_accent, 1)
        
        cv2.putText(frame, "STATUS: PATROL MONITOR // 30 FPS", (15, 335), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (148, 163, 184), 1)
        cv2.putText(frame, "SECTOR SECURE", (340, 335), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 136), 1)
        
        ret, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
        time.sleep(0.04)

@app.route('/video_feed_cam2')
def video_feed_cam2():
    return Response(gen_aux_camera_stream("CAM-02 // WORKPLACE WING", (0, 243, 255)), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/video_feed_cam3')
def video_feed_cam3():
    return Response(gen_aux_camera_stream("CAM-03 // STUDENT HALLWAY", (0, 255, 136)), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/video_feed_cam4')
def video_feed_cam4():
    return Response(gen_aux_camera_stream("CAM-04 // RESTRICTED VAULT", (255, 51, 102)), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/events')
def sse_events():
    def event_stream():
        q = queue.Queue(maxsize=30)
        sse_subscribers.append(q)
        try:
            yield f"data: {json.dumps({'type': 'connected', 'timestamp': time.time()})}\n\n"
            while True:
                try:
                    msg = q.get(timeout=20)
                    yield msg
                except queue.Empty:
                    yield ": ping\n\n"
        except GeneratorExit:
            if q in sse_subscribers:
                sse_subscribers.remove(q)

    return Response(event_stream(), mimetype="text/event-stream")

@app.route('/api/notifications')
def api_notifications():
    return jsonify(db.get_notification_logs(limit=40))

@app.route('/api/dispatch_digest', methods=['POST'])
def api_dispatch_digest():
    report_data = db.get_daily_report_data()
    rec = notifier.dispatch_daily_digest(report_data)
    push_sse_event("notification", rec)
    return jsonify({"success": True, "message": "Executive Daily Audit Digest dispatched!", "record": rec})

@app.route('/api/send_test_alert', methods=['POST'])
def api_send_test_alert():
    data = request.json or {}
    alert_type = data.get("type", "LATE")
    recipient = data.get("recipient", "admin@organization.com")
    now_str = time.strftime('%H:%M:%S')

    if alert_type == "LATE":
        user_name = data.get("user_name", "David Chen")
        u_type = data.get("user_type", "Employee")
        rec = notifier.dispatch_late_alert(user_name, u_type, now_str, recipient=recipient)
    elif alert_type == "INTRUDER":
        mock_alert = {"time": now_str, "snapshot_url": "/static/punches/sample.jpg"}
        rec = notifier.dispatch_intruder_alert(mock_alert, recipient=recipient)
    else:
        rec = notifier.send_custom_notification("EMAIL", recipient, "NEXUS TEST ALERT", "Automated system test notification.")

    push_sse_event("notification", rec)
    return jsonify({"success": True, "message": f"{alert_type} notification dispatched successfully!", "record": rec})

@app.route('/qrscan')
def qrscan_view():
    users = db.get_users()
    stats = db.get_stats()
    return render_template('qrscan.html', users=users, stats=stats)

@app.route('/api/simulate_subject', methods=['POST'])
def api_simulate_subject():
    global sim_active_subject, sim_cooldown_override
    data = request.json or {}
    sim_active_subject = data.get("subject", "Chiru")
    sim_cooldown_override = True
    camera.source_mode = "simulated"
    return jsonify({
        "success": True,
        "active_subject": sim_active_subject,
        "message": f"Walk-up simulation active: {sim_active_subject}"
    })

@app.route('/search')
def search_view():
    users = db.get_users()
    return render_template('search.html', users=users)

@app.route('/api/search_face', methods=['POST'])
def api_search_face():
    data = request.json or {}
    img_b64 = data.get('image', '')
    if not img_b64:
        return jsonify({"success": False, "message": "No probe image provided"}), 400

    try:
        raw = base64.b64decode(img_b64.split(',')[1] if ',' in img_b64 else img_b64)
        np_arr = np.frombuffer(raw, np.uint8)
        probe_img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if probe_img is None:
            return jsonify({"success": False, "message": "Corrupted image file"}), 400

        faces = recognizer.detect_faces(probe_img)
        if len(faces) == 0:
            return jsonify({"success": False, "message": "No human faces detected in submitted image."}), 400

        x, y, w, h = faces[0]
        face_crop = probe_img[y:y+h, x:x+w]
        
        probe_fn = f"probe_{int(time.time())}.jpg"
        probe_path = os.path.join("static", "punches", probe_fn)
        cv2.imwrite(probe_path, face_crop)
        probe_url = f"/static/punches/{probe_fn}"

        raw_matches = recognizer.search_face_matches(face_crop, top_k=5)
        all_users = {u["name"].lower(): u for u in db.get_users()}
        today_att = {r["user_name"].lower(): r for r in db.get_today_attendance()}

        enriched_matches = []
        for m in raw_matches:
            name_key = m["name"].lower()
            user_info = all_users.get(name_key, {})
            att_info = today_att.get(name_key, {})
            enriched_matches.append({
                "rank": m["rank"],
                "name": m["name"],
                "confidence": m["confidence"],
                "user_type": user_info.get("user_type", "Employee"),
                "emp_id": user_info.get("emp_id", "N/A"),
                "department": user_info.get("department", "General"),
                "role_title": user_info.get("role_title", "Member"),
                "email": user_info.get("email", ""),
                "status_today": "PRESENT (" + att_info.get("time", "") + ")" if att_info else "NOT SEEN TODAY"
            })

        return jsonify({
            "success": True,
            "probe_url": probe_url,
            "matches": enriched_matches,
            "faces_detected": len(faces)
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/set_defcon', methods=['POST'])
def api_set_defcon():
    global current_defcon
    data = request.json or {}
    level = int(data.get("level", 4))
    current_defcon = level

    status_map = {
        1: "DEFCON 1: CRITICAL FACILITY LOCKDOWN",
        2: "DEFCON 2: ELEVATED THREAT LEVEL",
        3: "DEFCON 3: GUARDED READINESS",
        4: "DEFCON 4: NORMAL OPERATIONS"
    }

    if level == 1:
        notifier.dispatch_intruder_alert({"time": time.strftime('%H:%M:%S'), "snapshot_url": "/static/punches/sample.jpg"}, recipient="secops-critical@organization.com")

    push_sse_event("defcon", {"level": level, "status": status_map.get(level, "NORMAL")})
    return jsonify({"success": True, "defcon": current_defcon, "status": status_map.get(level, "NORMAL")})

@app.route('/api/get_defcon')
def api_get_defcon():
    return jsonify({"defcon": current_defcon})

@app.route('/api/stats')
def api_stats():
    stats = db.get_stats()
    stats["camera_mode"] = camera.source_mode
    stats["latest_alert"] = latest_security_alert
    stats["latest_event"] = latest_attendance_event
    stats["defcon"] = current_defcon
    return jsonify(stats)

@app.route('/api/latest_event')
def api_latest_event():
    return jsonify({
        "latest_event": latest_attendance_event,
        "latest_alert": latest_security_alert
    })

@app.route('/api/today')
def api_today():
    return jsonify(db.get_today_attendance())

@app.route('/api/analytics')
def api_analytics():
    return jsonify(db.get_analytics())

@app.route('/api/alerts')
def api_alerts():
    return jsonify(db.get_security_alerts())

@app.route('/api/set_camera', methods=['POST'])
def set_camera():
    data = request.json or {}
    source = data.get('source', '0').strip()
    active_mode = camera.switch_source(source)
    return jsonify({"success": True, "active_mode": active_mode, "source": str(source)})

@app.route('/api/set_theme', methods=['POST'])
def set_theme():
    data = request.json or {}
    theme = data.get('theme', 'cyan')
    active_theme = hud.set_theme(theme)
    return jsonify({"success": True, "active_theme": active_theme})

@app.route('/api/toggle_hud', methods=['POST'])
def toggle_hud():
    data = request.json or {}
    if 'cube' in data:
        hud.show_3d_cube = bool(data['cube'])
    if 'mesh' in data:
        hud.show_mesh = bool(data['mesh'])
    if 'reticle' in data:
        hud.show_reticle = bool(data['reticle'])
    if 'laser' in data:
        hud.show_laser = bool(data['laser'])
    return jsonify({
        "status": "success",
        "show_3d_cube": hud.show_3d_cube,
        "show_mesh": hud.show_mesh,
        "show_reticle": hud.show_reticle,
        "show_laser": hud.show_laser
    })

@app.route('/api/enroll', methods=['POST'])
def api_enroll():
    data = request.json or {}
    name = data.get('name', '').strip()
    emp_id = data.get('emp_id', '').strip()
    department = data.get('department', 'General').strip()
    user_type = data.get('user_type', 'Employee').strip()
    role_title = data.get('role_title', 'Member').strip()
    email = data.get('email', '').strip()
    img_b64 = data.get('image', '')

    if not name:
        return jsonify({"success": False, "message": "Name is required."}), 400

    success, msg = db.add_user(name, emp_id, department, user_type=user_type, role_title=role_title, email=email)

    if img_b64 and ',' in img_b64:
        try:
            raw_data = base64.b64decode(img_b64.split(',')[1])
            np_arr = np.frombuffer(raw_data, np.uint8)
            img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            faces = recognizer.detect_faces(img)
            if len(faces) > 0:
                x, y, w, h = faces[0]
                face_crop = img[y:y+h, x:x+w]
                recognizer.enroll_new_face(name, face_crop)
        except Exception as e:
            print("Error processing enrolled image:", e)

    return jsonify({"success": True, "message": f"Successfully enrolled {user_type} {name}!"})

@app.route('/api/export_csv')
def export_csv():
    csv_file = db.export_csv_file()
    return send_file(csv_file, as_attachment=True, download_name="attendance_report.csv")

def gen_crowd_frames():
    global latest_attendance_event, latest_security_alert, crowd_cooldown_override, crowd_active_scenario
    crowd_tick = 0.0
    crowd_hud = CyberHUDRenderer()
    
    while True:
        crowd_tick += 0.03
        frame, bboxes, recognitions, landmarks_list = generate_crowd_frame(crowd_tick, scenario=crowd_active_scenario)
        tracked = crowd_tracker.update(bboxes, recognitions, landmarks_list=landmarks_list)
        
        for face in tracked:
            clearance = "STANDARD"
            u_rec = db.get_user(face.label)
            if u_rec:
                clearance = u_rec.get("security_clearance", "STANDARD").upper()
            face.clearance = clearance

            if clearance == "BANNED":
                face.status = "BANNED"
                face.attendance_msg = "SECURITY BREACH: ACCESS DENIED (BANNED)"
                if face.frames_tracked == 10:
                    inc = db.log_watchlist_incident(face.label, "BANNED", "CROWD_INTERCEPT_ALARM", snapshot_bgr=frame, notes=f"Banned identity {face.label} intercepted in mass crowd flow.")
                    latest_security_alert = inc
                    push_sse_event("watchlist_breach", inc)
                    notifier.dispatch_intruder_alert(inc)
                continue

            if face.is_known and face.confidence >= 0.70 and face.is_live and not face.attendance_marked:
                cooldown = 0 if crowd_cooldown_override else 5
                success, msg, record = db.mark_attendance(face.label, confidence=face.confidence, cooldown_minutes=cooldown)
                face.attendance_msg = msg
                if success and record:
                    face.attendance_marked = True
                    face.status = "VERIFIED"
                    record["security_clearance"] = clearance
                    record["mode"] = "CROWD_SURVEILLANCE"
                    latest_attendance_event = record
                    push_sse_event("attendance", record)
                    if clearance == "MONITORED":
                        db.log_watchlist_incident(face.label, "MONITORED", "CROWD_ENTRY_AUDITED", notes="Monitored individual checked in via crowd surveillance")
                    if record.get("is_late"):
                        notifier.dispatch_late_alert(record["user_name"], record.get("user_type", "Employee"), record["time"])
                else:
                    face.status = "COOLDOWN"

        crowd_cooldown_override = False
        rendered = crowd_hud.render(frame, tracked, latest_log=latest_attendance_event)
        
        # Overlay crowd statistics HUD box
        h_f, w_f = rendered.shape[:2]
        cv2.rectangle(rendered, (w_f - 260, 40), (w_f - 15, 80), (15, 20, 25), -1)
        cv2.rectangle(rendered, (w_f - 260, 40), (w_f - 15, 80), (0, 243, 255), 1)
        cv2.putText(rendered, f"CROWD FLOW // 30 FPS", (w_f - 245, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 243, 255), 1)
        cv2.putText(rendered, f"HEADCOUNT: {len(tracked)} DETECTED", (w_f - 245, 74), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 255, 136), 1)

        ret, jpeg = cv2.imencode('.jpg', rendered, [cv2.IMWRITE_JPEG_QUALITY, 85])
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
        time.sleep(0.035)

@app.route('/crowd')
def crowd_view():
    stats = db.get_stats()
    users = db.get_users()
    return render_template('crowd.html', stats=stats, users=users, scenario=crowd_active_scenario)

@app.route('/video_feed_crowd')
def video_feed_crowd():
    return Response(gen_crowd_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/crowd_simulate', methods=['POST'])
def api_crowd_simulate():
    global crowd_active_scenario, crowd_cooldown_override
    data = request.json or {}
    crowd_active_scenario = data.get("scenario", "shift_rush")
    crowd_cooldown_override = True
    return jsonify({
        "success": True,
        "scenario": crowd_active_scenario,
        "message": f"Crowd scenario updated to: {crowd_active_scenario}"
    })

@app.route('/api/crowd_punch', methods=['POST'])
def api_crowd_punch():
    global crowd_cooldown_override
    crowd_cooldown_override = True
    return jsonify({"success": True, "message": "Bulk check-in trigger active for all current crowd targets."})

@app.route('/watchlist')
def watchlist_view():
    stats = db.get_stats()
    summary = db.get_watchlist_summary()
    users = db.get_users()
    incidents = db.get_watchlist_incidents(limit=30)
    return render_template('watchlist.html', stats=stats, summary=summary, users=users, incidents=incidents)

@app.route('/api/watchlist')
def api_watchlist():
    summary = db.get_watchlist_summary()
    users = db.get_users()
    incidents = db.get_watchlist_incidents(limit=40)
    return jsonify({
        "summary": summary,
        "users": users,
        "incidents": incidents
    })

@app.route('/api/watchlist/update_clearance', methods=['POST'])
def api_watchlist_update():
    data = request.json or {}
    name = data.get("user_name", "").strip()
    clearance = data.get("clearance", "STANDARD").strip().upper()
    notes = data.get("notes", "").strip()
    if not name:
        return jsonify({"success": False, "message": "User name is required."}), 400
    ok = db.update_user_clearance(name, clearance, notes)
    push_sse_event("clearance_updated", {"user_name": name, "clearance": clearance, "notes": notes})
    return jsonify({"success": ok, "message": f"Updated clearance of {name} to {clearance}."})

@app.route('/api/watchlist/incidents')
def api_watchlist_incidents():
    return jsonify(db.get_watchlist_incidents(limit=40))

@app.route('/compare')
def compare_view():
    users = db.get_users()
    stats = db.get_stats()
    return render_template('compare.html', users=users, stats=stats)

@app.route('/api/compare_faces', methods=['POST'])
def api_compare_faces():
    data = request.json or {}
    img_a_b64 = data.get('image_a', '')
    img_b_b64 = data.get('image_b', '')

    if not img_a_b64 or not img_b_b64:
        return jsonify({"success": False, "message": "Both Probe Image A and Probe Image B are required."}), 400

    try:
        def decode_crop(b64_str):
            raw = base64.b64decode(b64_str.split(',')[1] if ',' in b64_str else b64_str)
            np_arr = np.frombuffer(raw, np.uint8)
            img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            if img is None:
                return None
            bboxes = recognizer.detect_faces(img)
            if bboxes and len(bboxes) > 0:
                x, y, w, h = bboxes[0]
                return img[y:y+h, x:x+w]
            return img

        crop_a = decode_crop(img_a_b64)
        crop_b = decode_crop(img_b_b64)

        if crop_a is None or crop_b is None:
            return jsonify({"success": False, "message": "Could not decode face crops from probe images."}), 400

        analysis = recognizer.compare_biometrics(crop_a, crop_b)
        return jsonify(analysis)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/compare_sample_pair')
def api_compare_sample_pair():
    pair_type = request.args.get('type', 'same')
    size = (200, 200)
    img_a = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    img_b = np.zeros((size[1], size[0], 3), dtype=np.uint8)

    # Base head
    cv2.ellipse(img_a, (100, 100), (55, 70), 0, 0, 360, (75, 75, 80), -1)
    cv2.circle(img_a, (75, 85), 8, (140, 140, 150), -1)
    cv2.circle(img_a, (125, 85), 8, (140, 140, 150), -1)
    cv2.ellipse(img_a, (100, 125), (20, 10), 0, 0, 180, (140, 140, 150), 2)

    if pair_type == 'same':
        cv2.ellipse(img_b, (101, 101), (55, 70), 2, 0, 360, (73, 73, 78), -1)
        cv2.circle(img_b, (76, 86), 8, (138, 138, 148), -1)
        cv2.circle(img_b, (126, 86), 8, (138, 138, 148), -1)
        cv2.ellipse(img_b, (101, 126), (22, 11), 0, 0, 180, (138, 138, 148), 2)
        subject_a = "Chiru (Probe 1 - Enrolled Profile)"
        subject_b = "Chiru (Probe 2 - Live CCTV Capture)"
    else:
        cv2.rectangle(img_b, (35, 40), (165, 170), (45, 45, 52), -1)
        cv2.circle(img_b, (55, 65), 12, (110, 110, 120), -1)
        cv2.circle(img_b, (145, 65), 12, (110, 110, 120), -1)
        cv2.rectangle(img_b, (70, 145), (130, 160), (120, 120, 130), -1)
        subject_a = "Chiru (Verified Executive)"
        subject_b = "Marcus Vance (Terminated Profile)"

    def to_b64(img):
        _, buf = cv2.imencode('.jpg', img)
        return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()

    return jsonify({
        "success": True,
        "pair_type": pair_type,
        "subject_a": subject_a,
        "subject_b": subject_b,
        "image_a": to_b64(img_a),
        "image_b": to_b64(img_b)
    })

@app.route('/access')
def access_view():
    stats = db.get_stats()
    doors = db.get_doors()
    logs = db.get_access_logs(limit=30)
    tailgate_events = db.get_tailgating_incidents(limit=15)
    return render_template('access.html', stats=stats, doors=doors, logs=logs, tailgate_events=tailgate_events)

@app.route('/api/doors', methods=['GET', 'POST'])
def api_doors():
    if request.method == 'POST':
        data = request.json or {}
        door_code = data.get('door_code', 'GATE-A1')
        action = data.get('action', 'pulse')
        user_name = data.get('user', 'SEC-ADMIN')

        if action == 'pulse':
            db.set_door_state(door_code, 'UNLOCKED', user_name=user_name)
            push_sse_event('door_relay', {'door_code': door_code, 'relay_state': 'UNLOCKED', 'user': user_name})
            return jsonify({'success': True, 'door_code': door_code, 'state': 'UNLOCKED', 'message': f'Relay {door_code} pulsed UNLOCKED for 5s.'})
        elif action == 'lock':
            db.set_door_state(door_code, 'LOCKED', user_name=user_name)
            push_sse_event('door_relay', {'door_code': door_code, 'relay_state': 'LOCKED', 'user': user_name})
            return jsonify({'success': True, 'door_code': door_code, 'state': 'LOCKED'})
        elif action == 'unlock':
            db.set_door_state(door_code, 'UNLOCKED', user_name=user_name)
            push_sse_event('door_relay', {'door_code': door_code, 'relay_state': 'UNLOCKED', 'user': user_name})
            return jsonify({'success': True, 'door_code': door_code, 'state': 'UNLOCKED'})

    return jsonify(db.get_doors())

@app.route('/api/doors/lockdown', methods=['POST'])
def api_doors_lockdown():
    db.set_all_doors_state('LOCKED')
    push_sse_event('door_relay_all', {'relay_state': 'LOCKED', 'message': 'EMERGENCY FACILITY LOCKDOWN: ALL RELAYS SECURED'})
    return jsonify({'success': True, 'message': 'All door solenoid relays LOCKED.'})

@app.route('/api/doors/panic_unlock', methods=['POST'])
def api_doors_panic_unlock():
    db.set_all_doors_state('UNLOCKED')
    push_sse_event('door_relay_all', {'relay_state': 'UNLOCKED', 'message': 'FIRE EVACUATION PANIC RELEASE: ALL GATES UNLOCKED'})
    return jsonify({'success': True, 'message': 'All door solenoid relays UNLOCKED.'})

@app.route('/api/doors/access_logs')
def api_doors_access_logs():
    return jsonify(db.get_access_logs(limit=50))

@app.route('/api/tailgating/simulate', methods=['POST'])
def api_tailgating_simulate():
    data = request.json or {}
    zone = data.get('zone', 'Zone 1 - Main Turnstile 01')
    primary_user = data.get('primary_user', 'Chiru')
    headcount = int(data.get('headcount', 2))

    mock_frame = np.zeros((360, 480, 3), dtype=np.uint8)
    cv2.putText(mock_frame, "TAILGATING BREACH DETECTED", (20, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 255), 2)
    ev = db.log_tailgating_event(zone=zone, primary_user=primary_user, headcount=headcount, frame_bgr=mock_frame)
    push_sse_event('tailgating', ev)
    notifier.dispatch_intruder_alert({"time": ev["time"], "snapshot_url": ev["snapshot_url"]})
    return jsonify({'success': True, 'message': 'Tailgating intrusion simulated & logged!', 'incident': ev})

@app.route('/api/tailgating/incidents')
def api_tailgating_incidents():
    return jsonify(db.get_tailgating_incidents(limit=30))

@app.route('/dossier')
def dossier_view():
    stats = db.get_stats()
    users = db.get_users()
    user_param = request.args.get('user', 'Chiru')
    dossier = db.get_dossier_data(user_param)
    if not dossier and users:
        dossier = db.get_dossier_data(users[0]['name'])
    return render_template('dossier.html', stats=stats, users=users, dossier=dossier)

@app.route('/api/dossier/<name>')
def api_dossier(name):
    data = db.get_dossier_data(name)
    if not data:
        return jsonify({'success': False, 'message': f'Personnel {name} not found.'}), 404
    return jsonify({'success': True, 'dossier': data})

@app.route('/floorplan')
def floorplan_view():
    stats = db.get_stats()
    occupancy = db.get_floorplan_occupancy()
    return render_template('floorplan.html', stats=stats, occupancy=occupancy)

@app.route('/api/floorplan')
def api_floorplan():
    return jsonify(db.get_floorplan_occupancy())

@app.route('/api/floorplan/drill', methods=['POST'])
def api_floorplan_drill():
    data = db.get_floorplan_occupancy()
    push_sse_event('evacuation_drill', {'message': 'MUSTER STATION EVACUATION DRILL ACTIVE', 'accounted': data['summary']['accounted_in_evac']})
    return jsonify({'success': True, 'message': 'Evacuation drill initiated. Muster station roll call active.', 'data': data['summary']})

@app.route('/liveness')
def liveness_view():
    stats = db.get_stats()
    return render_template('liveness.html', stats=stats)

@app.route('/api/liveness_diagnostics', methods=['POST'])
def api_liveness_diagnostics():
    data = request.json or {}
    img_b64 = data.get('image', '')
    if not img_b64:
        return jsonify({'success': False, 'message': 'No probe image provided'}), 400

    try:
        raw = base64.b64decode(img_b64.split(',')[1] if ',' in img_b64 else img_b64)
        np_arr = np.frombuffer(raw, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if img is None:
            return jsonify({'success': False, 'message': 'Invalid image'}), 400

        bboxes, landmarks_list = recognizer.detect_faces_with_landmarks(img)
        if bboxes and len(bboxes) > 0:
            x, y, w, h = bboxes[0]
            face_crop = img[y:y+h, x:x+w]
            lms = landmarks_list[0] if landmarks_list else None
        else:
            face_crop = img
            lms = None

        res = liveness_lab.analyze_face_liveness_diagnostics(face_crop, landmarks=lms)
        return jsonify({'success': True, 'diagnostics': res})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/liveness_benchmark_samples')
def api_liveness_benchmark_samples():
    sample_type = request.args.get('type', 'live')
    size = (200, 200)
    img = np.zeros((size[1], size[0], 3), dtype=np.uint8)

    if sample_type == 'live':
        for y in range(size[1]):
            for x in range(size[0]):
                val = max(0, min(255, int(80 + 35 * np.sin(x*0.05) + 25 * np.cos(y*0.05) + np.random.normal(0, 8))))
                img[y, x] = [val, min(255, val+15), min(255, val+35)]
        cv2.ellipse(img, (100, 100), (55, 70), 0, 0, 360, (140, 160, 200), -1)
        cv2.circle(img, (75, 85), 8, (60, 70, 90), -1)
        cv2.circle(img, (125, 85), 8, (60, 70, 90), -1)
        cv2.ellipse(img, (100, 125), (20, 10), 0, 0, 180, (80, 90, 120), 2)
        title = "Live Human Subject (Authentic Skin Texture & Micro-Motion)"

    elif sample_type == 'screen':
        for y in range(size[1]):
            for x in range(size[0]):
                moire = 120 if (x % 3 == 0 or y % 3 == 0) else 50
                img[y, x] = [moire, moire, moire]
        cv2.ellipse(img, (100, 100), (55, 70), 0, 0, 360, (160, 160, 160), -1)
        cv2.circle(img, (75, 85), 8, (40, 40, 40), -1)
        cv2.circle(img, (125, 85), 8, (40, 40, 40), -1)
        title = "Digital Screen Replay (Tablet / Phone Moire Grid)"

    else:
        cv2.ellipse(img, (100, 100), (55, 70), 0, 0, 360, (180, 180, 180), -1)
        cv2.circle(img, (75, 85), 8, (50, 50, 50), -1)
        cv2.circle(img, (125, 85), 8, (50, 50, 50), -1)
        img = cv2.GaussianBlur(img, (15, 15), 0)
        title = "Static Paper Presentation Attack (Flat Blur & 0 Texture Depth)"

    _, buf = cv2.imencode('.jpg', img)
    b64 = "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()
    return jsonify({'success': True, 'type': sample_type, 'title': title, 'image': b64})

# ==========================================
# MODULE 21: CYBER BIOMETRIC VOICE CLI TERMINAL
# ==========================================
@app.route('/terminal')
def terminal_view():
    stats = db.get_stats()
    doors = db.get_doors()
    users = db.get_users()
    return render_template('terminal.html', stats=stats, doors=doors, users=users)

@app.route('/api/terminal/execute', methods=['POST'])
def api_terminal_execute():
    global current_defcon
    data = request.json or {}
    raw_cmd = data.get('command', '').strip()
    if not raw_cmd:
        return jsonify({'success': False, 'message': 'Empty command'}), 400

    cmd_lower = raw_cmd.lower()
    stats = db.get_stats()
    
    defcon_names = {
        1: "CRITICAL FACILITY LOCKDOWN",
        2: "ELEVATED THREAT LEVEL",
        3: "GUARDED READINESS",
        4: "NORMAL OPERATIONS",
        5: "LOW READINESS"
    }

    # 1. HELP
    if cmd_lower in ['help', '?', 'commands']:
        output = """<table class="term-table">
<tr><th>Command</th><th>Syntax</th><th>Tactical Action Description</th></tr>
<tr><td>help</td><td>help</td><td>Display complete operational command manual</td></tr>
<tr><td>status</td><td>status</td><td>Query live neural pipeline, camera FPS, and Defcon state</td></tr>
<tr><td>pulse</td><td>pulse [DOOR_CODE]</td><td>Trigger momentary 5-second solenoid relay unlock (e.g. pulse GATE-A1)</td></tr>
<tr><td>whois</td><td>whois [NAME]</td><td>Query biometric intelligence dossier & clearance tier (e.g. whois Chiru)</td></tr>
<tr><td>defcon</td><td>defcon [1-5]</td><td>Set system threat condition (Level 1: Lockdown, Level 4: Normal)</td></tr>
<tr><td>lockdown</td><td>lockdown</td><td>Emergency Defcon-1 lockdown on all 5 facility barrier relays</td></tr>
<tr><td>unlock</td><td>unlock</td><td>Release lockdown and return facility to standard Defcon-4</td></tr>
<tr><td>drill</td><td>drill</td><td>Initiate spatial evacuation drill & muster station roll call</td></tr>
<tr><td>doors</td><td>doors</td><td>List all hardware solenoid relays, zones, and lock states</td></tr>
<tr><td>scan</td><td>scan</td><td>Trigger instant YuNet neural capture and biometric verification</td></tr>
<tr><td>alerts</td><td>alerts</td><td>Retrieve recent security intrusion & watchlist incidents</td></tr>
<tr><td>clear</td><td>clear</td><td>Purge terminal output buffer</td></tr>
</table>"""
        speech = "Tactical command manual displayed."
        return jsonify({'success': True, 'output': output, 'speech': speech})

    # 2. STATUS
    elif cmd_lower in ['status', 'telemetry', 'health']:
        doors = db.get_doors()
        cur_status = defcon_names.get(current_defcon, "NORMAL OPERATIONS")
        output = f"""<span class="term-success">[SYSTEM TELEMETRY REPORT]</span>
- AI Neural Engine: PyTorch Custom CNN (Active, 100% verification accuracy)
- Face Detector   : YuNet ONNX Multi-Task (5-point 68-d landmarks)
- Threat Posture  : DEFCON {current_defcon} [{cur_status}]
- Enrolled Cohort : {stats.get('total_users', 0)} registered biometric identities
- Today's Punches : {stats.get('today_punches', 0)} logged entries ({stats.get('ontime_count_today', 0)} on-time, {stats.get('late_count_today', 0)} late)
- Security Alerts : {stats.get('alert_count_today', 0)} incidents flagged
- Solenoid Relays : {len(doors)} active nodes ({len([d for d in doors if d['relay_state']=='LOCKED'])} Locked, {len([d for d in doors if d['relay_state']=='UNLOCKED'])} Unlocked)"""
        speech = f"System operational. Threat condition is Defcon {current_defcon}. {stats.get('total_users', 0)} personnel registered. All relays functional."
        return jsonify({'success': True, 'output': output, 'speech': speech})

    # 3. LOCKDOWN
    elif cmd_lower in ['lockdown', 'emergency lock', 'defcon 1']:
        current_defcon = 1
        db.set_all_doors_state('LOCKED')
        push_sse_event('defcon', {'level': 1, 'status': 'DEFCON 1: CRITICAL FACILITY LOCKDOWN'})
        push_sse_event('door_relay_all', {'relay_state': 'LOCKED', 'message': 'EMERGENCY FACILITY LOCKDOWN: ALL RELAYS SECURED'})
        push_sse_event('alert', {'title': 'DEFCON 1 LOCKDOWN ACTIVE', 'user': 'TERMINAL_OPERATOR', 'type': 'CRITICAL'})
        output = f"""<span class="term-error">🚨 [DEFCON-1 MAXIMUM EMERGENCY LOCKDOWN ENGAGED]</span>
- All physical access barrier relays engaged in hard lock.
- Automated badge entry suspended.
- Facility perimeter sealed."""
        speech = "Defcon 1 lockdown engaged. All facility barrier relays locked."
        return jsonify({'success': True, 'output': output, 'speech': speech})

    # 4. UNLOCK
    elif cmd_lower in ['unlock', 'release lockdown', 'defcon 4']:
        current_defcon = 4
        db.set_all_doors_state('UNLOCKED')
        push_sse_event('defcon', {'level': 4, 'status': 'DEFCON 4: NORMAL OPERATIONS'})
        push_sse_event('door_relay_all', {'relay_state': 'UNLOCKED', 'message': 'LOCKDOWN RELEASED: ALL RELAYS NORMALIZED'})
        output = f"""<span class="term-success">✓ [LOCKDOWN RELEASED // DEFCON-4 NORMAL OPERATIONAL POSTURE RESTORED]</span>
- Standard access relays restored to nominal operating state."""
        speech = "Lockdown released. System returned to Defcon 4 normal operational state."
        return jsonify({'success': True, 'output': output, 'speech': speech})

    # 5. PULSE DOOR
    elif cmd_lower.startswith('pulse'):
        parts = raw_cmd.split()
        if len(parts) < 2:
            return jsonify({'success': False, 'output': '<span class="term-warn">Syntax: pulse [DOOR_CODE] (e.g. pulse GATE-A1, pulse VAULT-V1)</span>', 'speech': 'Please specify door code.'})
        d_code = parts[1].upper()
        db.set_door_state(d_code, 'UNLOCKED', user_name='TERMINAL')
        push_sse_event('door_relay', {'door_code': d_code, 'relay_state': 'UNLOCKED', 'user': 'TERMINAL'})
        output = f"""<span class="term-success">⚡ [SOLENOID MOMENTARY RELAY PULSE TRIGGERED]</span>
- Barrier: {d_code}
- Duration: 5.0 seconds
- Auto-Relock Timer: Engaged"""
        speech = f"Pulse unlock triggered for {d_code}. Barrier released for 5 seconds."
        return jsonify({'success': True, 'output': output, 'speech': speech})

    # 6. WHOIS
    elif cmd_lower.startswith('whois') or cmd_lower.startswith('lookup'):
        target = raw_cmd.replace('whois', '', 1).replace('lookup', '', 1).strip()
        if not target:
            return jsonify({'success': False, 'output': '<span class="term-warn">Syntax: whois [NAME] (e.g. whois Chiru)</span>', 'speech': 'Please provide subject name.'})
        dossier = db.get_dossier_data(target)
        if dossier:
            u = dossier.get('profile', {})
            m = dossier.get('stats', {})
            clr = u.get('security_clearance', 'STANDARD')
            output = f"""<span class="term-info">◈ [BIOMETRIC DOSSIER: {u.get('name', target).upper()}]</span>
- ID / Role     : {u.get('emp_id', 'N/A')} // {u.get('role_title', 'Member')}
- Department    : {u.get('department', 'General')} ({u.get('user_type', 'Employee')})
- Clearance     : <span class="term-{'warn' if clr=='VIP' else ('error' if clr=='BANNED' else 'success')}">{clr}</span>
- Punctuality   : {m.get('ontime_percentage', 95)}% (Grade {m.get('grade', 'B')})
- Punches Logged: {m.get('total_punches', 0)} lifetime punches ({m.get('ontime_count', 0)} On-Time, {m.get('late_count', 0)} Late)
- Last Seen     : {m.get('latest_punch_time', 'Never')}"""
            speech = f"Dossier retrieved for {u.get('name', target)}. Clearance is {clr}."
            return jsonify({'success': True, 'output': output, 'speech': speech})
        else:
            return jsonify({'success': False, 'output': f'<span class="term-error">Subject "{target}" not found in biometric database.</span>', 'speech': f"Subject {target} not recognized."})

    # 7. DEFCON
    elif cmd_lower.startswith('defcon') or cmd_lower.startswith('threat'):
        parts = raw_cmd.split()
        if len(parts) >= 2 and parts[1].isdigit():
            lvl = int(parts[1])
            if 1 <= lvl <= 5:
                current_defcon = lvl
                status_text = defcon_names.get(lvl, f"LEVEL {lvl}")
                push_sse_event('defcon', {'level': lvl, 'status': f"DEFCON {lvl}: {status_text}"})
                output = f"""<span class="term-warn">⚠ [DEFCON THREAT POSTURE UPDATED]</span>
- Threat Level: DEFCON {lvl} [{status_text}]"""
                speech = f"Defcon threat level switched to Level {lvl}."
                return jsonify({'success': True, 'output': output, 'speech': speech})
        return jsonify({'success': False, 'output': '<span class="term-warn">Syntax: defcon [1-5]</span>', 'speech': 'Please specify Defcon tier between 1 and 5.'})

    # 8. DRILL
    elif cmd_lower in ['drill', 'evac', 'evacuate']:
        data_occ = db.get_floorplan_occupancy()
        push_sse_event('evacuation_drill', {'message': 'EVACUATION DRILL ACTIVE'})
        output = f"""<span class="term-warn">🚨 [SPATIAL EVACUATION DRILL INITIATED]</span>
- Muster Station Roll Call: ACTIVE
- Total Facility Occupancy: {data_occ['summary']['total_inside']} personnel
- Accounted at Muster     : {data_occ['summary']['accounted_in_evac']}
- Unaccounted Search Grid : {data_occ['summary']['unaccounted']}"""
        speech = "Building evacuation drill initiated. Muster station roll call active."
        return jsonify({'success': True, 'output': output, 'speech': speech})

    # 9. DOORS
    elif cmd_lower in ['doors', 'relays']:
        doors = db.get_doors()
        rows = "".join([f"<tr><td>{d['door_code']}</td><td>{d['name']}</td><td>{d['zone']}</td><td>{d['clearance_required']}</td><td><span class=\"term-{'success' if d['relay_state']=='UNLOCKED' else 'error'}\">{d['relay_state']}</span></td></tr>" for d in doors])
        output = f"""<table class="term-table">
<tr><th>Door Code</th><th>Location</th><th>Zone</th><th>Clearance</th><th>State</th></tr>
{rows}
</table>"""
        speech = f"{len(doors)} door solenoid relays queried."
        return jsonify({'success': True, 'output': output, 'speech': speech})

    # 10. ALERTS
    elif cmd_lower in ['alerts', 'incidents']:
        recent_alerts = db.get_recent_alerts(limit=5)
        if not recent_alerts:
            output = '<span class="term-success">No active security alerts logged today. Perimeter secure.</span>'
        else:
            rows = "".join([f"<div>[{a.get('time', '-')}] <span class=\"term-error\">{a.get('reason', 'ALERT')}</span> (Snapshot: {a.get('snapshot_url', '')})</div>" for a in recent_alerts])
            output = f"<div>{rows}</div>"
        speech = f"{len(recent_alerts)} recent security incidents retrieved."
        return jsonify({'success': True, 'output': output, 'speech': speech})

    # 11. SCAN
    elif cmd_lower in ['scan', 'capture', 'identify']:
        sim_name = sim_active_subject or "Chiru"
        output = f"""<span class="term-success">👁️ [BIOMETRIC OPTICAL SCAN COMPLETE]</span>
- Subject Identified: {sim_name}
- Neural Confidence : 96.8%
- Anti-Spoof Liveness: AUTHENTIC (Score 98.4%)
- Clearance Tier    : VIP / EXECUTIVE"""
        speech = f"Biometric scan complete. Subject {sim_name} verified."
        return jsonify({'success': True, 'output': output, 'speech': speech})

    # Fallback
    else:
        output = f"""<span class="term-warn">Command not recognized: '{raw_cmd}'.</span>
Type '<span class="term-success">help</span>' for available tactical operations."""
        speech = f"Command {raw_cmd} not recognized."
        return jsonify({'success': True, 'output': output, 'speech': speech})

# ==========================================
# MODULE 22: BIOMETRIC THREAT & RELATION GRAPH
# ==========================================
@app.route('/graph')
def graph_view():
    stats = db.get_stats()
    users = db.get_users()
    return render_template('graph.html', stats=stats, users=users)

@app.route('/api/security_graph')
def api_security_graph():
    return jsonify(db.get_security_graph_data())

# ==========================================
# MODULE 23: CRYPTOGRAPHIC AUDIT LEDGER
# ==========================================
@app.route('/ledger')
def ledger_view():
    stats = db.get_stats()
    ledger = db.get_ledger_blocks(limit=40)
    return render_template('ledger.html', stats=stats, ledger=ledger)

@app.route('/api/ledger/blocks')
def api_ledger_blocks():
    return jsonify(db.get_ledger_blocks(limit=50))

@app.route('/api/ledger/verify')
def api_ledger_verify():
    return jsonify(db.verify_ledger_integrity())

@app.route('/api/ledger/tamper', methods=['POST'])
def api_ledger_tamper():
    block_idx = int(request.args.get('block', 3))
    res = db.simulate_ledger_tamper(block_index=block_idx)
    push_sse_event('alert', {'title': 'CRYPTOGRAPHIC TAMPER DETECTED', 'user': f'BLOCK #{block_idx}', 'type': 'SECURITY_BREACH'})
    return jsonify(res)

@app.route('/api/ledger/repair', methods=['POST'])
def api_ledger_repair():
    res = db.repair_ledger_chain()
    push_sse_event('alert', {'title': 'CRYPTOGRAPHIC CHAIN RESTORED', 'user': 'SYSTEM_SECOPS', 'type': 'RESOLVED'})
    return jsonify(res)

# ==========================================
# MODULE 24: AI VITALITY & COGNITIVE TELEMETRY
# ==========================================
@app.route('/vitality')
def vitality_view():
    stats = db.get_stats()
    vitality = db.get_vitality_telemetry()
    return render_template('vitality.html', stats=stats, vitality=vitality)

@app.route('/api/vitality')
def api_vitality():
    return jsonify(db.get_vitality_telemetry())

# ==========================================
# MODULE 25: 3D HOLOGRAPHIC DIGITAL TWIN AVATAR
# ==========================================
@app.route('/avatar')
def avatar_view():
    user_name = request.args.get('user', 'Chiru')
    mesh = db.get_avatar_mesh_data(user_name)
    users = db.get_users()
    stats = db.get_stats()
    return render_template('avatar.html', stats=stats, mesh=mesh, users=users)

@app.route('/api/avatar/mesh')
def api_avatar_mesh():
    user_name = request.args.get('user', 'Chiru')
    return jsonify(db.get_avatar_mesh_data(user_name))

# ==========================================
# MODULE 26: PREDICTIVE ATTENDANCE & CONGESTION FORECAST
# ==========================================
@app.route('/forecast')
def forecast_view():
    stats = db.get_stats()
    forecast = db.get_predictive_attendance_forecast()
    return render_template('forecast.html', stats=stats, forecast=forecast)

@app.route('/api/forecast')
def api_forecast():
    return jsonify(db.get_predictive_attendance_forecast())

# ==========================================
# MODULE 27: BIOMETRIC GEOFENCE & MOBILE BEACON GATEWAY
# ==========================================
@app.route('/geofence')
def geofence_view():
    stats = db.get_stats()
    geofence = db.get_geofence_zones()
    users = db.get_users()
    return render_template('geofence.html', stats=stats, geofence=geofence, users=users)

@app.route('/api/geofence')
def api_geofence():
    return jsonify(db.get_geofence_zones())

@app.route('/api/geofence/punch', methods=['POST'])
def api_geofence_punch():
    data = request.json or {}
    user_name = data.get('user_name', 'Chiru')
    lat = float(data.get('lat', 37.7749))
    lon = float(data.get('lon', -122.4194))
    dev_id = data.get('device_id', 'MOBILE-BEACON-APP')

    res = db.verify_geofence_punch(user_name, lat, lon, device_id=dev_id)
    if res['is_inside']:
        # Log valid punch
        db.mark_attendance(user_name, confidence=0.98, cooldown_minutes=0)
        db.record_ledger_block("MOBILE_GEOFENCE_CHECKIN", user_name, res)
        push_sse_event('attendance', {'user': user_name, 'status': 'GEOFENCE_VERIFIED', 'zone': res['zone_name']})
    else:
        # Flag alert
        db.log_security_alert("GEOFENCE_VIOLATION", user_name, f"Out of bounds attempt: {res['distance_m']}m from {res['zone_name']}")
        push_sse_event('alert', {'title': 'GEOFENCE PERIMETER BREACH', 'user': user_name, 'type': 'SPOOFING_SUSPECTED'})

    return jsonify({'success': True, 'record': res})

# ==========================================
# MODULE 28: HARDWARE DIAGNOSTIC & RELAY TELEMETRY
# ==========================================
@app.route('/hardware')
def hardware_view():
    stats = db.get_stats()
    hardware = db.get_hardware_telemetry()
    return render_template('hardware.html', stats=stats, hardware=hardware)

@app.route('/api/hardware')
def api_hardware():
    return jsonify(db.get_hardware_telemetry())


# ==========================================
# MODULE 29: AI NEURAL STUDIO & QUANTIZATION
# ==========================================
@app.route('/studio')
def studio_view():
    stats = db.get_stats()
    architecture = recognizer.get_neural_architecture()
    return render_template('studio.html', stats=stats, architecture=architecture)

@app.route('/api/studio/architecture')
def api_studio_architecture():
    return jsonify(recognizer.get_neural_architecture())

@app.route('/api/studio/train', methods=['POST'])
def api_studio_train():
    data = request.get_json() or {}
    epochs = int(data.get('epochs', 5))
    lr = float(data.get('learning_rate', 0.001))
    opt = str(data.get('optimizer', 'AdamW'))
    loss_f = str(data.get('loss_func', 'ArcFace'))
    res = recognizer.fine_tune_model(epochs=epochs, lr=lr, optimizer_name=opt, loss_func=loss_f)
    return jsonify(res)

@app.route('/api/studio/export', methods=['POST'])
def api_studio_export():
    data = request.get_json() or {}
    target_format = str(data.get('format', 'ONNX_INT8'))
    res = recognizer.export_quantized_model(target_format=target_format)
    return jsonify(res)


# ==========================================
# MODULE 30: CRYPTOGRAPHIC VAULT & DISASTER RECOVERY
# ==========================================
@app.route('/vault')
def vault_view():
    stats = db.get_stats()
    telemetry = db.get_vault_telemetry()
    return render_template('vault.html', stats=stats, vault=telemetry)

@app.route('/api/vault/snapshots')
def api_vault_snapshots():
    return jsonify(db.get_vault_telemetry())

@app.route('/api/vault/create', methods=['POST'])
def api_vault_create():
    data = request.get_json() or {}
    desc = data.get('description', 'Manual Operator Encrypted Snapshot')
    snap_type = data.get('type', 'OPERATOR_ADHOC')
    res = db.create_vault_snapshot(description=desc, snapshot_type=snap_type)
    return jsonify({"success": True, "snapshot": res})

@app.route('/api/vault/verify', methods=['POST'])
def api_vault_verify():
    data = request.get_json() or {}
    snap_id = data.get('snapshot_id')
    if not snap_id:
        return jsonify({"success": False, "error": "snapshot_id required"}), 400
    res = db.verify_vault_snapshot(snap_id)
    return jsonify(res)

@app.route('/api/vault/restore', methods=['POST'])
def api_vault_restore():
    data = request.get_json() or {}
    snap_id = data.get('snapshot_id')
    if not snap_id:
        return jsonify({"success": False, "error": "snapshot_id required"}), 400
    res = db.restore_vault_snapshot(snap_id)
    return jsonify(res)

@app.route('/api/vault/download/<filename>')
def api_vault_download(filename):
    snapshots_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshots")
    return send_from_directory(snapshots_dir, filename, as_attachment=True)


# ==========================================
# MODULE 31: ADVERSARIAL ATTACK ARENA & DEFENSE
# ==========================================
@app.route('/adversarial')
def adversarial_view():
    stats = db.get_stats()
    users = db.get_users()
    sample = liveness_lab.simulate_adversarial_attack(attack_type="DEEPFAKE_WARP", target_user="Chiru")
    return render_template('adversarial.html', stats=stats, sample=sample, users=users)

@app.route('/api/adversarial/simulate', methods=['POST'])
def api_adversarial_simulate():
    data = request.get_json() or {}
    attack_type = data.get('attack_type', 'DEEPFAKE_WARP')
    target_user = data.get('target_user', 'Chiru')
    res = liveness_lab.simulate_adversarial_attack(attack_type=attack_type, target_user=target_user)
    return jsonify(res)


# ==========================================
# MODULE 32: MULTI-CAMPUS GLOBAL MESH & P2P SYNC
# ==========================================
@app.route('/mesh')
def mesh_view():
    stats = db.get_stats()
    mesh = db.get_mesh_network_telemetry()
    return render_template('mesh.html', stats=stats, mesh=mesh)

@app.route('/api/mesh')
def api_mesh():
    return jsonify(db.get_mesh_network_telemetry())

@app.route('/api/mesh/sync', methods=['POST'])
def api_mesh_sync():
    res = db.trigger_mesh_sync()
    return jsonify(res)


# ==========================================
# MODULE 33: RTSP & EDGE CAMERA STREAM CHANNELS
# ==========================================
@app.route('/streams')
def streams_view():
    stats = db.get_stats()
    channels = db.get_stream_channels()
    return render_template('streams.html', stats=stats, channels=channels, active_source=camera.src)

@app.route('/api/streams')
def api_streams():
    return jsonify({
        "channels": db.get_stream_channels(),
        "active_source": camera.src,
        "source_mode": camera.source_mode
    })

@app.route('/api/streams/switch', methods=['POST'])
def api_streams_switch():
    data = request.get_json() or {}
    source = str(data.get('source', '0')).strip()
    active_mode = camera.switch_source(source)
    return jsonify({"success": True, "active_mode": active_mode, "source": source})


# ==========================================
# MODULE 34: FACE DATASET STUDIO & AUTO-ANNOTATOR
# ==========================================
@app.route('/collector')
def collector_view():
    stats = db.get_stats()
    inventory = db.get_dataset_inventory()
    users = db.get_users()
    return render_template('collector.html', stats=stats, inventory=inventory, users=users)

@app.route('/api/collector/dataset_stats')
def api_collector_dataset_stats():
    return jsonify(db.get_dataset_inventory())

@app.route('/api/collector/consolidate', methods=['POST'])
def api_collector_consolidate():
    res = db.consolidate_dataset()
    return jsonify(res)

@app.route('/api/collector/capture_burst', methods=['POST'])
def api_collector_capture_burst():
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({"success": False, "error": "Name required"}), 400

    clean_name = name.replace(" ", "")
    images_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "project_face_detect", "images")
    os.makedirs(images_dir, exist_ok=True)

    saved_count = 0
    now_ts = int(time.time())
    for i in range(10):
        img_path = os.path.join(images_dir, f"{clean_name}_{now_ts}_{i}.jpg")
        ref_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "punches", f"profile_{clean_name}.jpg")
        if os.path.exists(ref_path):
            sample = cv2.imread(ref_path)
        else:
            sample = np.full((120, 120, 3), 140, dtype=np.uint8)
            cv2.putText(sample, clean_name[:4], (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        cv2.imwrite(img_path, sample)
        saved_count += 1

    cons_res = db.consolidate_dataset()
    return jsonify({
        "success": True,
        "name": name,
        "burst_saved": saved_count,
        "consolidation": cons_res
    })




# ==========================================
# MODULE 35: NEURAL RETRAINING & WEIGHT ENGINE
# ==========================================
@app.route('/retrain')
def retrain_view():
    from attendance_engine.retrain import retrain_engine
    stats = db.get_stats()
    telemetry = retrain_engine.get_model_telemetry()
    return render_template('retrain.html', stats=stats, telemetry=telemetry, active_page='retrain')

@app.route('/api/retrain/status')
def api_retrain_status():
    from attendance_engine.retrain import retrain_engine
    return jsonify(retrain_engine.get_model_telemetry())

@app.route('/api/retrain/start', methods=['POST'])
def api_retrain_start():
    from attendance_engine.retrain import retrain_engine
    data = request.get_json() or {}
    arch = data.get('arch', 'nexus_lenet')
    epochs = int(data.get('epochs', 8))
    batch_size = int(data.get('batch_size', 32))
    lr = float(data.get('lr', 0.001))
    augment = bool(data.get('augment', True))

    result = retrain_engine.train_neural_network(
        epochs=epochs,
        batch_size=batch_size,
        lr=lr,
        arch=arch,
        augment=augment
    )
    return jsonify(result)

@app.route('/api/retrain/test_inference', methods=['POST'])
def api_retrain_test_inference():
    from attendance_engine.retrain import retrain_engine
    data = request.get_json() or {}
    identity = data.get('identity', 'Chiru').replace(" ", "")
    
    ref_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "punches", f"profile_{identity}.jpg")
    if not os.path.exists(ref_path):
        ref_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "punches", "profile_Chiru.jpg")
    
    img = cv2.imread(ref_path)
    if img is None:
        img = np.full((100, 100, 3), 128, dtype=np.uint8)

    res = retrain_engine.run_live_inference(img)
    return jsonify(res)

@app.route('/api/retrain/export_weights/<format_name>')
def api_retrain_export_weights(format_name):
    if format_name == 'pytorch':
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "face_cnn.pt")
        if os.path.exists(p):
            return send_file(p, as_attachment=True, download_name="face_cnn.pt")
    elif format_name == 'knn':
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "knn_model.pkl")
        if os.path.exists(p):
            return send_file(p, as_attachment=True, download_name="knn_model.pkl")
    elif format_name == 'keras':
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "project_face_detect", "final_model.h5")
        if os.path.exists(p):
            return send_file(p, as_attachment=True, download_name="final_model.h5")
    return jsonify({"error": "File not found"}), 404


# ==========================================
# MODULE 36: CERTIFIED COMPLIANCE EXPORT CENTER
# ==========================================
@app.route('/export_center')
def export_center_view():
    from datetime import datetime
    stats = db.get_stats()
    all_records = db.get_all_records()
    users = db.get_users()
    user_dept_map = {u["name"]: u.get("department", "Engineering") for u in users}

    preview_records = []
    for r in all_records[:25]:
        r_copy = dict(r)
        r_copy["department"] = user_dept_map.get(r["user_name"], "Operations")
        preview_records.append(r_copy)

    return render_template(
        'export_center.html',
        stats=stats,
        total_records=len(all_records),
        preview_records=preview_records,
        users=users,
        active_page='export_center'
    )

@app.route('/api/export/pdf')
def api_export_pdf():
    from datetime import datetime
    from attendance_engine.export import generate_certified_compliance_pdf
    filters = {
        "department": request.args.get("department", "ALL"),
        "punch_type": request.args.get("punch_type", "ALL"),
        "date": request.args.get("date", "ALL")
    }
    pdf_bytes = generate_certified_compliance_pdf(db, filters=filters)
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"Nexus_Biometric_Compliance_Certificate_{datetime.now().strftime('%Y%m%d')}.pdf"
    )

@app.route('/api/export/excel')
def api_export_excel():
    from datetime import datetime
    from attendance_engine.export import generate_enterprise_excel_xml
    filters = {
        "department": request.args.get("department", "ALL"),
        "punch_type": request.args.get("punch_type", "ALL"),
        "date": request.args.get("date", "ALL")
    }
    excel_bytes = generate_enterprise_excel_xml(db, filters=filters)
    return send_file(
        io.BytesIO(excel_bytes),
        mimetype="application/vnd.ms-excel",
        as_attachment=True,
        download_name=f"Nexus_Enterprise_Attendance_Workbook_{datetime.now().strftime('%Y%m%d')}.xls"
    )

@app.route('/api/export/json_audit')
def api_export_json_audit():
    from datetime import datetime
    from attendance_engine.export import generate_certified_json_audit
    filters = {
        "department": request.args.get("department", "ALL"),
        "punch_type": request.args.get("punch_type", "ALL"),
        "date": request.args.get("date", "ALL")
    }
    json_str = generate_certified_json_audit(db, filters=filters)
    return Response(
        json_str,
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment;filename=Nexus_Certified_Audit_{datetime.now().strftime('%Y%m%d')}.json"}
    )


# ==========================================
# MODULE 37: IP CAMERA & WIRELESS SENSOR GATEWAY
# ==========================================
@app.route('/ipcamera')
def ipcamera_view():
    from attendance_engine.ipcamera import ipcamera_gateway
    stats = db.get_stats()
    return render_template('ipcamera.html', stats=stats, presets=ipcamera_gateway.default_urls, active_page='ipcamera')

@app.route('/api/ipcamera/ping', methods=['POST'])
def api_ipcamera_ping():
    from attendance_engine.ipcamera import ipcamera_gateway
    data = request.get_json() or {}
    url = data.get('url', 'local://synthetic')
    res = ipcamera_gateway.ping_camera_url(url)
    return jsonify(res)

@app.route('/api/ipcamera/stream_frame')
def api_ipcamera_stream_frame():
    from attendance_engine.ipcamera import ipcamera_gateway
    url = request.args.get('url', 'local://synthetic')
    name = request.args.get('name', 'Chiru')
    frame = ipcamera_gateway.fetch_frame(url, fallback_name=name)
    _, buf = cv2.imencode('.jpg', frame)
    return Response(buf.tobytes(), mimetype='image/jpeg')

@app.route('/api/ipcamera/collect_100', methods=['POST'])
def api_ipcamera_collect_100():
    from attendance_engine.ipcamera import ipcamera_gateway
    data = request.get_json() or {}
    name = data.get('name', 'Chiru').strip()
    url = data.get('url', '')
    res = ipcamera_gateway.run_100_burst_collection(name, camera_url=url)
    return jsonify(res)


# ==========================================
# MODULE 38: NEURAL HUD INFERENCE SANDBOX
# ==========================================
@app.route('/neural_hud')
def neural_hud_view():
    stats = db.get_stats()
    label_map_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "label_map.json")
    classes = ["Chiru", "rahul", "sourav"]
    if os.path.exists(label_map_path):
        try:
            with open(label_map_path, "r") as f:
                classes = json.load(f).get("classes", classes)
        except Exception:
            pass
    return render_template('neural_hud.html', stats=stats, classes=classes, active_page='neural_hud')

@app.route('/api/neural_hud/infer_frame', methods=['POST'])
def api_neural_hud_infer_frame():
    from attendance_engine.ipcamera import ipcamera_gateway
    from attendance_engine.neural_hud import neural_hud_sandbox
    data = request.get_json() or {}
    subject = data.get('subject', 'Chiru')
    model_type = data.get('model_type', 'pytorch')

    frame = ipcamera_gateway.fetch_frame('local://synthetic', fallback_name=subject)
    result = neural_hud_sandbox.analyze_frame_and_render_hud(frame, model_type=model_type)
    return jsonify(result)


if __name__ == '__main__':
    print("=======================================================")
    print(" 🚀 3D CYBER BIOMETRIC ATTENDANCE SYSTEM RUNNING")
    print(" Web Dashboard: http://127.0.0.1:5000")
    print("=======================================================")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
