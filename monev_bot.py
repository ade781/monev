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
import tempfile
import urllib.request
import urllib.parse
import http.cookiejar
from datetime import datetime, timezone, timedelta

# 1. Konfigurasi Lingkungan
def load_dotenv(env_path=".env"):
    if not os.path.isabs(env_path):
        base_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
        env_path = os.path.join(base_dir, env_path)
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    os.environ.setdefault(k, v)


# Muat variabel environment dari .env jika ada
load_dotenv(".env")

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
        ],
        [
            {"text": "📦 Sisa Template", "callback_data": "/sisa"}
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
_TRIGGER_HISTORY = {}

# Masa berlaku token SSO Kemnaker (Kemnaker asli = 21600 detik / 6 jam; kita beri batas aman 20000 detik / ~5.5 jam)
TOKEN_CACHE_TTL = 20000

# Utilitas Sanitasi Markdown Telegram
def safe_markdown(text, max_len=None):
    """Membersihkan karakter khusus agar tidak menyebabkan error parse_mode Markdown Telegram"""
    if not text:
        return ""
    clean = str(text).replace("_", " ").replace("`", "'")
    clean = re.sub(r"\s+", " ", clean).strip()
    if max_len and len(clean) > max_len:
        clean = clean[:max_len].rstrip() + "..."
    return clean

# Utilitas Disk Cache Token SSO (Antar-Panggilan Serverless)
def _token_cache_file():
    return os.path.join(tempfile.gettempdir(), "kemnaker_token_cache.json")

def _get_cached_token_from_disk():
    path = _token_cache_file()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                token = data.get("token")
                ts = data.get("timestamp", 0)
                if token and (time.time() - ts) < TOKEN_CACHE_TTL:
                    return token, ts
        except Exception:
            pass
    return None, 0

def _save_cached_token_to_disk(token):
    path = _token_cache_file()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"token": token, "timestamp": time.time()}, f)
    except Exception:
        pass

def _clear_cached_token_from_disk():
    path = _token_cache_file()
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass

# Mekanisme Anti-Spam & Deduplikasi Trigger (Debounce 15 Menit)
def check_and_lock_trigger(trigger_name, window_seconds=900, force=False):
    """
    Mencegah eksekusi ganda (misal dari Cloudflare & cron-job.org di jam yang sama).
    Window default 900 detik (15 menit). Mengembalikan True jika boleh dieksekusi, False jika duplikat.
    """
    now = time.time()
    today_str = datetime.now(WIB).strftime("%Y-%m-%d")
    key = f"{today_str}_{trigger_name}"

    lock_file = os.path.join(tempfile.gettempdir(), "monev_trigger_locks.json")
    locks = {}

    global _TRIGGER_HISTORY
    locks.update(_TRIGGER_HISTORY)

    if os.path.exists(lock_file):
        try:
            with open(lock_file, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if isinstance(saved, dict):
                    for k, v in saved.items():
                        if k not in locks or v > locks[k]:
                            locks[k] = v
        except Exception:
            pass

    last_run = locks.get(key, 0)
    if not force and (now - last_run) < window_seconds:
        print(f"[Debounce] Trigger '{key}' diabaikan karena sudah berjalan {int(now - last_run)} detik yang lalu.", flush=True)
        return False

    locks[key] = now
    _TRIGGER_HISTORY[key] = now
    try:
        with open(lock_file, "w", encoding="utf-8") as f:
            json.dump(locks, f)
    except Exception:
        pass
    return True

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
        with urllib.request.urlopen(req, timeout=25) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            _CACHED_TOKEN = None
            _clear_cached_token_from_disk()
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

def edit_pesan_telegram(chat_id, message_id, text=None, reply_markup=None):
    """Mengubah isi teks atau reply markup dari pesan Telegram yang sudah terkirim (misal menghapus tombol setelah diklik)"""
    target_chat = str(chat_id).strip() if chat_id else (TELEGRAM_CHAT_ID.strip() if TELEGRAM_CHAT_ID else None)
    if not TELEGRAM_BOT_TOKEN or not target_chat or not message_id:
        return False

    clean_token = TELEGRAM_BOT_TOKEN.strip()
    if clean_token.lower().startswith("bot"):
        clean_token = clean_token[3:]

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        if text is not None:
            payload = {
                "chat_id": target_chat,
                "message_id": message_id,
                "text": text,
                "parse_mode": "Markdown"
            }
            if reply_markup is not None:
                payload["reply_markup"] = reply_markup
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{clean_token}/editMessageText",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with opener.open(req, timeout=10):
                return True
        elif reply_markup is not None:
            payload = {
                "chat_id": target_chat,
                "message_id": message_id,
                "reply_markup": reply_markup
            }
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{clean_token}/editMessageReplyMarkup",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with opener.open(req, timeout=10):
                return True
    except Exception as e:
        print(f"[Telegram Edit Notice] {e}", flush=True)
        return False
    return False

# 3. Autentikasi SSO Kemnaker
class SafeCookieJar(http.cookiejar.CookieJar):
    """CookieJar yang memfilter cookie tracking WAF (acw_tc) agar tidak bocor antar-subdomain Kemnaker"""
    def set_cookie(self, cookie):
        if cookie.name == "acw_tc":
            return
        super().set_cookie(cookie)

def login_kemnaker(force_refresh=False):
    global _CACHED_TOKEN, _CACHED_TOKEN_TIME
    now = time.time()
    if not force_refresh:
        if _CACHED_TOKEN and (now - _CACHED_TOKEN_TIME) < TOKEN_CACHE_TTL:
            return _CACHED_TOKEN
        disk_token, disk_ts = _get_cached_token_from_disk()
        if disk_token:
            _CACHED_TOKEN = disk_token
            _CACHED_TOKEN_TIME = disk_ts
            return disk_token

    manual = os.getenv("KEMNAKER_BEARER_TOKEN")
    if manual and len(manual) > 20:
        return manual.strip()

    cj = SafeCookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    browser_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8"
    }

    # Inisiasi SSO
    req_init = urllib.request.Request(wrap_url("https://maganghub.kemnaker.go.id/api/naco/login?redirect_url=/"), headers=browser_headers)
    res_init = opener.open(req_init, timeout=25)
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
    res_login = opener.open(req_login, timeout=25)
    login_data = json.loads(res_login.read().decode("utf-8"))
    if not login_data.get("data", {}).get("authenticated"):
        raise Exception(f"Autentikasi gagal: {login_data}")

    # Callback handshake
    opener.open(urllib.request.Request(wrap_url(login_data["data"]["redirect_uri"]), headers=browser_headers), timeout=25)

    token = next((c.value for c in cj if c.name == "naco_access_token"), None)
    if not token:
        raise Exception("Gagal mengekstrak naco_access_token")

    _CACHED_TOKEN = token
    _CACHED_TOKEN_TIME = now
    _save_cached_token_to_disk(token)
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
        err_msg = safe_markdown(diag.get("error", "Koneksi terputus"), max_len=200)
        return f"🔍 *STATUS PRESENSI HARI INI*\n\n⏰ *Waktu:* `{diag['waktu']}`\n❌ *Status:* Gagal terhubung ke Kemnaker\n🚨 *Pesan:* `{err_msg}`"

    sisa, total = hitung_sisa_template(token=_CACHED_TOKEN)
    sisa_info = f"📦 *Template Cadangan:* `{sisa} dari {total} template belum terpakai`\n\n"
    user_name = safe_markdown(diag.get("user_name", "Mas Ade"))
    mentor_name = safe_markdown(diag.get("mentor_name", "-"))

    if diag["sudah_absen"]:
        dt = diag.get("data_absen") or {}
        app_st = dt.get("approval_status", "SUBMITTED")
        jam = f" (Tercatat jam {dt['created_at'].split('T')[1][:8]} WIB)" if "T" in dt.get("created_at", "") else ""
        act_clean = safe_markdown(diag.get("activity_text", ""), max_len=280)
        act = f"📝 *Kegiatan Terdata:*\n_{act_clean}_\n\n" if act_clean else ""
        return (
            "🔍 *STATUS PRESENSI HARI INI*\n\n"
            f"👤 *Nama Peserta:* `{user_name}`\n"
            f"🏢 *Nama Mentor:* `{mentor_name}`\n"
            f"📅 *Tanggal:* `{diag['today_str']}`\n"
            f"⏰ *Waktu Cek:* `{diag['waktu']}`\n\n"
            f"📊 *Status:* ✅ *SUDAH TERISI (PRESENT)*{jam}\n"
            f"📋 *Persetujuan Mentor:* `{app_st}`\n\n"
            f"{act}"
            f"{sisa_info}"
            "✨ _Presensi hari ini sudah aman tercatat. Tidak perlu diisi ulang!_"
        )
    return (
        "🔍 *STATUS PRESENSI HARI INI*\n\n"
        f"👤 *Nama Peserta:* `{user_name}`\n"
        f"🏢 *Nama Mentor:* `{mentor_name}`\n"
        f"📅 *Tanggal:* `{diag['today_str']}`\n"
        f"⏰ *Waktu Cek:* `{diag['waktu']}`\n\n"
        "📊 *Status Presensi:* ⚠️ *BELUM TERISI*\n\n"
        f"{sisa_info}"
        "💡 _Belum ada presensi untuk hari ini. Mas Ade bisa mengisi manual di web, ketik `/isi <kegiatan>`, atau jalankan `/monev`._"
    )

# 5. Template & Eksekusi Monev
def muat_semua_template():
    global _ACTIVITY_TEMPLATES
    if _ACTIVITY_TEMPLATES is None:
        p = os.path.join(os.path.dirname(__file__), "templates.json")
        try:
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    _ACTIVITY_TEMPLATES = json.load(f)
        except Exception as e:
            print(f"[Template Error] Gagal membaca templates.json: {e}", flush=True)
        if not _ACTIVITY_TEMPLATES:
            _ACTIVITY_TEMPLATES = [{
                "id": 1,
                "category": "default",
                "activity": "Melakukan penelusuran modul fungsional aplikasi serta dokumentasi teknis pendukung.",
                "learning": "Mempelajari alur integrasi sistem data dan prosedur validasi parameter operasional.",
                "obstacles": "Tidak ada kendala yang berarti, seluruh tugas berjalan dengan lancar."
            }]
    return _ACTIVITY_TEMPLATES

def _baca_file_used_templates():
    """Membaca riwayat used_templates baik dari root project maupun fallback /tmp"""
    p_local = os.path.join(os.path.dirname(__file__), "used_templates.json")
    p_tmp = os.path.join(tempfile.gettempdir(), "monev_used_templates.json")
    data = {"used_ids": [], "history": []}

    for p in [p_local, p_tmp]:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    content = json.load(f)
                    if isinstance(content, dict):
                        data["used_ids"].extend(content.get("used_ids", []))
                        data["history"].extend(content.get("history", []))
            except Exception:
                pass
    data["used_ids"] = sorted(list(set(data["used_ids"])))
    return data

def ambil_riwayat_terpakai(token=None):
    """Mengambil riwayat template yang sudah dipakai dari used_templates.json
    serta verifikasi silang langsung dengan riwayat daily-logs di Kemnaker."""
    used_ids = set()
    used_snippets = set()

    # 1. Baca dari file lokal & /tmp
    data = _baca_file_used_templates()
    for i in data.get("used_ids", []):
        used_ids.add(i)
    for h in data.get("history", []):
        act = str(h.get("activity", "")).strip().lower()
        if act:
            used_snippets.add(act[:80])

    # 2. Verifikasi silang dengan riwayat daily-logs dari Kemnaker (dengan pagination limit)
    if token:
        try:
            logs = api_call("https://monev-api.maganghub.kemnaker.go.id/api/v1/daily-logs?limit=100&page=1", token).get("data", [])
            for item in logs:
                act = str(item.get("activity_log", "")).strip().lower()
                if act:
                    used_snippets.add(act[:80])
        except Exception as e:
            print(f"[Template Warning] Gagal sinkronisasi daily-logs Kemnaker: {e}", flush=True)

    return used_ids, used_snippets

def ambil_template_belum_terpakai(today_wib=None, token=None):
    """
    Mengambil template kegiatan yang BELUM PERNAH DIPAKAI sama sekali.
    Mengembalikan tuple: (template_terpilih, sisa_belum_terpakai, total_template)
    """
    templates = muat_semua_template()
    total = len(templates)
    used_ids, used_snippets = ambil_riwayat_terpakai(token=token)

    # Filter template yang belum pernah dipakai
    belum_terpakai = []
    for t in templates:
        t_id = t.get("id")
        t_act_snippet = str(t.get("activity", "")).strip().lower()[:80]
        if (t_id is not None and t_id in used_ids) or (t_act_snippet in used_snippets):
            continue
        belum_terpakai.append(t)

    sisa = len(belum_terpakai)

    if belum_terpakai:
        terpilih = belum_terpakai[0]
        return terpilih, sisa, total
    else:
        # Jika seluruh template sudah terpakai
        today_wib = today_wib or datetime.now(WIB)
        day = today_wib.timetuple().tm_yday
        fallback = templates[day % total] if total > 0 else {
            "id": 0,
            "category": "fallback",
            "activity": "Melakukan penelusuran modul fungsional aplikasi serta dokumentasi teknis pendukung.",
            "learning": "Mempelajari alur integrasi sistem data dan prosedur validasi parameter operasional.",
            "obstacles": "Tidak ada kendala yang berarti, seluruh tugas berjalan dengan lancar."
        }
        return fallback, 0, total

def hitung_sisa_template(token=None):
    """Menghitung sisa template yang belum terpakai dan total template yang ada."""
    if not token:
        try:
            token = _CACHED_TOKEN or login_kemnaker()
        except Exception:
            token = None
    _, sisa, total = ambil_template_belum_terpakai(token=token)
    return sisa, total

def tandai_template_terpakai(template, date_str):
    """Mencatat template yang telah dipakai ke file used_templates.json (dengan fallback /tmp jika read-only)"""
    if not template or not isinstance(template, dict):
        return
    t_id = template.get("id")
    data = _baca_file_used_templates()

    used_ids = set(data.get("used_ids", []))
    if t_id is not None:
        used_ids.add(t_id)
    data["used_ids"] = sorted(list(used_ids))

    history = data.get("history", [])
    now_iso = datetime.now(WIB).isoformat()
    history.append({
        "date": date_str,
        "template_id": t_id,
        "category": template.get("category", "general"),
        "activity": template.get("activity", "")[:120],
        "timestamp": now_iso
    })
    data["history"] = history

    # Coba tulis ke root project
    p_local = os.path.join(os.path.dirname(__file__), "used_templates.json")
    saved = False
    try:
        with open(p_local, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        saved = True
    except OSError:
        pass

    # Fallback simpan ke /tmp jika root project read-only di serverless Vercel
    if not saved:
        p_tmp = os.path.join(tempfile.gettempdir(), "monev_used_templates.json")
        try:
            with open(p_tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Template Error] Gagal mencatat template ke /tmp: {e}", flush=True)

def ambil_template(today_wib, token=None):
    """Fungsi pembungkus kompatibilitas yang mengembalikan 1 template belum terpakai."""
    template, _, _ = ambil_template_belum_terpakai(today_wib=today_wib, token=token)
    return template

def submit_monev(token=None, today_str=None, template=None, custom_activity=None):
    """Fungsi tunggal untuk submit presensi (otomatis maupun kustom)"""
    today_wib = datetime.now(WIB)
    today_str = today_str or today_wib.strftime("%Y-%m-%d")
    token = token or login_kemnaker()
    
    if not template and not custom_activity:
        template, _, _ = ambil_template_belum_terpakai(today_wib, token=token)
    elif not template:
        template = {
            "activity": custom_activity,
            "learning": "Mempelajari dan menyelesaikan tugas operasional harian sesuai arahan di unit kerja.",
            "obstacles": "Semua kegiatan berjalan dengan lancar dan tidak ada kendala yang berarti."
        }

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
    res = api_call("https://monev-api.maganghub.kemnaker.go.id/api/v1/attendances/with-daily-log", token, method="POST", payload=payload)

    # Tandai template sebagai terpakai jika sukses dan bukan custom activity
    if not custom_activity and template and template.get("id"):
        tandai_template_terpakai(template, today_str)

    return res

# Alias backward-compatibility
test_post_kemnaker = submit_monev

def muat_template_pengingat():
    global _REMINDER_TEMPLATES
    if _REMINDER_TEMPLATES is None:
        p = os.path.join(os.path.dirname(__file__), "reminder_templates.json")
        _REMINDER_TEMPLATES = json.load(open(p, "r", encoding="utf-8")) if os.path.exists(p) else {
            "pagi_09": ["🌅 Selamat pagi Mas Ade! Sistem monitoring aktif memantau hari magangmu."],
            "sore_15": ["🌤️ Selamat sore Mas Ade! Jam 3 sore saatnya laporan dan auto-monev."],
            "sore_18": ["🌤️ Halo Mas Ade! Cek presensi monev jam 6 sore nih, yuk pastikan aman~"],
            "malam_21": ["🌙 Selamat malam Mas Ade! Evaluasi presensi monev jam 9 malam."]
        }
    return _REMINDER_TEMPLATES

def extract_activity_snippet(text, max_words=12):
    """Mengambil sekitar 8-12 kata pertama dari kegiatan logbook."""
    if not text:
        return ""
    words = str(text).strip().split()
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words]) + "..."

def kirim_pengingat_monev(chat_id=None, force_mode=None, force_send=False):
    today_wib = datetime.now(WIB)
    today_str = today_wib.strftime("%Y-%m-%d")
    is_weekend = today_wib.weekday() >= 5
    try:
        sudah, _ = periksa_absen_hari_ini(login_kemnaker(), today_str)
        if sudah and not force_send:
            print(f"[Pengingat] Presensi {today_str} sudah terisi. Pengingat dilewati.", flush=True)
            return {"status": "already_submitted", "message": "Presensi hari ini sudah terisi, pengingat dilewati."}
    except Exception as e:
        print(f"[Pengingat] Status presensi tidak dapat dicek ({e}), tetap kirim pengingat.", flush=True)

    temps = muat_template_pengingat()
    is_malam = force_mode == "malam" or (force_mode is None and today_wib.hour >= 20)
    daftar = temps.get("malam_21" if is_malam else "sore_18", [])
    salam_random = random.choice(daftar) if daftar else "Halo Mas Ade, jangan lupa cek monev hari ini ya!"
    catatan_weekend = "\n🏖️ _Catatan: Jika hari ini Anda libur magang/tidak ada shift, silakan abaikan pengingat ini._\n" if is_weekend else ""

    pesan = (
        f"{salam_random}\n\n"
        f"_{('🌙 EVALUASI MALAM JAM 21:00 WIB' if is_malam else '🌤️ CEK STATUS SORE JAM 18:00 WIB')}_\n"
        f"⏰ *Jadwal Presensi:* Mandiri atau Auto-Monev Jam 15:00 WIB{catatan_weekend}\n"
        "💡 _Ketik `/isi <kegiatan>` atau klik tombol di bawah._"
    )
    kirim_telegram(pesan, chat_id=chat_id, reply_markup=MENU_KEYBOARD)
    return {"status": "success", "message": "Pengingat terkirim"}

kirim_pengingat_sore = kirim_pengingat_monev

def kirim_status_harian(waktu_label=None, chat_id=None):
    """
    Mengirim laporan status presensi & monitoring sistem harian:
    - 09:00 WIB ("pagi"): Monitoring pagi & cek kesehatan SSO / proxy.
    - 18:00 WIB ("sore"): Cek apakah sudah monev. Jika belum (misal jam 15:00 gagal), otomatis auto-retry!
    - 21:00 WIB ("malam"): Cek apakah sudah monev + cuplikan kegiatan (8-12 kata). Jika belum, otomatis auto-retry & peringatan darurat!
    """
    today_wib = datetime.now(WIB)
    today_str = today_wib.strftime("%Y-%m-%d")
    jam_str = today_wib.strftime("%H:%M:%S")
    is_weekend = today_wib.weekday() >= 5

    if waktu_label:
        w_norm = str(waktu_label).lower().strip()
    else:
        h = today_wib.hour
        if h < 12:
            w_norm = "pagi"
        elif h < 20:
            w_norm = "sore"
        else:
            w_norm = "malam"

    is_pagi = w_norm == "pagi"
    is_sore = w_norm == "sore"
    is_malam = w_norm == "malam"

    weekend_badge = " 🏖️ [AKHIR PEKAN]" if is_weekend else ""
    if is_pagi:
        waktu_title = f"PAGI (09:00 WIB){weekend_badge}"
        icon_waktu = "🌅"
    elif is_sore:
        waktu_title = f"SORE (18:00 WIB){weekend_badge}"
        icon_waktu = "🌤️"
    else:
        waktu_title = f"MALAM (21:00 WIB){weekend_badge}"
        icon_waktu = "🌙"

    temps = muat_template_pengingat()
    if is_pagi:
        salam_list = temps.get("pagi_09", [])
        default_salam = "Selamat pagi Mas Ade!"
    elif is_sore:
        salam_list = temps.get("sore_18", [])
        default_salam = "Selamat sore Mas Ade!"
    else:
        salam_list = temps.get("malam_21", [])
        default_salam = "Selamat malam Mas Ade!"

    salam_text = random.choice(salam_list) if salam_list else default_salam

    diag = periksa_koneksi_dan_status()
    cf = os.getenv("CLOUDFLARE_WORKER_URL", "").strip()
    proxy_st = "Aktif" if len(cf) > 5 else "Direct"

    if not diag.get("success"):
        err_clean = safe_markdown(diag.get("error", "Koneksi terputus"), max_len=200)
        pesan = (
            f"{salam_text}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{icon_waktu} *MONITORING SISTEM {waktu_title}*\n\n"
            f"📅 *Tanggal:* `{today_str}` ({jam_str} WIB)\n"
            "🚨 *Status Koneksi Kemnaker:* Gagal Terhubung\n"
            f"❌ *Detail Kendala:* `{err_clean}`\n\n"
            "⚠️ _Sistem otomatis mendeteksi kendala pada login Kemnaker. Mohon periksa kembali kredensial atau server Kemnaker._"
        )
        kirim_telegram(pesan, chat_id=chat_id, reply_markup=MENU_KEYBOARD)
        return {"status": "error", "message": diag.get("error")}

    user_name = safe_markdown(diag.get("user_name", "Mas Ade"))
    sisa, total = hitung_sisa_template(token=_CACHED_TOKEN)

    # 1. KONDISI SUDAH ABSEN
    if diag.get("sudah_absen"):
        dt = diag.get("data_absen") or {}
        app_st = dt.get("approval_status", "SUBMITTED")
        jam_absen = f"jam {dt['created_at'].split('T')[1][:8]} WIB" if "T" in dt.get("created_at", "") else "Tercatat"
        act_raw = diag.get("activity_text", "")

        if is_malam:
            # Jam 21:00 malam: Tampilkan status + cuplikan kegiatan (8-12 kata)
            snippet = extract_activity_snippet(act_raw, max_words=12)
            snippet_clean = safe_markdown(snippet)
            preview_sec = f"📝 *Cuplikan Kegiatan:*\n_{snippet_clean}_\n\n" if snippet_clean else ""
            pesan = (
                f"{salam_text}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{icon_waktu} *MONITORING MONEV MALAM ({waktu_title})*\n\n"
                "🤖 *Status Sistem & Trigger:* ✅ *Aktif & Berfungsi Normal*\n"
                f"📅 *Tanggal:* `{today_str}` ({jam_str} WIB)\n"
                f"👤 *Peserta:* `{user_name}`\n\n"
                f"📊 *Status Presensi Hari Ini:*\n"
                f"✅ *SUDAH TERISI (PRESENT)*\n"
                f"⏱️ *Waktu Submit:* `{jam_absen}`\n"
                f"📋 *Persetujuan Mentor:* `{app_st}`\n\n"
                f"{preview_sec}"
                f"📦 *Stok Template Cadangan:* `{sisa} dari {total} template`\n\n"
                "✨ _Laporan monev dan kehadiran hari ini telah selesai dan aman! Selamat beristirahat._"
            )
        else:
            act_clean = safe_markdown(act_raw, max_len=280)
            act_sec = f"📝 *Kegiatan Terdata:*\n_{act_clean}_\n\n" if act_clean else ""
            pesan = (
                f"{salam_text}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{icon_waktu} *MONITORING MONEV & SISTEM ({waktu_title})*\n\n"
                "🤖 *Status Sistem & Trigger:* ✅ *Aktif & Berfungsi Normal*\n"
                f"🌐 *Jalur Proxy:* `{proxy_st}` | 🔐 *SSO Kemnaker:* `Terhubung`\n"
                f"📅 *Tanggal:* `{today_str}` ({jam_str} WIB)\n"
                f"👤 *Peserta:* `{user_name}`\n\n"
                f"📊 *Status Presensi Hari Ini:*\n"
                f"✅ *SUDAH TERISI (PRESENT)*\n"
                f"⏱️ *Waktu Submit:* `{jam_absen}`\n"
                f"📋 *Persetujuan Mentor:* `{app_st}`\n\n"
                f"{act_sec}"
                f"📦 *Stok Template Cadangan:* `{sisa} dari {total} template`\n\n"
                "✨ _Presensi hari ini sudah aman dan tercatat di Kemnaker._"
            )

        kirim_telegram(pesan, chat_id=chat_id, reply_markup=MENU_KEYBOARD)
        return {"status": "success", "sudah_absen": True, "message": f"Status {w_norm} terkirim (sudah monev)"}

    # 2. KONDISI BELUM ABSEN
    if is_weekend:
        pesan = (
            f"{salam_text}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{icon_waktu} *MONITORING AKHIR PEKAN ({waktu_title})*\n\n"
            "🏖️ *Hari ini adalah akhir pekan (Sabtu/Minggu).*\n"
            "Sistem auto-monev dinonaktifkan di hari libur kerja. Selamat menikmati akhir pekan dan selamat beristirahat! ☕✨\n\n"
            f"📅 *Tanggal:* `{today_str}` ({jam_str} WIB)\n"
            f"👤 *Peserta:* `{user_name}`\n"
            f"📦 *Stok Template Tersedia:* `{sisa} dari {total} template`\n\n"
            "👉 _Jika Anda memiliki shift operasional/tugas khusus hari ini, silakan isi manual via `/isi <kegiatan>`._"
        )
        kirim_telegram(pesan, chat_id=chat_id, reply_markup=MENU_KEYBOARD)
        return {"status": "weekend_skipped", "sudah_absen": False, "message": f"Status akhir pekan ({w_norm}) terkirim (libur)"}

    if is_pagi:
        pesan = (
            f"{salam_text}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{icon_waktu} *MONITORING MONEV PAGI ({waktu_title})*\n\n"
            "🤖 *Status Sistem & Trigger:* ✅ *Aktif & Berfungsi Normal*\n"
            f"🌐 *Jalur Proxy:* `{proxy_st}` | 🔐 *SSO Kemnaker:* `Terhubung`\n"
            f"📅 *Tanggal:* `{today_str}` ({jam_str} WIB)\n"
            f"👤 *Peserta:* `{user_name}`\n\n"
            "📊 *Status Presensi Hari Ini:*\n"
            "⏳ *BELUM TERISI (NORMAL)*\n"
            "⚡ _Auto-Monev dijadwalkan otomatis berjalan pada pukul 15:00 WIB (Jam 3 Sore)._\n\n"
            f"📦 *Stok Template Cadangan:* `{sisa} dari {total} template`\n\n"
            "👉 _Jika ingin mengisi sekarang lebih awal, klik tombol di bawah atau ketik `/isi <kegiatan>`._"
        )
        kirim_telegram(pesan, chat_id=chat_id, reply_markup=MENU_KEYBOARD)
        return {"status": "success", "sudah_absen": False, "message": "Status pagi terkirim (menunggu jadwal 15:00)"}

    # Jam 18:00 WIB (Sore) atau Jam 21:00 WIB (Malam) dan belum monev -> AUTO-RETRY SUBMIT SEKARANG!
    print(f"[Status {w_norm.upper()}] Presensi {today_str} masih kosong. Memulai auto-retry pengisian monev...", flush=True)
    try:
        retry_res = main(force=False, notify_telegram=False)
        diag_after = periksa_koneksi_dan_status()
        act_text = diag_after.get("activity_text") or (retry_res.get("template") or {}).get("activity", "")
        snippet = extract_activity_snippet(act_text, max_words=12)
        snippet_clean = safe_markdown(snippet)

        sisa_now, total_now = hitung_sisa_template(token=_CACHED_TOKEN)
        pesan = (
            f"{salam_text}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{icon_waktu} *MONITORING & AUTO-RETRY ({waktu_title})*\n\n"
            "⚠️ *Perhatian:* Presensi hari ini sebelumnya belum terisi (kemungkinan gagal di jam 15:00).\n"
            "🔄 *Sistem telah melakukan Auto-Retry pengisian dan BERHASIL!* 🎉\n\n"
            f"📅 *Tanggal:* `{today_str}` ({jam_str} WIB)\n"
            f"👤 *Peserta:* `{user_name}`\n"
            f"✅ *Status Presensi:* `PRESENT`\n"
            f"📝 *Cuplikan Kegiatan:* _{snippet_clean}_\n"
            f"📦 *Sisa Stok Template:* `{sisa_now} dari {total_now} template`\n\n"
            "✨ _Laporan presensi dan logbook hari ini telah berhasil diselamatkan ke Kemnaker!_"
        )
        kirim_telegram(pesan, chat_id=chat_id, reply_markup=MENU_KEYBOARD)
        return {"status": "retry_success", "sudah_absen": True, "message": f"Auto-retry jam {w_norm} berhasil"}

    except Exception as retry_err:
        err_msg = safe_markdown(str(retry_err), max_len=200)
        pesan = (
            f"🚨 *PERINGATAN DARURAT: MONEV BELUM TERISI ({waktu_title})*\n\n"
            f"⚠️ *Halo {user_name}! Mohon Perhatian Segera!*\n"
            f"Presensi Monev hari ini (`{today_str}`) masih *KOSONG*.\n"
            f"Sistem otomatis telah mencoba melakukan auto-retry pada {jam_str} WIB, namun gagal:\n"
            f"❌ *Detail Kendala:* `{err_msg}`\n\n"
            "👇 _Mohon segera lakukan pengisian manual sekarang sebelum batas hari berakhir!_\n"
            "Klik tombol *⚡ Eksekusi Monev* di bawah atau ketik `/isi <kegiatan>`."
        )
        kirim_telegram(pesan, chat_id=chat_id, reply_markup=MENU_KEYBOARD)
        return {"status": "retry_failed", "sudah_absen": False, "error": str(retry_err)}

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
    jam_label = today_wib.strftime("%H:%M")

    print(f"=== MONEV RUNNER: {today_str} {jam_str} WIB ===", flush=True)

    is_weekend = today_wib.weekday() >= 5
    if is_weekend and not force:
        msg = (
            f"🏖️ *AKHIR PEKAN: AUTO-MONEV DILEWATI (JAM {jam_label} WIB)*\n\n"
            f"📅 *Tanggal:* `{today_str}` ({jam_str} WIB)\n"
            "Hari ini adalah akhir pekan (Sabtu/Minggu). Pengisian presensi otomatis dinonaktifkan untuk menjaga integritas data hari kerja magang di Kemnaker.\n\n"
            "💡 _Jika Anda memiliki shift operasional khusus hari ini, silakan gunakan perintah `/isi <kegiatan>` atau klik tombol di bawah._"
        )
        print(f"[Weekend Skip] {today_str} adalah akhir pekan (Sabtu/Minggu). Auto-Monev dilewati.", flush=True)
        if notify_telegram:
            kirim_telegram(msg, reply_markup=MENU_KEYBOARD)
        return {"status": "weekend_skipped", "date": today_str, "message": msg}

    try:
        token = login_kemnaker()
        sudah, data_absen = periksa_absen_hari_ini(token, today_str)
        if sudah and not force:
            msg = "✅ *Presensi Monev Hari Ini Sudah Terisi!*\nAnda sudah tercatat hadir (PRESENT) di Kemnaker. Tidak perlu mengisi ulang."
            if notify_telegram:
                kirim_telegram(msg)
            return {"status": "already_submitted", "date": today_str, "message": msg}

        # Ambil template yang belum pernah dipakai sama sekali
        template, sisa_sebelum, total = ambil_template_belum_terpakai(today_wib, token=token)
        hasil = submit_monev(token=token, today_str=today_str, template=template)

        # Hitung sisa template setelah berhasil terpakai
        sisa_sekarang = max(0, sisa_sebelum - 1) if sisa_sebelum > 0 else 0

        # Peringatan jika stok template mulai menipis
        warning_sisa = ""
        if sisa_sekarang == 0:
            warning_sisa = "\n\n⚠️ *PERHATIAN:* Semua template telah terpakai! Mohon segera tambahkan variasi baru ke `templates.json` agar tidak terjadi pengulangan."
        elif sisa_sekarang <= 5:
            warning_sisa = f"\n\n⚠️ *Pengingat:* Stok template hampir habis (tersisa {sisa_sekarang}). Disarankan menambah template baru ke `templates.json`."

        msg = (
            f"🚀 *AUTO MONEV BERHASIL DIKIRIM (JAM {jam_label} WIB)*\n\n"
            f"📅 *Tanggal:* `{today_str}` ({jam_str} WIB)\n"
            f"📍 *Lokasi:* `{OFFICE_LAT}, {OFFICE_LONG}`\n\n"
            f"📝 *Kegiatan:*\n_{template['activity']}_\n\n"
            f"💡 *Pembelajaran:*\n_{template['learning']}_\n\n"
            f"⚠️ *Kendala:*\n_{template['obstacles']}_\n\n"
            f"📊 *Status Template:*\n"
            f"📦 Sisa template belum terpakai: *{sisa_sekarang} dari {total} template*"
            f"{warning_sisa}\n\n"
            "✨ _Laporan presensi dan logbook harian berhasil diserahkan ke Kemnaker!_"
        )
        if notify_telegram:
            kirim_telegram(msg)
        return {"status": "success", "date": today_str, "message": msg, "template": template, "sisa_template": sisa_sekarang, "total_template": total}
    except Exception as e:
        err_clean = safe_markdown(str(e), max_len=200)
        msg = (
            f"🚨 *PERINGATAN: AUTO MONEV GAGAL DIKIRIM (JAM {jam_label} WIB)*\n\n"
            f"📅 *Tanggal:* `{today_str}` ({jam_str} WIB)\n"
            f"❌ *Detail Kendala:* `{err_clean}`\n\n"
            "⚠️ Presensi hari ini belum berhasil terisi otomatis.\n"
            "Sistem akan mencoba auto-retry pada pemantauan jam 18:00 dan 21:00 WIB, atau Anda dapat eksekusi manual lewat tombol di bawah."
        )
        if notify_telegram:
            kirim_telegram(msg, reply_markup=MENU_KEYBOARD)
        raise e

if __name__ == "__main__":
    main(notify_telegram=True)

