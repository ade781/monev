import os
import sys
import unittest
from datetime import datetime, timezone, timedelta

# Tambahkan root direktori ke path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import monev_bot

class TestMonevCore(unittest.TestCase):
    def test_safe_markdown(self):
        """Uji sanitasi teks markdown telegram"""
        raw = "Testing_text_with_underscore and `backticks`   multiple   spaces."
        cleaned = monev_bot.safe_markdown(raw)
        self.assertNotIn("_", cleaned)
        self.assertNotIn("`", cleaned)
        self.assertIn("'", cleaned)

        # Uji truncation
        truncated = monev_bot.safe_markdown("A" * 100, max_len=20)
        self.assertTrue(truncated.endswith("..."))
        self.assertLessEqual(len(truncated), 23)

    def test_wrap_url(self):
        """Uji pembungkusan URL proxy"""
        target = "https://maganghub.kemnaker.go.id/api/naco/login"
        
        # Simpan env lama
        old_proxy = os.environ.get("CLOUDFLARE_WORKER_URL")
        try:
            # Tanpa proxy
            os.environ["CLOUDFLARE_WORKER_URL"] = ""
            self.assertEqual(monev_bot.wrap_url(target), target)

            # Dengan proxy
            os.environ["CLOUDFLARE_WORKER_URL"] = "https://proxy.example.workers.dev"
            wrapped = monev_bot.wrap_url(target)
            self.assertTrue(wrapped.startswith("https://proxy.example.workers.dev/?url="))

            # Tidak double wrap
            double_wrapped = monev_bot.wrap_url(wrapped)
            self.assertEqual(wrapped, double_wrapped)
        finally:
            if old_proxy is not None:
                os.environ["CLOUDFLARE_WORKER_URL"] = old_proxy
            else:
                os.environ.pop("CLOUDFLARE_WORKER_URL", None)

    def test_jittered_coordinates(self):
        """Uji deviasi koordinat GPS jitter"""
        lat, long = monev_bot.get_jittered_coordinates()
        self.assertAlmostEqual(lat, monev_bot.OFFICE_LAT, delta=0.0003)
        self.assertAlmostEqual(long, monev_bot.OFFICE_LONG, delta=0.0003)

    def test_debounce_lock(self):
        """Uji mekanisme debounce penguncian trigger"""
        trigger_name = "test_unit_lock_action"
        # Panggilan pertama harus diizinkan
        allowed1 = monev_bot.check_and_lock_trigger(trigger_name, window_seconds=60, force=True)
        self.assertTrue(allowed1)

        # Panggilan kedua dalam window 60s tanpa force harus ditolak
        allowed2 = monev_bot.check_and_lock_trigger(trigger_name, window_seconds=60, force=False)
        self.assertFalse(allowed2)

        # Panggilan ketiga dengan force=True harus diizinkan kembali
        allowed3 = monev_bot.check_and_lock_trigger(trigger_name, window_seconds=60, force=True)
        self.assertTrue(allowed3)

    def test_template_collection(self):
        """Uji struktur template kegiatan"""
        templates = monev_bot.muat_semua_template()
        self.assertIsInstance(templates, list)
        self.assertGreaterEqual(len(templates), 1)

        first = templates[0]
        self.assertIn("id", first)
        self.assertIn("category", first)
        self.assertIn("activity", first)
        self.assertIn("learning", first)
        self.assertIn("obstacles", first)

    def test_extract_activity_snippet(self):
        """Uji ekstraksi cuplikan 8-12 kata kegiatan monev"""
        short_text = "Mengerjakan tugas operasional unit kerja."
        self.assertEqual(monev_bot.extract_activity_snippet(short_text, max_words=12), short_text)

        long_text = "Satu dua tiga empat lima enam tujuh delapan sembilan sepuluh sebelas dua belas tiga belas empat belas"
        snip = monev_bot.extract_activity_snippet(long_text, max_words=12)
        self.assertTrue(snip.endswith("..."))
        # 12 kata + trailing ellipsis dihitung
        words = snip.replace("...", "").split()
        self.assertEqual(len(words), 12)

    def test_safe_cookie_jar(self):
        """Uji SafeCookieJar memfilter cookie acw_tc WAF"""
        import http.cookiejar
        jar = monev_bot.SafeCookieJar()
        
        c_waf = http.cookiejar.Cookie(
            version=0, name="acw_tc", value="secret123", port=None, port_specified=False,
            domain="kemnaker.go.id", domain_specified=True, domain_initial_dot=False,
            path="/", path_specified=True, secure=True, expires=None, discard=False,
            comment=None, comment_url=None, rest={}
        )
        c_normal = http.cookiejar.Cookie(
            version=0, name="session_token", value="valid456", port=None, port_specified=False,
            domain="kemnaker.go.id", domain_specified=True, domain_initial_dot=False,
            path="/", path_specified=True, secure=True, expires=None, discard=False,
            comment=None, comment_url=None, rest={}
        )
        jar.set_cookie(c_waf)
        jar.set_cookie(c_normal)
        
        cookie_names = [c.name for c in jar]
        self.assertNotIn("acw_tc", cookie_names)
        self.assertIn("session_token", cookie_names)

    def test_template_stock_and_themes(self):
        """Uji stok 40 template dan fokus pengembangan aplikasi"""
        templates = monev_bot.muat_semua_template()
        self.assertEqual(len(templates), 40)
        
        # Seluruh template harus memiliki ID unik dan non-empty fields
        ids = [t["id"] for t in templates]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(min(ids), 18)
        self.assertEqual(max(ids), 57)
        
        for t in templates:
            self.assertTrue(len(t["activity"]) > 80)
            self.assertTrue(len(t["learning"]) > 40)
            self.assertTrue(len(t["obstacles"]) > 40)
            # Pastikan kategori relevan dengan engineering/pengembangan web
            self.assertIn(t["category"], [
                "security", "ui_ux", "qr_scanner", "backend_api", "master_data",
                "frontend_features", "performance", "realtime_features", "testing_qa",
                "database_migration", "api_documentation", "backup_routine", "authorization_rbac",
                "image_compression", "offline_sync", "logging_monitoring", "healthcheck_system",
                "pwa_offline", "data_analytics", "security_audit", "automated_testing",
                "geofencing_validation", "bulk_management", "error_telemetry", "pwa_push_notification",
                "data_export_excel", "form_validation_advanced", "search_indexing", "theme_customization",
                "camera_scanner_enhancement", "database_optimization", "api_rate_limiting",
                "frontend_routing_guards", "responsive_layout_stepper", "data_security_encryption",
                "pdf_export_formatting", "performance_image_lazyload", "ci_cd_automation"
            ])

        # Sisa template belum terpakai harus tepat 40
        _, sisa, total = monev_bot.ambil_template_belum_terpakai()
        self.assertEqual(sisa, 40)
        self.assertEqual(total, 40)

    def test_weekend_auto_monev_skip(self):
        """Uji auto-monev melewati eksekusi di hari Sabtu dan Minggu"""
        from unittest.mock import patch
        
        # Simulasi hari Sabtu (2026-09-26)
        saturday = datetime(2026, 9, 26, 15, 0, 0, tzinfo=monev_bot.WIB)
        with patch("monev_bot.datetime") as mock_dt:
            mock_dt.now.return_value = saturday
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            
            res = monev_bot.main(force=False, notify_telegram=False)
            self.assertEqual(res["status"], "weekend_skipped")
            self.assertIn("akhir pekan", res["message"].lower())

if __name__ == "__main__":
    unittest.main()
