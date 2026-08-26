# ?? Panduan Lengkap Instalasi & Pemindahan ke PC Ruang Rapat (1-Click Deployment)

Panduan ini disusun khusus agar Anda dapat memindahkan dan memasang sistem **AI Monitoring Ruang Elektrikal** ke **PC Ruang Rapat (Standard PC)** dengan mudah, tanpa perlu menginstal dependensi manual satu per satu.

---

## ??? 1. Kebutuhan Sistem PC Ruang Rapat

* **Sistem Operasi:** Windows 10 atau Windows 11 (64-bit).
* **Prosesor & RAM:** CPU Standard (Intel Core i3/i5/i7 atau AMD Ryzen), RAM minimal 4 GB.
* **Koneksi Jaringan:** 
  * Internet (hanya dibutuhkan saat pertama kali menjalankan `install.bat`).
  * Satu jaringan LAN / WiFi yang sama dengan kamera CCTV Imou Cruiser.

---

## ?? 2. Langkah 1: Mengunduh File dari GitHub ke PC Ruang Rapat

Ada **2 cara mudah** untuk memindahkan proyek ini ke PC Ruang Rapat:

### Cara A: Download ZIP Langsung (Paling Mudah, Tanpa Perlu Install Git)
1. Buka tautan repository GitHub proyek ini di browser PC Ruang Rapat.
2. Klik tombol hijau **`< > Code`** di pojok kanan atas.
3. Pilih **`Download ZIP`**.
4. Setelah terunduh, klik kanan file `.zip` tersebut $\to$ pilih **`Extract All...`** ke folder yang Anda inginkan (misal di `D:\AI-Electrical-Monitor` atau `C:\AI-Electrical-Monitor`).

### Cara B: Menggunakan Git Clone (Jika PC memiliki Git)
Buka Command Prompt (CMD) / PowerShell dan jalankan:
```bash
git clone <URL_REPOSITORY_GITHUB_ANDA>
cd imou-electrical-monitor
```

---

## ? 3. Langkah 2: Instalasi Otomatis (1-Click Installer)

1. Buka folder proyek hasil ekstrak di PC Ruang Rapat.
2. Cari file bernama **`install.bat`**.
3. **Klik 2 kali** file **`install.bat`** (atau klik kanan $\to$ *Run as administrator*).
4. Skrip otomatis akan melakukan:
   - ? Memeriksa & memasang **Python 3.12** secara otomatis.
   - ? Memeriksa & memasang **Node.js** secara otomatis.
   - ? Membuat lingkungan terisolasi (*Virtual Environment `venv`*).
   - ? Memasang **PyTorch, YOLO11, OpenCV, FastAPI, Edge-TTS**.
   - ? Memasang modul **WhatsApp Bot Bridge (Baileys)**.
   - ? Menyiapkan seluruh model AI & file suara alarm.
5. Tunggu beberapa menit hingga muncul pesan teks hijau:
   ```text
   ===============================================================================
                          INSTALASI BERHASIL 100%!
   ===============================================================================
   ```
6. Tekan tombol apa saja untuk menutup jendela instalasi.

---

## ?? 4. Langkah 3: Menjalankan Sistem (1-Click Launcher)

1. Di dalam folder proyek, **klik 2 kali** file **`start.bat`**.
2. Sistem akan otomatis:
   - Menjalankan WhatsApp Bot Bridge (Port 3001) di latar belakang.
   - Menjalankan Engine AI Video Analytics & Server Web (Port 8000).
   - **Membuka Dashboard Web secara otomatis** di browser default Anda (**`http://127.0.0.1:8000`**).

---

## ?? 5. Langkah 4: Menghubungkan Kamera CCTV Imou Cruiser

Jika sistem ingin beralih dari webcam laptop ke kamera CCTV Imou Cruiser di ruang panel:
1. Buka file bernama **`.env`** (atau copy dari `.env.example` lalu rename menjadi `.env`) menggunakan Notepad.
2. Ubah baris `IMOU_RTSP_URL` dengan format:
   ```env
   IMOU_RTSP_URL=rtsp://admin:SAFETY_CODE@IP_KAMERA_IMOU:554/cam/realmonitor?channel=1&subtype=1
   ```
   * *Contoh:* `rtsp://admin:L28FA92C@192.168.1.108:554/cam/realmonitor?channel=1&subtype=1`
   * *(Safety Code adalah 6 digit huruf kapital di stiker bawah kamera Imou).*
3. Simpan file `.env` dan jalankan kembali `start.bat`.

---

## ?? 6. Langkah 5: Pairing WhatsApp Bot K3

1. Di halaman dashboard web (**`http://127.0.0.1:8000`**), gulir ke bagian **Koneksi WhatsApp Bot Barcode**.
2. Buka aplikasi WhatsApp di HP pengawas K3 / nomor bot $\to$ pilih menu **Perangkat Tertaut (*Linked Devices*)** $\to$ **Tautkan Perangkat**.
3. Scan kode QR barcode yang muncul di layar dashboard web.
4. Setelah terhubung, pilih grup WhatsApp K3 dari dropdown **"Pilih Grup WhatsApp dari Daftar"** $\to$ klik **`Simpan`**.
5. Klik tombol **`?? Kirim Pesan & Foto Snapshot Uji Coba`** untuk memastikan notifikasi grup berjalan normal.

---

## ?? 7. Menghentikan Sistem

Jika Anda ingin mematikan sistem pemantauan:
- **Klik 2 kali** file **`stop.bat`** di dalam folder, ATAU
- Cukup tutup jendela terminal hitam `start.bat` / tekan `Ctrl + C`.

---

## ? FAQ & Troubleshooting di PC Ruang Rapat

1. **Tanya: Apakah PC Ruang Rapat memerlukan VGA/GPU khusus?**
   - **Jawab:** Tidak wajib. Sistem telah dioptimasi menggunakan model arsitektur `nano` (YOLO11n & SFace) yang berjalan sangat cepat dan ringan di prosesor (CPU) standar.
2. **Tanya: Bagaimana jika koneksi internet di ruang rapat lambat?**
   - **Jawab:** Internet hanya dibutuhkan 1 kali saat menjalankan `install.bat`. Setelah instalasi selesai, sistem AI deteksi APD, Wajah, Merokok, dan Pingsan berjalan 100% lokal tanpa internet. Internet/WiFi lokal hanya digunakan untuk mengirim pesan WhatsApp.
3. **Tanya: Apakah foto wajah yang didaftarkan akan hilang jika PC direstart?**
   - **Jawab:** Tidak, semua data personel tersimpan permanen di database lokal `events.db` dan folder `known_faces/`.
