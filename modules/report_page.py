import streamlit as st
import pandas as pd
import numpy as np
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

    # table is chosen from a fixed internal mapping (not user-supplied text),
    # so it's safe to interpolate; all user-supplied values below are bound as params.
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
    """Format angka untuk tampilan dengan konvensi Indonesia:
    titik (.) sebagai pemisah ribuan, koma (,) sebagai pemisah desimal."""
    if pd.isna(x):
        x = 0
    try:
        # format Python standar dulu (koma=ribuan, titik=desimal), lalu tukar simbolnya
        s = f"{float(x):,.{decimals}f}"
    except (ValueError, TypeError):
        return str(x)
    return s.replace(",", "§").replace(".", ",").replace("§", ".")

# Metadata bahasa untuk ringkasan naratif per kolom indikator.
# subject: frasa subjek kalimat, verb: kata penghubung jumlah ("sebanyak"/"sebesar"),
# satuan: satuan angka, is_penumpang: pakai frasa "menggunakan angkutan ... dalam negeri" atau tidak.
NARRATIVE_META = {
    'penumpang_datang':     {'subject': 'Jumlah penumpang yang datang', 'verb': 'sebanyak', 'satuan': 'orang', 'is_penumpang': True},
    'penumpang_berangkat':  {'subject': 'Jumlah penumpang yang berangkat', 'verb': 'sebanyak', 'satuan': 'orang', 'is_penumpang': True},
    'barang_bongkar_kg':    {'subject': 'Volume barang yang dibongkar', 'verb': 'sebesar', 'satuan': 'kg', 'is_penumpang': False},
    'barang_muat_kg':       {'subject': 'Volume barang yang dimuat', 'verb': 'sebesar', 'satuan': 'kg', 'is_penumpang': False},
    'dn_penumpang_turun':   {'subject': 'Jumlah penumpang yang datang', 'verb': 'sebanyak', 'satuan': 'orang', 'is_penumpang': True},
    'dn_penumpang_naik':    {'subject': 'Jumlah penumpang yang berangkat', 'verb': 'sebanyak', 'satuan': 'orang', 'is_penumpang': True},
    'dn_bongkar_barang_ton':{'subject': 'Volume barang yang dibongkar', 'verb': 'sebesar', 'satuan': 'ton', 'is_penumpang': False},
    'dn_muat_barang_ton':   {'subject': 'Volume barang yang dimuat', 'verb': 'sebesar', 'satuan': 'ton', 'is_penumpang': False},
}

def _arah(pct):
    if pct > 0:
        return "naik"
    elif pct < 0:
        return "turun"
    return "tidak berubah"

def generate_narrative(report_flat, col_target, moda, region_label, bln, thn, prev_bln, prev_thn,
                        col_prev, col_curr, col_cum_prev, col_cum_curr):
    """Buat 2 paragraf ringkasan naratif (bulanan & kumulatif) dari tabel report_flat
    (kolom flat, sudah termasuk baris TOTAL), meniru gaya narasi BRS BPS.
    Ini murni template teks berbasis data -- tidak memakai AI/API eksternal."""
    meta = NARRATIVE_META.get(col_target, {'subject': 'Jumlah', 'verb': 'sebanyak', 'satuan': '', 'is_penumpang': False})
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

    # --- Paragraf 1: perbandingan bulan ke bulan ---
    para1 = (
        f"{subject} pada {bln} {thn} tercatat {meta['verb']} {fmt(total_curr)} {meta['satuan']} "
        f"atau {_arah(total_mtm)} sebesar {fmt_pct(abs(total_mtm))} persen dibanding {prev_bln} {prev_thn} "
        f"yang {meta['verb']} {fmt(total_prev)} {meta['satuan']}."
    )

    if len(data) > 0:
        if len(data) <= 3:
            rincian = [
                f"{region_label} {r} tercatat {meta['verb']} {fmt(data.loc[r, col_curr])} {meta['satuan']} "
                f"atau {_arah(data.loc[r, 'M-to-M (%)'])} sebesar {fmt_pct(abs(data.loc[r, 'M-to-M (%)']))} persen"
                for r in data.index
            ]
            para1 += f" Jika dirinci menurut {region_label.lower()}, " + "; dan ".join(rincian) + "."
        else:
            top_r = data['M-to-M (%)'].idxmax()
            bot_r = data['M-to-M (%)'].idxmin()
            para1 += (
                f" Jika dirinci menurut {region_label.lower()}, peningkatan tertinggi terjadi di {region_label} {top_r} "
                f"yaitu sebesar {fmt_pct(data.loc[top_r, 'M-to-M (%)'])} persen, sedangkan penurunan terdalam terjadi di "
                f"{region_label} {bot_r} yaitu sebesar {fmt_pct(abs(data.loc[bot_r, 'M-to-M (%)']))} persen."
            )

    # --- Paragraf 2: kumulatif Januari s.d. bulan berjalan, tahun ke tahun ---
    para2 = (
        f"Secara kumulatif, {meta['subject'].lower()} selama Januari-{bln} {thn} mencapai {fmt(total_cum_curr)} "
        f"{meta['satuan']} atau {_arah(total_yoy)} sebesar {fmt_pct(abs(total_yoy))} persen bila dibandingkan "
        f"Januari-{bln} {int(thn)-1} yang {meta['verb']} {fmt(total_cum_prev)} {meta['satuan']}."
    )

    if len(data) > 0:
        if len(data) <= 3:
            rincian2 = [
                f"{region_label} {r} {_arah(data.loc[r, 'Y-on-Y (%)'])} sebesar {fmt_pct(abs(data.loc[r, 'Y-on-Y (%)']))} persen "
                f"menjadi {fmt(data.loc[r, col_cum_curr])} {meta['satuan']}"
                for r in data.index
            ]
            para2 += f" Jika dirinci menurut {region_label.lower()}, " + "; ".join(rincian2) + "."
        else:
            top_r2 = data['Y-on-Y (%)'].idxmax()
            bot_r2 = data['Y-on-Y (%)'].idxmin()
            para2 += (
                f" Peningkatan tertinggi secara kumulatif terjadi di {region_label} {top_r2} sebesar "
                f"{fmt_pct(data.loc[top_r2, 'Y-on-Y (%)'])} persen, sedangkan penurunan terdalam terjadi di "
                f"{region_label} {bot_r2} sebesar {fmt_pct(abs(data.loc[bot_r2, 'Y-on-Y (%)']))} persen."
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
    report['M-to-M (%)'] = ((report[col_curr] - report[col_prev]) / report[col_prev] * 100).replace([np.inf, -np.inf], np.nan).fillna(0)

    report[col_cum_prev] = cum_prev_grp
    report[col_cum_curr] = cum_curr_grp
    report['Y-on-Y (%)'] = ((report[col_cum_curr] - report[col_cum_prev]) / report[col_cum_prev] * 100).replace([np.inf, -np.inf], np.nan).fillna(0)

    report = report.fillna(0)

    # Baris TOTAL: nilai absolut dijumlahkan, lalu persentase M-to-M/Y-on-Y
    # dihitung ULANG dari total tersebut (bukan rata-rata dari persentase
    # per baris), supaya representatif secara agregat.
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
    region_label = "Bandara" if moda == "Transportasi Udara" else "Kabupaten/Kota"

    # Ringkasan naratif otomatis berbasis template teks (tanpa AI/API eksternal),
    # meniru gaya narasi Berita Resmi Statistik (BRS) BPS.
    para1, para2 = generate_narrative(
        report_flat, col_target, moda, region_label, bln, thn, prev_bln, prev_thn,
        col_prev, col_curr, col_cum_prev, col_cum_curr
    )
    st.markdown(para1)


    if table_no is not None:
        judul = f"Tabel {table_no} Perkembangan {label} {angkutan} Dalam Negeri Provinsi {prov}, {bln} {thn}"
        st.markdown(f"**{judul}**")
    else:
        st.markdown(f"##### 📝 Indikator: {label}")

    # Susun header 2 level:
    # Grup 1 -> label indikator: kolom M-1, M, M-to-M (%)
    # Grup 2 -> "Kumulatif {label}": kolom Jan-M tahun lalu, Jan-M tahun ini, Y-on-Y (%)
    cum_label = f"Kumulatif {label}"
    report = report_flat.copy()
    report.columns = pd.MultiIndex.from_tuples([
        (label, col_prev), (label, col_curr), (label, 'M-to-M (%)'),
        (cum_label, col_cum_prev), (cum_label, col_cum_curr), (cum_label, 'Y-on-Y (%)')
    ])

    pct_cols = [(label, 'M-to-M (%)'), (cum_label, 'Y-on-Y (%)')]

    st.dataframe(report.style.format(format_id_number).background_gradient(subset=pct_cols, cmap='RdYlGn'))
    st.markdown(para2)

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
