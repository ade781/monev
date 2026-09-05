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
            "👋 *Halo Mas Ade! Saya Bot Monev ADE7 Reminder.*\n\n"
            "Bot ini siap membantu monitoring dan pengisian presensi cadangan harian Anda.\n\n"
            "📌 *Perintah yang Tersedia:*\n"
            "🔹 `/cek` - Cek riwayat & status presensi terbaru hari ini\n"
            "🔹 `/rekap` - Ringkasan performa kehadiran 7 hari terakhir\n"
            "🔹 `/isi <kegiatan>` - Isi presensi hari ini dengan catatan khusus\n"
            "🔹 `/tes` - Tes tembak POST ke Kemnaker & tampilkan respons server\n"
            "🔹 `/monev` - Jalankan pengisian monev cadangan otomatis\n"
            "🔹 `/proxy` - Cek status Cloudflare Reverse Proxy aktif\n\n"
            f"🆔 *Chat ID Anda:* `{chat_id}`"
        )

    elif cmd in ["/rekap"]:
        return monev_bot.ambil_rekap_mingguan()

    elif cmd in ["/isi"]:
        kegiatan = text[len(cmd):].strip()
        if not kegiatan:
            return (
                "⚠️ *Format Pengisian Kegiatan Kustom:*\n"
                "Ketik `/isi <kegiatan Anda>`\n\n"
                "Contoh:\n"
                "`/isi Mengerjakan integrasi REST API dan optimasi query database`"
            )
        
        res = monev_bot.test_post_kemnaker(custom_activity=kegiatan)
        return (
            "📝 *PENGISIAN KEGIATAN KUSTOM KEMNAKER*\n\n"
            "👤 *Peserta:* `Mas Ade`\n"
            f"📌 *Kegiatan:* _{kegiatan}_\n\n"
            f"📡 *Respon Server:* `{res}`"
        )

    elif cmd in ["/tes"]:
        msg = monev_bot.test_post_kemnaker()
        return msg

    elif cmd in ["/cek", "/status"]:
        diag = monev_bot.periksa_koneksi_dan_status()
        if diag.get("success"):
            sudah = diag.get("sudah_absen")
            status_absen = "✅ *SUDAH TERISI (PRESENT)*" if sudah else "⚠️ *BELUM TERISI*"
            ket = "Mas Ade sudah mengisi presensi hari ini secara aman." if sudah else "Belum ada presensi untuk hari ini. Bot akan backup otomatis pukul 21:00 WIB."
            
            return (
                "🔍 *HASIL MONITORING KEMNAKER*\n\n"
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
                "⚠️ *HASIL MONITORING KEMNAKER*\n\n"
                f"⏰ *Waktu:* `{diag.get('waktu')}`\n"
                f"❌ *Status:* Gagal terhubung ke Kemnaker\n"
                f"🚨 *Pesan:* `{err}`\n\n"
                "💡 *Solusi:* Pastikan variabel `CLOUDFLARE_WORKER_URL` sudah dipasang di Environment Variables Vercel."
            )

    elif cmd in ["/monev", "/run", "/submit"]:
        try:
            res = monev_bot.main()
            return res.get("message", "Selesai dieksekusi")
        except Exception as e:
            return f"❌ *Gagal:* `{str(e)}`"

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
            "Ketik `/help` untuk melihat daftar perintah, atau gunakan tombol di bawah."
        )

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        """Menangani Webhook pesan masuk dan callback query tombol dari Telegram"""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            update = json.loads(body.decode("utf-8")) if body else {}

            token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
            if token.lower().startswith("bot"):
                token = token[3:]

            # 1. Tangani tombol interaktif (Callback Query)
            callback_query = update.get("callback_query")
            if callback_query:
                cq_id = callback_query.get("id")
                chat_id = callback_query.get("message", {}).get("chat", {}).get("id")
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
                    reply_text = handle_telegram_command(chat_id, cq_data)
                    monev_bot.kirim_telegram(reply_text, chat_id=chat_id, reply_markup=monev_bot.MENU_KEYBOARD)

            # 2. Tangani pesan teks biasa
            message = update.get("message") or update.get("edited_message")
            if message:
                chat_id = message.get("chat", {}).get("id")
                text = message.get("text", "").strip()

                if chat_id and text:
                    reply_text = handle_telegram_command(chat_id, text)
                    monev_bot.kirim_telegram(reply_text, chat_id=chat_id, reply_markup=monev_bot.MENU_KEYBOARD)

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
                "instruction": "Webhook aktif! Sekarang buka Telegram @Cekad_bot dan ketik /start"
            }, indent=2).encode("utf-8"))
            return

        # 2. Fitur Pengingat (Jam 19:00 Santai & Jam 20:00 Keras)
        if "type" in query_params and query_params["type"][0] == "reminder":
            force_mode = query_params.get("mode", [None])[0]
            result = monev_bot.kirim_pengingat_monev(force_mode=force_mode)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode("utf-8"))
            return

        # 3. Fitur Tes Diagnostik via GET
        if "test" in query_params:
            diag = monev_bot.periksa_koneksi_dan_status()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(diag, indent=2).encode("utf-8"))
            return

        # 4. Default: Trigger pengisian otomatis harian (Cron 21:00 WIB)
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
