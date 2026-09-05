#!/usr/bin/env python3
"""
MONEV AUTOMATION BACKUP BOT - MAGANGHUB KEMNAKER
Zero-dependency Python script: standard library only (urllib, http.cookiejar, json, os).
"""

import os
import re
import json
import time
import random
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

# Menu tombol interaktif Inline Keyboard Telegram
MENU_KEYBOARD = {
    "inline_keyboard": [
        [
            {"text": "🔍 Cek Presensi", "callback_data": "/cek"},
            {"text": "🧪 Tes Pesan", "callback_data": "/tes"}
        ],
        [
            {"text": "⚡ Eksekusi Monev", "callback_data": "/monev"},
            {"text": "📊 Rekap Minggu Ini", "callback_data": "/rekap"}
        ]
    ]
}

def get_jittered_coordinates():
    """Memberikan deviasi mikro alami (~10-25 meter) pada koordinat GPS agar natural seperti HP asli"""
    delta_lat = random.uniform(-0.00015, 0.00015)
    delta_long = random.uniform(-0.00015, 0.00015)
    return round(OFFICE_LAT + delta_lat, 7), round(OFFICE_LONG + delta_long, 7)

def kirim_telegram(pesan, chat_id=None, reply_markup=None):
    """Kirim pesan notifikasi ke Telegram via HTTP POST (fail-safe)"""
    target_chat = str(chat_id).strip() if chat_id else (TELEGRAM_CHAT_ID.strip() if TELEGRAM_CHAT_ID else None)
    if not TELEGRAM_BOT_TOKEN or not target_chat:
        print("[Telegram] Token atau Chat ID belum disetel, skip notifikasi.", flush=True)
        return False
    
    clean_token = TELEGRAM_BOT_TOKEN.strip()
    if clean_token.lower().startswith("bot"):
        clean_token = clean_token[3:]

    url = f"https://api.telegram.org/bot{clean_token}/sendMessage"
    payload_dict = {
        "chat_id": target_chat,
        "text": pesan,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        payload_dict["reply_markup"] = reply_markup

    payload = json.dumps(payload_dict).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        # Selalu gunakan koneksi direct untuk Telegram API (jangan lewat proxy)
        direct_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        direct_opener.open(req, timeout=10)
        print(f"[Telegram] Notifikasi berhasil terkirim ke chat {target_chat}!", flush=True)
        return True
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        print(f"[Telegram] Gagal mengirim pesan (HTTP {e.code}): {err_body}", flush=True)
        return False
    except Exception as e:
        print(f"[Telegram] Gagal mengirim pesan: {e}", flush=True)
        return False

def get_opener():
    """Membuat HTTP opener dengan cookie processor standar"""
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    return opener, cj

def wrap_url(target_url):
    """Mengarahkan URL melalui Cloudflare Worker Reverse Proxy jika disetel"""
    cf_worker = os.getenv("CLOUDFLARE_WORKER_URL")
    if cf_worker and len(cf_worker.strip()) > 8:
        cf_worker = cf_worker.strip().rstrip("/")
        if cf_worker in target_url:
            return target_url
        encoded = urllib.parse.quote(target_url, safe="")
        return f"{cf_worker}/?url={encoded}"
    return target_url

def login_kemnaker():
    """Melakukan alur SSO Kemnaker dan mengambil Bearer Token secara otomatis"""
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
    req_init = urllib.request.Request(wrap_url("https://maganghub.kemnaker.go.id/api/naco/login?redirect_url=/"), headers=browser_headers)
    try:
        res_init = opener.open(req_init, timeout=15)
        html_init = res_init.read().decode("utf-8", errors="ignore")
    except Exception as e:
        raise Exception(f"Gagal koneksi SSO Kemnaker: {e}") from e


    csrf_match = re.search(r'name="csrf-token"\s+content="([^"]+)"', html_init)
    csrf_token = csrf_match.group(1) if csrf_match else ""

    # 2. Kirim kredensial ke SSO account.kemnaker.go.id
    print("[1/4] Mengirim autentikasi kredensial pengguna...")
    payload_login = json.dumps({
        "username": KEMNAKER_USERNAME,
        "password": KEMNAKER_PASSWORD
    }).encode("utf-8")

    req_login = urllib.request.Request(wrap_url("https://account.kemnaker.go.id/auth/login"), data=payload_login, headers={
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
    req_redir = urllib.request.Request(wrap_url(redirect_uri), headers=browser_headers)
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
        req_me = urllib.request.Request(wrap_url("https://monev-api.maganghub.kemnaker.go.id/api/v1/users/me"), headers=headers)
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

def test_post_kemnaker(custom_activity=None):
    """Melakukan pengujian langsung request POST ke endpoint Monev Kemnaker dengan koordinat jitter & template dinamis"""
    today_wib = datetime.now(WIB)
    today_str = today_wib.strftime("%Y-%m-%d")
    template = ambil_template(today_wib)
    
    # Fitur 1: Human jitter (jeda mikro acak 1.5 - 3.5 detik)
    time.sleep(random.uniform(1.5, 3.5))

    try:
        token = login_kemnaker()
    except Exception as e:
        return f"Gagal login SSO: {e}"

    # Fitur 2: Micro GPS Jitter
    lat, long = get_jittered_coordinates()

    # Fitur 5: Kustom aktivitas jika disediakan
    activity = custom_activity.strip() if custom_activity else template["activity"]

    payload = {
        "date": today_str,
        "status": "PRESENT",
        "latitude": lat,
        "longitude": long,
        "activity_log": activity,
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

    url = wrap_url("https://monev-api.maganghub.kemnaker.go.id/api/v1/attendances/with-daily-log")
    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")

    try:
        res = urllib.request.urlopen(req)
        res_body = json.loads(res.read().decode("utf-8"))
        return res_body.get("message") or res_body.get("status") or str(res_body)
    except urllib.error.HTTPError as e:
        raw_error = e.read().decode("utf-8", errors="ignore")
        try:
            err_json = json.loads(raw_error)
            return err_json.get("message") or err_json.get("error_code") or raw_error
        except Exception:
            return raw_error
    except Exception as e:
        return str(e)

def periksa_absen_hari_ini(token, today_str):
    """Mengecek apakah hari ini sudah melakukan pengisian di portal Monev"""
    print(f"[2/4] Memeriksa status presensi untuk tanggal {today_str}...", flush=True)
    headers = {
        "User-Agent": USER_AGENT,
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    req = urllib.request.Request(wrap_url("https://monev-api.maganghub.kemnaker.go.id/api/v1/attendances"), headers=headers)
    res = urllib.request.urlopen(req)
    res_data = json.loads(res.read().decode("utf-8"))

    attendances = res_data.get("data", [])
    for item in attendances:
        if item.get("date") == today_str:
            return True, item

    return False, None

def ambil_template(today_wib):
    """Mengambil template kegiatan bervariasi cerdas berdasarkan kombinasi hari & minggu"""
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
    
    # Fitur 3: Rotasi cerdas dinamis berdasarkan hari dalam tahun + variasi indeks minggu
    day_of_year = today_wib.timetuple().tm_yday
    week_num = today_wib.isocalendar()[1]
    index = (day_of_year + (week_num * 3)) % len(templates)
    return templates[index]

def submit_monev(token, today_str, template, custom_activity=None):
    """Mengirim presensi dan laporan harian ke endpoint Kemnaker dengan koordinat natural"""
    print(f"[3/4] Menyiapkan pengiriman laporan otomatis untuk tanggal {today_str}...", flush=True)

    lat, long = get_jittered_coordinates()
    activity = custom_activity.strip() if custom_activity else template["activity"]

    payload = {
        "date": today_str,
        "status": "PRESENT",
        "latitude": lat,
        "longitude": long,
        "activity_log": activity,
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

    url = wrap_url("https://monev-api.maganghub.kemnaker.go.id/api/v1/attendances/with-daily-log")
    data_bytes = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
    try:
        res = urllib.request.urlopen(req)
        res_body = json.loads(res.read().decode("utf-8"))
        return res_body
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="ignore")
        print(f"[ERROR Kemnaker API] HTTP {e.code}: {error_body}", flush=True)
        raise Exception(f"Server Kemnaker menolak pengiriman: {error_body}") from e

def muat_template_pengingat():
    """Memuat 300 template pengingat (150 santai jam 19 & 150 keras jam 20) dari reminder_templates.json"""
    path_file = os.path.join(os.path.dirname(__file__), "reminder_templates.json")
    if os.path.exists(path_file):
        try:
            with open(path_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[ERROR] Gagal memuat reminder_templates.json: {e}", flush=True)
    return {
        "santai_19": ["☕ Halo Mas Ade! Santai sejenak yuk, jangan lupa isi presensi monev hari ini ya~"],
        "keras_20": ["🚨 WOI MAS ADE! Jam 8 malam ini cuy! Buruan isi monev sebelum kena amuk Kemnaker!"]
    }

def kirim_pengingat_monev(chat_id=None, force_mode=None):
    """Pengingat lucu acak: Santai di jam 19:00 WIB & Keras/Ngegas di jam 20:00 WIB untuk Mas Ade"""
    today_wib = datetime.now(WIB)
    today_str = today_wib.strftime("%Y-%m-%d")
    jam_sekarang = today_wib.hour

    sudah_absen = False
    try:
        token = login_kemnaker()
        sudah_absen, _ = periksa_absen_hari_ini(token, today_str)
    except Exception as e:
        print(f"[Pengingat Monev] Gagal cek status: {e}", flush=True)

    if sudah_absen:
        pesan = (
            "👋 *Halo Mas Ade!*\n\n"
            "Presensi monev hari ini terpantau sudah terisi aman (✅ *PRESENT*).\n\n"
            "Mantap maszeh! Lanjutkan santai atau rebahannya, malam ini aman terkendali! 🛋️✨"
        )
    else:
        kumpulan_template = muat_template_pengingat()
        
        # Mode keras jam 20:00 (atau force_mode 'keras'), santai jam 19:00
        if force_mode == "keras" or (force_mode is None and jam_sekarang >= 20):
            daftar = kumpulan_template.get("keras_20", [])
            tipe = "🔥 PENGINGAT KERAS JAM 20:00 WIB"
        else:
            daftar = kumpulan_template.get("santai_19", [])
            tipe = "☕ PENGINGAT SANTAI JAM 19:00 WIB"

        kalimat_lucu = random.choice(daftar) if daftar else "Mas Ade, yuk sempatkan isi monev hari ini!"
        pesan = (
            f"{kalimat_lucu}\n\n"
            f"_{tipe}_\n"
            "⏰ *Batas Waktu Mandiri:* Sebelum 21:00 WIB\n"
            "💡 _Ketik `/isi <kegiatan>` untuk langsung isi lewat chat bot, atau klik tombol di bawah._"
        )

    kirim_telegram(pesan, chat_id=chat_id, reply_markup=MENU_KEYBOARD)
    return {"status": "success", "message": "Pengingat terkirim ke Mas Ade"}

# Alias untuk kompatibilitas
kirim_pengingat_sore = kirim_pengingat_monev

def ambil_rekap_mingguan():
    """Fitur 8: Mengambil ringkasan riwayat presensi 7 hari terakhir untuk Mas Ade"""
    try:
        token = login_kemnaker()
    except Exception as e:
        return f"❌ Gagal login ke Kemnaker: {e}"

    headers = {
        "User-Agent": USER_AGENT,
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    try:
        req = urllib.request.Request(wrap_url("https://monev-api.maganghub.kemnaker.go.id/api/v1/attendances"), headers=headers)
        res = urllib.request.urlopen(req)
        res_data = json.loads(res.read().decode("utf-8"))
        attendances = res_data.get("data", [])
    except Exception as e:
        return f"❌ Gagal memuat riwayat presensi Kemnaker: {e}"

    # Urutkan tanggal descending dan ambil 7 data terbaru
    attendances_sorted = sorted(attendances, key=lambda x: x.get("date", ""), reverse=True)[:7]

    total_hadir = sum(1 for a in attendances_sorted if a.get("status") == "PRESENT")
    total_approved = sum(1 for a in attendances_sorted if a.get("approval_status") == "APPROVED")
    total_submitted = sum(1 for a in attendances_sorted if a.get("approval_status") == "SUBMITTED")

    lines = [
        "📊 *REKAPITULASI MINGGUAN MONEV*",
        "👤 *Peserta:* `Mas Ade`\n",
        f"✅ *Total Hadir Terdata:* `{total_hadir} hari`",
        f"📋 *Status Mentor:* `{total_approved} Disetujui (Approved)` | `{total_submitted} Menunggu (Submitted)`\n",
        "🗓️ *Rincian 7 Hari Terakhir:*"
    ]

    for item in attendances_sorted:
        tgl = item.get("date", "-")
        st = item.get("status", "-")
        app = item.get("approval_status", "-")
        icon = "✅" if st == "PRESENT" else "⚠️"
        lines.append(f"{icon} `{tgl}` : *{st}* ({app})")

    lines.append("\n💡 _Semangat magangnya, Mas Ade! Sistem pengawasan selalu aktif menjaga kehadiranmu._")
    return "\n".join(lines)

def main():
    today_wib = datetime.now(WIB)
    today_str = today_wib.strftime("%Y-%m-%d")
    jam_str = today_wib.strftime("%H:%M:%S")

    print(f"=== MONEV ADE7 REMINDER RUNNER ===", flush=True)
    print(f"Waktu Sekarang: {today_str} {jam_str} WIB", flush=True)

    try:
        # Kirim request ke server Kemnaker dan ambil teks 'message' aslinya
        pesan_server = test_post_kemnaker()
        print(f"[Respon Server Kemnaker]: {pesan_server}", flush=True)

        # Kirimkan hanya pesan dari server ke Telegram
        kirim_telegram(pesan_server)
        return {"status": "success", "date": today_str, "message": pesan_server}

    except Exception as e:
        pesan_error = f"Gagal: {e}"
        print(f"[ERROR] {pesan_error}", flush=True)
        kirim_telegram(pesan_error)
        raise e

if __name__ == "__main__":
    main()

