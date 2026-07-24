import streamlit as st
import pandas as pd
import numpy as np
import google.generativeai as genai
from modules.database import get_engine
from modules.config import PEMETAAN_WILAYAH

MONTH_MAP = {'Januari':1, 'Februari':2, 'Maret':3, 'April':4, 'Mei':5, 'Juni':6,
             'Juli':7, 'Agustus':8, 'September':9, 'Oktober':10, 'November':11, 'Desember':12}
INV_MONTH_MAP = {v: k for k, v in MONTH_MAP.items()}

def generate_ai_caption(label, df_report):
    try:
        keys_raw = st.secrets['GEMINI_API_KEYS']
        if isinstance(keys_raw, str):
            api_keys = [k.strip() for k in keys_raw.split(',')]
        else:
            api_keys = list(keys_raw)
    except:
        return "Konfigurasi GEMINI_API_KEYS tidak ditemukan."

    data_str = df_report.to_string()
    prompt = f"""Anda berperan sebagai penulis publikasi resmi Badan Pusat Statistik (BPS).

Berdasarkan tabel data '{label}' berikut ini, buatlah satu paragraf ringkasan statistik yang memenuhi ketentuan:
1. Menjelaskan kondisi utama pada bulan berjalan dibandingkan bulan sebelumnya (M-to-M);
2. Menjelaskan kondisi kumulatif Januari-bulan berjalan dibandingkan periode yang sama tahun sebelumnya (Y-on-Y);
3. Panjang ringkasan sekitar 80-120 kata dengan gaya formal BPS.

Data Tabel:\n{data_str}"""

    for key in api_keys:
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(prompt)
            return response.text
        except:
            continue
    return "Maaf, terjadi kesalahan teknis pada AI."

def indonesian_number_format(x):
    if pd.isna(x) or x == "Undefined": return x
    try:
        if isinstance(x, (int, float)):
            return "{:,.2f}".format(x).replace(",", "X").replace(".", ",").replace("X", ".")
        return x
    except:
        return x

def get_comparison_data(prov, thn, bln, moda):
    table = "transportasi_udara" if moda == "Transportasi Udara" else "transportasi_laut"
    bln_num = MONTH_MAP[bln]
    thn_int = int(thn)
    engine = get_engine()
    where_clause = f"WHERE UPPER(nama_provinsi) = '{prov.upper()}'"
    q_curr = f"SELECT * FROM {table} {where_clause} AND CAST(tahun AS TEXT) = '{thn}' AND bulan = '{bln}'"
    df_curr = pd.read_sql(q_curr, engine)
    prev_bln_num = bln_num - 1 if bln_num > 1 else 12
    prev_thn = thn_int if bln_num > 1 else thn_int - 1
    prev_bln_name = INV_MONTH_MAP[prev_bln_num]
    q_prev = f"SELECT * FROM {table} {where_clause} AND CAST(tahun AS TEXT) = '{prev_thn}' AND bulan = '{prev_bln_name}'"
    df_prev = pd.read_sql(q_prev, engine)
    months_cum = [INV_MONTH_MAP[i] for i in range(1, bln_num + 1)]
    months_tuple = str(tuple(months_cum)) if len(months_cum) > 1 else f"('{months_cum[0]}')"
    q_cum_curr = f"SELECT * FROM {table} {where_clause} AND CAST(tahun AS TEXT) = '{thn}' AND bulan IN {months_tuple}"
    df_cum_curr = pd.read_sql(q_cum_curr, engine)
    q_cum_prev = f"SELECT * FROM {table} {where_clause} AND CAST(tahun AS TEXT) = '{thn_int-1}' AND bulan IN {months_tuple}"
    df_cum_prev = pd.read_sql(q_cum_prev, engine)
    return df_curr, df_prev, df_cum_curr, df_cum_prev, prev_bln_name, prev_thn

def format_report_table(
    df_curr,
    df_prev,
    df_cum_curr,
    df_cum_prev,
    col_target,
    label,
    row_col,
    thn,
    bln,
    prev_bln,
    prev_thn,
):
    curr_grp = df_curr.groupby(row_col)[col_target].sum()
    prev_grp = df_prev.groupby(row_col)[col_target].sum()
    cum_curr_grp = df_cum_curr.groupby(row_col)[col_target].sum()
    cum_prev_grp = df_cum_prev.groupby(row_col)[col_target].sum()

    report = pd.DataFrame(index=curr_grp.index)
    col_curr, col_prev = f"{bln} {thn}", f"{prev_bln} {prev_thn}"
    col_cum_curr, col_cum_prev = f"Jan-{bln} {thn}", f"Jan-{bln} {int(thn)-1}"

    # 1. Masukkan data dasar ke DataFrame
    report[col_prev] = prev_grp
    report[col_curr] = curr_grp
    report[col_cum_prev] = cum_prev_grp
    report[col_cum_curr] = cum_curr_grp

    # 2. Tambahkan baris total
    total_row = pd.DataFrame(
        {
            col_prev: [report[col_prev].sum()],
            col_curr: [report[col_curr].sum()],
            col_cum_prev: [report[col_cum_prev].sum()],
            col_cum_curr: [report[col_cum_curr].sum()],
        },
        index=["JUMLAH TOTAL"],
    )
    report = pd.concat([report, total_row])

    # 3. Hitung M-to-M (%) dan Y-on-Y (%)
    report["M-to-M (%)"] = (
        (report[col_curr] - report[col_prev]) / report[col_prev] * 100
    ).replace([np.inf, -np.inf], np.nan).fillna(0)
    report["Y-on-Y (%)"] = (
        (report[col_cum_curr] - report[col_cum_prev])
        / report[col_cum_prev]
        * 100
    ).replace([np.inf, -np.inf], np.nan).fillna(0)

    # =========================================================================
    # RE-ORDER KOLOM (M-to-M diletakkan di antara col_curr dan col_cum_prev)
    # =========================================================================
    ordered_columns = [
        col_prev,
        col_curr,
        "M-to-M (%)",  # <-- M-to-M diletakkan di sini
        col_cum_prev,
        col_cum_curr,
        "Y-on-Y (%)",
    ]
    report = report[ordered_columns]

    # Render Tabel
    st.markdown(f"##### 📝 Indikator: {label}")
    st.dataframe(
        report.fillna(0)
        .style.format(indonesian_number_format)
        .background_gradient(subset=["M-to-M (%)", "Y-on-Y (%)"], cmap="RdYlGn")
    )

    with st.expander(f"✨ AI Insight: {label}"):
        caption = generate_ai_caption(label, report)
        st.write(caption)
