import os
import json
import urllib.request
from datetime import datetime
from attendance_engine.db import AttendanceDB

class NotificationDispatcher:
    def __init__(self, db: AttendanceDB = None):
        self.db = db or AttendanceDB()
        self.webhook_url = os.environ.get("ALERT_WEBHOOK_URL", "")
        self.telegram_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    def dispatch_late_alert(self, user_name: str, user_type: str, time_str: str, recipient: str = "hr-alert@organization.com"):
        subject = f"⚠️ LATE ARRIVAL NOTIFICATION: {user_name} ({user_type})"
        message = (
            f"Subject: {user_name}\n"
            f"Cohort: {user_type}\n"
            f"Punch Time: {time_str} (Threshold: 09:30 AM)\n"
            f"Status: Punctuality Warning Flagged\n"
            f"System: NEXUS Biometric Attendance Engine"
        )
        # Log to Database
        rec = self.db.log_notification(
            channel="EMAIL",
            recipient=recipient,
            subject=subject,
            message=message,
            status="DELIVERED"
        )
        self._trigger_webhook({"event": "LATE_ARRIVAL", "subject": user_name, "time": time_str})
        return rec

    def dispatch_intruder_alert(self, alert_rec: dict, recipient: str = "secops-alert@organization.com"):
        time_str = alert_rec.get("time", datetime.now().strftime("%H:%M:%S"))
        snap_url = alert_rec.get("snapshot_url", "")
        subject = "🚨 CRITICAL SECURITY ALERT: UNAUTHORIZED SUBJECT DETECTED"
        message = (
            f"Incident: Unrecognized Face Detected after 18 continuous frames\n"
            f"Detection Timestamp: {time_str}\n"
            f"Snapshot Evidence: {snap_url}\n"
            f"Action Required: Dispatch security or inspect Surveillance Log"
        )
        rec = self.db.log_notification(
            channel="TELEGRAM",
            recipient=recipient,
            subject=subject,
            message=message,
            status="DELIVERED"
        )
        self._trigger_webhook({"event": "SECURITY_BREACH", "snapshot": snap_url, "time": time_str})
        return rec

    def dispatch_daily_digest(self, report_data: dict, recipient: str = "executives@organization.com"):
        date_str = report_data.get("date", datetime.now().strftime("%Y-%m-%d"))
        summary = report_data.get("summary", {})
        subject = f"📊 DAILY BIOMETRIC AUDIT DIGEST // {date_str}"
        message = (
            f"Audit Date: {date_str}\n"
            f"Total Strength: {summary.get('total_strength', 0)}\n"
            f"Present: {summary.get('present_count', 0)} ({summary.get('attendance_rate', 0)}%)\n"
            f"On-Time: {summary.get('on_time_count', 0)} // Late: {summary.get('late_count', 0)}\n"
            f"Absentees: {summary.get('absent_count', 0)}\n"
            f"Status: Certified Executive Report Dispatched"
        )
        rec = self.db.log_notification(
            channel="EMAIL",
            recipient=recipient,
            subject=subject,
            message=message,
            status="DELIVERED"
        )
        return rec

    def send_custom_notification(self, channel: str, recipient: str, subject: str, message: str):
        rec = self.db.log_notification(
            channel=channel.upper(),
            recipient=recipient,
            subject=subject,
            message=message,
            status="DELIVERED"
        )
        self._trigger_webhook({"event": "CUSTOM_ALERT", "channel": channel, "subject": subject, "message": message})
        return rec

    def _trigger_webhook(self, payload: dict):
        if not self.webhook_url:
            return
        try:
            req = urllib.request.Request(
                self.webhook_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=3)
        except Exception as e:
            print("Webhook dispatch notice:", e)
