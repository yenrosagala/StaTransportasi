import random
import logging
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import text
from google import genai
from modules.database import get_engine

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)


# ==============================================================================
# HELPER MANDIRI (tidak bergantung pada modules.report_page, agar tidak rapuh
# terhadap perubahan/versi file tersebut)
# ==============================================================================
def format_id_number(x, decimals=2):
    """Format angka ke gaya Indonesia (titik ribuan, koma desimal)."""
    if pd.isna(x) or str(x).lower() in ['nan', 'inf', '-inf', 'undefined']:
        return "Undefined"
    try:
        val = float(x)
        if pd.isna(val):
            return "Undefined"
        s = f"{val:,.{decimals}f}"
    except (ValueError, TypeError):
        return str(x)
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def _arah_dinamis(pct):
    if pd.isna(pct):
        return "tercatat"
    if pct > 0:
        return random.choice(["mengalami lonjakan", "naik", "meningkat", "mengalami pertumbuhan"])
    elif pct < 0:
        return random.choice(["terkoreksi", "turun", "mengalami penurunan", "menyusut"])
    return "stabil"


def get_gemini_api_keys():
    """Ambil daftar API key Gemini dari st.secrets (mendukung beberapa nama key)."""
    keys = []

    def add_value(v):
        if not v:
            return
        if isinstance(v, str):
            v = v.strip()
            if v:
                keys.append(v)
        elif isinstance(v, (list, tuple)):
            for x in v:
                add_value(x)
        else:
            s = str(v).strip()
            if s:
                keys.append(s)

    try:
        add_value(st.secrets.get("GEMINI_API_KEYS"))
        add_value(st.secrets.get("GEMINI_API_KEY"))
        add_value(st.secrets.get("GOOGLE_API_KEY"))
        add_value(st.secrets.get("API_GEMINI_KEYS"))
        add_value(st.secrets.get("API_GEMINI_KEY"))
        add_value(st.secrets.get("API-GEMINI-KEYS"))
    except Exception as e:
        logger.info("Secrets Gemini tidak ditemukan (%s); narasi akan pakai fallback.", e)

    seen = set()
    unique_keys = []
    for k in keys:
        if k not in seen:
            seen.add(k)
            unique_keys.append(k)
    return unique_keys

MONTH_MAP = {'Januari': 1, 'Februari': 2, 'Maret': 3, 'April': 4, 'Mei': 5, 'Juni': 6,
             'Juli': 7, 'Agustus': 8, 'September': 9, 'Oktober': 10, 'November': 11, 'Desember': 12}
INV_MONTH_MAP = {v: k for k, v in MONTH_MAP.items()}
MONTH_ABBR = {'Januari': 'Jan', 'Februari': 'Feb', 'Maret': 'Mar', 'April': 'Apr', 'Mei': 'Mei', 'Juni': 'Jun',
              'Juli': 'Jul', 'Agustus': 'Agt', 'September': 'Sep', 'Oktober': 'Okt', 'November': 'Nov', 'Desember': 'Des'}

PROVINSI_ORDER = ['Papua', 'Papua Selatan', 'Papua Tengah', 'Papua Pegunungan']


# ==============================================================================
# HELPERS
# ==============================================================================
def get_available_periods(engine):
    """Kumpulan periode (tahun, bulan) yang tersedia di kedua tabel moda, terurut kronologis."""
    periods = set()
    for table in ['transportasi_udara', 'transportasi_laut']:
        try:
            df = pd.read_sql(text(f"SELECT DISTINCT tahun, bulan FROM {table}"), engine)
            for _, r in df.iterrows():
                periods.add((int(r['tahun']), r['bulan']))
        except Exception:
            continue
    return sorted(periods, key=lambda x: (x[0], MONTH_MAP.get(x[1], 0)))


def get_prev_period(thn, bln):
    m = MONTH_MAP[bln]
    if m > 1:
        return thn, INV_MONTH_MAP[m - 1]
    return thn - 1, 'Desember'


def load_period_data(engine, table, thn, bln):
    query = f"SELECT * FROM {table} WHERE CAST(tahun AS TEXT) = :thn AND bulan = :bln"
    return pd.read_sql(text(query), engine, params={"thn": str(thn), "bln": bln})


def agg_by_provinsi(df, cols):
    """Agregasi total per provinsi, dinormalisasi & diurutkan sesuai PROVINSI_ORDER."""
    base = pd.DataFrame(0.0, index=PROVINSI_ORDER, columns=cols)
    if df is None or df.empty:
        return base
    tmp = df.copy()
    tmp['nama_provinsi'] = tmp['nama_provinsi'].astype(str).str.strip().str.title()
    g = tmp.groupby('nama_provinsi')[cols].sum()
    for p in PROVINSI_ORDER:
        if p in g.index:
            base.loc[p] = g.loc[p]
    return base


def pct_change(curr, prev):
    if prev == 0 or pd.isna(prev) or pd.isna(curr):
        return None
    return (curr - prev) / prev * 100


def load_cumulative_data(engine, table, thn, bln):
    """Ambil seluruh baris dari Januari s.d. bulan terpilih pada tahun `thn` (untuk hitung YTD/Y-on-Y)."""
    bln_num = MONTH_MAP[bln]
    months = [INV_MONTH_MAP[i] for i in range(1, bln_num + 1)]
    params = {f"m{i}": m for i, m in enumerate(months)}
    placeholders = ", ".join(f":{k}" for k in params)
    query = f"SELECT * FROM {table} WHERE CAST(tahun AS TEXT) = :thn AND bulan IN ({placeholders})"
    params["thn"] = str(thn)
    return pd.read_sql(text(query), engine, params=params)


def build_stacked_bar(df_curr, col_bottom, col_top, label_bottom, label_top,
                       color_bottom, color_top, title):
    fig = go.Figure()
    fig.add_bar(
        name=label_bottom, x=df_curr.index, y=df_curr[col_bottom],
        marker_color=color_bottom,
        text=[f"{v:,.0f}".replace(",", ".") for v in df_curr[col_bottom]],
        textposition='inside', textfont=dict(color='white', size=12)
    )
    fig.add_bar(
        name=label_top, x=df_curr.index, y=df_curr[col_top],
        marker_color=color_top,
        text=[f"{v:,.0f}".replace(",", ".") for v in df_curr[col_top]],
        textposition='inside', textfont=dict(color='white', size=12)
    )
    fig.update_layout(
        barmode='stack', title=dict(text=title, font=dict(size=14)),
        template='plotly_white', legend=dict(orientation='h', y=-0.15, x=0.5, xanchor='center'),
        margin=dict(t=50, b=10, l=10, r=10), height=380
    )
    return fig


def build_growth_table(df_curr, df_prev, cols, labels, periode_label):
    rows = []
    for prov in PROVINSI_ORDER:
        row = {'PROVINSI': prov}
        for c, l in zip(cols, labels):
            curr_v = df_curr.loc[prov, c] if prov in df_curr.index else 0
            prev_v = df_prev.loc[prov, c] if prov in df_prev.index else 0
            row[f"PERKEMBANGAN {l} {periode_label} (%)"] = pct_change(curr_v, prev_v)
        rows.append(row)
    return pd.DataFrame(rows).set_index('PROVINSI')


def style_growth_table(df, header_color):
    def fmt(v):
        return "" if pd.isna(v) else f"{v:,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")

    styler = df.style.format(fmt).background_gradient(cmap='RdYlGn', axis=None, vmin=-30, vmax=30)
    styler = styler.set_table_styles([
        {'selector': 'th', 'props': [('background-color', header_color), ('color', 'white'),
                                      ('font-weight', 'bold'), ('text-align', 'center')]},
        {'selector': 'td', 'props': [('text-align', 'right')]}
    ])
    return styler


# ==============================================================================
# NARASI PER SECTION (Executive Summary)
# ==============================================================================
def compute_indicator_stats(df_curr, df_prev, df_cum_curr, df_cum_prev, cols):
    """Gabungkan sepasang kolom (mis. berangkat+datang, atau muat+bongkar) menjadi satu
    indikator, lalu hitung total M-to-M dan kumulatif Y-on-Y, plus provinsi ekstrem."""
    combined_curr = df_curr[cols].sum(axis=1)
    combined_prev = df_prev[cols].sum(axis=1)
    combined_cum_curr = df_cum_curr[cols].sum(axis=1)
    combined_cum_prev = df_cum_prev[cols].sum(axis=1)

    mtm_per_prov = pd.Series({p: pct_change(combined_curr.get(p, 0), combined_prev.get(p, 0)) for p in PROVINSI_ORDER})
    yoy_per_prov = pd.Series({p: pct_change(combined_cum_curr.get(p, 0), combined_cum_prev.get(p, 0)) for p in PROVINSI_ORDER})

    total_curr, total_prev = combined_curr.sum(), combined_prev.sum()
    total_cum_curr, total_cum_prev = combined_cum_curr.sum(), combined_cum_prev.sum()

    return {
        'curr': total_curr, 'prev': total_prev, 'mtm': pct_change(total_curr, total_prev),
        'cum_curr': total_cum_curr, 'cum_prev': total_cum_prev, 'yoy': pct_change(total_cum_curr, total_cum_prev),
        'mtm_per_prov': mtm_per_prov, 'yoy_per_prov': yoy_per_prov,
    }


def _top_bottom(series):
    valid = series.dropna()
    if valid.empty:
        return None, None
    return {'nama': valid.idxmax(), 'pct': valid.max()}, {'nama': valid.idxmin(), 'pct': valid.min()}


def ensure_dashboard_narasi_cache():
    if "dashboard_narasi_cache" not in st.session_state:
        st.session_state["dashboard_narasi_cache"] = {}


def generate_section_narrative_ai(moda_nama, bln, thn, prev_bln, prev_thn,
                                   penumpang_stats, barang_stats, satuan_barang):
    api_keys = get_gemini_api_keys()
    if not api_keys:
        return None

    # Daftar model dengan versi yang lebih lama/stabil
    candidate_models = [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite"    
        "gemini-3.1-flash-lite"
    ]

    if "gemini_key_index" not in st.session_state:
        st.session_state["gemini_key_index"] = 0

    num_keys = len(api_keys)
    
    p_top, p_bot = _top_bottom(penumpang_stats['mtm_per_prov'])
    b_top, b_bot = _top_bottom(barang_stats['mtm_per_prov'])
    p_top_yoy, p_bot_yoy = _top_bottom(penumpang_stats['yoy_per_prov'])
    b_top_yoy, b_bot_yoy = _top_bottom(barang_stats['yoy_per_prov'])

    prompt = (
        "Anda adalah Analis Kebijakan Utama dan Ahli Statistik Senior pada Direktorat Statistik Transportasi Badan Pusat Statistik (BPS).\n"
        f"Susunlah sebuah Executive Summary resmi yang objektif, analitis, dan berwibawa tepat dalam 2 (dua) paragraf untuk publikasi kinerja Transportasi {moda_nama} "
        f"di regional Papua (Provinsi Papua, Papua Selatan, Papua Tengah, dan Papua Pegunungan) periode {bln} {thn}.\n\n"
        "Standar Penulisan & Kaidah Kebahasaan:\n"
        "- Gunakan ragam bahasa resmi instansi pemerintah (bahasa baku, objektif, berorientasi data).\n"
        "- Hindari pengulangan kata yang monoton; gunakan diksi analitis (contoh: \"membukukan volume\", \"terkoreksi tipis\", \"menunjukkan tren ekspansif\", \"menyumbang deviasi signifikan\").\n\n"
        "Struktur & Substansi Wajib:\n"
        "1. Paragraf Pertama (Analisis Bulanan / Month-to-Month):\n"
        f"   - Evaluasi komparatif volume agregat penumpang (datang + berangkat) saat ini ({format_id_number(penumpang_stats['curr'], 0)} orang) terhadap baseline {prev_bln} {prev_thn} ({format_id_number(penumpang_stats['prev'], 0)} orang) yang merepresentasikan pertumbuhan {format_id_number(penumpang_stats['mtm'], 2) if penumpang_stats['mtm'] is not None else 'Undefined'}%.\n"
        f"   - Analisis dinamika volume muat dan bongkar barang: realisasi {format_id_number(barang_stats['curr'], 2)} {satuan_barang} berbanding periode sebelumnya {format_id_number(barang_stats['prev'], 2)} {satuan_barang} dengan fluktuasi sebesar {format_id_number(barang_stats['mtm'], 2) if barang_stats['mtm'] is not None else 'Undefined'}%.\n"
        f"   - Soroti wilayah pendorong utama (pertumbuhan tertinggi) serta wilayah yang mengalami kontraksi untuk indikator penumpang (tertinggi: {p_top}, terendah: {p_bot}) dan barang (tertinggi: {b_top}, terendah: {b_bot}).\n\n"
        "2. Paragraf Kedua (Analisis Kumulatif / Year-to-Date & Year-on-Year):\n"
        f"   - Bedah performa makro kumulatif Januari–{bln} {thn} untuk penumpang ({format_id_number(penumpang_stats['cum_curr'], 0)} orang) versus periode yang sama tahun lalu ({format_id_number(penumpang_stats['cum_prev'], 0)} orang).\n"
        f"   - Bedah performa kumulatif arus barang ({format_id_number(barang_stats['cum_curr'], 2)} {satuan_barang} vs {format_id_number(barang_stats['cum_prev'], 2)} {satuan_barang}).\n"
        f"   - Paparkan kontribusi wilayah dengan deviasi kumulatif paling mencolok (penumpang: {p_top_yoy} / {p_bot_yoy}; barang: {b_top_yoy} / {b_bot_yoy}).\n\n"
        "Aturan Mutlak:\n"
        "- Keluarkan HANYA teks dua paragraf tanpa pengantar, tanpa judul, dan tanpa penutup.\n"
        "- Format angka mutlak menerapkan standar penulisan Indonesia (titik sebagai pemisah ribuan, koma sebagai desimal)."
    )

    for attempt in range(num_keys):
        current_idx = (st.session_state["gemini_key_index"] + attempt) % num_keys
        key = api_keys[current_idx]
        
        for model_name in candidate_models:
            try:
                client = genai.Client(api_key=key.strip())
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=genai.types.GenerateContentConfig(temperature=0.3)
                )
                raw_text = getattr(response, "text", None)
                if raw_text and str(raw_text).strip():
                    st.session_state["gemini_key_index"] = (current_idx + 1) % num_keys
                    return str(raw_text).strip()
            except Exception as e:
                logger.warning("Gagal dengan Key ke-%d menggunakan model versi lama %s: %s. Mencoba opsi lain...", current_idx + 1, model_name, e)
                continue
            
    return None                                       

def generate_section_narrative_fallback(moda_nama, bln, thn, prev_bln, prev_thn,
                                         penumpang_stats, barang_stats, satuan_barang):
    fmt0 = lambda v: format_id_number(v, decimals=0)
    fmt2 = lambda v: format_id_number(v, decimals=2)
    fmt_pct = lambda v: fmt2(abs(v)) if v is not None else "Undefined"

    verb1 = random.choice(["mencapai", "menyentuh angka", "berada di level", "tercatat sebanyak"])
    verb2 = random.choice(["berada di angka", "sebanyak", "tercatat sejumlah"])
    verb3 = random.choice(["terakumulasi menjadi", "berhasil mencapai", "terkumpul sebanyak"])

    p_top, p_bot = _top_bottom(penumpang_stats['mtm_per_prov'])
    b_top, b_bot = _top_bottom(barang_stats['mtm_per_prov'])

    para1 = (
        f"Total pergerakan penumpang (berangkat dan datang) angkutan {moda_nama.lower()} dalam negeri pada bulan {bln} {thn} "
        f"{verb1} {fmt0(penumpang_stats['curr'])} orang, {_arah_dinamis(penumpang_stats['mtm'])} sebesar "
        f"{fmt_pct(penumpang_stats['mtm'])} persen dibandingkan {prev_bln} {prev_thn} yang {verb2} "
        f"{fmt0(penumpang_stats['prev'])} orang. Volume barang (muat dan bongkar) turut {_arah_dinamis(barang_stats['mtm'])} "
        f"sebesar {fmt_pct(barang_stats['mtm'])} persen, dari {fmt2(barang_stats['prev'])} {satuan_barang} menjadi "
        f"{fmt2(barang_stats['curr'])} {satuan_barang}."
    )
    if p_top and p_bot:
        para1 += (
            f" Dari sisi penumpang, Provinsi {p_top['nama']} mencatatkan pertumbuhan tertinggi sebesar {fmt2(p_top['pct'])} persen, "
            f"sementara Provinsi {p_bot['nama']} mengalami koreksi terdalam sebesar {fmt2(abs(p_bot['pct']))} persen."
        )
    if b_top and b_bot:
        para1 += (
            f" Untuk arus barang, lonjakan tertinggi terjadi di Provinsi {b_top['nama']} ({fmt2(b_top['pct'])} persen), "
            f"sedangkan penurunan terdalam terjadi di Provinsi {b_bot['nama']} ({fmt2(abs(b_bot['pct']))} persen)."
        )

    p_top_yoy, p_bot_yoy = _top_bottom(penumpang_stats['yoy_per_prov'])
    b_top_yoy, b_bot_yoy = _top_bottom(barang_stats['yoy_per_prov'])

    para2 = (
        f"Secara kumulatif, total penumpang periode Januari-{bln} {thn} {verb3} {fmt0(penumpang_stats['cum_curr'])} orang, "
        f"{_arah_dinamis(penumpang_stats['yoy'])} {fmt_pct(penumpang_stats['yoy'])} persen dibandingkan periode Januari-{bln} "
        f"{thn - 1} yang {verb2} {fmt0(penumpang_stats['cum_prev'])} orang. Total barang kumulatif {verb3} "
        f"{fmt2(barang_stats['cum_curr'])} {satuan_barang}, {_arah_dinamis(barang_stats['yoy'])} {fmt_pct(barang_stats['yoy'])} "
        f"persen dari {fmt2(barang_stats['cum_prev'])} {satuan_barang} pada periode yang sama tahun sebelumnya."
    )
    if p_top_yoy and b_top_yoy:
        para2 += (
            f" Secara kumulatif, pertumbuhan penumpang tertinggi disumbang oleh Provinsi {p_top_yoy['nama']} "
            f"({fmt2(p_top_yoy['pct'])} persen), sedangkan arus barang kumulatif tertinggi tercatat di Provinsi "
            f"{b_top_yoy['nama']} ({fmt2(b_top_yoy['pct'])} persen)."
        )

    return para1, para2


def _generate_and_cache_section_narrative(cache, cache_key, moda_nama, table, engine,
                                         cols_penumpang, cols_barang, satuan_barang,
                                         df_curr, df_prev, thn, bln, prev_thn, prev_bln):
    # Cek apakah narasi untuk periode dan tabel ini sudah ada di cache
    if cache_key in cache:
        return cache[cache_key]

    df_cum_curr_raw = load_cumulative_data(engine, table, thn, bln)
    df_cum_prev_raw = load_cumulative_data(engine, table, thn - 1, bln)
    all_cols = cols_penumpang + cols_barang
    df_cum_curr = agg_by_provinsi(df_cum_curr_raw, all_cols)
    df_cum_prev = agg_by_provinsi(df_cum_prev_raw, all_cols)

    penumpang_stats = compute_indicator_stats(df_curr, df_prev, df_cum_curr, df_cum_prev, cols_penumpang)
    barang_stats = compute_indicator_stats(df_curr, df_prev, df_cum_curr, df_cum_prev, cols_barang)

    with st.spinner(f"Menyusun ringkasan naratif Transportasi {moda_nama}..."):
        text_ai = generate_section_narrative_ai(
            moda_nama, bln, thn, prev_bln, prev_thn, penumpang_stats, barang_stats, satuan_barang
        )
        
    if text_ai:
        parts = [p.strip() for p in text_ai.split("\n\n") if p.strip()]
        para1 = parts[0] if parts else ""
        para2 = "\n\n".join(parts[1:]) if len(parts) > 1 else ""
        source = "Gemini AI"
    else:
        para1, para2 = generate_section_narrative_fallback(
            moda_nama, bln, thn, prev_bln, prev_thn, penumpang_stats, barang_stats, satuan_barang
        )
        source = "Sistem Fallback"
        
    # Simpan hasil (para1, para2, source) ke dalam cache session state
    cache[cache_key] = (para1, para2, source)
    return cache[cache_key]


def render_section_narrative(moda_nama, table, engine, cols_penumpang, cols_barang, satuan_barang,
                            df_curr, df_prev, thn, bln, prev_thn, prev_bln):
    ensure_dashboard_narasi_cache()
    cache = st.session_state["dashboard_narasi_cache"]
    cache_key = f"{table}|{thn}|{bln}"

    # Panggil fungsi yang mengelola cache (akan mengambil dari memori jika sudah ada, atau men-generate baru jika belum)
    para1, para2, source = _generate_and_cache_section_narrative(
        cache, cache_key, moda_nama, table, engine, cols_penumpang, cols_barang, satuan_barang,
        df_curr, df_prev, thn, bln, prev_thn, prev_bln
    )

    h1, h2 = st.columns([5, 1])
    with h1:
        st.markdown(f"**📝 Ringkasan Naratif** *(Sumber: {source})*")
    with h2:
        # Batasi tombol regenerasi hanya untuk role admin
        if st.session_state.get("role") == "admin":
            if st.button("🔄 Regenerasi", key=f"regen_{cache_key}", width='stretch'):
                # Hapus kunci cache khusus ini agar dipaksa membuat narasi baru dari API/Fallback
                if cache_key in cache:
                    del cache[cache_key]
                # Panggil ulang untuk mengisi cache dengan data baru
                _generate_and_cache_section_narrative(
                    cache, cache_key, moda_nama, table, engine, cols_penumpang, cols_barang, satuan_barang,
                    df_curr, df_prev, thn, bln, prev_thn, prev_bln
                )
                st.rerun()

    st.markdown(para1)
    if para2:
        st.markdown(para2)

# ==============================================================================
# SECTION RENDERER (satu moda transportasi)
# ==============================================================================
def show_section(engine, table, moda_title, icon, header_color,
                  cols_penumpang, labels_penumpang, colors_penumpang,
                  cols_barang, labels_barang, colors_barang,
                  thn, bln, prev_thn, prev_bln):
    st.markdown(f"## {icon} PERKEMBANGAN TRANSPORTASI {moda_title.upper()}")
    st.caption(f"Kondisi {bln} {thn}")

    df_curr_raw = load_period_data(engine, table, thn, bln)
    df_prev_raw = load_period_data(engine, table, prev_thn, prev_bln)

    if df_curr_raw.empty:
        st.warning(f"⚠️ Belum ada data Transportasi {moda_title} untuk periode {bln} {thn}.")
        return

    all_cols = cols_penumpang + cols_barang
    df_curr = agg_by_provinsi(df_curr_raw, all_cols)
    df_prev = agg_by_provinsi(df_prev_raw, all_cols)

    # --- GAMBAR (chart periode terpilih) ---
    c1, c2 = st.columns(2)
    with c1:
        fig1 = build_stacked_bar(
            df_curr, cols_penumpang[0], cols_penumpang[1],
            labels_penumpang[0], labels_penumpang[1],
            colors_penumpang[0], colors_penumpang[1],
            "PENUMPANG DATANG DAN BERANGKAT"
        )
        st.plotly_chart(fig1, width='stretch')
    with c2:
        fig2 = build_stacked_bar(
            df_curr, cols_barang[0], cols_barang[1],
            labels_barang[0], labels_barang[1],
            colors_barang[0], colors_barang[1],
            "MUAT DAN BONGKAR BARANG"
        )
        st.plotly_chart(fig2, width='stretch')

    # --- TABEL (pertumbuhan M-to-M: periode M-1 vs M) ---
    periode_label = f"{MONTH_ABBR[prev_bln]}-{MONTH_ABBR[bln]} {thn}"
    t1, t2 = st.columns(2)
    with t1:
        tbl1 = build_growth_table(df_curr, df_prev, cols_penumpang, labels_penumpang, periode_label)
        st.dataframe(style_growth_table(tbl1, header_color), width='stretch')
    with t2:
        tbl2 = build_growth_table(df_curr, df_prev, cols_barang, labels_barang, periode_label)
        st.dataframe(style_growth_table(tbl2, "#C0392B" if header_color != "#C0392B" else "#7B241C"), width='stretch')

    # --- NARASI (Executive Summary per section) ---
    satuan_barang = "ton" if moda_title == "Laut" else "kg"
    render_section_narrative(
        moda_title, table, engine, cols_penumpang, cols_barang, satuan_barang,
        df_curr, df_prev, thn, bln, prev_thn, prev_bln
    )


# ==============================================================================
# MAIN PAGE
# ==============================================================================
def show_dashboard_page():
    st.title("📊 Dashboard Statistik Perkembangan Transportasi")

    engine = get_engine()
    periods = get_available_periods(engine)

    if not periods:
        st.warning("⚠️ Belum ada data tersedia di database.")
        return

    period_labels = [f"{b} {t}" for t, b in periods]

    with st.expander("⚙️ Filter Periode", expanded=True):
        selected = st.selectbox("Pilih Periode (Bulan & Tahun)", period_labels, index=len(period_labels) - 1)

    sel_bln = selected.split(" ")[0]
    sel_thn = int(selected.split(" ")[1])
    prev_thn, prev_bln = get_prev_period(sel_thn, sel_bln)

    st.markdown("---")

    # SECTION 1: TRANSPORTASI LAUT
    show_section(
        engine, 'transportasi_laut', "Laut", "🚢", "#B8860B",
        cols_penumpang=['dn_penumpang_naik', 'dn_penumpang_turun'],
        labels_penumpang=['PENUMPANG BERANGKAT', 'PENUMPANG DATANG'],
        colors_penumpang=['#B8860B', '#FFC72C'],
        cols_barang=['dn_muat_barang_ton', 'dn_bongkar_barang_ton'],
        labels_barang=['MUAT BARANG', 'BONGKAR BARANG'],
        colors_barang=['#E74C3C', '#E8720C'],
        thn=sel_thn, bln=sel_bln, prev_thn=prev_thn, prev_bln=prev_bln
    )

    st.markdown("---")

    # SECTION 2: TRANSPORTASI UDARA
    show_section(
        engine, 'transportasi_udara', "Udara", "✈️", "#D4A017",
        cols_penumpang=['penumpang_berangkat', 'penumpang_datang'],
        labels_penumpang=['PENUMPANG BERANGKAT', 'PENUMPANG DATANG'],
        colors_penumpang=['#FFC72C', '#FFE699'],
        cols_barang=['barang_muat_kg', 'barang_bongkar_kg'],
        labels_barang=['MUAT BARANG', 'BONGKAR BARANG'],
        colors_barang=['#F4A460', '#E8720C'],
        thn=sel_thn, bln=sel_bln, prev_thn=prev_thn, prev_bln=prev_bln
    )

    st.markdown("---")

    # --- DATA DETAIL (opsional, untuk transparansi angka mentah) ---
    with st.expander("📋 Lihat Data Detail Mentah", expanded=False):
        moda_detail = st.radio("Moda", ["Transportasi Laut", "Transportasi Udara"], horizontal=True, key="detail_moda")
        table_detail = "transportasi_laut" if moda_detail == "Transportasi Laut" else "transportasi_udara"
        df_detail = load_period_data(engine, table_detail, sel_thn, sel_bln)
        st.dataframe(df_detail, width='stretch')
