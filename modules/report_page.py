import streamlit as st
import pandas as pd
import numpy as np
import random
import io
import docx
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
            "utama": ['Moppah'],
            "lainnya": [
                'Okaba', 'Tanah Merah', 'Bomakia', 
                'Mindiptanah', 'Kepi', 'Bade', 
                'Ewer', 'Kamur'
            ],
            "label_subtotal": "Jumlah",
            "label_total": "Total",
            "teks_separator": "Bandara lainnya"
        }
    }
}

def normalisasi_entitas(nama, moda):
    if not isinstance(nama, str):
        return str(nama)
    clean_name = nama.strip()
    if moda == "Transportasi Udara":
        if clean_name.lower().startswith("bandara "):
            clean_name = clean_name[8:].strip()
        mapping_khusus = {"Nabire": "Douw Aturure"}
        return mapping_khusus.get(clean_name, clean_name)
    else:
        if clean_name.lower().startswith("pelabuhan "):
            clean_name = clean_name[10:].strip()
        return clean_name

def build_brs_display_table(report_flat, prov, moda):
    df = report_flat.copy()
    if 'TOTAL' in df.index:
        total_row = df.loc[['TOTAL']]
        df = df.drop(index='TOTAL')
    else:
        total_row = pd.DataFrame()
        
    df = df.reset_index()
    row_col = df.columns[0]
    
    df[row_col] = df[row_col].apply(lambda x: normalisasi_entitas(x, moda))
    df = df.groupby(row_col).sum(min_count=1).reset_index() 
    
    raw_cols = [c for c in df.columns if '(%)' not in c and c != row_col]
    potongan = []
    
    if prov in HIERARKI_BRS and moda in HIERARKI_BRS[prov]:
        config = HIERARKI_BRS[prov][moda]
        df['match_key'] = df[row_col].astype(str).str.lower()
        utama_lower = [str(x).lower() for x in config["utama"]]
        lainnya_lower = [str(x).lower() for x in config["lainnya"]]
        
        df_utama = df[df['match_key'].isin(utama_lower)].copy()
        if not df_utama.empty:
            df_utama = df_utama.drop(columns=['match_key'])
            potongan.append(df_utama)
            if len(config["lainnya"]) > 0:
                sub_utama = pd.DataFrame(df_utama[raw_cols].sum()).T
                sub_utama[row_col] = config["label_subtotal"]
                potongan.append(sub_utama)
            
        if len(config["lainnya"]) > 0:
            separator = pd.DataFrame([{row_col: config["teks_separator"]}])
            for c in df.columns: 
                if c != row_col and c != 'match_key': 
                    separator[c] = np.nan
            potongan.append(separator)
            
            df_lain = df[df['match_key'].isin(lainnya_lower)].copy()
            if not df_lain.empty:
                df_lain = df_lain.drop(columns=['match_key'])
                potongan.append(df_lain)
                sub_lain = pd.DataFrame(df_lain[raw_cols].sum()).T
                sub_lain[row_col] = config["label_subtotal"] + " " 
                potongan.append(sub_lain)
                
        if not potongan and not df.empty:
            if 'match_key' in df.columns: df = df.drop(columns=['match_key'])
            potongan.append(df)
    else:
        if 'match_key' in df.columns: df = df.drop(columns=['match_key'])
        potongan.append(df)
        
    if not total_row.empty:
        t_label = HIERARKI_BRS.get(prov, {}).get(moda, {}).get("label_total", "TOTAL")
        total_row = total_row.reset_index()
        total_row.rename(columns={'index': row_col}, inplace=True)
        total_row[row_col] = t_label
        potongan.append(total_row)
        
    res = pd.concat(potongan, ignore_index=True).set_index(row_col) if potongan else df.set_index(row_col)
    
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
    if pd.isna(x) or str(x).lower() in ['nan', 'inf', '-inf', 'undefined']:
        return "Undefined"
    try:
        val = float(x)
        if np.isinf(val) or np.isnan(val): return "Undefined"
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
    if pd.isna(pct): return "tercatat"
    if pct > 0: return random.choice(["mengalami lonjakan", "naik", "meningkat", "mengalami pertumbuhan"])
    elif pct < 0: return random.choice(["terkoreksi", "turun", "mengalami penurunan", "menyusut"])
    return "stabil"

def generate_narrative_ai(df_flat, col_target, moda, prov, bln, thn, prev_bln, prev_thn):
    # Mengambil daftar kunci API dari secrets (mendukung berbagai penamaan key)
    api_keys = st.secrets.get("API-GEMINI-KEYS") or st.secrets.get("API_GEMINI_KEYS") or st.secrets.get("API_GEMINI_KEY")
    
    # Jika tidak ada kunci sama sekali, langsung kembalikan None agar beralih ke fallback
    if not api_keys:
        return None

    # Jika api_keys berupa string tunggal, ubah ke dalam bentuk list agar bisa di-loop
    if isinstance(api_keys, str):
        api_keys = [api_keys]

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

    # Melakukan perulangan mencoba setiap API Key yang tersedia secara berurutan
    for key in api_keys:
        if not key.strip():
            continue
        try:
            client = genai.Client(api_key=key.strip())
            response = client.models.generate_content(
                model='gemini-1.5-flash',
                contents=prompt,
                config=genai.types.GenerateContentConfig(temperature=0.1)
            )
            # Jika berhasil mendapatkan teks dari AI, langsung kembalikan hasilnya
            if response and response.text:
                return response.text
        except Exception as e:
            # Jika kunci ini gagal/error (misal kuota habis atau salah key), catat dan lanjut ke key berikutnya
            continue
            
    # Jika seluruh kunci di dalam list terbukti gagal, kembalikan None
    return None

with st.spinner(f"Menyusun narasi untuk indikator {label} menggunakan AI..."):
    narasi_ai = generate_narrative_ai(report_display_brs, label, moda, prov, bln, thn, prev_bln, prev_thn)
    
  if narasi_ai is None:
      # Hanya dijalankan jika seluruh API key gagal atau tidak ditemukan
      p1, p2 = generate_narrative_fallback(
          report_flat, col_target, moda, region_label, bln, thn, prev_bln, prev_thn,
          col_prev, col_curr, col_cum_prev, col_cum_curr
      )
      para1_text = f"*(Semua API AI Gagal - Narasi Dihasilkan oleh Sistem Fallback)*\n\n{p1}"
      para2_text = p2
  else:
      parts = [p.strip() for p in narasi_ai.split('\n\n') if p.strip()]
      if len(parts) >= 2:
          para1_text = f"*(Narasi Berhasil Dihasilkan oleh Gemini AI)*\n\n{parts[0]}"
          para2_text = "\n\n".join(parts[1:])
      elif len(parts) == 1:
          para1_text = f"*(Narasi Berhasil Dihasilkan oleh Gemini AI)*\n\n{parts[0]}"
          para2_text = ""

def generate_narrative_fallback(report_flat, col_target, moda, region_label, bln, thn, prev_bln, prev_thn,
                                col_prev, col_curr, col_cum_prev, col_cum_curr):
    meta = NARRATIVE_META.get(col_target, {'subject': 'Jumlah', 'satuan': '', 'is_penumpang': False})
    angkutan_kecil = 'udara' if moda == 'Transportasi Udara' else 'laut'
    val_decimals = 0 if meta['satuan'] == 'orang' else 2
    fmt = lambda v: format_id_number(v, decimals=val_decimals)
    fmt_pct = lambda v: format_id_number(v, decimals=2)

    subject = meta['subject']
    if meta['is_penumpang']: subject += f" menggunakan angkutan {angkutan_kecil} dalam negeri"

    total = report_flat.loc['TOTAL']
    data = report_flat.drop(index='TOTAL')
    total_curr, total_prev, total_mtm = total[col_curr], total[col_prev], total['M-to-M (%)']
    total_cum_curr, total_cum_prev, total_yoy = total[col_cum_curr], total[col_cum_prev], total['Y-on-Y (%)']

    para1 = f"{subject} pada bulan {bln} {thn} tercatat {fmt(total_curr)} {meta['satuan']}. Angka ini {_arah_dinamis(total_mtm)} sebesar {fmt_pct(abs(total_mtm) if pd.notna(total_mtm) else np.nan)} persen dibanding {prev_bln} {prev_thn}."
    para2 = f"Performa kumulatif Januari-{bln} {thn} mencapai {fmt(total_cum_curr)} {meta['satuan']}, {_arah_dinamis(total_yoy)} {fmt_pct(abs(total_yoy) if pd.notna(total_yoy) else np.nan)} persen dibanding periode tahun sebelumnya."
    return para1, para2

def create_complete_master_word_report(prov, thn, bln, all_report_data):
    doc = docx.Document()
    doc.add_heading(f"Laporan Komprehensif Perkembangan Transportasi Provinsi {prov} - {bln} {thn}", level=1)
    doc.add_paragraph(f"Dokumen ini memuat seluruh tabel hierarki BRS dan narasi strategis moda Transportasi Udara dan Transportasi Laut.")
    doc.add_paragraph()

    for item in all_report_data:
        moda_name = item['moda']
        table_no = item['table_no']
        label = item['label']
        p1 = item['p1']
        p2 = item['p2']
        df_display = item['df_display']

        doc.add_heading(f"Moda: {moda_name} - Tabel {table_no}: {label}", level=2)
        if p1: doc.add_paragraph(p1)
        
        df_to_export = df_display.reset_index()
        
        total_rows = len(df_to_export) + 2
        total_cols = len(df_to_export.columns)
        
        table = doc.add_table(rows=total_rows, cols=total_cols)
        table.style = 'Table Grid'
        
        hdr_row_0 = table.rows[0]
        hdr_row_1 = table.rows[1]
        
        for j, col_tuple in enumerate(df_to_export.columns):
            if isinstance(col_tuple, tuple):
                lvl_0, lvl_1 = str(col_tuple[0]), str(col_tuple[1])
            else:
                lvl_0, lvl_1 = str(col_tuple), ""
                
            hdr_row_0.cells[j].text = lvl_0
            hdr_row_1.cells[j].text = lvl_1

        try:
            hdr_row_0.cells[0].merge(hdr_row_1.cells[0])
            if total_cols >= 4:
                hdr_row_0.cells[1].merge(hdr_row_0.cells[3])
                if total_cols >= 7:
                    hdr_row_0.cells[4].merge(hdr_row_0.cells[6])
        except Exception:
            pass

        # Mengisi Data Baris ke dalam Tabel Word
        for i, row_data in enumerate(df_to_export.values):
            row_cells = table.rows[i + 2].cells
            first_col_val = str(row_data[0]) if not pd.isna(row_data[0]) else ""
            
            # Cek apakah baris ini adalah baris separator (Bandara lainnya / Pelabuhan lainnya)
            is_separator_row = "lainnya" in first_col_val.lower()
            
            for j, val in enumerate(row_data):
                if j == 0:
                    row_cells[j].text = first_col_val
                else:
                    if is_separator_row:
                        # Kosongkan sel selain kolom pertama pada baris separator
                        row_cells[j].text = ""
                    else:
                        row_cells[j].text = format_id_number(val, decimals=2)
            
            # Jika baris separator, lakukan merge horizontal dari kolom pertama sampai kolom terakhir
            if is_separator_row and total_cols > 1:
                try:
                    row_cells[0].merge(row_cells[total_cols - 1])
                except Exception:
                    pass
                
        doc.add_paragraph()
        if p2: doc.add_paragraph(p2)
        doc.add_paragraph("---")

    file_stream = io.BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)
    return file_stream
  
def process_single_indicator(df_curr, df_prev, df_cum_curr, df_cum_prev, col_target, label, row_col, thn, bln, prev_bln, prev_thn, table_no, prov, moda):
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
    report[col_cum_curr] = cum_curr_grp.reindex(report.index).fillna(0)
    
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

    region_label = "Bandara" if moda == "Transportasi Udara" else "Kabupaten/Kota"
    narasi_ai = generate_narrative_ai(report_display_brs, label, moda, prov, bln, thn, prev_bln, prev_thn)
    
    if narasi_ai is None:
        p1, p2 = generate_narrative_fallback(
            report_flat, col_target, moda, region_label, bln, thn, prev_bln, prev_thn,
            col_prev, col_curr, col_cum_prev, col_cum_curr
        )
        p1_text, p2_text = f"*(Narasi Sistem)*\n\n{p1}", p2
    else:
        parts = [p.strip() for p in narasi_ai.split('\n\n') if p.strip()]
        p1_text = f"*(Narasi AI)*\n\n{parts[0]}" if parts else ""
        p2_text = "\n\n".join(parts[1:]) if len(parts) >= 2 else ""

    cum_label = f"Kumulatif {label}"
    report_display = report_display_brs.copy()
    report_display.columns = pd.MultiIndex.from_tuples([
        (label, col_prev), (label, col_curr), (label, 'M-to-M (%)'),
        (cum_label, col_cum_prev), (cum_label, col_cum_curr), (cum_label, 'Y-on-Y (%)')
    ])

    # Render UI Streamlit
    if p1_text: st.markdown(p1_text)
    st.markdown(f"**Tabel {table_no} Perkembangan {label} {moda} Provinsi {prov}, {bln} {thn}**")

    pct_cols = [(label, 'M-to-M (%)'), (cum_label, 'Y-on-Y (%)')]
    st.dataframe(report_display.style.format(format_id_number).background_gradient(subset=pct_cols, cmap='RdYlGn'))
    if p2_text: st.markdown(p2_text)
    st.markdown("---")

    return {
        'moda': moda,
        'table_no': table_no,
        'label': label,
        'p1': p1_text,
        'p2': p2_text,
        'df_display': report_display
    }

def show_report_page():
    st.title("📋 Laporan Komparatif Strategis")
    
    c1, c2, c3 = st.columns(3)
    with c1: prov = st.selectbox("Provinsi", list(PEMETAAN_WILAYAH.keys()))
    with c2: thn = st.selectbox("Tahun", ['2024', '2025', '2026'], index=1)
    with c3: bln = st.selectbox("Bulan", list(MONTH_MAP.keys()))

    if st.button("Generate Semua Laporan (Udara & Laut)"):
        all_collected_data = []
        
        # Proses Moda Transportasi Udara (4 Tabel)
        moda_udara = "Transportasi Udara"
        df_cu, df_pr, df_cc, df_cp, p_bln, p_thn = get_comparison_data(prov, thn, bln, moda_udara)
        if not df_cu.empty:
            st.subheader("✈️ Moda: Transportasi Udara")
            targets_udara = [
                ('penumpang_datang', 'Penumpang Datang'), ('penumpang_berangkat', 'Penumpang Berangkat'),
                ('barang_bongkar_kg', 'Barang Bongkar (Kg)'), ('barang_muat_kg', 'Barang Muat (Kg)')
            ]
            for i, (col, label) in enumerate(targets_udara, start=1):
                res_item = process_single_indicator(df_cu, df_pr, df_cc, df_cp, col, label, 'nama_bandara', thn, bln, p_bln, p_thn, i, prov, moda_udara)
                all_collected_data.append(res_item)

        # Proses Moda Transportasi Laut (4 Tabel)
        moda_laut = "Transportasi Laut"
        df_cu_l, df_pr_l, df_cc_l, df_cp_l, p_bln_l, p_thn_l = get_comparison_data(prov, thn, bln, moda_laut)
        if not df_cu_l.empty:
            st.subheader("🚢 Moda: Transportasi Laut")
            targets_laut = [
                ('dn_penumpang_turun', 'Penumpang Turun'), ('dn_penumpang_naik', 'Penumpang Naik'),
                ('dn_bongkar_barang_ton', 'Barang Bongkar (Ton)'), ('dn_muat_barang_ton', 'Barang Muat (Ton)')
            ]
            for i, (col, label) in enumerate(targets_laut, start=1):
                res_item = process_single_indicator(df_cu_l, df_pr_l, df_cc_l, df_cp_l, col, label, 'nama_kabkota', thn, bln, p_bln_l, p_thn_l, i, prov, moda_laut)
                all_collected_data.append(res_item)

        # Jika data terkumpul, tampilkan tombol download master di paling atas atau bawah
        if all_collected_data:
            master_word_file = create_complete_master_word_report(prov, thn, bln, all_collected_data)
            st.success("Semua data laporan berhasil digenerate!")
            st.download_button(
                label="📥 Download Master Dokumen Word (Semua 8 Tabel & Narasi)",
                data=master_word_file,
                file_name=f"Master_Laporan_Transportasi_{prov}_{bln}_{thn}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
