"""
COMPREHENSIVE TEST SUITE FOR NEXUS 38-MODULE BIOMETRIC INTELLIGENCE PLATFORM
Verifies all 38 web modules and key REST API endpoints return HTTP 200 OK.
"""

import sys
import unittest
from app import app, db

class TestNexusAll38Modules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        cls.client = app.test_client()

    def test_all_38_views(self):
        endpoints = [
            ('/', 'Live Monitor'),
            ('/kiosk', 'Gate Kiosk'),
            ('/crowd', 'Crowd Multi-Target'),
            ('/access', 'Door Solenoids'),
            ('/watchlist', 'Watchlist & VIP'),
            ('/compare', 'Face Compare & Heatmap'),
            ('/liveness', 'Anti-Spoof Liveness Lab'),
            ('/avatar', '3D Digital Twin Avatar'),
            ('/graph', 'Relation & Threat Graph'),
            ('/ledger', 'Cryptographic Ledger'),
            ('/search', 'Forensic Search'),
            ('/dossier', 'Biometric Dossier'),
            ('/geofence', 'GPS Geo-Fence'),
            ('/hardware', 'Hardware Telemetry'),
            ('/floorplan', 'Spatial Floor Plan'),
            ('/vitality', 'Vitality & Fatigue'),
            ('/multicam', 'Surveillance Matrix'),
            ('/terminal', 'Voice CLI Terminal'),
            ('/qrscan', '2FA QR Scanner'),
            ('/enroll', 'Face Enrollment'),
            ('/forecast', 'Predictive Forecast'),
            ('/shifts', 'Shifts & Policies'),
            ('/analytics', 'Analytics Suite'),
            ('/records', 'Audit Records'),
            ('/report', 'Daily Audit Report'),
            ('/idcard', 'Holo ID Badges'),
            ('/notifications', 'Notification Hub'),
            ('/alerts', 'Security Incidents'),
            ('/studio', 'AI Neural Studio'),
            ('/vault', 'Cryptographic Vault'),
            ('/adversarial', 'Adversarial Arena'),
            ('/mesh', 'Global Campus Mesh'),
            ('/streams', 'RTSP & IP Streams'),
            ('/collector', 'Dataset Studio'),
            ('/retrain', 'Neural Retrainer (Module 35)'),
            ('/export_center', 'Certified Export Center (Module 36)'),
            ('/ipcamera', 'IP Camera Gateway (Module 37)'),
            ('/neural_hud', 'Neural HUD Sandbox (Module 38)')
        ]

        print(f"\n=======================================================")
        print(f" TESTING ALL 38 NEXUS WEB MODULES (HTTP GET 200 OK)")
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
        print(f" ALL 38 WEB MODULES PASSED WITH 100% SUCCESS!")
        print(f"=======================================================\n")

    def test_new_apis(self):
        print(f"=======================================================")
        print(f" TESTING MODULE 37 & 38 REST APIS")
        print(f"=======================================================")

        # 1. IP Camera Ping
        r = self.client.post('/api/ipcamera/ping', json={"url": "local://synthetic"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json().get("reachable"))
        print(" [✓] /api/ipcamera/ping -> HTTP 200 OK (reachable=True)")

        # 2. IP Camera Stream Frame
        r = self.client.get('/api/ipcamera/stream_frame?url=local://synthetic&name=Chiru')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, 'image/jpeg')
        print(f" [✓] /api/ipcamera/stream_frame -> HTTP 200 OK (bytes={len(r.data)})")

        # 3. Neural HUD Inference
        r = self.client.post('/api/neural_hud/infer_frame', json={"subject": "Chiru", "model_type": "pytorch"})
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data.get("success"))
        print(f" [✓] /api/neural_hud/infer_frame -> HTTP 200 OK (faces={data.get('faces_count')}, latency={data.get('latency_ms')}ms)")

        print(f"=======================================================")
        print(f" ALL MODULE 37 & 38 REST APIS PASSED!")
        print(f"=======================================================\n")


if __name__ == '__main__':
    unittest.main()
