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

# ==============================================================================
# KONFIGURASI HIERARKI BRS & NORMALISASI
# ==============================================================================
HIERARKI_BRS = {
    "Papua Tengah": {
        "Transportasi Udara": {
            "utama": ['Douw Aturure', 'Mozes Kilangin'],
            "lainnya": ['Enarotali', 'Zugapa Bilorai', 'Moanamani', 'Sinak', 'Ilaga', 'Beoga', 'Mulia'],
            "label_subtotal": "Sub Total",
            "label_total": "Total",
            "teks_separator": "Bandara Lainnya"
        },
        "Transportasi Laut": {
            "utama": ['Mimika', 'Nabire'],
            "lainnya": [],
            "label_subtotal": "", 
            "label_total": "Total",
            "teks_separator": ""
        }
    },
    "Papua": {
        "Transportasi Laut": {
            "utama": ['Jayapura', 'Biak'],
            "lainnya": ['Sarmi', 'Serui', 'Waren', 'Kasonaweja'],
            "label_subtotal": "Subtotal",
            "label_total": "Total",
            "teks_separator": "Pelabuhan Lainnya"
        },
        "Transportasi Udara": {
            "utama": ['Sentani', 'Frans Kaisiepo'],
            "lainnya": ['Mararena', 'Stevanus Rumbewas', 'Kasonaweja'],
            "label_subtotal": "Subtotal",
            "label_total": "Total",
            "teks_separator": "Bandara Lainnya"
        }
    },
    "Papua Pegunungan": {
        "Transportasi Udara": {
            "utama": ['Wamena', 'Dekai', 'Batom'],
            "lainnya": ['Oksibil', 'Karubaga'],
            "label_subtotal": "Total",
            "label_total": "Total Keseluruhan",
            "teks_separator": "Bandara Lainnya"
        }
    },
    "Papua Selatan": {
        "Transportasi Laut": {
            "utama": ['Merauke'],
            "lainnya": ['Bade', 'Habesilam', 'Agats', 'Atsy'],
            "label_subtotal": "Jumlah",
            "label_total": "Total",
            "teks_separator": "Pelabuhan lainnya"
        },
        "Transportasi Udara": {
            "utama": ['Mopah'],
            "lainnya": ['Okaba', 'Tanah Merah', 'Bomakia', 'Mindiptanah', 'Kepi', 'Bade', 'Ewer', 'Kamur'],
            "label_subtotal": "Jumlah",
            "label_total": "Total",
            "teks_separator": "Bandara lainnya"
        }
    }
}

def normalisasi_entitas(nama):
    """
    Membersihkan kata 'Bandara' dari database agar cocok dengan list HIERARKI_BRS 
    yang ditulis tanpa awalan kata 'Bandara'.
    """
    if not isinstance(nama, str):
        return str(nama)
    
    clean_name = nama.strip()
    if clean_name.lower().startswith("bandara "):
        clean_name = clean_name[8:].strip()
        
    mapping_khusus = {
        "Nabire": "Douw Aturure"
    }
    
    return mapping_khusus.get(clean_name, clean_name)

def build_brs_display_table(report_flat, prov, moda):
    """
    Menyusun ulang dataframe menjadi bentuk hierarki BRS (ada Subtotal & Total)
    """
    df = report_flat.copy()
    
    if 'TOTAL' in df.index:
        total_row = df.loc[['TOTAL']]
        df = df.drop(index='TOTAL')
    else:
        total_row = pd.DataFrame()
        
    df = df.reset_index()
    row_col = df.columns[0]
    
    # Terapkan Normalisasi Nama
    df[row_col] = df[row_col].apply(normalisasi_entitas)
    df = df.groupby(row_col).sum(min_count=1).reset_index() 
    
    raw_cols = [c for c in df.columns if '(%)' not in c and c != row_col]
    potongan = []
    
    if prov in HIERARKI_BRS and moda in HIERARKI_BRS[prov]:
        config = HIERARKI_BRS[prov][moda]
        
        # Kelompok Utama
        df_utama = df[df[row_col].isin(config["utama"])].copy()
        if not df_utama.empty:
            df_utama[row_col] = pd.Categorical(df_utama[row_col], categories=config["utama"], ordered=True)
            df_utama = df_utama.sort_values(row_col)
            potongan.append(df_utama)
            
        # Kelompok Lainnya
        if len(config["lainnya"]) > 0 and not df_utama.empty:
            sub_utama = pd.DataFrame(df_utama[raw_cols].sum()).T
            sub_utama[row_col] = config["label_subtotal"]
            
            separator = pd.DataFrame([{row_col: config["teks_separator"]}])
            for c in df.columns: 
                if c != row_col: separator[c] = np.nan
            
            df_lain = df[df[row_col].isin(config["lainnya"])].copy()
            if not df_lain.empty:
                df_lain[row_col] = pd.Categorical(df_lain[row_col], categories=config["lainnya"], ordered=True)
                df_lain = df_lain.sort_values(row_col)
                
                sub_lain = pd.DataFrame(df_lain[raw_cols].sum()).T
                sub_lain[row_col] = config["label_subtotal"] + " " 
                
                potongan.extend([sub_utama, separator, df_lain, sub_lain])
    else:
        potongan.append(df)
        
    if not total_row.empty:
        t_label = HIERARKI_BRS.get(prov, {}).get(moda, {}).get("label_total", "TOTAL")
        total_row = total_row.reset_index()
        total_row.rename(columns={'index': row_col}, inplace=True)
        total_row[row_col] = t_label
        potongan.append(total_row)
        
    res = pd.concat(potongan, ignore_index=True).set_index(row_col)
    
    col_prev, col_curr = raw_cols[0], raw_cols[1]
    col_cum_prev, col_cum_curr = raw_cols[2], raw_cols[3]
    
    prev_vals_res = res[col_prev].values
    curr_vals_res = res[col_curr].values
    with np.errstate(divide='ignore', invalid='ignore'):
        mtm_res = np.where(prev_vals_res == 0, np.nan, ((curr_vals_res - prev_vals_res) / prev_vals_res) * 100)
    res['M-to-M (%)'] = pd.Series(mtm_res, index=res.index).replace([np.inf, -np.inf], np.nan)
    
    cum_prev_vals_res = res[col_cum_prev].values
    cum_curr_vals_res = res[col_cum_curr].values
    with np.errstate(divide='ignore', invalid='ignore'):
        yoy_res = np.where(cum_prev_vals_res == 0, np.nan, ((cum_curr_vals_res - cum_prev_vals_res) / cum_prev_vals_res) * 100)
    res['Y-on-Y (%)'] = pd.Series(yoy_res, index=res.index).replace([np.inf, -np.inf], np.nan)
    
    return res[[col_prev, col_curr, 'M-to-M (%)', col_cum_prev, col_cum_curr, 'Y-on-Y (%)']]

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
    """Format angka konvensi Indonesia, menangkap NaN/Inf menjadi Undefined."""
    if pd.isna(x) or str(x).lower() in ['nan', 'inf', '-inf', 'undefined']:
        return "Undefined"
    try:
        val = float(x)
        if np.isinf(val) or np.isnan(val):
            return "Undefined"
        s = f"{val:,.{decimals}f}"
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
    if pd.isna(pct):
        return "tercatat"
    if pct > 0:
        return random.choice(["mengalami lonjakan", "naik", "meningkat", "mengalami pertumbuhan"])
    elif pct < 0:
        return random.choice(["terkoreksi", "turun", "mengalami penurunan", "menyusut"])
    return "stabil"

def generate_narrative_ai(df_flat, col_target, moda, prov, bln, thn, prev_bln, prev_thn):
    api_keys = st.secrets.get("API-GEMINI-KEYS") or st.secrets.get("API_GEMINI_KEYS")
    if not api_keys:
        return None

    data_str = df_flat.to_markdown()
    
    prompt = f"""
    Bertindaklah sebagai analis data senior di Badan Pusat Statistik (BPS) yang profesional namun komunikatif. 
    Buatlah tepat 2 paragraf ringkasan naratif dari data tabel statistik di bawah ini. Pisahkan paragraf pertama dan kedua dengan baris kosong ganda (\\n\\n). Adaptasi gaya bahasa Berita Resmi Statistik (BRS), namun buatlah kalimatnya lebih mengalir, natural, dan tidak kaku. 
    
    Variasikan pilihan kata (jangan monoton menggunakan frasa "tercatat sebanyak"). Anda bisa menggunakan kata ganti seperti "mencapai", "berada di angka", "menyentuh", "mengalami lonjakan", atau "terkoreksi".
    Nilai "Undefined" artinya tidak bisa dihitung karena pembaginya nol. Jika ada Undefined, sesuaikan narasinya dengan logis atau lewati sebutan persentasenya.

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
            client = genai.Client(api_key=key)
            response = client.models.generate_content(
                model='gemini-1.5-flash',
                contents=prompt,
                config=genai.types.GenerateContentConfig(temperature=0.1)
            )
            if response.text:
                return response.text
        except Exception:
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

    val_mtm_pct = fmt_pct(abs(total_mtm) if pd.notna(total_mtm) else np.nan)
    
    para1 = (
        f"{subject} pada bulan {bln} {thn} {verb_1} {fmt(total_curr)} {meta['satuan']}. "
        f"Angka ini {arah_mtm} sebesar {val_mtm_pct} persen dibandingkan periode {prev_bln} {prev_thn} "
        f"yang {verb_2} {fmt(total_prev)} {meta['satuan']}."
    )

    if len(data) > 0:
        if len(data) <= 3:
            rincian = []
            for r in data.index:
                pct_val = data.loc[r, 'M-to-M (%)']
                pct_str = fmt_pct(abs(pct_val) if pd.notna(pct_val) else np.nan)
                rincian.append(f"{region_label} {r} {random.choice(['berada di posisi', 'mencapai'])} {fmt(data.loc[r, col_curr])} {meta['satuan']} ({_arah_dinamis(pct_val)} {pct_str} persen)")
            para1 += f" Apabila dilihat lebih rinci pada tingkat {region_label.lower()}, " + "; dan ".join(rincian) + "."
        else:
            valid_mtm = data['M-to-M (%)'].dropna()
            if not valid_mtm.empty:
                top_r = valid_mtm.idxmax()
                bot_r = valid_mtm.idxmin()
                para1 += (
                    f" Jika dirinci per {region_label.lower()}, lonjakan tertinggi dialami oleh {region_label} {top_r} "
                    f"dengan kenaikan {fmt_pct(data.loc[top_r, 'M-to-M (%)'])} persen. Sebaliknya, penurunan terdalam terjadi di "
                    f"{region_label} {bot_r} yang terkoreksi hingga {fmt_pct(abs(data.loc[bot_r, 'M-to-M (%)']))} persen."
                )

    verb_3 = random.choice(["terakumulasi menjadi", "berhasil mencapai", "terkumpul sebanyak"])
    arah_yoy = _arah_dinamis(total_yoy)
    val_yoy_pct = fmt_pct(abs(total_yoy) if pd.notna(total_yoy) else np.nan)

    para2 = (
        f"Sementara itu, performa kumulatif dari Januari hingga {bln} {thn} {verb_3} {fmt(total_cum_curr)} "
        f"{meta['satuan']}. Capaian tersebut {arah_yoy} {val_yoy_pct} persen jika disandingkan dengan periode "
        f"Januari-{bln} {int(thn)-1} yang {verb_2} {fmt(total_cum_prev)} {meta['satuan']}."
    )

    if len(data) > 0:
        if len(data) > 3:
            valid_yoy = data['Y-on-Y (%)'].dropna()
            if not valid_yoy.empty:
                top_r2 = valid_yoy.idxmax()
                bot_r2 = valid_yoy.idxmin()
                para2 += (
                    f" Secara kumulatif, {region_label} {top_r2} mencatatkan pertumbuhan tertinggi sebesar "
                    f"{fmt_pct(valid_yoy.loc[top_r2])} persen. Di sisi lain, {region_label} {bot_r2} "
                    f"mengalami penyusutan paling dalam sebesar {fmt_pct(abs(valid_yoy.loc[bot_r2]))} persen."
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

    report[col_prev] = prev_grp.reindex(report.index).fillna(0)
    report[col_curr] = curr_grp.reindex(report.index).fillna(0)
    
    prev_vals = report[col_prev].values
    curr_vals = report[col_curr].values
    with np.errstate(divide='ignore', invalid='ignore'):
        mtm_pct = np.where(prev_vals == 0, np.nan, ((curr_vals - prev_vals) / prev_vals) * 100)
    report['M-to-M (%)'] = pd.Series(mtm_pct, index=report.index).replace([np.inf, -np.inf], np.nan)

    report[col_cum_prev] = cum_prev_grp.reindex(report.index).fillna(0)
    report[col_cum_curr] = cum_cum_grp.reindex(report.index).fillna(0)
    
    cum_prev_vals = report[col_cum_prev].values
    cum_curr_vals = report[col_cum_curr].values
    with np.errstate(divide='ignore', invalid='ignore'):
        yoy_pct = np.where(cum_prev_vals == 0, np.nan, ((cum_curr_vals - cum_prev_vals) / cum_prev_vals) * 100)
    report['Y-on-Y (%)'] = pd.Series(yoy_pct, index=report.index).replace([np.inf, -np.inf], np.nan)

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
    report_display_brs = build_brs_display_table(report_flat, prov, moda)

    angkutan = "Angkutan Udara" if moda == "Transportasi Udara" else "Angkutan Laut"
    region_label = "Bandara" if moda == "Transportasi Udara" else "Kabupaten/Kota"

    para1_text = ""
    para2_text = ""

    with st.spinner(f"Menyusun narasi untuk indikator {label}..."):
        narasi_ai = generate_narrative_ai(report_display_brs, label, moda, prov, bln, thn, prev_bln, prev_thn)
        
    if narasi_ai is None:
        p1, p2 = generate_narrative_fallback(
            report_flat, col_target, moda, region_label, bln, thn, prev_bln, prev_thn,
            col_prev, col_curr, col_cum_prev, col_cum_curr
        )
        para1_text = f"*(Narasi Dihasilkan oleh Sistem)*\n\n{p1}"
        para2_text = p2
    else:
        parts = [p.strip() for p in narasi_ai.split('\n\n') if p.strip()]
        if len(parts) >= 2:
            para1_text = f"*(Narasi Dihasilkan oleh Gemini AI)*\n\n{parts[0]}"
            para2_text = "\n\n".join(parts[1:])
        elif len(parts) == 1:
            para1_text = f"*(Narasi Dihasilkan oleh Gemini AI)*\n\n{parts[0]}"
            para2_text = ""
            
    if para1_text:
        st.markdown(para1_text)

    st.write("")
    if table_no is not None:
        judul = f"Tabel {table_no} Perkembangan {label} {angkutan} Dalam Negeri Provinsi {prov}, {bln} {thn}"
        st.markdown(f"**{judul}**")
    else:
        st.markdown(f"##### 📝 Indikator: {label}")

    cum_label = f"Kumulatif {label}"
    report_display = report_display_brs.copy()
    report_display.columns = pd.MultiIndex.from_tuples([
        (label, col_prev), (label, col_curr), (label, 'M-to-M (%)'),
        (cum_label, col_cum_prev), (cum_label, col_cum_curr), (cum_label, 'Y-on-Y (%)')
    ])
    pct_cols = [(label, 'M-to-M (%)'), (cum_label, 'Y-on-Y (%)')]

    def style_brs_hierarchy(styler):
        def highlight_rows(row):
            styles = [''] * len(row)
            val = str(row.name).strip().lower()
            if val in ['subtotal', 'sub total', 'jumlah', 'total', 'total keseluruhan']:
                styles = ['font-weight: bold; background-color: #fce8b2;'] * len(row)
            elif 'lainnya' in val:
                styles = ['font-style: italic; background-color: #e8eaed;'] * len(row)
            return styles
            
        styler = styler.format(format_id_number).background_gradient(subset=pct_cols, cmap='RdYlGn')
        styler = styler.apply(highlight_rows, axis=1)
        return styler

    st.dataframe(style_brs_hierarchy(report_display.style))

    if para2_text:
        st.markdown(para2_text)

    st.markdown("---")

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
