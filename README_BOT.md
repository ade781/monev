# Monev ADE7 Reminder - MagangHub Kemnaker

Sistem monitoring, pengingat, dan pengisian presensi cerdas otomatis untuk MagangHub Kemnaker dengan anti-blokir Cloudflare Worker dan integrasi bot Telegram 24/7.

---

## Fitur Utama

1. **Auto SSO Kemnaker**: Mengambil Bearer Token secara otomatis menggunakan kredensial SIAPkerja.
2. **Pengecekan Aman (Guard Check)**: Jika sudah presensi mandiri, bot tidak akan menimpa data yang ada.
3. **Pengingat Sore Ramah (17:30 WIB)**: Menyapa *"Mas Ade"* setiap sore jam pulang kerja di hari kerja (Senin–Jumat) sebagai early reminder sebelum backup malam.
4. **Eksekusi Otomatis Harian (21:00 WIB)**: Berjalan otomatis setiap malam sebagai jaring pengaman jika lupa mengisi.
5. **Human Jitter**: Jeda acak manusiawi (1.5–3.5 detik) sebelum eksekusi agar tidak terdeteksi bot otomatisasi.
6. **Micro GPS Jitter**: Variasi koordinat mikro natural (radius 10–25 meter) sehingga posisi GPS terlihat otentik seperti HP asli.
7. **15 Variasi Template Cerdas**: Template logbook profesional (Frontend, Backend, Database, QA, Dokumentasi) yang berotasi otomatis setiap minggu.
8. **Tombol Interaktif (Inline Keyboard)**: Menu tombol di Telegram yang dapat diklik langsung tanpa perlu mengetik manual.
9. **Kirim Kegiatan Kustom (`/isi <kegiatan>`)**: Kemampuan mengisi logbook kegiatan harian kustom langsung dari chat Telegram.
10. **Rekapitulasi Mingguan (`/rekap`)**: Ringkasan performa kehadiran 7 hari terakhir beserta status approval mentor.
11. **Cloudflare Worker Reverse Proxy**: Mem-bypass proteksi Cloudflare WAF (Error 403) saat dijalankan di cloud Vercel.

---

## Daftar Perintah Telegram (@Cekad_bot)

| Perintah | Fungsi |
| :--- | :--- |
| `/start` atau `/help` | Menampilkan menu utama dan tombol interaktif |
| `/cek` | Memeriksa status presensi hari ini dan nama mentor |
| `/rekap` | Menampilkan ringkasan kehadiran 7 hari terakhir |
| `/isi <kegiatan>` | Mengisi presensi hari ini dengan catatan khusus |
| `/tes` | Tes request POST ke Kemnaker & melihat pesan asli server |
| `/monev` | Menjalankan pencadangan monev secara manual |
| `/proxy` | Menampilkan URL Cloudflare Worker yang sedang aktif |

---

## Variabel Environment

| Variabel | Keterangan |
| :--- | :--- |
| `KEMNAKER_USERNAME` | NIK Akun SIAPkerja Kemnaker |
| `KEMNAKER_PASSWORD` | Password Akun Kemnaker |
| `OFFICE_LAT` | Latitude kantor (contoh: `-7.8981812`) |
| `OFFICE_LONG` | Longitude kantor (contoh: `110.0499084`) |
| `TELEGRAM_BOT_TOKEN` | Token Bot Telegram dari `@BotFather` |
| `TELEGRAM_CHAT_ID` | Chat ID Telegram pengguna |
| `CLOUDFLARE_WORKER_URL` | URL Cloudflare Worker reverse proxy |
