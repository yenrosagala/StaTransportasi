import streamlit as st
import pandas as pd
import numpy as np
from modules.database import get_engine
from modules.config import PEMETAAN_WILAYAH

MONTH_MAP = {'Januari':1, 'Februari':2, 'Maret':3, 'April':4, 'Mei':5, 'Juni':6,
             'Juli':7, 'Agustus':8, 'September':9, 'Oktober':10, 'November':11, 'Desember':12}
INV_MONTH_MAP = {v: k for k, v in MONTH_MAP.items()}

def get_comparison_data(prov, thn, bln, moda):
    table = "transportasi_udara" if moda == "Transportasi Udara" else "transportasi_laut"
    bln_num = MONTH_MAP[bln]
    thn_int = int(thn)
    engine = get_engine()

    where_clause = f"WHERE UPPER(nama_provinsi) = '{prov.upper()}'"

    # 1. Current Month
    q_curr = f"SELECT * FROM {table} {where_clause} AND CAST(tahun AS TEXT) = '{thn}' AND bulan = '{bln}'"
    df_curr = pd.read_sql(q_curr, engine)

    # 2. Previous Month
    prev_bln_num = bln_num - 1 if bln_num > 1 else 12
    prev_thn = thn_int if bln_num > 1 else thn_int - 1
    prev_bln_name = INV_MONTH_MAP[prev_bln_num]
    q_prev = f"SELECT * FROM {table} {where_clause} AND CAST(tahun AS TEXT) = '{prev_thn}' AND bulan = '{prev_bln_name}'"
    df_prev = pd.read_sql(q_prev, engine)

    # 3. YTD Current
    months_cum = [INV_MONTH_MAP[i] for i in range(1, bln_num + 1)]
    months_tuple = str(tuple(months_cum)) if len(months_cum) > 1 else f"('{months_cum[0]}')"
    q_cum_curr = f"SELECT * FROM {table} {where_clause} AND CAST(tahun AS TEXT) = '{thn}' AND bulan IN {months_tuple}"
    df_cum_curr = pd.read_sql(q_cum_curr, engine)

    # 4. YTD Previous
    q_cum_prev = f"SELECT * FROM {table} {where_clause} AND CAST(tahun AS TEXT) = '{thn_int-1}' AND bulan IN {months_tuple}"
    df_cum_prev = pd.read_sql(q_cum_prev, engine)

    return df_curr, df_prev, df_cum_curr, df_cum_prev, prev_bln_name, prev_thn

def format_report_table(df_curr, df_prev, df_cum_curr, df_cum_prev, col_target, label, row_col, thn, bln, prev_bln, prev_thn):
    curr_grp = df_curr.groupby(row_col)[col_target].sum()
    prev_grp = df_prev.groupby(row_col)[col_target].sum()
    cum_curr_grp = df_cum_curr.groupby(row_col)[col_target].sum()
    cum_prev_grp = df_cum_prev.groupby(row_col)[col_target].sum()

    report = pd.DataFrame(index=curr_grp.index)
    col_curr, col_prev = f"{bln} {thn}", f"{prev_bln} {prev_thn}"
    col_cum_curr, col_cum_prev = f"Jan-{bln} {thn}", f"Jan-{bln} {int(thn)-1}"

    report[col_prev] = prev_grp
    report[col_curr] = curr_grp
    report['M-to-M (%)'] = ((report[col_curr] - report[col_prev]) / report[col_prev] * 100).replace([np.inf, -np.inf], np.nan).fillna(0)

    report[col_cum_prev] = cum_prev_grp
    report[col_cum_curr] = cum_curr_grp
    report['Y-on-Y (%)'] = ((report[col_cum_curr] - report[col_cum_prev]) / report[col_cum_prev] * 100).replace([np.inf, -np.inf], np.nan).fillna(0)

    st.markdown(f"##### 📝 Indikator: {label}")
    st.dataframe(report.fillna(0).style.format("{:,.2f}").background_gradient(subset=['M-to-M (%)', 'Y-on-Y (%)'], cmap='RdYlGn'))

def show_report_page():
    st.title("📋 Laporan Komparatif Strategis")
    
    c1, c2, c3, c4 = st.columns(4)
    with c1: prov = st.selectbox("Provinsi", list(PEMETAAN_WILAYAH.keys()))
    with c2: thn = st.selectbox("Tahun", ['2024', '2025', '2026'], index=1)
    with c3: bln = st.selectbox("Bulan", list(MONTH_MAP.keys()))
    with c4: moda = st.selectbox("Moda", ["Transportasi Udara", "Transportasi Laut"])

    if st.button("Generate Laporan"):
        df_curr, df_prev, df_cum_curr, df_cum_prev, prev_bln, prev_thn = get_comparison_data(prov, thn, bln, moda)
        
        if df_curr.empty:
            st.warning("Tidak ada data untuk periode terpilih.")
            return

        row_col = 'nama_bandara' if moda == 'Transportasi Udara' else 'nama_kabkota'
        targets = [
            ('penumpang_datang', 'Penumpang Datang'), ('penumpang_berangkat', 'Penumpang Berangkat')
        ] if moda == 'Transportasi Udara' else [
            ('dn_penumpang_turun', 'Penumpang Turun'), ('dn_penumpang_naik', 'Penumpang Naik')
        ]
        
        for col, label in targets:
            format_report_table(df_curr, df_prev, df_cum_curr, df_cum_prev, col, label, row_col, thn, bln, prev_bln, prev_thn)