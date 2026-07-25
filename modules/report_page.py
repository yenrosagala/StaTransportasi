import streamlit as st
import pandas as pd
import numpy as np
import random
import google.genai as genai
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

    q_curr = f"SELECT * FROM {table} {where_clause} AND CAST(tahun AS TEXT) = :thn AND bulan = :bln"
    df_curr = pd.read_sql(text(q_curr), engine, params={"prov": prov.upper(), "thn": str(thn), "bln": bln})

    prev_bln_num = bln_num - 1 if bln_num > 1 else 12
    prev_thn = thn_int if bln_num > 1 else thn_int - 1
    prev_bln_name = INV_MONTH_MAP[prev_bln_num]
    q_prev = f"SELECT * FROM {table} {where_clause} AND CAST(tahun AS TEXT) = :prev_thn AND bulan = :prev_bln"
    df_prev = pd.read_sql(text(q_prev), engine, params={"prov": prov.upper(), "prev_thn": str(prev_thn), "prev_bln": prev_bln_name})

    months_cum = [INV_MONTH_MAP[i] for i in range(1, bln_num + 1)]
    month_params = {f"m{i}": m for i, m in enumerate(months_cum)}
    months_placeholder = "(" + ", ".join(f":{k}" for k in month_params) + ")"
    q_cum_curr = f"SELECT * FROM {table} {where_clause} AND CAST(tahun AS TEXT) = :thn AND bulan IN {months_placeholder}"
    df_cum_curr = pd.read_sql(text(q_cum_curr), engine, params={"prov": prov.upper(), "thn": str(thn), **month_params})

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

NARRATIVE_META = {
    'penumpang_datang':     {'subject': 'Jumlah penumpang yang datang', 'satuan': 'orang', 'is_penumpang': True},
    'penumpang_berangkat':  {'subject': 'Jumlah penumpang yang berangkat', 'satuan': 'orang', 'is_penumpang': True},
    'barang_bongkar_kg':    {'subject': 'Volume barang yang dibongkar', 'satuan': 'kg', 'is_penumpang': False},
    'barang_muat_kg':       {'subject': 'Volume barang yang dimuat', 'satuan': 'kg', 'is_penumpang': False},
    'dn_penumpang_turun':   {'subject': 'Jumlah penumpang yang datang', 'satuan': 'orang', 'is_penumpang': True},
    'dn_penumpang_naik':    {'subject': 'Jumlah penumpang yang berangkat', 'satuan': 'orang', 'is_penumpang': True},
    'dn_bongkar_barang_ton':{'subject': 'Volume barang yang dibongkar', 'satuan': 'ton', 'is_penumpang': False},
    'dn_muat_barang_ton':   {'subject': 'Volume barang yang dimuat', 'satuan': 'ton', 'is_penumpang': False},
}

def _arah_dinamis(pct):
    if pct > 0:
        return random.choice(["mengalami lonjakan", "naik", "meningkat", "mengalami pertumbuhan"])
    elif pct < 0:
        return random.choice(["terkoreksi", "turun", "mengalami penurunan", "menyusut"])
    return "stabil"

def generate_narrative_ai(df_flat, col_target, moda, prov, bln, thn, prev_bln, prev_thn):
    if "API-GEMINI-KEYS" not in st.secrets:
        return None

    api_keys = st.secrets["API-GEMINI-KEYS"]
    data_str = df_flat.to_markdown()
    
    prompt = f"""
    Bertindaklah sebagai analis data senior di Badan Pusat Statistik (BPS) yang profesional namun komunikatif. 
    Buatlah tepat 2 paragraf ringkasan naratif dari data tabel statistik di bawah ini. Pisahkan paragraf pertama dan kedua dengan baris kosong ganda (\\n\\n). Adaptasi gaya bahasa Berita Resmi Statistik (BRS), namun buatlah kalimatnya lebih mengalir, natural, dan tidak kaku. 
    
    Variasikan pilihan kata (jangan monoton menggunakan frasa "tercatat sebanyak"). Anda bisa menggunakan kata ganti seperti "mencapai", "berada di angka", "menyentuh", "mengalami lonjakan", atau "terkoreksi".

    Struktur Narasi yang Wajib Diikuti:
    1. Paragraf Pertama (Bulan ke Bulan / M-to-M):
       - Bandingkan total indikator pada {bln} {thn} dengan {prev_bln} {prev_thn}.
       - Jika merinci ke tingkat wilayah (pelabuhan/bandara), cukup soroti wilayah dengan peningkatan tertinggi dan/atau penurunan terdalam agar efisien.
    
    2. Paragraf Kedua (Kumulatif Tahun ke Tahun / Y-on-Y):
       - Bandingkan total kumulatif dari Januari hingga {bln} {thn} dengan periode yang sama di tahun sebelumnya.
       - Berikan rincian singkat wilayah mana yang memiliki lonjakan kumulatif tertinggi atau penurunan terdalam.

    Konteks Data:
    - Provinsi: {prov}
    - Moda Transportasi: {moda}
    - Indikator: {col_target}
    
    Tabel Data:
    {data_str}
    
    Aturan Tambahan:
    - Langsung berikan output teks saja yang berisi 2 paragraf, tanpa kalimat pengantar/penutup.
    - Format angka sesuai kaidah Bahasa Indonesia (titik untuk ribuan, koma untuk desimal).
    """

    for key in api_keys:
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(prompt)
            if response.text:
                return response.text
        except Exception as e:
            continue
            
    return None

def generate_narrative_fallback(report_flat, col_target, moda, region_label, bln, thn, prev_bln, prev_thn,
                                col_prev, col_curr, col_cum_prev, col_cum_curr):
    meta = NARRATIVE_META.get(col_target, {'subject': 'Jumlah', 'satuan': '', 'is_penumpang': False})
    angkutan_kecil = 'udara' if moda == 'Transportasi Udara' else 'laut'
    val_decimals = 0 if meta['satuan'] == 'orang' else 2
    fmt = lambda v: format_id_number(v, decimals=val_decimals)
    fmt_pct = lambda v: format_id_number(v, decimals=2)

    subject = meta['subject']
    if meta['is_penumpang']:
        subject += f" menggunakan angkutan {angkutan_kecil} dalam negeri"

    total = report_flat.loc['TOTAL']
    data = report_flat.drop(index='TOTAL')

    total_curr, total_prev, total_mtm = total[col_curr], total[col_prev], total['M-to-M (%)']
    total_cum_curr, total_cum_prev, total_yoy = total[col_cum_curr], total[col_cum_prev], total['Y-on-Y (%)']

    verb_1 = random.choice(["mencapai", "menyentuh angka", "berada di level", "tercatat sebanyak"])
    verb_2 = random.choice(["berada di angka", "sebanyak", "tercatat sejumlah"])
    arah_mtm = _arah_dinamis(total_mtm)

    para1 = (
        f"{subject} pada bulan {bln} {thn} {verb_1} {fmt(total_curr)} {meta['satuan']}. "
        f"Angka ini {arah_mtm} sebesar {fmt_pct(abs(total_mtm))} persen dibandingkan periode {prev_bln} {prev_thn} "
        f"yang {verb_2} {fmt(total_prev)} {meta['satuan']}."
    )

    if len(data) > 0:
        if len(data) <= 3:
            rincian = [
                f"{region_label} {r} {random.choice(['berada di posisi', 'mencapai'])} {fmt(data.loc[r, col_curr])} {meta['satuan']} "
                f"({_arah_dinamis(data.loc[r, 'M-to-M (%)'])} {fmt_pct(abs(data.loc[r, 'M-to-M (%)']))} persen)"
                for r in data.index
            ]
            para1 += f" Apabila dilihat lebih rinci pada tingkat {region_label.lower()}, " + "; dan ".join(rincian) + "."
        else:
            top_r = data['M-to-M (%)'].idxmax()
            bot_r = data['M-to-M (%)'].idxmin()
            para1 += (
                f" Jika dirinci per {region_label.lower()}, lonjakan tertinggi dialami oleh {region_label} {top_r} "
                f"dengan kenaikan {fmt_pct(data.loc[top_r, 'M-to-M (%)'])} persen. Sebaliknya, penurunan terdalam terjadi di "
                f"{region_label} {bot_r} yang terkoreksi hingga {fmt_pct(abs(data.loc[bot_r, 'M-to-M (%)']))} persen."
            )

    verb_3 = random.choice(["terakumulasi menjadi", "berhasil mencapai", "terkumpul sebanyak"])
    arah_yoy = _arah_dinamis(total_yoy)

    para2 = (
        f"Sementara itu, performa kumulatif dari Januari hingga {bln} {thn} {verb_3} {fmt(total_cum_curr)} "
        f"{meta['satuan']}. Capaian tersebut {arah_yoy} {fmt_pct(abs(total_yoy))} persen jika disandingkan dengan periode "
        f"Januari-{bln} {int(thn)-1} yang {verb_2} {fmt(total_cum_prev)} {meta['satuan']}."
    )

    if len(data) > 0:
        if len(data) > 3:
            top_r2 = data['Y-on-Y (%)'].idxmax()
            bot_r2 = data['Y-on-Y (%)'].idxmin()
            para2 += (
                f" Secara kumulatif, {region_label} {top_r2} mencatatkan pertumbuhan tertinggi sebesar "
                f"{fmt_pct(data.loc[top_r2, 'Y-on-Y (%)'])} persen. Di sisi lain, {region_label} {bot_r2} "
                f"mengalami penyusutan paling dalam sebesar {fmt_pct(abs(data.loc[bot_r2, 'Y-on-Y (%)']))} persen."
            )

    return para1, para2

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
    report['M-to-M (%)'] = ((report[col_curr] - report[col_prev]) / report[col_prev] * 100).replace([np.inf, -np.inf], np.nan).fillna(None)2

    report[col_cum_prev] = cum_prev_grp
    report[col_cum_curr] = cum_curr_grp
    report['Y-on-Y (%)'] = ((report[col_cum_curr] - report[col_cum_prev]) / report[col_cum_prev] * 100).replace([np.inf, -np.inf], np.nan).fillna(None)

    report = report.fillna(0)

    sum_prev = report[col_prev].sum()
    sum_curr = report[col_curr].sum()
    sum_cum_prev = report[col_cum_prev].sum()
    sum_cum_curr = report[col_cum_curr].sum()

    total_mtm = ((sum_curr - sum_prev) / sum_prev * 100) if sum_prev != 0 else np.nan
    total_yoy = ((sum_cum_curr - sum_cum_prev) / sum_cum_prev * 100) if sum_cum_prev != 0 else np.nan

    total_row = pd.DataFrame([{
        col_prev: sum_prev, col_curr: sum_curr, 'M-to-M (%)': total_mtm,
        col_cum_prev: sum_cum_prev, col_cum_curr: sum_cum_curr, 'Y-on-Y (%)': total_yoy
    }], index=['TOTAL'])[report.columns]

    report_flat = pd.concat([report, total_row])

    angkutan = "Angkutan Udara" if moda == "Transportasi Udara" else "Angkutan Laut"
    region_label = "Bandara" if moda == "Transportasi Udara" else "Kabupaten/Kota"

    # Penampung paragraf agar posisinya bisa diatur bebas
    para1_text = ""
    para2_text = ""

    with st.spinner(f"Menyusun narasi untuk indikator {label}..."):
        narasi_ai = generate_narrative_ai(report_flat, label, moda, prov, bln, thn, prev_bln, prev_thn)
        
    if narasi_ai is None:
        p1, p2 = generate_narrative_fallback(
            report_flat, col_target, moda, region_label, bln, thn, prev_bln, prev_thn,
            col_prev, col_curr, col_cum_prev, col_cum_curr
        )
        para1_text = f"*(Narasi Dihasilkan oleh Sistem)*\n\n{p1}"
        para2_text = p2
    else:
        # Memecah respons AI menjadi dua paragraf berdasarkan baris baru
        parts = [p.strip() for p in narasi_ai.split('\n\n') if p.strip()]
        if len(parts) >= 2:
            para1_text = f"*(Narasi Dihasilkan oleh Gemini AI)*\n\n{parts[0]}"
            para2_text = "\n\n".join(parts[1:])
        elif len(parts) == 1:
            para1_text = f"*(Narasi Dihasilkan oleh Gemini AI)*\n\n{parts[0]}"
            para2_text = ""

    # ---- MULAI MERENDER KOMPONEN UI ----

    # 1. Paragraf Pertama (Bulan ke Bulan) diletakkan SEBELUM judul
    if para1_text:
        st.markdown(para1_text)

    # 2. Judul Tabel
    st.write("") # Memberi spasi kecil
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

    # 3. Merender Tabel
    st.dataframe(report_display.style.format(format_id_number).background_gradient(subset=pct_cols, cmap='RdYlGn'))

    # 4. Paragraf Kedua (Kumulatif Y-on-Y) diletakkan SETELAH tabel
    if para2_text:
        st.markdown(para2_text)

    st.markdown("---") # Memberi garis batas sebelum indikator berikutnya

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
