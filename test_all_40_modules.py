"""
COMPREHENSIVE TEST SUITE FOR NEXUS 40-MODULE BIOMETRIC INTELLIGENCE PLATFORM
Verifies all 40 web modules and key REST API endpoints return HTTP 200 OK.
"""

import sys
import unittest
from app import app, db

class TestNexusAll40Modules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        cls.client = app.test_client()

    def test_all_40_views(self):
        endpoints = [
            ('/', 'Live Monitor & 3D HUD'),
            ('/kiosk', 'Gate Kiosk Turnstile'),
            ('/crowd', 'Crowd Multi-Target'),
            ('/access', 'Door Solenoid Relays'),
            ('/watchlist', 'Watchlist & VIP Clearance'),
            ('/compare', 'Face Compare & Heatmap'),
            ('/liveness', 'Anti-Spoof Liveness Lab'),
            ('/avatar', '3D Digital Twin Avatar'),
            ('/graph', 'Relation & Threat Graph'),
            ('/ledger', 'Cryptographic Audit Ledger'),
            ('/search', 'Forensic Re-ID Search'),
            ('/dossier', 'Biometric Dossier Timeline'),
            ('/geofence', 'GPS Geo-Fence & Beacon'),
            ('/hardware', 'Hardware Telemetry & Coils'),
            ('/floorplan', 'Spatial Floor Plan Radar'),
            ('/vitality', 'Vitality & Fatigue Telemetry'),
            ('/multicam', '4x CCTV Surveillance Matrix'),
            ('/terminal', 'Cyber Voice CLI Terminal'),
            ('/qrscan', '2FA QR Badge Scanner'),
            ('/enroll', 'Dynamic Face Enrollment'),
            ('/forecast', 'Predictive Attendance ML'),
            ('/shifts', 'Department Shifts & Policies'),
            ('/analytics', 'Deep Analytics Suite'),
            ('/records', 'Audit Attendance Records'),
            ('/report', 'Daily Certified Audit Report'),
            ('/idcard', 'Holographic ID Badges'),
            ('/notifications', 'Notification Dispatch Hub'),
            ('/alerts', 'Security Intrusion Incidents'),
            ('/studio', 'AI Neural Studio'),
            ('/vault', 'Cryptographic Vault & Failover'),
            ('/adversarial', 'Adversarial & Deepfake Arena'),
            ('/mesh', 'Global Campus Mesh & P2P'),
            ('/streams', 'RTSP & Edge Camera Router'),
            ('/collector', 'Face Dataset Studio'),
            ('/retrain', 'Neural Retrainer (Module 35)'),
            ('/export_center', 'Certified Export Center (Module 36)'),
            ('/ipcamera', 'Wireless IP Camera (Module 37)'),
            ('/neural_hud', 'Neural HUD Sandbox (Module 38)'),
            ('/aging', 'Facial Aging Lab (Module 39)'),
            ('/mission_control', 'Mission Control SOC (Module 40)')
        ]

        print(f"\n=======================================================")
        print(f" TESTING ALL 40 NEXUS WEB MODULES (HTTP GET 200 OK)")
        print(f"=======================================================")

        failed = []
        for path, name in endpoints:
            response = self.client.get(path)
            status = response.status_code
            has_nav = b'apps-matrix-drawer' in response.data or b'cyber-header' in response.data
            status_symbol = "✓" if status == 200 and has_nav else "✗"
            print(f" [{status_symbol}] {path:18} -> HTTP {status} (nav={has_nav}) [{name}]")
            if status != 200 or not has_nav:
                failed.append((path, name, status, has_nav))

        self.assertEqual(len(failed), 0, f"Failed endpoints: {failed}")
        print(f"=======================================================")
        print(f" ALL 40 WEB MODULES PASSED WITH 100% SUCCESS!")
        print(f"=======================================================\n")

    def test_new_apis(self):
        print(f"=======================================================")
        print(f" TESTING MODULE 39 & 40 REST APIS")
        print(f"=======================================================")

        # 1. Aging simulation API
        r = self.client.post('/api/aging/simulate', json={"person": "Chiru", "target_age": 60})
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data.get("success"))
        print(f" [✓] /api/aging/simulate -> HTTP 200 OK (retention={data.get('biometric_retention_pct')}%, status={data.get('match_status')})")

        # 2. Mission Control Telemetry
        r = self.client.get('/api/mission_control/telemetry')
        self.assertEqual(r.status_code, 200)
        soc_data = r.get_json()
        self.assertEqual(soc_data.get("active_modules_count"), 40)
        print(f" [✓] /api/mission_control/telemetry -> HTTP 200 OK (modules={soc_data.get('active_modules_count')}, defcon={soc_data.get('defcon', {}).get('level')})")

        # 3. Mission Control Emergency Lockdown
        r = self.client.post('/api/mission_control/lockdown', json={"reason": "Automated Unit Test Verification"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json().get("success"))
        print(" [✓] /api/mission_control/lockdown -> HTTP 200 OK")

        print(f"=======================================================")
        print(f" ALL MODULE 39 & 40 REST APIS PASSED!")
        print(f"=======================================================\n")


if __name__ == '__main__':
    unittest.main()
