"""
COMPREHENSIVE TEST SUITE FOR NEXUS 36-MODULE BIOMETRIC INTELLIGENCE PLATFORM
Verifies all 36 web modules and key REST API endpoints return HTTP 200 OK.
"""

import sys
import unittest
from app import app, db

class TestNexusAll36Modules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        cls.client = app.test_client()

    def test_all_36_views(self):
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
            ('/export_center', 'Certified Export Center (Module 36)')
        ]

        print(f"\n=======================================================")
        print(f" TESTING ALL 36 NEXUS WEB MODULES (HTTP GET 200 OK)")
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
        print(f" ALL 36 WEB MODULES PASSED WITH 100% SUCCESS!")
        print(f"=======================================================\n")

    def test_key_apis(self):
        print(f"=======================================================")
        print(f" TESTING KEY REST & EXPORT APIS")
        print(f"=======================================================")

        # 1. Stats
        r = self.client.get('/api/stats')
        self.assertEqual(r.status_code, 200)
        print(" [✓] /api/stats -> HTTP 200 OK")

        # 2. Retrain status
        r = self.client.get('/api/retrain/status')
        self.assertEqual(r.status_code, 200)
        print(" [✓] /api/retrain/status -> HTTP 200 OK")

        # 3. Certified PDF export
        r = self.client.get('/api/export/pdf')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, 'application/pdf')
        self.assertGreater(len(r.data), 1000)
        print(f" [✓] /api/export/pdf -> HTTP 200 OK (size={len(r.data)} bytes PDF)")

        # 4. Enterprise Excel export
        r = self.client.get('/api/export/excel')
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'urn:schemas-microsoft-com:office:spreadsheet', r.data)
        print(f" [✓] /api/export/excel -> HTTP 200 OK (size={len(r.data)} bytes XLS)")

        # 5. Signed JSON audit export
        r = self.client.get('/api/export/json_audit')
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'digital_signature', r.data)
        print(" [✓] /api/export/json_audit -> HTTP 200 OK")

        # 6. Live Inference test bench
        r = self.client.post('/api/retrain/test_inference', json={"identity": "Chiru"})
        self.assertEqual(r.status_code, 200)
        json_data = r.get_json()
        self.assertTrue(json_data.get('success'))
        print(f" [✓] /api/retrain/test_inference -> HTTP 200 OK (pred={json_data.get('predicted_identity')}, conf={json_data.get('confidence')}%)")

        print(f"=======================================================")
        print(f" ALL REST & EXPORT APIS PASSED!")
        print(f"=======================================================\n")


if __name__ == '__main__':
    unittest.main()
