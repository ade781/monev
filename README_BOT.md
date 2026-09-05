# Monev ADE7 Reminder - MagangHub Kemnaker

Sistem bot otomatis cadangan untuk monitoring dan pengisian presensi serta laporan harian MagangHub Kemnaker jika belum mengisi hingga pukul 21:00 WIB.

## Fitur Unggulan
1. **Otomatis Login SSO Kemnaker**: Mengambil Bearer Token secara mandiri menggunakan kredensial SIAPkerja.
2. **Pengecekan Aman (Guard Check)**: Jika Anda sudah presensi sebelum jadwal bot, bot **TIDAK AKAN** menimpa data Anda.
3. **Template Kegiatan Dinamis**: Variasi template kegiatan >100 karakter sesuai syarat validasi Kemnaker.
4. **Interaktif Telegram Bot (`Monev ADE7 Reminder`)**: Cek status koneksi (`/tes`), presensi (`/cek`), atau status proxy (`/proxy`) langsung dari HP via `@Cekad_bot`.
5. **Cloudflare Worker Reverse Proxy**: Anti-blokir Cloudflare 403 saat berjalan di cloud serverless (Vercel).
6. **100% Gratis 24/7 Tanpa Laptop Nyala**.

---

## Variabel Environment (Vercel & .env)

| Variabel | Keterangan |
| :--- | :--- |
| `KEMNAKER_USERNAME` | NIK Akun SIAPkerja Kemnaker |
| `KEMNAKER_PASSWORD` | Password Akun Kemnaker |
| `OFFICE_LAT` | Latitude kantor (contoh: `-7.8981812`) |
| `OFFICE_LONG` | Longitude kantor (contoh: `110.0499084`) |
| `TELEGRAM_BOT_TOKEN` | Token Bot Telegram dari `@BotFather` |
| `TELEGRAM_CHAT_ID` | Chat ID Telegram Anda |
| `CLOUDFLARE_WORKER_URL` | URL Cloudflare Worker reverse proxy |
