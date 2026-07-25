# 📊 Papua Transportation Analysis Dashboard

Aplikasi dashboard berbasis Streamlit untuk mengelola, menganalisis, dan memvisualisasikan data transportasi udara dan laut di Provinsi Papua (termasuk 3 DOB: Papua Selatan, Papua Tengah, dan Papua Pegunungan).

## 🚀 Fitur Utama
- **Dashboard Visualisasi**: Grafik tren interaktif menggunakan Plotly untuk indikator penumpang dan barang.
- **Laporan Komparatif**: Tabel perbandingan Month-to-Month (M-to-M) dan Year-on-YTD (Y-on-Y) dengan baris 'JUMLAH TOTAL' otomatis.
- **Admin Data Correction**: Antarmuka spreadsheet interaktif untuk mencari, mengubah, atau menghapus data langsung dari database.
- **ETL Engine**: Pengolah file Excel otomatis dari BPS Papua menjadi data terstruktur dalam SQLite.
- **Format Angka Indonesia**: Tampilan angka menggunakan format ribuan titik (.) dan desimal koma (,).

## 📂 Struktur Proyek
```text
. 
├── app.py                # Entry point aplikasi Streamlit
├── requirements.txt      # Daftar dependensi Python
├── DEPLOYMENT_GUIDE.md   # Panduan deployment ke cloud
├── modules/              # Folder modul modular
│   ├── admin_page.py     # Halaman manajemen data
│   ├── config.py         # Metadata wilayah & pemetaan
│   ├── dashboard_page.py # Halaman grafik visualisasi
│   ├── database.py       # Koneksi SQLite
│   ├── etl_engine.py     # Logika pemrosesan Excel
│   └── report_page.py    # Logika laporan komparatif
└── transportasi_papua.db # Database SQLite lokal
```

## 🛠️ Instalasi Lokal
1. Clone repositori ini:
   ```bash
   git clone https://github.com/yenrosagala/StaTransportasi.git
   cd StaTransportasi
   ```
2. Install dependensi:
   ```bash
   pip install -r requirements.txt
   ```
3. Jalankan aplikasi:
   ```bash
   streamlit run app.py
   ```

## 🛡️ Keamanan
Aplikasi ini menggunakan parameter binding pada query SQL untuk mencegah SQL Injection pada fitur pencarian dan penghapusan data manual.

## 📝 Lisensi
Proyek ini dikembangkan untuk kebutuhan analisis data transportasi internal Provinsi Papua.