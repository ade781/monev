# Monev ADE7 Reminder - MagangHub Kemnaker

Sistem monitoring, pengingat, dan pengisian presensi cerdas otomatis untuk MagangHub Kemnaker dengan anti-blokir Cloudflare Worker dan integrasi bot Telegram 24/7.

---

## Fitur Utama

1. **Auto SSO Kemnaker**: Mengambil Bearer Token secara otomatis menggunakan kredensial SIAPkerja.
2. **Pengecekan Aman (Guard Check)**: Jika sudah presensi mandiri, bot tidak akan menimpa data yang ada.
3. **Monitoring Pagi (09:00 WIB) & Sore (15:00 WIB)**: Notifikasi status kehadiran harian sekaligus pengecekan kesehatan koneksi sistem/heartbeat trigger.
4. **Pengingat Santai (19:00 WIB) & Keras (20:00 WIB)**: Pengingat Telegram bervariasi setiap hari (Senin–Minggu) jika belum absen.
5. **Auto Monev Cadangan (21:00 WIB)**: Jaring pengaman otomatis di jam 9 malam jika belum mengisi.
5. **Human Jitter & GPS Jitter**: Jeda acak manusiawi dan deviasi koordinat natural (10–25m).
6. **35 Variasi Template Autentik (Anti-Duplikasi)**: Template kegiatan magang nyata (ARFF YIA Angkasa Pura, React, Express, QR Code, inspeksi APAR, koordinasi). Sistem menjamin setiap template yang sudah dipakai **tidak akan dipakai lagi**.
7. **Laporan Sisa Template Otomatis**: Saat auto-monev jam 21:00 WIB berjalan, notifikasi menyertakan informasi sisa template yang belum terpakai dan peringatan jika stok menipis.
8. **Tombol Interaktif (Inline Keyboard)**: Menu tombol di Telegram yang dapat diklik langsung (termasuk tombol cek Sisa Template).
9. **Konfirmasi Eksekusi (`/monev`)**: Dialog konfirmasi Ya/Tidak sebelum melakukan submit.
10. **Kirim Kegiatan Kustom (`/isi <kegiatan>`)**: Mengisi logbook kegiatan harian kustom dari chat Telegram.
11. **Rekapitulasi Mingguan (`/rekap`)**: Ringkasan performa kehadiran 7 hari terakhir beserta status mentor.
12. **Cloudflare Worker Reverse Proxy**: Mem-bypass proteksi Cloudflare WAF saat dijalankan di Vercel.

---

## Daftar Perintah Telegram (@Cekad_bot)

| Perintah | Fungsi |
| :--- | :--- |
| `/start` atau `/help` | Menampilkan menu utama dan tombol interaktif |
| `/cek` | Memeriksa apakah presensi hari ini sudah terisi atau belum (Read-only) |
| `/tes` | Menguji kesehatan sistem, SSO, dan koneksi tanpa submit presensi |
| `/sisa` atau `/template` | Mengecek sisa stok template kegiatan yang belum pernah dipakai |
| `/monev` | Eksekusi pengisian monev dengan konfirmasi Ya/Tidak |
| `/isi <kegiatan>` | Mengisi presensi hari ini dengan catatan kegiatan khusus |
| `/rekap` | Menampilkan ringkasan kehadiran 7 hari terakhir |
| `/proxy` | Menampilkan status Cloudflare Worker reverse proxy |

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
