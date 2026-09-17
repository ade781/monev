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

if __name__ == "__main__":
    unittest.main()
