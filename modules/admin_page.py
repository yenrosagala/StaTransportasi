import streamlit as st
import pandas as pd
from sqlalchemy import text
from modules.database import get_engine, delete_db
from modules.etl_engine import parse_transport_file

def show_admin_page():
    st.title("📂 Admin Dashboard: Upload & Database Management")
    
    # Database Reset Section
    with st.expander("⚠️ Zone Danger: Manage Database"):
        st.warning("Tindakan ini akan menghapus seluruh data secara permanen dan tidak dapat dibatalkan.")
        confirm = st.checkbox("Saya paham risikonya dan ingin menghapus database ini.")
        if st.button("Reset/Delete Database", disabled=not confirm):
            if delete_db():
                st.success("Database deleted successfully!")
            else:
                st.info("Database file not found.")

    # Upload Section
    st.subheader("Upload New Data")
    col1, col2 = st.columns(2)
    with col1:
        tahun = st.selectbox("Pilih Tahun", [2024, 2025, 2026], index=1)
    with col2:
        bulan = st.selectbox("Pilih Bulan", ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"])

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
                    
                    # Metadata addition
                    df_clean['tahun'] = str(tahun)
                    df_clean['bulan'] = bulan
                    
                    # Write to SQL
                    df_clean.to_sql(table_type, engine, if_exists='append', index=False)
                    st.success(f"Berhasil memproses {uploaded_file.name} ke tabel {table_type}")
                    st.dataframe(df_clean.head(3))
                except Exception as e:
                    st.error(f"Gagal memproses {uploaded_file.name}: {e}")