# Panduan Otomatisasi Monev MagangHub Kemnaker

Sistem bot otomatis cadangan untuk mengisi laporan harian dan presensi MagangHub Kemnaker jika Anda lupa mengisi hingga jam 21:00 WIB.

## Fitur Unggulan
1. **Otomatis Login SSO Kemnaker**: Mengambil `naco_access_token` secara mandiri setiap kali berjalan menggunakan kredensial NIK & Password Anda. Tidak perlu lagi copy-paste token manual!
2. **Pengecekan Aman (Guard Check)**: Jika Anda sudah mengisi presensi secara manual sebelum jam 21:00 WIB, bot **TIDAK AKAN** mengirim apa pun (laporan asli Anda aman).
3. **Template Kegiatan Dinamis**: Memiliki 5 variasi kalimat aktivitas, pembelajaran, dan kendala yang memenuhi syarat minimal 100 karakter.
4. **Notifikasi Telegram**: Memberikan laporan langsung ke bot Telegram `@Cekad_bot` di HP Anda.
5. **100% Gratis Tanpa Laptop Nyala**: Dijalankan via GitHub Actions Workflow Cron.

---

## Variabel Rahasia di GitHub Secrets

Saat memasukkan script ini ke repositori private GitHub Anda, tambahkan rahasia berikut di menu **Settings -> Secrets and variables -> Actions -> New repository secret**:

| Nama Secret | Deskripsi / Nilai |
| :--- | :--- |
| `KEMNAKER_USERNAME` | NIK Akun SIAPkerja Kemnaker Anda |
| `KEMNAKER_PASSWORD` | Password Akun Kemnaker Anda |
| `OFFICE_LAT` | Latitude kantor (misal: `-7.8981812`) |
| `OFFICE_LONG` | Longitude kantor (misal: `110.0499084`) |
| `TELEGRAM_BOT_TOKEN` | Token Bot Telegram dari `@BotFather` |
| `TELEGRAM_CHAT_ID` | Chat ID Telegram Anda dari `@userinfobot` |

---

## Cara Menjalankan Manual di Komputer
```bash
python monev_bot.py
```
Script tidak membutuhkan instalasi pustaka eksternal apa pun (*zero external dependencies*, hanya memakai modul bawaan Python 3).
