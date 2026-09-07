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

# 1. Konfigurasi Lingkungan
def load_dotenv(env_path=".env"):
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("'\""))

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

WIB = timezone(timedelta(hours=7))
def _safe_float(val, default):
    try:
        return float(val) if val is not None and str(val).strip() else default
    except (ValueError, TypeError):
        return default

KEMNAKER_USERNAME = os.getenv("KEMNAKER_USERNAME")
KEMNAKER_PASSWORD = os.getenv("KEMNAKER_PASSWORD")
OFFICE_LAT = _safe_float(os.getenv("OFFICE_LAT"), -7.8981812)
OFFICE_LONG = _safe_float(os.getenv("OFFICE_LONG"), 110.0499084)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

MENU_KEYBOARD = {
    "inline_keyboard": [
        [
            {"text": "🔍 Cek Presensi", "callback_data": "/cek"},
            {"text": "🧪 Tes Sistem", "callback_data": "/tes"}
        ],
        [
            {"text": "⚡ Eksekusi Monev", "callback_data": "/monev"},
            {"text": "📊 Rekap Minggu Ini", "callback_data": "/rekap"}
        ]
    ]
}

CONFIRM_KEYBOARD = {
    "inline_keyboard": [
        [
            {"text": "✅ Ya, Eksekusi Sekarang", "callback_data": "/monev_confirm"},
            {"text": "❌ Batalkan", "callback_data": "/monev_cancel"}
        ]
    ]
}

# Cache in-memory untuk template & token SSO
_CACHED_TOKEN = None
_CACHED_TOKEN_TIME = 0
_REMINDER_TEMPLATES = None
_ACTIVITY_TEMPLATES = None

# 2. Utilitas Jaringan & Koordinat
def wrap_url(target_url):
    cf_worker = os.getenv("CLOUDFLARE_WORKER_URL", "").strip().rstrip("/")
    if cf_worker and len(cf_worker) > 8 and cf_worker not in target_url:
        return f"{cf_worker}/?url={urllib.parse.quote(target_url, safe='')}"
    return target_url

def api_call(endpoint, token, method="GET", payload=None):
    """Fungsi helper tunggal terstandarisasi untuk semua request ke Kemnaker API"""
    global _CACHED_TOKEN
    headers = {
        "User-Agent": USER_AGENT,
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }
    data_bytes = json.dumps(payload).encode("utf-8") if payload is not None else None
    if data_bytes is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(wrap_url(endpoint), data=data_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            _CACHED_TOKEN = None
        try:
            err_data = json.loads(e.read().decode("utf-8"))
            msg = err_data.get("message") or err_data.get("error") or str(e)
            raise Exception(f"{e.code}: {msg}") from None
        except Exception as inner_e:
            if str(inner_e).startswith(str(e.code)):
                raise inner_e
            raise Exception(f"HTTP {e.code}: {e.reason}") from None

def get_jittered_coordinates():
    """Memberikan deviasi mikro alami (~10-25 meter) pada koordinat GPS"""
    return (
        round(OFFICE_LAT + random.uniform(-0.00015, 0.00015), 7),
        round(OFFICE_LONG + random.uniform(-0.00015, 0.00015), 7)
    )

def kirim_telegram(pesan, chat_id=None, reply_markup=None):
    target_chat = str(chat_id).strip() if chat_id else (TELEGRAM_CHAT_ID.strip() if TELEGRAM_CHAT_ID else None)
    if not TELEGRAM_BOT_TOKEN or not target_chat:
        return False

    clean_token = TELEGRAM_BOT_TOKEN.strip()
    if clean_token.lower().startswith("bot"):
        clean_token = clean_token[3:]

    payload_dict = {"chat_id": target_chat, "text": pesan, "parse_mode": "Markdown"}
    if reply_markup:
        payload_dict["reply_markup"] = reply_markup

    req = urllib.request.Request(
        f"https://api.telegram.org/bot{clean_token}/sendMessage",
        data=json.dumps(payload_dict).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=10):
            return True
    except urllib.error.HTTPError as e:
        if e.code == 400 and "parse_mode" in payload_dict:
            del payload_dict["parse_mode"]
            req_plain = urllib.request.Request(
                f"https://api.telegram.org/bot{clean_token}/sendMessage",
                data=json.dumps(payload_dict).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            try:
                with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req_plain, timeout=10):
                    return True
            except Exception:
                pass
        print(f"[Telegram Error] {e}", flush=True)
        return False
    except Exception as e:
        print(f"[Telegram Error] {e}", flush=True)
        return False

# 3. Autentikasi SSO Kemnaker
def login_kemnaker(force_refresh=False):
    global _CACHED_TOKEN, _CACHED_TOKEN_TIME
    now = time.time()
    if not force_refresh and _CACHED_TOKEN and (now - _CACHED_TOKEN_TIME) < 900:
        return _CACHED_TOKEN

    manual = os.getenv("KEMNAKER_BEARER_TOKEN")
    if manual and len(manual) > 20:
        return manual.strip()

    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    browser_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8"
    }

    # Inisiasi SSO
    req_init = urllib.request.Request(wrap_url("https://maganghub.kemnaker.go.id/api/naco/login?redirect_url=/"), headers=browser_headers)
    res_init = opener.open(req_init, timeout=15)
    html_init = res_init.read().decode("utf-8", errors="ignore")
    csrf = (re.search(r'name="csrf-token"\s+content="([^"]+)"', html_init) or ["", ""])[1]

    # Kirim login
    payload_login = json.dumps({"username": KEMNAKER_USERNAME, "password": KEMNAKER_PASSWORD}).encode("utf-8")
    req_login = urllib.request.Request(wrap_url("https://account.kemnaker.go.id/auth/login"), data=payload_login, headers={
        **browser_headers,
        "Content-Type": "application/json",
        "X-CSRF-TOKEN": csrf,
        "Origin": "https://account.kemnaker.go.id",
        "Referer": res_init.geturl()
    })
    res_login = opener.open(req_login, timeout=15)
    login_data = json.loads(res_login.read().decode("utf-8"))
    if not login_data.get("data", {}).get("authenticated"):
        raise Exception(f"Autentikasi gagal: {login_data}")

    # Callback handshake
    opener.open(urllib.request.Request(wrap_url(login_data["data"]["redirect_uri"]), headers=browser_headers), timeout=15)

    token = next((c.value for c in cj if c.name == "naco_access_token"), None)
    if not token:
        raise Exception("Gagal mengekstrak naco_access_token")

    _CACHED_TOKEN = token
    _CACHED_TOKEN_TIME = now
    return token

# 4. Pengecekan & Diagnosis Sistem
def periksa_absen_hari_ini(token, today_str):
    attendances = api_call("https://monev-api.maganghub.kemnaker.go.id/api/v1/attendances", token).get("data", [])
    for item in attendances:
        item_date = str(item.get("date", ""))
        if item_date == today_str or item_date.startswith(today_str):
            return True, item
    return False, None

def periksa_koneksi_dan_status():
    """Diagnosis lengkap: profil, status presensi, dan log harian dalam 1 panggilan login"""
    today_wib = datetime.now(WIB)
    today_str = today_wib.strftime("%Y-%m-%d")
    jam_str = today_wib.strftime("%H:%M:%S")

    try:
        token = login_kemnaker()
        me_data = api_call("https://monev-api.maganghub.kemnaker.go.id/api/v1/users/me", token).get("data", {})
        sudah, data_absen = periksa_absen_hari_ini(token, today_str)

        activity_text = ""
        if sudah:
            try:
                logs = api_call(f"https://monev-api.maganghub.kemnaker.go.id/api/v1/daily-logs?date={today_str}", token).get("data", [])
                if logs:
                    activity_text = logs[0].get("activity_log", "")
            except Exception:
                pass

        return {
            "success": True,
            "waktu": f"{today_str} {jam_str} WIB",
            "user_name": me_data.get("name", "Mas Ade"),
            "mentor_name": me_data.get("mentor_name", "-"),
            "sudah_absen": sudah,
            "data_absen": data_absen,
            "activity_text": activity_text,
            "today_str": today_str
        }
    except Exception as e:
        return {"success": False, "error": str(e), "waktu": f"{today_str} {jam_str} WIB", "today_str": today_str}

def test_koneksi_sistem():
    """Uji status kesehatan sistem tanpa mengirim data presensi"""
    diag = periksa_koneksi_dan_status()
    cf = os.getenv("CLOUDFLARE_WORKER_URL", "").strip()
    proxy_st = f"Aktif (`{cf}`)" if len(cf) > 5 else "Direct (Tanpa Proxy)"

    if not diag.get("success"):
        return (
            "🧪 *HASIL TES STATUS SISTEM*\n\n"
            f"⏰ *Waktu Server:* `{diag['waktu']}`\n"
            f"🌐 *Jalur Proxy:* {proxy_st}\n"
            f"❌ *Status SSO Kemnaker:* Gagal Login\n"
            f"🚨 *Detail Kendala:* `{diag['error']}`"
        )

    return (
        "🧪 *HASIL TES STATUS SISTEM*\n\n"
        "✅ *Sistem Monev berjalan normal dan siap digunakan!*\n\n"
        "🤖 *Bot Telegram:* Aktif & Responsif\n"
        f"🌐 *Jalur Koneksi:* {proxy_st}\n"
        "🔐 *Autentikasi SSO:* Berhasil (Token Aktif)\n"
        f"👤 *Akun Peserta:* `{diag['user_name']}`\n"
        f"🏢 *Mentor Lapangan:* `{diag['mentor_name']}`\n"
        f"⏰ *Waktu Server:* `{diag['waktu']}`\n\n"
        "💡 _Catatan: Tes ini murni memeriksa status kesehatan sistem tanpa mengirim data presensi ke Kemnaker._"
    )

def format_status_presensi():
    """Fungsi cek presensi hari ini untuk /cek (Read-only)"""
    diag = periksa_koneksi_dan_status()
    if not diag.get("success"):
        return f"🔍 *STATUS PRESENSI HARI INI*\n\n⏰ *Waktu:* `{diag['waktu']}`\n❌ *Status:* Gagal terhubung ke Kemnaker\n🚨 *Pesan:* `{diag['error']}`"

    if diag["sudah_absen"]:
        dt = diag.get("data_absen") or {}
        app_st = dt.get("approval_status", "SUBMITTED")
        jam = f" (Tercatat jam {dt['created_at'].split('T')[1][:8]} WIB)" if "T" in dt.get("created_at", "") else ""
        act = f"📝 *Kegiatan Terdata:*\n_{diag['activity_text']}_\n\n" if diag.get("activity_text") else ""
        return (
            "🔍 *STATUS PRESENSI HARI INI*\n\n"
            f"👤 *Nama Peserta:* `{diag['user_name']}`\n"
            f"🏢 *Nama Mentor:* `{diag['mentor_name']}`\n"
            f"📅 *Tanggal:* `{diag['today_str']}`\n"
            f"⏰ *Waktu Cek:* `{diag['waktu']}`\n\n"
            f"📊 *Status:* ✅ *SUDAH TERISI (PRESENT)*{jam}\n"
            f"📋 *Persetujuan Mentor:* `{app_st}`\n\n"
            f"{act}"
            "✨ _Presensi hari ini sudah aman tercatat. Tidak perlu diisi ulang!_"
        )
    return (
        "🔍 *STATUS PRESENSI HARI INI*\n\n"
        f"👤 *Nama Peserta:* `{diag['user_name']}`\n"
        f"🏢 *Nama Mentor:* `{diag['mentor_name']}`\n"
        f"📅 *Tanggal:* `{diag['today_str']}`\n"
        f"⏰ *Waktu Cek:* `{diag['waktu']}`\n\n"
        "📊 *Status Presensi:* ⚠️ *BELUM TERISI*\n\n"
        "💡 _Belum ada presensi untuk hari ini. Mas Ade bisa mengisi manual di web, ketik `/isi <kegiatan>`, atau jalankan `/monev`._"
    )

# 5. Template & Eksekusi Monev
def ambil_template(today_wib):
    global _ACTIVITY_TEMPLATES
    if not _ACTIVITY_TEMPLATES:
        p = os.path.join(os.path.dirname(__file__), "templates.json")
        try:
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    _ACTIVITY_TEMPLATES = json.load(f)
        except Exception:
            pass
        if not _ACTIVITY_TEMPLATES:
            _ACTIVITY_TEMPLATES = [{
                "activity": "Melakukan penelusuran modul fungsional aplikasi serta dokumentasi teknis pendukung.",
                "learning": "Mempelajari alur integrasi sistem data dan prosedur validasi parameter operasional.",
                "obstacles": "Tidak ada kendala yang berarti, seluruh tugas berjalan dengan lancar."
            }]
    day = today_wib.timetuple().tm_yday
    return _ACTIVITY_TEMPLATES[day % len(_ACTIVITY_TEMPLATES)]

def submit_monev(token=None, today_str=None, template=None, custom_activity=None):
    """Fungsi tunggal untuk submit presensi (otomatis maupun kustom)"""
    today_wib = datetime.now(WIB)
    today_str = today_str or today_wib.strftime("%Y-%m-%d")
    token = token or login_kemnaker()
    template = template or ambil_template(today_wib)
    lat, long = get_jittered_coordinates()

    payload = {
        "date": today_str,
        "status": "PRESENT",
        "latitude": lat,
        "longitude": long,
        "activity_log": (custom_activity or template["activity"]).strip(),
        "lesson_learned": template["learning"],
        "obstacles": template["obstacles"],
        "is_reviewed": True
    }
    return api_call("https://monev-api.maganghub.kemnaker.go.id/api/v1/attendances/with-daily-log", token, method="POST", payload=payload)

# Alias backward-compatibility
test_post_kemnaker = submit_monev

def muat_template_pengingat():
    global _REMINDER_TEMPLATES
    if _REMINDER_TEMPLATES is None:
        p = os.path.join(os.path.dirname(__file__), "reminder_templates.json")
        _REMINDER_TEMPLATES = json.load(open(p, "r", encoding="utf-8")) if os.path.exists(p) else {
            "santai_19": ["☕ Halo Mas Ade! Santai sejenak yuk, jangan lupa isi presensi monev hari ini ya~"],
            "keras_20": ["🚨 WOI MAS ADE! Jam 8 malam ini cuy! Buruan isi monev sebelum kena amuk Kemnaker!"]
        }
    return _REMINDER_TEMPLATES

def kirim_pengingat_monev(chat_id=None, force_mode=None):
    today_wib = datetime.now(WIB)
    today_str = today_wib.strftime("%Y-%m-%d")
    try:
        sudah, _ = periksa_absen_hari_ini(login_kemnaker(), today_str)
        if sudah:
            print(f"[Pengingat] Presensi {today_str} sudah terisi. Pengingat dilewati.", flush=True)
            return {"status": "already_submitted", "message": "Presensi hari ini sudah terisi, pengingat dilewati."}
    except Exception as e:
        print(f"[Pengingat] Status presensi tidak dapat dicek ({e}), tetap kirim pengingat.", flush=True)

    temps = muat_template_pengingat()
    is_keras = force_mode == "keras" or (force_mode is None and today_wib.hour >= 20)
    daftar = temps.get("keras_20" if is_keras else "santai_19", [])
    pesan = (
        f"{random.choice(daftar) if daftar else 'Halo Mas Ade, jangan lupa isi monev hari ini ya!'}\n\n"
        f"_{('🔥 PENGINGAT KERAS JAM 20:00 WIB' if is_keras else '☕ PENGINGAT SANTAI JAM 19:00 WIB')}_\n"
        "⏰ *Batas Waktu Mandiri:* Sebelum 21:00 WIB\n"
        "💡 _Ketik `/isi <kegiatan>` atau klik tombol di bawah._"
    )
    kirim_telegram(pesan, chat_id=chat_id, reply_markup=MENU_KEYBOARD)
    return {"status": "success", "message": "Pengingat terkirim"}

kirim_pengingat_sore = kirim_pengingat_monev

def ambil_rekap_mingguan():
    try:
        attendances = api_call("https://monev-api.maganghub.kemnaker.go.id/api/v1/attendances", login_kemnaker()).get("data", [])
    except Exception as e:
        return f"❌ Gagal memuat riwayat presensi Kemnaker: {e}"

    sorted_att = sorted(attendances, key=lambda x: x.get("date", ""), reverse=True)[:7]
    total_hadir = sum(1 for a in sorted_att if a.get("status") == "PRESENT")
    total_app = sum(1 for a in sorted_att if a.get("approval_status") == "APPROVED")
    total_sub = sum(1 for a in sorted_att if a.get("approval_status") == "SUBMITTED")

    lines = [
        "📊 *REKAPITULASI MINGGUAN MONEV*",
        "👤 *Peserta:* `Mas Ade`\n",
        f"✅ *Total Hadir Terdata:* `{total_hadir} hari`",
        f"📋 *Status Mentor:* `{total_app} Disetujui (Approved)` | `{total_sub} Menunggu (Submitted)`\n",
        "🗓️ *Rincian 7 Hari Terakhir:*"
    ]
    for it in sorted_att:
        icon = "✅" if it.get("status") == "PRESENT" else "⚠️"
        lines.append(f"{icon} `{it.get('date', '-')}` : *{it.get('status', '-')}* ({it.get('approval_status', '-')})")
    lines.append("\n💡 _Semangat magangnya, Mas Ade! Sistem pengawasan selalu aktif menjaga kehadiranmu._")
    return "\n".join(lines)

def main(force=False, notify_telegram=False):
    today_wib = datetime.now(WIB)
    today_str = today_wib.strftime("%Y-%m-%d")
    jam_str = today_wib.strftime("%H:%M:%S")

    print(f"=== MONEV RUNNER: {today_str} {jam_str} WIB ===", flush=True)
    try:
        token = login_kemnaker()
        sudah, data_absen = periksa_absen_hari_ini(token, today_str)
        if sudah:
            msg = "monev sudah diisii"
            if notify_telegram:
                kirim_telegram(msg)
            return {"status": "already_submitted", "date": today_str, "message": msg}

        template = ambil_template(today_wib)
        hasil = submit_monev(token=token, today_str=today_str, template=template)
        msg = (
            f"🚀 *MONEV BERHASIL DIKIRIM!*\n\n"
            f"📅 *Tanggal:* `{today_str}` ({jam_str} WIB)\n"
            f"📍 *Lokasi:* `{OFFICE_LAT}, {OFFICE_LONG}`\n\n"
            f"📝 *Kegiatan:*\n_{template['activity']}_\n\n"
            f"💡 *Pembelajaran:*\n_{template['learning']}_\n\n"
            "Laporan presensi berhasil diserahkan ke server Kemnaker!"
        )
        if notify_telegram:
            kirim_telegram(msg)
        return {"status": "success", "date": today_str, "message": msg}
    except Exception as e:
        msg = f"❌ *Gagal Eksekusi Monev:*\n`{e}`"
        if notify_telegram:
            kirim_telegram(msg)
        raise e

if __name__ == "__main__":
    main(notify_telegram=True)
