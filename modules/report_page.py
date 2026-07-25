import streamlit as st
import pandas as pd
import numpy as np
import google.generativeai as genai
from sqlalchemy import text
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

    where_clause = "WHERE UPPER(nama_provinsi) = :prov"

    # 1. Current Month
    q_curr = f"SELECT * FROM {table} {where_clause} AND CAST(tahun AS TEXT) = :thn AND bulan = :bln"
    df_curr = pd.read_sql(text(q_curr), engine, params={"prov": prov.upper(), "thn": str(thn), "bln": bln})

    # 2. Previous Month
    prev_bln_num = bln_num - 1 if bln_num > 1 else 12
    prev_thn = thn_int if bln_num > 1 else thn_int - 1
    prev_bln_name = INV_MONTH_MAP[prev_bln_num]
    q_prev = f"SELECT * FROM {table} {where_clause} AND CAST(tahun AS TEXT) = :prev_thn AND bulan = :prev_bln"
    df_prev = pd.read_sql(text(q_prev), engine, params={"prov": prov.upper(), "prev_thn": str(prev_thn), "prev_bln": prev_bln_name})

    # 3. YTD Current
    months_cum = [INV_MONTH_MAP[i] for i in range(1, bln_num + 1)]
    month_params = {f"m{i}": m for i, m in enumerate(months_cum)}
    months_placeholder = "(" + ", ".join(f":{k}" for k in month_params) + ")"
    q_cum_curr = f"SELECT * FROM {table} {where_clause} AND CAST(tahun AS TEXT) = :thn AND bulan IN {months_placeholder}"
    df_cum_curr = pd.read_sql(text(q_cum_curr), engine, params={"prov": prov.upper(), "thn": str(thn), **month_params})

    # 4. YTD Previous
    q_cum_prev = f"SELECT * FROM {table} {where_clause} AND CAST(tahun AS TEXT) = :prev_thn_full AND bulan IN {months_placeholder}"
    df_cum_prev = pd.read_sql(text(q_cum_prev), engine, params={"prov": prov.upper(), "prev_thn_full": str(thn_int - 1), **month_params})

    return df_curr, df_prev, df_cum_curr, df_cum_prev, prev_bln_name, prev_thn

def format_id_number(x, decimals=2):
    if pd.isna(x):
        x = 0
    try:
        s = f"{float(x):,.{decimals}f}"
    except (ValueError, TypeError):
        return str(x)
    return s.replace(",", "§").replace(".", ",").replace("§", ".")

def generate_narrative_ai(df_flat, col_target, moda, prov, bln, thn, prev_bln, prev_thn):
    """
    Menghasilkan narasi bergaya BRS BPS dengan memanggil API Gemini.
    Otomatis melakukan rotasi API Key jika terjadi limit/error.
    """
    api_keys = st.secrets["API-GEMINI-KEYS"]
    
    # Konversi dataframe ke format string/markdown agar mudah dibaca oleh AI
    data_str = df_flat.to_markdown()
    
    prompt = f"""
    Bertindaklah sebagai analis data Badan Pusat Statistik (BPS).
    Buatlah 2 paragraf ringkasan naratif dari data tabel statistik di bawah ini.
    - Paragraf pertama: Fokus pada perbandingan bulan ke bulan (Month-to-Month) pada {bln} {thn} dibandingkan dengan {prev_bln} {prev_thn}.
    - Paragraf kedua: Fokus pada perbandingan kumulatif tahun ke tahun (Year-on-Year) periode berjalan.
    
    Konteks Data:
    - Provinsi: {prov}
    - Moda Transportasi: {moda}
    - Indikator: {col_target}
    
    Tabel Data:
    {data_str}
    
    Gunakan gaya bahasa resmi, objektif, dan profesional khas BRS (Berita Resmi Statistik) BPS.
    Jangan tambahkan kalimat pembuka/penutup seperti "Tentu, ini ringkasannya" atau format tebal berlebihan. Langsung berikan teks paragrafnya.
    """

    # Rotasi API Key
    for key in api_keys:
        try:
            genai.configure(api_key=key)
            # Menggunakan gemini-1.5-flash untuk kecepatan dan efisiensi teks
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(prompt)
            
            if response.text:
                return response.text
                
        except Exception as e:
            # Jika key ini limit (ResourceExhausted) atau error lain, lanjutkan ke key berikutnya
            continue
            
    # Jika semua key dalam list gagal/limit
    return "*(Gagal memuat narasi otomatis: Semua API Key telah mencapai limit atau terjadi kesalahan pada sistem AI.)*"

def format_report_table(df_curr, df_prev, df_cum_curr, df_cum_prev, col_target, label, row_col, thn, bln, prev_bln, prev_thn, table_no=None, prov=None, moda=None):
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

    report = report.fillna(0)

    sum_prev = report[col_prev].sum()
    sum_curr = report[col_curr].sum()
    sum_cum_prev = report[col_cum_prev].sum()
    sum_cum_curr = report[col_cum_curr].sum()

    total_mtm = ((sum_curr - sum_prev) / sum_prev * 100) if sum_prev != 0 else 0
    total_yoy = ((sum_cum_curr - sum_cum_prev) / sum_cum_prev * 100) if sum_cum_prev != 0 else 0

    total_row = pd.DataFrame([{
        col_prev: sum_prev, col_curr: sum_curr, 'M-to-M (%)': total_mtm,
        col_cum_prev: sum_cum_prev, col_cum_curr: sum_cum_curr, 'Y-on-Y (%)': total_yoy
    }], index=['TOTAL'])[report.columns]

    report_flat = pd.concat([report, total_row])

    angkutan = "Angkutan Udara" if moda == "Transportasi Udara" else "Angkutan Laut"

    # Hasilkan narasi menggunakan Gemini AI dengan rotasi Key
    with st.spinner(f"Menyusun narasi AI untuk {label}..."):
        narasi_ai = generate_narrative_ai(report_flat, label, moda, prov, bln, thn, prev_bln, prev_thn)
    
    st.markdown(narasi_ai)

    if table_no is not None:
        judul = f"Tabel {table_no} Perkembangan {label} {angkutan} Dalam Negeri Provinsi {prov}, {bln} {thn}"
        st.markdown(f"**{judul}**")
    else:
        st.markdown(f"##### 📝 Indikator: {label}")

    cum_label = f"Kumulatif {label}"
    report_display = report_flat.copy()
    report_display.columns = pd.MultiIndex.from_tuples([
        (label, col_prev), (label, col_curr), (label, 'M-to-M (%)'),
        (cum_label, col_cum_prev), (cum_label, col_cum_curr), (cum_label, 'Y-on-Y (%)')
    ])

    pct_cols = [(label, 'M-to-M (%)'), (cum_label, 'Y-on-Y (%)')]

    st.dataframe(report_display.style.format(format_id_number).background_gradient(subset=pct_cols, cmap='RdYlGn'))

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
            ('penumpang_datang', 'Penumpang Datang'), ('penumpang_berangkat', 'Penumpang Berangkat'),
            ('barang_bongkar_kg', 'Barang Bongkar (Kg)'), ('barang_muat_kg', 'Barang Muat (Kg)')
        ] if moda == 'Transportasi Udara' else [
            ('dn_penumpang_turun', 'Penumpang Turun'), ('dn_penumpang_naik', 'Penumpang Naik'),
            ('dn_bongkar_barang_ton', 'Barang Bongkar (Ton)'), ('dn_muat_barang_ton', 'Barang Muat (Ton)')
        ]
        
        for i, (col, label) in enumerate(targets, start=1):
            format_report_table(df_curr, df_prev, df_cum_curr, df_cum_prev, col, label, row_col, thn, bln, prev_bln, prev_thn, table_no=i, prov=prov, moda=moda)
