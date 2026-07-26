import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import text
from modules.database import get_engine, delete_db
from modules.etl_engine import parse_transport_file
from modules.config import PEMETAAN_WILAYAH

MONTH_MAP = {'Januari': 1, 'Februari': 2, 'Maret': 3, 'April': 4, 'Mei': 5, 'Juni': 6,
             'Juli': 7, 'Agustus': 8, 'September': 9, 'Oktober': 10, 'November': 11, 'Desember': 12}


def show_series_chart_section():
    """Memberi admin akses membuat grafik time series dengan memilih
    provinsi, kabupaten/kota, dan variabel indikator secara bebas."""
    engine = get_engine()

    col1, col2, col3 = st.columns(3)
    with col1:
        moda = st.selectbox("Moda Transportasi", ["Transportasi Udara", "Transportasi Laut"], key="series_moda")
    with col2:
        provinsi = st.selectbox("Provinsi", list(PEMETAAN_WILAYAH.keys()), key="series_provinsi")
    with col3:
        kabupaten_options = ["SEMUA"] + PEMETAAN_WILAYAH[provinsi]
        kabupaten = st.selectbox("Kabupaten/Kota", kabupaten_options, key="series_kabupaten")

    var_options = {
        "Transportasi Udara": [
            'penumpang_berangkat', 'penumpang_datang', 'penumpang_transit',
            'barang_muat_kg', 'barang_bongkar_kg', 'bagasi_muat_kg', 'bagasi_bongkar_kg',
            'pos_muat_kg', 'pos_bongkar_kg', 'pesawat_berangkat', 'pesawat_datang'
        ],
        "Transportasi Laut": [
            'dn_penumpang_turun', 'dn_penumpang_naik', 'dn_bongkar_barang_ton', 'dn_muat_barang_ton',
            'ln_penumpang_turun', 'ln_penumpang_naik', 'ln_bongkar_barang_ton', 'ln_muat_barang_ton'
        ]
    }
    variabel = st.selectbox("Variabel", var_options[moda], key="series_variabel")

    if st.button("📈 Tampilkan Grafik Series", key="series_generate"):
        table = "transportasi_udara" if moda == "Transportasi Udara" else "transportasi_laut"

        query = f"SELECT * FROM {table} WHERE UPPER(nama_provinsi) = :provinsi"
        params = {"provinsi": provinsi.upper()}
        if kabupaten != "SEMUA":
            kab_clean = kabupaten.replace('KABUPATEN ', '').replace('KOTA ', '').strip()
            query += " AND (UPPER(nama_kabkota) = :kab_full OR UPPER(nama_kabkota) = :kab_clean)"
            params["kab_full"] = kabupaten.upper()
            params["kab_clean"] = kab_clean.upper()

        df = pd.read_sql(text(query), engine, params=params)

        if df.empty:
            st.warning("⚠️ Tidak ada data untuk kombinasi filter yang dipilih.")
            return

        df['month_num'] = df['bulan'].map(MONTH_MAP)
        df['tahun_int'] = df['tahun'].astype(int)
        df['periode'] = df['bulan'] + " " + df['tahun'].astype(str)

        df_plot = (
            df.groupby(['tahun_int', 'month_num', 'periode'])[variabel]
            .sum()
            .reset_index()
            .sort_values(['tahun_int', 'month_num'])
        )

        wilayah_label = provinsi if kabupaten == "SEMUA" else kabupaten

        fig = px.line(
            df_plot, x='periode', y=variabel,
            title=f"Tren {variabel.replace('_', ' ').title()} di {wilayah_label} ({moda})",
            markers=True, template='plotly_white'
        )
        fig.update_layout(xaxis_title="Periode", yaxis_title=variabel.replace('_', ' ').title())
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("📋 Lihat Data di Balik Grafik"):
            st.dataframe(
                df_plot.rename(columns={'periode': 'Periode', variabel: variabel.replace('_', ' ').title()})
                       .drop(columns=['tahun_int', 'month_num']),
                use_container_width=True
            )


def show_admin_page():
    st.title("🔐 Admin Dashboard: Authenticated Access")

    # 1. Login System
    if 'admin_logged_in' not in st.session_state:
        st.session_state['admin_logged_in'] = False

    if not st.session_state['admin_logged_in']:
        with st.form("login_form"):
            st.subheader("Login Admin")
            password = st.text_input("Masukkan Kata Sandi", type="password")
            submit_button = st.form_submit_button("Login")

            if submit_button:
                if password == "papua123":
                    st.session_state['admin_logged_in'] = True
                    st.success("Akses Diterima!")
                    st.rerun()
                else:
                    st.error("Kata sandi salah!")
        return

    # Logout Button at the top right
    if st.sidebar.button("Log Out Admin"):
        st.session_state['admin_logged_in'] = False
        st.rerun()

    st.success("🔓 Anda masuk sebagai Admin.")

    # 2. Database Maintenance Section
    with st.expander("⚠️ Zone Danger: Manage Database"):
        st.warning("Tindakan ini akan menghapus seluruh data yang ada!")
        if st.button("Reset/Delete Database"):
            if delete_db():
                st.success("Database deleted successfully!")
            else:
                st.info("Database file not found.")

    # 3. Manual Data Correction Section
    st.subheader("🛠️ Koreksi Data Manual")
    with st.expander("Buka Editor Database"):
        engine = get_engine()
        col_edit1, col_edit2, col_edit3 = st.columns(3)
        with col_edit1:
            table_edit = st.selectbox("Pilih Tabel", ["transportasi_udara", "transportasi_laut"])
        with col_edit2:
            year_edit = st.text_input("Tahun (Contoh: 2026)", "2026")
        with col_edit3:
            month_edit = st.selectbox("Bulan", ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"], key="edit_month")

        if st.button("Cari Data"):
            query = text(f"SELECT * FROM {table_edit} WHERE CAST(tahun AS TEXT) = :tahun AND bulan = :bulan")
            df_to_edit = pd.read_sql(query, engine, params={"tahun": year_edit, "bulan": month_edit})
            if df_to_edit.empty:
                st.warning("Data tidak ditemukan untuk periode tersebut.")
            else:
                st.session_state['df_to_edit'] = df_to_edit

        if 'df_to_edit' in st.session_state:
            edited_df = st.data_editor(st.session_state['df_to_edit'], use_container_width=True, num_rows="dynamic")

            if st.button("Simpan Perubahan"):
                try:
                    with engine.begin() as conn:
                        del_query = text(f"DELETE FROM {table_edit} WHERE CAST(tahun AS TEXT) = :tahun AND bulan = :bulan")
                        conn.execute(del_query, {"tahun": year_edit, "bulan": month_edit})
                        edited_df.to_sql(table_edit, conn, if_exists='append', index=False)
                    st.success("✅ Perubahan berhasil disimpan ke database!")
                    del st.session_state['df_to_edit']
                except Exception as e:
                    st.error(f"Gagal menyimpan data: {e}")

    st.divider()

    # 4. Grafik Series Section
    st.subheader("📈 Buat Grafik Series")
    st.caption("Pilih provinsi, kabupaten/kota, dan variabel untuk melihat tren data antar periode.")
    with st.expander("Buka Pembuat Grafik", expanded=True):
        show_series_chart_section()

    st.divider()

    # 5. Upload Section
    st.subheader("📥 Upload Data Baru")
    col1, col2 = st.columns(2)
    with col1:
        tahun = st.selectbox("Pilih Tahun Upload", [2024, 2025, 2026], index=1)
    with col2:
        bulan = st.selectbox("Pilih Bulan Upload", ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"])

    uploaded_files = st.file_uploader("Pilih file Excel BPS", type=['xls', 'xlsx'], accept_multiple_files=True)

    if st.button("Proses & Simpan ke Database"):
        if not uploaded_files:
            st.warning("Harap unggah file terlebih dahulu.")
        else:
            engine = get_engine()
            for uploaded_file in uploaded_files:
                try:
                    file_bytes = uploaded_file.read()
                    table_type, df_clean = parse_transport_file(file_bytes, tahun, bulan)
                    df_clean['tahun'] = str(tahun)
                    df_clean['bulan'] = bulan
                    df_clean.to_sql(table_type, engine, if_exists='append', index=False)
                    st.success(f"Berhasil memproses {uploaded_file.name} ke tabel {table_type}")
                except Exception as e:
                    st.error(f"Gagal memproses {uploaded_file.name}: {e}")