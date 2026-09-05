from http.server import BaseHTTPRequestHandler
import urllib.request
import urllib.parse
import json
import sys
import os

# Tambahkan direktori root agar bisa import monev_bot
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

import monev_bot

def handle_telegram_command(chat_id, text):
    """Memproses command Telegram dari pengguna dan mengembalikan teks balasan"""
    cmd = text.split()[0].lower() if text else ""

    if cmd in ["/start", "/help", "/bantuan"]:
        return (
            "👋 *Halo! Saya Bot Monev MagangHub Kemnaker.*\n\n"
            "Bot ini siap membantu monitoring dan pengisian presensi cadangan harian Anda.\n\n"
            "📌 *Perintah yang Tersedia:*\n"
            "🔹 `/tes` - Tes koneksi ke SSO Kemnaker & cek status absensi hari ini\n"
            "🔹 `/cek` - Cek riwayat presensi terbaru Anda\n"
            "🔹 `/monev` - Eksekusi pengisian monev otomatis sekarang\n"
            "🔹 `/proxy` - Cek status proxy Indonesia yang aktif\n\n"
            f"🆔 *Chat ID Anda:* `{chat_id}`"
        )

    elif cmd in ["/tes", "/cek", "/status"]:
        diag = monev_bot.periksa_koneksi_dan_status()
        if diag.get("success"):
            sudah = diag.get("sudah_absen")
            status_absen = "✅ *SUDAH TERISI (PRESENT)*" if sudah else "⚠️ *BELUM TERISI*"
            ket = "Anda sudah mengisi presensi hari ini secara aman." if sudah else "Belum ada presensi untuk hari ini. Bot akan backup otomatis pukul 21:00 WIB."
            
            return (
                "🔍 *HASIL TES KONEKSI KEMNAKER*\n\n"
                f"👤 *Nama Peserta:* `{diag.get('user_name')}`\n"
                f"🏢 *Nama Mentor:* `{diag.get('mentor_name')}`\n"
                f"📅 *Tanggal:* `{diag.get('today_str')}`\n"
                f"⏰ *Waktu Server:* `{diag.get('waktu')}`\n\n"
                f"📊 *Status Presensi Hari Ini:* {status_absen}\n"
                f"📝 _{ket}_"
            )
        else:
            err = diag.get("error", "Koneksi gagal")
            return (
                "⚠️ *HASIL TES KONEKSI KEMNAKER*\n\n"
                f"⏰ *Waktu:* `{diag.get('waktu')}`\n"
                f"❌ *Status:* Gagal terhubung ke Kemnaker\n"
                f"🚨 *Pesan:* `{err}`\n\n"
                "💡 *Solusi:* Pastikan variabel `CLOUDFLARE_WORKER_URL` sudah dipasang di Environment Variables Vercel."
            )

    elif cmd in ["/monev", "/run", "/submit"]:
        try:
            res = monev_bot.main()
            status = res.get("status")
            if status == "already_submitted":
                return f"✅ *Monev Aman!*\nPresensi untuk tanggal `{res.get('date')}` sudah terisi sebelumnya."
            elif status == "submitted":
                return f"🚀 *Berhasil!*\nLaporan Monev tanggal `{res.get('date')}` berhasil disubmit ke server Kemnaker!"
            else:
                return f"ℹ️ *Hasil Monev:* `{res}`"
        except Exception as e:
            return f"❌ *Gagal Menjalankan Monev:*\n`{str(e)}`"

    elif cmd in ["/proxy"]:
        cf_proxy = os.getenv("CLOUDFLARE_WORKER_URL")
        if cf_proxy:
            return f"🌐 *Status Cloudflare Reverse Proxy:*\n✅ Aktif: `{cf_proxy}`"
        else:
            return (
                "🌐 *Status Cloudflare Reverse Proxy:*\n"
                "⚠️ Belum disetel. Tambahkan variabel `CLOUDFLARE_WORKER_URL` di Vercel Settings -> Environment Variables."
            )

    else:
        return (
            f"❓ Perintah `{text}` tidak dikenal.\n"
            "Ketik `/tes` untuk memeriksa koneksi ke Kemnaker, atau `/help` untuk bantuan."
        )

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        """Menangani Webhook pesan masuk dari Telegram"""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            update = json.loads(body.decode("utf-8")) if body else {}

            message = update.get("message") or update.get("edited_message")
            if message:
                chat_id = message.get("chat", {}).get("id")
                text = message.get("text", "").strip()

                if chat_id and text:
                    reply_text = handle_telegram_command(chat_id, text)
                    monev_bot.kirim_telegram(reply_text, chat_id=chat_id)

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
        """Menangani Cron Vercel, registrasi Webhook, dan diagnosa via browser"""
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
                "instruction": "Webhook aktif! Sekarang buka Telegram @Cekad_bot dan ketik /tes"
            }, indent=2).encode("utf-8"))
            return

        # 2. Fitur Tes Diagnostik via GET
        if "test" in query_params:
            diag = monev_bot.periksa_koneksi_dan_status()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(diag, indent=2).encode("utf-8"))
            return

        # 3. Default: Trigger pengisian otomatis harian (Cron)
        try:
            result = monev_bot.main()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response = {
                "status": "success",
                "result": result
            }
            self.wfile.write(json.dumps(response).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response = {
                "status": "error",
                "message": str(e)
            }
            self.wfile.write(json.dumps(response).encode("utf-8"))
