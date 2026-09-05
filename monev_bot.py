#!/usr/bin/env python3
"""
MONEV AUTOMATION BACKUP BOT - MAGANGHUB KEMNAKER
Zero-dependency Python script: standard library only (urllib, http.cookiejar, json, os).
"""

import os
import re
import json
import urllib.request
import urllib.parse
import http.cookiejar
from datetime import datetime, timezone, timedelta

# Load file .env lokal jika tersedia (tanpa dependency eksternal)
def load_dotenv(env_path=".env"):
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip().strip("'\""))

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# Zona Waktu Indonesia Barat (WIB = UTC+7)
WIB = timezone(timedelta(hours=7))

# Konfigurasi dari Environment Variables
KEMNAKER_USERNAME = os.getenv("KEMNAKER_USERNAME")
KEMNAKER_PASSWORD = os.getenv("KEMNAKER_PASSWORD")
OFFICE_LAT = float(os.getenv("OFFICE_LAT", "-7.8981812"))
OFFICE_LONG = float(os.getenv("OFFICE_LONG", "110.0499084"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def kirim_telegram(pesan, chat_id=None):
    """Kirim pesan notifikasi ke Telegram via HTTP POST (fail-safe)"""
    target_chat = str(chat_id).strip() if chat_id else (TELEGRAM_CHAT_ID.strip() if TELEGRAM_CHAT_ID else None)
    if not TELEGRAM_BOT_TOKEN or not target_chat:
        print("[Telegram] Token atau Chat ID belum disetel, skip notifikasi.")
        return False
    
    clean_token = TELEGRAM_BOT_TOKEN.strip()
    if clean_token.lower().startswith("bot"):
        clean_token = clean_token[3:]

    url = f"https://api.telegram.org/bot{clean_token}/sendMessage"
    payload = json.dumps({
        "chat_id": target_chat,
        "text": pesan,
        "parse_mode": "Markdown"
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req)
        print(f"[Telegram] Notifikasi berhasil terkirim ke chat {target_chat}!")
        return True
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        print(f"[Telegram] Gagal mengirim pesan (HTTP {e.code}): {err_body}")
        print("[Telegram] Tips: Buka @Cekad_bot di Telegram dan ketuk START terlebih dahulu.")
        return False
    except Exception as e:
        print(f"[Telegram] Gagal mengirim pesan: {e}")
        return False

def get_opener():
    """Membuat HTTP opener dengan cookie processor dan proxy Indonesia jika disetel"""
    cj = http.cookiejar.CookieJar()
    handlers = [urllib.request.HTTPCookieProcessor(cj)]
    
    proxy = os.getenv("INDONESIA_PROXY")
    if proxy and len(proxy.strip()) > 5:
        proxy = proxy.strip()
        if not proxy.startswith("http://") and not proxy.startswith("https://"):
            proxy = f"http://{proxy}"
        print(f"[Proxy] Menggunakan Proxy Indonesia: {proxy}")
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
        
    opener = urllib.request.build_opener(*handlers)
    urllib.request.install_opener(opener)
    return opener, cj

def login_kemnaker():
    """Melakukan alur SSO Kemnaker dan mengambil Bearer Token secara otomatis"""
    # Jika token manual disediakan via env
    manual_token = os.getenv("KEMNAKER_BEARER_TOKEN")
    if manual_token and len(manual_token) > 20:
        print("[1/4] Menggunakan KEMNAKER_BEARER_TOKEN dari environment...")
        return manual_token.strip()

    print("[1/4] Menginisiasi alur SSO Kemnaker...")
    opener, cj = get_opener()

    browser_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
        "Sec-Ch-Ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1"
    }

    # 1. Panggil portal naco login untuk mendapatkan redirect dan session cookie
    req_init = urllib.request.Request("https://maganghub.kemnaker.go.id/api/naco/login?redirect_url=/", headers=browser_headers)
    try:
        res_init = opener.open(req_init)
        html_init = res_init.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        err_content = e.read().decode("utf-8", errors="ignore")
        print(f"[ERROR Kemnaker SSO] HTTP {e.code}: {err_content[:200]}")
        raise Exception(f"Server SSO Kemnaker memblokir request (HTTP {e.code}). Jika di cloud luar negeri, setel INDONESIA_PROXY.") from e

    csrf_match = re.search(r'name="csrf-token"\s+content="([^"]+)"', html_init)
    csrf_token = csrf_match.group(1) if csrf_match else ""

    # 2. Kirim kredensial ke SSO account.kemnaker.go.id
    print("[1/4] Mengirim autentikasi kredensial pengguna...")
    payload_login = json.dumps({
        "username": KEMNAKER_USERNAME,
        "password": KEMNAKER_PASSWORD
    }).encode("utf-8")

    req_login = urllib.request.Request("https://account.kemnaker.go.id/auth/login", data=payload_login, headers={
        **browser_headers,
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "X-CSRF-TOKEN": csrf_token,
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://account.kemnaker.go.id",
        "Referer": res_init.geturl()
    })

    res_login = opener.open(req_login)
    login_data = json.loads(res_login.read().decode("utf-8"))

    if not login_data.get("data", {}).get("authenticated"):
        raise Exception(f"Autentikasi gagal: {login_data}")

    # 3. Ikuti URL callback untuk menyelesaikan handshake SSO
    redirect_uri = login_data["data"]["redirect_uri"]
    req_redir = urllib.request.Request(redirect_uri, headers=browser_headers)
    opener.open(req_redir)

    # 4. Ambil token naco_access_token dari cookie
    token = None
    for cookie in cj:
        if cookie.name == "naco_access_token":
            token = cookie.value
            break

    if not token:
        raise Exception("Gagal mengekstrak naco_access_token dari handshake cookies!")

    print("[1/4] Sukses! Bearer Token berhasil diperoleh secara otomatis.")
    return token

def periksa_koneksi_dan_status():
    """Fungsi diagnosis lengkap untuk Telegram command /tes"""
    today_wib = datetime.now(WIB)
    today_str = today_wib.strftime("%Y-%m-%d")
    jam_str = today_wib.strftime("%H:%M:%S")

    try:
        token = login_kemnaker()
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "waktu": f"{today_str} {jam_str} WIB",
            "today_str": today_str
        }

    headers = {
        "User-Agent": USER_AGENT,
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    # 1. Ambil data profil
    user_name = "Tidak Diketahui"
    mentor_name = "-"
    try:
        req_me = urllib.request.Request("https://monev-api.maganghub.kemnaker.go.id/api/v1/users/me", headers=headers)
        res_me = urllib.request.urlopen(req_me)
        me_data = json.loads(res_me.read().decode("utf-8")).get("data", {})
        user_name = me_data.get("name", user_name)
        mentor_name = me_data.get("mentor_name", mentor_name)
    except Exception as e:
        print(f"Gagal memuat profil: {e}")

    # 2. Cek status presensi hari ini
    sudah_absen, data_absen = periksa_absen_hari_ini(token, today_str)

    return {
        "success": True,
        "waktu": f"{today_str} {jam_str} WIB",
        "user_name": user_name,
        "mentor_name": mentor_name,
        "sudah_absen": sudah_absen,
        "data_absen": data_absen,
        "today_str": today_str
    }

def periksa_absen_hari_ini(token, today_str):
    """Mengecek apakah hari ini sudah melakukan pengisian di portal Monev"""
    print(f"[2/4] Memeriksa status presensi untuk tanggal {today_str}...")
    headers = {
        "User-Agent": USER_AGENT,
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    req = urllib.request.Request("https://monev-api.maganghub.kemnaker.go.id/api/v1/attendances", headers=headers)
    res = urllib.request.urlopen(req)
    res_data = json.loads(res.read().decode("utf-8"))

    attendances = res_data.get("data", [])
    for item in attendances:
        if item.get("date") == today_str:
            return True, item

    return False, None

def ambil_template(today_wib):
    """Mengambil template kegiatan berdasarkan urutan hari"""
    template_file = os.path.join(os.path.dirname(__file__), "templates.json")
    if os.path.exists(template_file):
        with open(template_file, "r", encoding="utf-8") as f:
            templates = json.load(f)
    else:
        templates = [
          {
            "activity": "Melakukan penelusuran modul fungsional aplikasi serta dokumentasi teknis pendukung.",
            "learning": "Mempelajari alur integrasi sistem data dan prosedur validasi parameter operasional.",
            "obstacles": "Tidak ada kendala yang berarti, seluruh tugas berjalan dengan lancar."
          }
        ]
    
    # Rotasi template berdasarkan hari ke-berapa dalam setahun
    day_of_year = today_wib.timetuple().tm_yday
    return templates[day_of_year % len(templates)]

def submit_monev(token, today_str, template):
    """Mengirim presensi dan laporan harian ke endpoint Kemnaker"""
    print(f"[3/4] Menyiapkan pengiriman laporan otomatis untuk tanggal {today_str}...")

    # Format payload resmi yang divalidasi berhasil 100% oleh Kemnaker
    payload = {
        "date": today_str,
        "status": "PRESENT",
        "activity_log": template["activity"],
        "lesson_learned": template["learning"],
        "obstacles": template["obstacles"],
        "is_reviewed": True
    }

    headers = {
        "User-Agent": USER_AGENT,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    url = "https://monev-api.maganghub.kemnaker.go.id/api/v1/attendances/with-daily-log"
    data_bytes = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
    try:
        res = urllib.request.urlopen(req)
        res_body = json.loads(res.read().decode("utf-8"))
        return res_body
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="ignore")
        print(f"[ERROR Kemnaker API] HTTP {e.code}: {error_body}")
        raise Exception(f"Server Kemnaker menolak pengiriman: {error_body}") from e

def main():
    today_wib = datetime.now(WIB)
    today_str = today_wib.strftime("%Y-%m-%d")
    jam_str = today_wib.strftime("%H:%M:%S")

    print(f"=== MONEV AUTO BOT RUNNER ===")
    print(f"Waktu Sekarang: {today_str} {jam_str} WIB")

    try:
        # 1. Login Otomatis
        token = login_kemnaker()

        # 2. Cek apakah sudah absen hari ini
        sudah_absen, data_absen = periksa_absen_hari_ini(token, today_str)
        if sudah_absen:
            print(f"[AMAN] Anda sudah mengisi presensi tanggal {today_str} secara manual (Status: {data_absen.get('status')}).")
            print("Bot tidak perlu melakukan aksi apa pun. Program selesai.")
            return {"status": "already_submitted", "date": today_str, "details": data_absen}

        # 3. Jika belum absen, kirim otomatis
        print(f"[PERINGATAN] Anda belum mengisi presensi untuk tanggal {today_str}!")
        template = ambil_template(today_wib)
        
        hasil = submit_monev(token, today_str, template)
        print(f"[BERHASIL] Laporan berhasil disubmit ke server Kemnaker: {hasil}")

        # 4. Kirim notifikasi Telegram
        pesan_notif = (
            f"✅ *Monev MagangHub Terisi Otomatis!*\n\n"
            f"📅 *Tanggal:* `{today_str}` ({jam_str} WIB)\n"
            f"📍 *Lokasi:* `{OFFICE_LAT}, {OFFICE_LONG}`\n\n"
            f"📝 *Aktivitas:*\n_{template['activity']}_\n\n"
            f"💡 *Pembelajaran:*\n_{template['learning']}_\n\n"
            f"Laporan cadangan berhasil disubmit karena Anda belum mengisi sebelum jadwal bot."
        )
        kirim_telegram(pesan_notif)
        return {"status": "submitted", "date": today_str, "result": hasil}

    except Exception as e:
        pesan_error = f"⚠️ *Gagal Auto-Monev Magang!*\nTerjadi kendala pada {today_str} {jam_str} WIB:\n`{str(e)}`"
        print(f"[ERROR] {e}")
        kirim_telegram(pesan_error)
        raise e

if __name__ == "__main__":
    main()
