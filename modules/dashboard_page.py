import streamlit as st
import pandas as pd
import plotly.express as px
from modules.database import get_engine
from modules.config import PEMETAAN_WILAYAH

def show_dashboard_page():
    st.title("📊 Dashboard Visualisasi Transportasi")
    
    # Filters
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
    variabel = st.selectbox("Indikator", var_options[moda])

    # Query Data
    table = "transportasi_udara" if moda == "Transportasi Udara" else "transportasi_laut"
    engine = get_engine()
    
    query = f"SELECT * FROM {table} WHERE UPPER(nama_provinsi) = '{provinsi.upper()}'"
    if kabupaten != "SEMUA":
        kab_clean = kabupaten.replace('KABUPATEN ', '').replace('KOTA ', '').strip()
        query += f" AND (UPPER(nama_kabkota) = '{kabupaten.upper()}' OR UPPER(nama_kabkota) = '{kab_clean.upper()}')"

    df = pd.read_sql(query, engine)

    if df.empty:
        st.info("Belum ada data tersedia untuk filter ini.")
        return

    # Sorting for time series
    month_map = {'Januari':1, 'Februari':2, 'Maret':3, 'April':4, 'Mei':5, 'Juni':6, 
                 'Juli':7, 'Agustus':8, 'September':9, 'Oktober':10, 'November':11, 'Desember':12}
    df['month_num'] = df['bulan'].map(month_map)
    df['tahun_int'] = df['tahun'].astype(int)
    df = df.sort_values(['tahun_int', 'month_num'])
    df['periode'] = df['bulan'] + " " + df['tahun'].astype(str)

    # Aggregation
    df_plot = df.groupby(['tahun', 'bulan', 'periode', 'month_num', 'tahun_int'])[variabel].sum().reset_index()
    df_plot = df_plot.sort_values(['tahun_int', 'month_num'])

    # Visualization
    fig = px.line(df_plot, x='periode', y=variabel, 
                  title=f"Tren {variabel.replace('_',' ').title()} di {provinsi}",
                  markers=True, template='plotly_white')
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Data Detail")
    st.dataframe(df.drop(columns=['month_num', 'tahun_int']))