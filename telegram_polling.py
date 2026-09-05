#!/usr/bin/env python3
"""
TELEGRAM BOT POLLING LISTENER - MONEV MAGANGHUB
Gunakan skrip ini untuk testing langsung interaksi bot via Telegram dari komputer lokal.
Ketik /tes, /cek, atau /monev di bot Telegram (@Cekad_bot).
"""

import os
import sys
import time
import json
import urllib.request
import urllib.parse

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

import monev_bot
from api.cron import handle_telegram_command

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("[ERROR] TELEGRAM_BOT_TOKEN belum disetel di file .env!")
        return

    clean_token = token.strip()
    if clean_token.lower().startswith("bot"):
        clean_token = clean_token[3:]

    # Gunakan direct opener tanpa proxy untuk semua request ke Telegram
    direct_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    # 1. Hapus webhook lama agar polling dapat menerima update secara real-time
    try:
        del_url = f"https://api.telegram.org/bot{clean_token}/deleteWebhook"
        direct_opener.open(del_url, timeout=10)
        print("[Telegram Polling] Webhook berhasil di-reset untuk polling.", flush=True)
    except Exception as e:
        print(f"[Telegram Polling] Catatan: {e}", flush=True)

    # 2. Cek identitas bot
    me_url = f"https://api.telegram.org/bot{clean_token}/getMe"
    try:
        res = direct_opener.open(me_url, timeout=10)
        bot_info = json.loads(res.read().decode("utf-8")).get("result", {})
        bot_username = bot_info.get("username", "Bot")
        print(f"=== TELEGRAM BOT POLLING AKTIF: Monev ADE7 Reminder (@{bot_username}) ===", flush=True)
        print("Silakan buka Telegram di HP / Laptop Anda, cari @" + bot_username + " lalu kirim:", flush=True)
        print(" -> /start", flush=True)
        print(" -> /tes", flush=True)
        print("Tekan Ctrl+C di terminal ini untuk berhenti.\n" + "="*50, flush=True)
    except Exception as e:
        print(f"[ERROR] Gagal memuat info bot Telegram: {e}", flush=True)
        return

    offset = None
    while True:
        try:
            url = f"https://api.telegram.org/bot{clean_token}/getUpdates?timeout=30"
            if offset is not None:
                url += f"&offset={offset}"

            req = urllib.request.Request(url, headers={"User-Agent": "MonevTelegramBot/1.0"})
            res = direct_opener.open(req, timeout=35)
            data = json.loads(res.read().decode("utf-8"))

            for item in data.get("result", []):
                offset = item["update_id"] + 1
                msg = item.get("message") or item.get("edited_message")
                if not msg:
                    continue

                chat_id = msg.get("chat", {}).get("id")
                sender = msg.get("from", {}).get("first_name", "User")
                text = msg.get("text", "").strip()

                print(f"[PESAN MASUK] Dari {sender} (ID: {chat_id}): '{text}'", flush=True)

                # Kirim feedback processing dulu jika command berat
                if text.startswith(("/tes", "/cek", "/status", "/monev")):
                    monev_bot.kirim_telegram("⏳ _Sedang memproses permintaan ke server Kemnaker, mohon tunggu sebentar..._", chat_id=chat_id)

                reply = handle_telegram_command(chat_id, text)
                monev_bot.kirim_telegram(reply, chat_id=chat_id)
                print(f"[BALASAN TERKIRIM] ke chat {chat_id}\n", flush=True)

        except KeyboardInterrupt:
            print("\n[STOP] Polling dihentikan oleh pengguna.", flush=True)
            break
        except Exception as e:
            print(f"[Polling Notice] {e}", flush=True)
            time.sleep(3)

if __name__ == "__main__":
    main()
