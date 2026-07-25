import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import text
from modules.database import get_engine
from modules.config import PEMETAAN_WILAYAH

def show_dashboard_page():
    st.title("📊 Dashboard Visualisasi Transportasi")
    
    # --- FILTER DALAM EXPANDER ---
    with st.expander("⚙️ Filter Data & Pengaturan Tampilan", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            moda = st.selectbox("Moda Transportasi", ["Transportasi Udara", "Transportasi Laut"])
        with col2:
            provinsi = st.selectbox("Provinsi", list(PEMETAAN_WILAYAH.keys()))
        with col3:
            kabupaten_options = ["SEMUA"] + PEMETAAN_WILAYAH[provinsi]
            kabupaten = st.selectbox("Kabupaten/Kota", kabupaten_options)

        # Variable Mapping
        var_options = {
            "Transportasi Udara": ['penumpang_berangkat', 'penumpang_datang', 'barang_muat_kg', 'barang_bongkar_kg', 'pesawat_berangkat', 'pesawat_datang'],
            "Transportasi Laut": ['dn_penumpang_turun', 'dn_penumpang_naik', 'dn_bongkar_barang_ton', 'dn_muat_barang_ton']
        }
        variabel = st.selectbox("Indikator Utama", var_options[moda])

    # --- QUERY DATA BERDASARKAN FILTER ---
    table = "transportasi_udara" if moda == "Transportasi Udara" else "transportasi_laut"
    engine = get_engine()
    
    query = f"SELECT * FROM {table} WHERE UPPER(nama_provinsi) = :provinsi"
    params = {"provinsi": provinsi.upper()}
    if kabupaten != "SEMUA":
        kab_clean = kabupaten.replace('KABUPATEN ', '').replace('KOTA ', '').strip()
        query += " AND (UPPER(nama_kabkota) = :kab_full OR UPPER(nama_kabkota) = :kab_clean)"
        params["kab_full"] = kabupaten.upper()
        params["kab_clean"] = kab_clean.upper()

    df = pd.read_sql(text(query), engine, params=params)

    if df.empty:
        st.warning("⚠️ Belum ada data tersedia untuk filter yang dipilih.")
        return

    # --- SORTING & PERIODE ---
    month_map = {'Januari':1, 'Februari':2, 'Maret':3, 'April':4, 'Mei':5, 'Juni':6, 
                 'Juli':7, 'Agustus':8, 'September':9, 'Oktober':10, 'November':11, 'Desember':12}
    df['month_num'] = df['bulan'].map(month_map)
    df['tahun_int'] = df['tahun'].astype(int)
    df = df.sort_values(['tahun_int', 'month_num'])
    df['periode'] = df['bulan'] + " " + df['tahun'].astype(str)

    # --- KPI METRICS (MENYESUAIKAN FILTER) ---
    st.markdown(f"### 📌 Ringkasan KPI ({kabupaten if kabupaten != 'SEMUA' else provinsi})")
    kpi1, kpi2, kpi3 = st.columns(3)
    
    with kpi1:
        # Menghitung jumlah titik lokasi/fasilitas unik berdasarkan filter aktif
        kolom_lokasi = 'nama_bandara' if moda == "Transportasi Udara" else 'nama_pelabuhan'
        if kolom_lokasi in df.columns:
            jml_titik = df[kolom_lokasi].nunique()
            label_titik = f"Jumlah {moda.split()[1]}"
        else:
            jml_titik = df['nama_kabkota'].nunique()
            label_titik = "Jumlah Cakupan Kab/Kota"
        st.metric(label=label_titik, value=f"{jml_titik:,}")

    with kpi2:
        if moda == "Transportasi Udara":
            total_penumpang = df['penumpang_berangkat'].sum() + df['penumpang_datang'].sum()
            label_penumpang = "Total Penumpang (Berangkat + Datang)"
        else:
            total_penumpang = df['dn_penumpang_naik'].sum() + df['dn_penumpang_turun'].sum()
            label_penumpang = "Total Penumpang (Naik + Turun)"
        st.metric(label=label_penumpang, value=f"{total_penumpang:,.0f}")

    with kpi3:
        if moda == "Transportasi Udara":
            total_barang = df['barang_muat_kg'].sum() + df['barang_bongkar_kg'].sum()
            label_barang = "Total Volume Barang (Kg)"
        else:
            total_barang = df['dn_muat_barang_ton'].sum() + df['dn_bongkar_barang_ton'].sum()
            label_barang = "Total Volume Barang (Ton)"
        st.metric(label=label_barang, value=f"{total_barang:,.2f}")

    st.markdown("---")

    # --- AGGREGATION & VISUALIZATION ---
    df_plot = df.groupby(['tahun', 'bulan', 'periode', 'month_num', 'tahun_int'])[variabel].sum().reset_index()
    df_plot = df_plot.sort_values(['tahun_int', 'month_num'])

    fig = px.line(df_plot, x='periode', y=variabel, 
                  title=f"Tren {variabel.replace('_',' ').title()} di {provinsi if kabupaten == 'SEMUA' else kabupaten}",
                  markers=True, template='plotly_white')
    st.plotly_chart(fig, use_container_width=True)

    # --- DATA DETAIL ---
    st.subheader("📋 Data Detail")
    st.dataframe(df.drop(columns=['month_num', 'tahun_int']), use_container_width=True)
