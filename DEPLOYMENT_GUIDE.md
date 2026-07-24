# 🚀 Panduan Deployment: Dashboard Transportasi Papua

Ikuti langkah-langkah berikut untuk meng-host aplikasi ini di Streamlit Cloud.

### 1. Persiapan Repositori GitHub
1. Buat repositori baru di GitHub.
2. Unggah struktur folder berikut ke repositori tersebut:
   - `app.py` (Main entry point)
   - `requirements.txt` (Daftar library)
   - `modules/` (Folder berisi `config.py`, `database.py`, dll)
   - `data/` (Folder kosong untuk manajemen file jika diperlukan)

### 2. Streamlit Cloud Deployment
1. Masuk ke [Streamlit Cloud](https://share.streamlit.io/).
2. Klik **'Create app'** dan hubungkan akun GitHub Anda.
3. Pilih repositori yang baru Anda buat.
4. Tentukan `Main file path` sebagai `app.py`.
5. Klik **'Deploy!'**.

### 3. Manajemen Database
- Aplikasi menggunakan SQLite (`transportasi_papua.db`). 
- Di Streamlit Cloud, database akan bersifat lokal pada session. Untuk data yang persisten secara permanen di cloud, disarankan menggunakan database eksternal seperti PostgreSQL (Supabase/Heroku) di masa mendatang.
- Gunakan halaman **Admin** pada aplikasi untuk mengunggah file Excel BPS awal guna mengisi database.