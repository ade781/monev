from http.server import BaseHTTPRequestHandler
import urllib.request
import urllib.parse
import json
import sys
import os
from datetime import datetime

# Tambahkan direktori root agar bisa import monev_bot
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

import monev_bot

# Penyimpanan in-memory & file fallback
PROCESSED_UPDATES = set()
_PENDING_ACTIVITY = {}

def _set_pending(chat_id, text):
    _PENDING_ACTIVITY[str(chat_id)] = text
    try:
        with open(os.path.join("/tmp", f"pending_{chat_id}.txt"), "w", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass

def _get_pending(chat_id):
    cid = str(chat_id)
    text = _PENDING_ACTIVITY.pop(cid, None)
    if not text:
        p = os.path.join("/tmp", f"pending_{chat_id}.txt")
        try:
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    text = f.read().strip()
                os.remove(p)
        except Exception:
            pass
    return text

# Keyboard konfirmasi khusus /isi
CONFIRM_ISI_KEYBOARD = {
    "inline_keyboard": [
        [
            {"text": "✅ Ya, Kirim Sekarang", "callback_data": "/isi_confirm"},
            {"text": "❌ Batalkan", "callback_data": "/monev_cancel"}
        ]
    ]
}

def handle_telegram_command(chat_id, text):
    """Memproses command Telegram dari pengguna dan mengembalikan (teks_balasan, keyboard)"""
    owner_chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if owner_chat_id and str(chat_id).strip() != owner_chat_id:
        return ("⛔ *Akses Ditolak*\nBot ini bersifat privat dan hanya merespons Mas Ade.", None)

    cmd = text.split()[0].lower().split("@")[0] if text else ""

    if cmd in ["/start", "/help", "/bantuan"]:
        return (
            "👋 *Halo Mas Ade! Saya Bot Monev ADE7 Reminder.*\n\n"
            "Bot ini siap membantu monitoring dan pengisian presensi cadangan harian Anda.\n\n"
            "📌 *Perintah yang Tersedia:*\n"
            "🔹 `/cek` - Cek apakah presensi hari ini sudah terisi atau belum\n"
            "🔹 `/tes` - Tes koneksi & kesehatan sistem (tanpa submit presensi)\n"
            "🔹 `/monev` - Eksekusi pengisian monev hari ini (dengan konfirmasi Ya/Tidak)\n"
            "🔹 `/rekap` - Ringkasan performa kehadiran 7 hari terakhir\n"
            "🔹 `/isi <kegiatan>` - Isi presensi hari ini dengan catatan khusus\n"
            "🔹 `/sisa` - Cek sisa stok template yang belum pernah terpakai\n"
            "🔹 `/proxy` - Cek status Cloudflare Reverse Proxy aktif\n\n"
            f"🆔 *Chat ID Anda:* `{chat_id}`",
            monev_bot.MENU_KEYBOARD
        )

    elif cmd in ["/tes"]:
        msg = monev_bot.test_koneksi_sistem()
        return (msg, monev_bot.MENU_KEYBOARD)

    elif cmd in ["/cek", "/status"]:
        msg = monev_bot.format_status_presensi()
        return (msg, monev_bot.MENU_KEYBOARD)

    elif cmd in ["/monev", "/run", "/submit"]:
        diag = monev_bot.periksa_koneksi_dan_status()
        if diag.get("success") and diag.get("sudah_absen"):
            return ("monev sudah diisii", monev_bot.MENU_KEYBOARD)

        today_wib = datetime.now(monev_bot.WIB)
        today_str = today_wib.strftime("%Y-%m-%d")
        jam_str = today_wib.strftime("%H:%M:%S")
        return (
            "⚠️ *KONFIRMASI EKSEKUSI MONEV*\n\n"
            "Halo Mas Ade, apakah Anda yakin ingin mengisi presensi dan laporan Monev hari ini ke server Kemnaker sekarang?\n\n"
            f"📅 *Tanggal:* `{today_str}`\n"
            f"⏰ *Waktu:* `{jam_str} WIB`\n\n"
            "👇 _Silakan klik tombol di bawah untuk konfirmasi:_",
            monev_bot.CONFIRM_KEYBOARD
        )

    elif cmd in ["/monev_confirm", "ya", "/ya"]:
        try:
            res = monev_bot.main(force=True, notify_telegram=False)
            return (res.get("message", "Selesai dieksekusi"), monev_bot.MENU_KEYBOARD)
        except Exception as e:
            return (f"❌ *Gagal Eksekusi:* `{str(e)}`", monev_bot.MENU_KEYBOARD)

    elif cmd in ["/isi_confirm"]:
        kegiatan = _get_pending(chat_id)
        if not kegiatan:
            return ("⚠️ *Sesi Kedaluwarsa*\nTidak ada catatan kegiatan yang tertunda. Silakan ketik ulang `/isi <kegiatan>`.", monev_bot.MENU_KEYBOARD)

        diag = monev_bot.periksa_koneksi_dan_status()
        if diag.get("success") and diag.get("sudah_absen"):
            return ("monev sudah diisii", monev_bot.MENU_KEYBOARD)

        try:
            res = monev_bot.submit_monev(custom_activity=kegiatan)
            msg = res.get("message") or "Laporan berhasil diserahkan ke server Kemnaker!"
            return (
                "📝 *PENGISIAN KEGIATAN KUSTOM BERHASIL*\n\n"
                "👤 *Peserta:* `Mas Ade`\n"
                f"📌 *Kegiatan:* _{kegiatan}_\n\n"
                f"📡 *Respon Server:* `{msg}`",
                monev_bot.MENU_KEYBOARD
            )
        except Exception as e:
            return (f"❌ *Gagal Kirim:* `{str(e)}`", monev_bot.MENU_KEYBOARD)

    elif cmd in ["/monev_cancel", "tidak", "/tidak", "/batal"]:
        _get_pending(chat_id)
        return (
            "❌ *Aksi Dibatalkan.*\n\n"
            "Tidak ada data atau laporan presensi yang dikirim ke Kemnaker. Semuanya tetap aman terkendali! 👍",
            monev_bot.MENU_KEYBOARD
        )

    elif cmd in ["/rekap"]:
        return (monev_bot.ambil_rekap_mingguan(), monev_bot.MENU_KEYBOARD)

    elif cmd in ["/isi"]:
        kegiatan = text[len(cmd):].strip()
        if not kegiatan:
            return (
                "⚠️ *Format Pengisian Kegiatan Kustom:*\n"
                "Ketik `/isi <kegiatan Anda>`\n\n"
                "Contoh:\n"
                "`/isi Mengerjakan integrasi REST API dan optimasi query database`",
                monev_bot.MENU_KEYBOARD
            )

        diag = monev_bot.periksa_koneksi_dan_status()
        if diag.get("success") and diag.get("sudah_absen"):
            return ("monev sudah diisii", monev_bot.MENU_KEYBOARD)

        _set_pending(chat_id, kegiatan)
        today_wib = datetime.now(monev_bot.WIB)
        today_str = today_wib.strftime("%Y-%m-%d")
        jam_str = today_wib.strftime("%H:%M:%S")

        return (
            "⚠️ *KONFIRMASI PENGISIAN KEGIATAN KUSTOM*\n\n"
            f"📅 *Tanggal:* `{today_str}` ({jam_str} WIB)\n"
            f"📝 *Kegiatan:*\n_{kegiatan}_\n\n"
            "Apakah Anda yakin ingin submit laporan ini ke Kemnaker sekarang?",
            CONFIRM_ISI_KEYBOARD
        )

    elif cmd in ["/proxy"]:
        cf_proxy = os.getenv("CLOUDFLARE_WORKER_URL")
        if cf_proxy:
            return (f"🌐 *Status Cloudflare Reverse Proxy:*\n✅ Aktif: `{cf_proxy}`", monev_bot.MENU_KEYBOARD)
        else:
            return (
                "🌐 *Status Cloudflare Reverse Proxy:*\n"
                "⚠️ Belum disetel. Tambahkan variabel `CLOUDFLARE_WORKER_URL` di Vercel Settings -> Environment Variables.",
                monev_bot.MENU_KEYBOARD
            )

    elif cmd in ["/sisa", "/template", "/templates"]:
        sisa, total = monev_bot.hitung_sisa_template()
        terpakai = total - sisa
        warning_info = ""
        if sisa == 0:
            warning_info = "\n\n⚠️ *Perhatian:* Semua template telah terpakai! Mohon tambahkan template baru ke `templates.json`."
        elif sisa <= 5:
            warning_info = f"\n\n⚠️ *Pengingat:* Sisa template tersisa sedikit ({sisa}). Disarankan menambah template baru."

        return (
            "📦 *STATUS STOK TEMPLATE KEGIATAN MONEV*\n\n"
            f"📊 *Total Koleksi:* `{total} template`\n"
            f"✅ *Sudah Pernah Terpakai:* `{terpakai} template`\n"
            f"⏳ *Sisa Belum Terpakai:* *{sisa} template*\n\n"
            "✨ _Setiap template dijamin tidak akan pernah dipakai berulang kali. Saat auto-monev jam 21:00 berjalan, sistem akan memilih template berikutnya secara berurutan._"
            f"{warning_info}",
            monev_bot.MENU_KEYBOARD
        )

    else:
        return (
            f"❓ Perintah `{text}` tidak dikenal.\n"
            "Ketik `/help` untuk melihat daftar perintah, atau gunakan tombol di bawah.",
            monev_bot.MENU_KEYBOARD
        )

def _send_reply(chat_id, res):
    reply_text, keyboard = res if isinstance(res, tuple) else (res, monev_bot.MENU_KEYBOARD)
    monev_bot.kirim_telegram(reply_text, chat_id=chat_id, reply_markup=keyboard)

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        """Menangani Webhook pesan masuk dan callback query tombol dari Telegram"""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            update = json.loads(body.decode("utf-8")) if body else {}

            # Pencegahan duplikasi request dari auto-retry Telegram
            update_id = update.get("update_id")
            if update_id:
                if update_id in PROCESSED_UPDATES:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"status": "duplicate_skipped"}')
                    return
                PROCESSED_UPDATES.add(update_id)
                if len(PROCESSED_UPDATES) > 100:
                    PROCESSED_UPDATES.pop()

            token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
            if token.lower().startswith("bot"):
                token = token[3:]

            # 1. Tangani tombol interaktif (Callback Query)
            callback_query = update.get("callback_query")
            if callback_query:
                cq_id = callback_query.get("id")
                chat_id = callback_query.get("message", {}).get("chat", {}).get("id") or callback_query.get("from", {}).get("id")
                cq_data = callback_query.get("data", "").strip()

                if cq_id and token:
                    try:
                        ack_url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
                        ack_req = urllib.request.Request(
                            ack_url,
                            data=json.dumps({"callback_query_id": cq_id}).encode("utf-8"),
                            headers={"Content-Type": "application/json"}
                        )
                        urllib.request.urlopen(ack_req, timeout=5)
                    except Exception:
                        pass

                if chat_id and cq_data:
                    _send_reply(chat_id, handle_telegram_command(chat_id, cq_data))

            # 2. Tangani pesan teks biasa
            message = update.get("message") or update.get("edited_message")
            if message:
                chat_id = message.get("chat", {}).get("id")
                text = message.get("text", "").strip()
                if chat_id and text:
                    _send_reply(chat_id, handle_telegram_command(chat_id, text))

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')

        except Exception as e:
            print(f"[Webhook Error] {e}")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "error_handled"}')

    def do_GET(self):
        """Menangani Webhook Telegram setup, diagnosa via browser, dan trigger aman"""
        parsed_url = urllib.parse.urlparse(self.path)
        query_params = urllib.parse.parse_qs(parsed_url.query)

        # 1. Fitur Setup Webhook otomatis
        if "setup" in query_params or "setup_webhook" in query_params:
            host = self.headers.get("Host", "")
            webhook_url = query_params.get("url", [f"https://{host}/api/cron"])[0]
            
            token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
            if token.lower().startswith("bot"):
                token = token[3:]

            tg_res_body = {}
            if token:
                tg_url = f"https://api.telegram.org/bot{token}/setWebhook?url={urllib.parse.quote(webhook_url)}"
                try:
                    res = urllib.request.urlopen(tg_url)
                    tg_res_body = json.loads(res.read().decode("utf-8"))
                except Exception as e:
                    tg_res_body = {"error": str(e)}

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "action": "setup_webhook",
                "webhook_url": webhook_url,
                "telegram_response": tg_res_body,
                "instruction": "Webhook aktif! Buka Telegram @Cekad_bot dan ketik /start"
            }, indent=2).encode("utf-8"))
            return

        # 2. Fitur Pengingat
        if "type" in query_params and query_params["type"][0] == "reminder":
            force_mode = query_params.get("mode", [None])[0]
            force_send = query_params.get("force", ["0"])[0] in ["1", "true"] or "force" in query_params
            result = monev_bot.kirim_pengingat_monev(force_mode=force_mode, force_send=force_send)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode("utf-8"))
            return

        # 3. Fitur Tes Diagnostik via GET (?test=1)
        if "test" in query_params:
            diag = monev_bot.test_koneksi_sistem()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(diag.encode("utf-8"))
            return

        # 4. Trigger pengisian otomatis harian (dengan verifikasi CRON_SECRET)
        if "type" in query_params and query_params["type"][0] in ["auto", "cron"]:
            cron_secret = os.getenv("CRON_SECRET", "").strip()
            auth_header = self.headers.get("Authorization", "")
            provided_secret = query_params.get("secret", [""])[0]

            if cron_secret and provided_secret != cron_secret and auth_header != f"Bearer {cron_secret}":
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error": "Unauthorized: Invalid CRON_SECRET"}')
                return

            try:
                result = monev_bot.main(notify_telegram=True)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "result": result}).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode("utf-8"))
            return

        # 5. Default GET (Safe: Halaman info status)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "status": "online",
            "service": "Monev ADE7 Reminder Bot API",
            "message": "Endpoint aktif. Silakan buka bot Telegram @Cekad_bot untuk interaksi."
        }, indent=2).encode("utf-8"))
