import streamlit as st
import pandas as pd
from sqlalchemy import text
from modules.database import get_engine, delete_db
from modules.etl_engine import parse_transport_file

def show_admin_page():
    st.title("📂 Admin Dashboard: Upload & Data Management")

    # 1. Database Maintenance Section
    with st.expander("⚠️ Zone Danger: Manage Database"):
        if st.button("Reset/Delete Database"):
            if delete_db():
                st.success("Database deleted successfully!")
            else:
                st.info("Database file not found.")

    # 2. Manual Data Correction Section
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
            query = f"SELECT * FROM {table_edit} WHERE CAST(tahun AS TEXT) = '{year_edit}' AND bulan = '{month_edit}'"
            df_to_edit = pd.read_sql(query, engine)
            if df_to_edit.empty:
                st.warning("Data tidak ditemukan untuk periode tersebut.")
            else:
                st.session_state['df_to_edit'] = df_to_edit

        if 'df_to_edit' in st.session_state:
            edited_df = st.data_editor(st.session_state['df_to_edit'], use_container_width=True, num_rows="dynamic")
            
            if st.button("Simpan Perubahan"):
                try:
                    with engine.begin() as conn:
                        # Hapus data lama di periode tersebut untuk menghindari duplikasi
                        conn.execute(text(f"DELETE FROM {table_edit} WHERE CAST(tahun AS TEXT) = '{year_edit}' AND bulan = '{month_edit}'"))
                        # Simpan data yang sudah diedit
                        edited_df.to_sql(table_edit, conn, if_exists='append', index=False)
                    st.success("✅ Perubahan berhasil disimpan ke database!")
                    del st.session_state['df_to_edit']
                except Exception as e:
                    st.error(f"Gagal menyimpan data: {e}")

    st.divider()

    # 3. Upload Section
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