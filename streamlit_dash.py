import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import geopandas as gpd
from pathlib import Path
from my_module import ETLEngine, generate_akomodasi_tables, get_gemini_client
from transportasi_module import TransportasiEngine, month_name_id, MONTH_NAMES_ID

# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(
    page_title="Pariwisata & Transportasi Papua — Monitoring Platform",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# THEME TOKENS — kept in sync with style.css
# ============================================================
PRIMARY, PRIMARY_DARK, POSITIVE, NEGATIVE = "#F59E0B", "#D97706", "#10B981", "#EF4444"
INK, INK_DIM, LINE, MAP_BG = "#0F172A", "#64748B", "#E2E8F0", "#0B0F14"

TARGET_PROVINCES = ["Papua", "Papua Tengah", "Papua Pegunungan", "Papua Selatan"]
LEFT_PROVINCES = ["Papua Tengah", "Papua Selatan"]
RIGHT_PROVINCES = ["Papua", "Papua Pegunungan"]

JENIS_LABELS = {"Hotel Bintang": "Klasifikasi Bintang", "Hotel Non Bintang": "Klasifikasi NonBintang"}
INDICATOR_META = {
    "tpk": {"label": "TPK (Occupancy Rate)", "unit": "%"},
    "rlmtgab": {"label": "RLMTGAB (Length of Stay)", "unit": " malam"},
}

# ============================================================
# STYLE INJECTION
# ============================================================
def load_css():
    css_path = Path(__file__).parent / "style.css"
    if css_path.exists():
        st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)

load_css()

def plotly_theme(fig, height=440, dark=False):
    font_color = "#F1F5F9" if dark else INK
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color=font_color, size=13),
        title_font=dict(family="Inter, sans-serif", size=16, color=font_color),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=font_color)),
        height=height,
        margin=dict(l=10, r=10, t=40, b=10),
    )
    fig.update_xaxes(gridcolor=LINE if not dark else "rgba(255,255,255,0.08)")
    fig.update_yaxes(gridcolor=LINE if not dark else "rgba(255,255,255,0.08)")
    return fig

def month_name(m):
    return pd.to_datetime(str(int(m)), format="%m").strftime("%B") if m else ""

def card_open(title=None, tag=None):
    if title:
        tag_html = f"<span>{tag}</span>" if tag else ""
        st.markdown(
            f'<div class="dashboard-card"><div class="card-header"><h3>{title}</h3>{tag_html}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)

def card_close():
    st.markdown("</div>", unsafe_allow_html=True)

# ============================================================
# DATA SOURCES
# ============================================================
@st.cache_resource
def get_etl():
    return ETLEngine()

etl_engine = get_etl()

@st.cache_resource
def get_transport_engine():
    # Uses the SAME database as the original R/Shiny "Monit Transportasi" app
    return TransportasiEngine(db_path="Monit Transportasi/transportasi.db")

transport_engine = get_transport_engine()

@st.cache_data
def load_geodata():
    return gpd.read_parquet("papua_provinces.parquet")

try:
    gdf_provinces = load_geodata()
except Exception:
    gdf_provinces = pd.DataFrame()

# ============================================================
# AUTH STATE
# ============================================================
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
    st.session_state["role"] = "user"
    st.session_state["name"] = "General Analyst"
if "app" not in st.session_state:
    st.session_state["app"] = "Pariwisata"

USERS = {
    "admin": {"password": "admin123", "role": "admin", "name": "Database Administrator"},
    "user": {"password": "user123", "role": "user", "name": "General Analyst"},
}

# ============================================================
# LOGIN SCREEN
# ============================================================
if not st.session_state["authenticated"]:
    st.markdown('<div class="login-wrap">', unsafe_allow_html=True)
    _, col2, _ = st.columns([1, 1.15, 1])
    with col2:
        st.markdown('<div class="login-card">', unsafe_allow_html=True)
        st.markdown(
            """
            <div class="brand-block" style="justify-content:center; margin-bottom:14px;">
                <div class="brand-mark">📊</div>
            </div>
            <h2 style='text-align:center; color:#0F172A; margin:0;'>Monitoring Platform</h2>
            <p style='text-align:center; color:#64748B; font-size:13px; margin:4px 0 18px 0;'>
                Sign in to the Papua Pariwisata &amp; Transportasi intelligence platform
            </p>
            """,
            unsafe_allow_html=True,
        )
        st.divider()
        with st.form("login_form"):
            username = st.text_input("Username", placeholder="admin or user")
            password = st.text_input("Password", type="password", placeholder="Enter password")
            submit = st.form_submit_button("Sign in", type="primary", use_container_width=True)
            if submit:
                if username in USERS and USERS[username]["password"] == password:
                    st.session_state["authenticated"] = True
                    st.session_state["role"] = USERS[username]["role"]
                    st.session_state["name"] = USERS[username]["name"]
                    st.rerun()
                else:
                    st.error("Username or password is incorrect. Please try again.")
        st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

# ============================================================
# FILTER OPTIONS (Pariwisata)
# ============================================================
@st.cache_data
def get_filter_options():
    with etl_engine._get_connection() as conn:
        try:
            return pd.read_sql_query(
                f"SELECT DISTINCT kd_prov, jenis_akomodasi, year, month FROM {etl_engine.general_table_name}",
                conn,
            )
        except Exception:
            return pd.DataFrame()

df_info = get_filter_options()
prov_list = sorted(df_info["kd_prov"].dropna().astype(str).unique().tolist()) if not df_info.empty else []
year_list = sorted(df_info["year"].dropna().astype(int).unique().tolist()) if not df_info.empty else []
month_list = sorted(df_info["month"].dropna().astype(int).unique().tolist()) if not df_info.empty else []

# ============================================================
# SIDEBAR — brand, APP switcher (each app = one page), session
# ============================================================
APPS = [
    ("Pariwisata", "🏨", "Pariwisata (Akomodasi)"),
    ("Transportasi", "🚢", "Transportasi (Monit)"),
]

with st.sidebar:
    st.markdown(
        """
        <div class="brand-block">
            <div class="brand-mark">📊</div>
            <div>
                <p class="sidebar-title">Monitoring Platform</p>
                <p class="sidebar-subtitle">Papua Provinces</p>
            </div>
        </div>
        <br>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<p style='font-size:11px;color:#64748B;font-weight:700;letter-spacing:.06em;margin-bottom:6px;'>PILIH APLIKASI</p>", unsafe_allow_html=True)
    for key, icon, label in APPS:
        is_active = st.session_state["app"] == key
        if st.button(f"{icon}  {label}", use_container_width=True, key=f"app_{key}",
                     type="primary" if is_active else "secondary"):
            st.session_state["app"] = key
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    ai_online = get_gemini_client() is not None
    ai_status = "AI Engine Online" if ai_online else "AI Engine Offline"
    st.markdown(
        f"""
        <div class="user-card">
            <b>USER:</b> {st.session_state['name']}<br>
            <b>ROLE:</b> {st.session_state['role'].upper()}<br>
            <span class="status-dot"></span>{ai_status}
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Log out", use_container_width=True):
        st.session_state["authenticated"] = False
        st.rerun()

app = st.session_state["app"]

# ============================================================
# HELPER — province stat card (Bintang / Non-Bintang breakdown)
# ============================================================
def render_province_card(province, df_cur, df_prev):
    rows_html = ""
    for jenis, jenis_label in JENIS_LABELS.items():
        cur_val = df_cur[(df_cur["province"] == province) & (df_cur["jenis_akomodasi"] == jenis)]["val"]
        prev_val = df_prev[(df_prev["province"] == province) & (df_prev["jenis_akomodasi"] == jenis)]["val"]
        cur_val = cur_val.mean() if not cur_val.empty else np.nan
        prev_val = prev_val.mean() if not prev_val.empty else np.nan

        delta = (
            ((cur_val - prev_val) / prev_val * 100)
            if pd.notna(cur_val) and pd.notna(prev_val) and prev_val != 0
            else np.nan
        )
        value_display = f"{cur_val:.2f}%" if pd.notna(cur_val) else "—"

        if pd.isna(delta):
            delta_html = '<span class="stat-delta-na">‒ N/A</span>'
        else:
            arrow = "▲" if delta >= 0 else "▼"
            cls = "badge-up" if delta >= 0 else "badge-down"
            delta_html = f'<span class="{cls}">{arrow} {abs(delta):.1f}%</span>'

        rows_html += f"""
        <div class="stat-row">
            <div><span class="stat-label">{jenis_label}</span><span class="stat-value">{value_display}</span></div>
            {delta_html}
        </div>
        """

    st.markdown(
        f"""
        <div class="province-card">
            <div class="province-header">{province}</div>
            {rows_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ############################################################
# PAGE 1 — PARIWISATA (AKOMODASI)
# every original page becomes a tab
# ############################################################
def page_pariwisata():
    st.markdown('<div class="hero-title">🏨 Pariwisata — Tourism &amp; Accommodation Dashboard</div>', unsafe_allow_html=True)

    tab_labels = ["🏠 Home Dashboard", "🗺️ Infographic Stat Map", "📈 Trends Visualizations", "📋 Report"]
    if st.session_state["role"] == "admin":
        tab_labels.append("🛠️ Admin ETL Uploads")

    tabs = st.tabs(tab_labels)

    # ---------------- Home Dashboard ----------------
    with tabs[0]:
        st.markdown(f'<div class="hero-title" style="font-size:20px;">👋 Welcome back, {st.session_state["name"]}</div>', unsafe_allow_html=True)

        if not df_info.empty:
            latest_year, latest_month = year_list[-1], month_list[-1]
            with etl_engine._get_connection() as conn:
                df_latest = pd.read_sql_query(
                    f"SELECT AVG(tpk) as tpk, AVG(rlmtgab) as rlmtgab FROM {etl_engine.general_table_name} "
                    "WHERE year = ? AND month = ?",
                    conn,
                    params=(latest_year, latest_month),
                )
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Provinces Tracked", len(TARGET_PROVINCES))
            m2.metric("Latest Period", f"{month_name(latest_month)} {latest_year}")
            m3.metric("Avg. TPK (latest)", f"{df_latest['tpk'].iloc[0]:.1f}%" if pd.notna(df_latest['tpk'].iloc[0]) else "—")
            m4.metric(
                "Avg. RLMTGAB (latest)",
                f"{df_latest['rlmtgab'].iloc[0]:.1f} malam" if pd.notna(df_latest['rlmtgab'].iloc[0]) else "—",
            )

            card_open("Data Coverage")
            st.write(f"Records span **{month_name(month_list[0])} {year_list[0]}** through "
                     f"**{month_name(month_list[-1])} {year_list[-1]}**, covering "
                     f"{len(prov_list)} province(s) and Hotel Bintang / Non Bintang classifications.")
            st.caption("Use the tabs above to jump to the Infographic map, trend charts, or the AI-narrated report.")
            card_close()
        else:
            card_open()
            st.info(
                "No data has been ingested yet. If you're an admin, head to **Admin ETL Uploads** "
                "to load the first Excel matrix."
            )
            card_close()

    # ---------------- Infographic Stat Map ----------------
    with tabs[1]:
        st.markdown('<div class="search-bar">', unsafe_allow_html=True)
        search_term = st.text_input(
            "Search", placeholder="🔍 Search a province…", label_visibility="collapsed", key="pw_search"
        )
        st.markdown("</div><br>", unsafe_allow_html=True)

        st.markdown('<div class="filter-pill">', unsafe_allow_html=True)
        f_col1, f_col2, f_col3 = st.columns(3)
        with f_col1:
            map_indicator = st.selectbox(
                "Select Indicator",
                options=[("tpk", "TPK (Occupancy Rate)"), ("rlmtgab", "RLMTGAB (Length of Stay)")],
                format_func=lambda x: x[1],
                label_visibility="collapsed", key="pw_indicator",
            )[0]
        with f_col2:
            map_year = st.selectbox(
                "Select Year", options=year_list, index=len(year_list) - 1 if year_list else 0,
                label_visibility="collapsed", key="pw_map_year",
            )
        with f_col3:
            map_month = st.selectbox(
                "Select Month", options=month_list, format_func=month_name,
                label_visibility="collapsed", key="pw_map_month",
            )
        st.markdown("</div>", unsafe_allow_html=True)

        if map_indicator and map_year and map_month:
            prev_month = (map_month - 1) if map_month > 1 else 12
            prev_year = map_year if map_month > 1 else (map_year - 1)

            query = f"""
                SELECT kd_prov AS province, jenis_akomodasi, month, year, AVG({map_indicator}) as val
                FROM {etl_engine.general_table_name}
                WHERE year IN (?, ?) AND month IN (?, ?)
                GROUP BY kd_prov, jenis_akomodasi, month, year
            """
            with etl_engine._get_connection() as conn:
                df_infographic = pd.read_sql_query(query, conn, params=(map_year, prev_year, map_month, prev_month))

            if df_infographic.empty:
                card_open()
                st.info(
                    "No records match this period yet. Try a different month/year, or ask an "
                    "admin to ingest data for this range in **Admin ETL Uploads**."
                )
                card_close()
            else:
                df_cur = df_infographic[(df_infographic["year"] == map_year) & (df_infographic["month"] == map_month)]
                df_prev = df_infographic[(df_infographic["year"] == prev_year) & (df_infographic["month"] == prev_month)]

                period_label = f"{month_name(map_month)} {map_year}"
                st.markdown(f'<div class="hero-title" style="font-size:20px;">Papua Regional Performance — {period_label}</div>', unsafe_allow_html=True)

                left_provs = [p for p in LEFT_PROVINCES if not search_term or search_term.lower() in p.lower()]
                right_provs = [p for p in RIGHT_PROVINCES if not search_term or search_term.lower() in p.lower()]

                col_left, col_map, col_right = st.columns([1.1, 2.2, 1.1])

                with col_left:
                    for prov in left_provs:
                        render_province_card(prov, df_cur, df_prev)

                with col_map:
                    if not gdf_provinces.empty:
                        merged_gdf = gdf_provinces.merge(
                            df_cur.groupby("province")["val"].mean().reset_index(),
                            left_on="PROVINSI", right_on="province", how="inner",
                        )
                        merged_gdf = merged_gdf[merged_gdf["PROVINSI"].isin(TARGET_PROVINCES)]

                        gdf_projected = merged_gdf.to_crs(epsg=32753)
                        wgs84_centroids = gdf_projected.geometry.centroid.to_crs(epsg=4326)
                        merged_gdf["lat"] = wgs84_centroids.y
                        merged_gdf["lon"] = wgs84_centroids.x

                        fig_map = px.choropleth(
                            merged_gdf, geojson=merged_gdf.geometry, locations=merged_gdf.index, color="val",
                            color_continuous_scale=[[0, "#3A2A0E"], [0.5, PRIMARY], [1, "#FDE68A"]],
                            hover_name="PROVINSI", hover_data={"val": ":.2f"},
                        )
                        fig_scatter = px.scatter_geo(merged_gdf, lat="lat", lon="lon", text="PROVINSI")
                        fig_scatter.update_traces(
                            marker=dict(size=11, color="#FDE68A", symbol="circle", line=dict(width=1.5, color=MAP_BG)),
                            textfont=dict(color="#F1F5F9", size=10),
                        )
                        for trace in fig_scatter.data:
                            fig_map.add_trace(trace)
                        fig_map.update_geos(fitbounds="locations", visible=False, bgcolor="rgba(0,0,0,0)")
                        fig_map.update_layout(showlegend=False, coloraxis_colorbar=dict(title="val", tickfont=dict(color="#F1F5F9")))
                        plotly_theme(fig_map, height=460, dark=True)

                        st.markdown('<div class="map-panel">', unsafe_allow_html=True)
                        st.plotly_chart(fig_map, use_container_width=True)
                        st.markdown("</div>", unsafe_allow_html=True)
                    else:
                        card_open()
                        st.warning("Map geometry file (papua_provinces.parquet) could not be loaded.")
                        card_close()

                    csv_data = df_cur.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        "📥 Download Summary CSV", data=csv_data,
                        file_name=f"infographic_{map_indicator}_{map_year}_{map_month}.csv", mime="text/csv",
                        use_container_width=True, key="pw_dl_csv",
                    )

                with col_right:
                    for prov in right_provs:
                        render_province_card(prov, df_cur, df_prev)

    # ---------------- Trends Visualizations ----------------
    with tabs[2]:
        st.markdown('<div class="filter-container">', unsafe_allow_html=True)
        v_col1, v_col2, v_col3 = st.columns(3)
        with v_col1:
            viz_prov = st.selectbox("Select Province", options=prov_list, key="v_prov")
        with v_col2:
            viz_year = st.selectbox("Select Year", options=year_list, key="v_year")
        with v_col3:
            viz_month = st.selectbox(
                "Select Month for Comparison", options=month_list, format_func=month_name, key="v_month"
            )
        st.markdown("</div>", unsafe_allow_html=True)

        if viz_prov and viz_year and viz_month:
            trend_query = f"""
                SELECT jenis_akomodasi, month, AVG(tpk) as tpk, AVG(rlmtgab) as rlmtgab
                FROM {etl_engine.general_table_name}
                WHERE kd_prov = ? AND year = ?
                GROUP BY jenis_akomodasi, month
                ORDER BY month
            """
            with etl_engine._get_connection() as conn:
                df_agg = pd.read_sql_query(trend_query, conn, params=(viz_prov, viz_year))

            if not df_agg.empty:
                for jenis in df_agg["jenis_akomodasi"].unique():
                    sub_df = df_agg[df_agg["jenis_akomodasi"] == jenis]
                    df_melted = sub_df.melt(
                        id_vars=["month"], value_vars=["tpk", "rlmtgab"], var_name="Indicator", value_name="Value"
                    )
                    df_melted["Indicator"] = df_melted["Indicator"].replace(
                        {"tpk": "TPK (Occupancy Rate)", "rlmtgab": "RLMTGAB (Length of Stay)"}
                    )
                    fig = px.line(
                        df_melted, x="month", y="Value", color="Indicator", markers=True,
                        color_discrete_map={"TPK (Occupancy Rate)": PRIMARY, "RLMTGAB (Length of Stay)": "#334155"},
                    )
                    fig.update_traces(line=dict(width=3), marker=dict(size=8))
                    plotly_theme(fig, height=380)

                    card_open(f"Monthly Performance — {jenis}", f"{viz_prov} · {viz_year}")
                    st.plotly_chart(fig, use_container_width=True)
                    card_close()
            else:
                card_open()
                st.info("No trend data found for this province and year yet.")
                card_close()

    # ---------------- Report ----------------
    with tabs[3]:
        st.markdown('<div class="filter-container">', unsafe_allow_html=True)
        r_col1, r_col2, r_col3 = st.columns(3)
        with r_col1:
            rep_prov = st.selectbox("Province", options=prov_list, key="rep_prov")
        with r_col2:
            rep_year = st.selectbox("Year", options=year_list, key="rep_year")
        with r_col3:
            rep_month = st.selectbox("Month", options=month_list, format_func=month_name, key="rep_month")
        st.markdown("</div>", unsafe_allow_html=True)

        if rep_prov and rep_year and rep_month:
            card_open()
            generate_akomodasi_tables(etl_engine, rep_prov, rep_year, rep_month)
            card_close()

    # ---------------- Admin ETL Uploads ----------------
    if st.session_state["role"] == "admin":
        with tabs[4]:
            card_open("Admin Control Panel", "ETL data ingestion")
            st.markdown(
                f"<p style='color:{INK_DIM};'>Upload source Excel matrices directly into the SQLite "
                "database and run system maintenance.</p>",
                unsafe_allow_html=True,
            )
            st.divider()

            uploaded_files = st.file_uploader("Upload Excel Source Files (.xlsx)", type=["xlsx"],
                                               accept_multiple_files=True, key="pw_uploader")

            adm_col1, adm_col2 = st.columns(2)
            with adm_col1:
                target_year = st.number_input("Target Year", value=2026, key="pw_target_year")
            with adm_col2:
                target_month = st.selectbox("Target Month", options=list(range(1, 13)), format_func=month_name, key="pw_target_month")

            if st.button("🚀 Process & Ingest Files", type="primary", key="pw_process_btn"):
                if uploaded_files:
                    with st.spinner("Ingesting files into the database…"):
                        for uploaded_file in uploaded_files:
                            etl_engine.etl_pipeline(uploaded_file, year=int(target_year), month=int(target_month))
                    st.success(f"{len(uploaded_files)} file(s) successfully ingested into the database.")
                    get_filter_options.clear()
                else:
                    st.warning("Please upload at least one Excel file before processing.")
            card_close()


# ############################################################
# PAGE 2 — TRANSPORTASI (MONIT)
# every original R/Shiny module (mod_upload, mod_update,
# mod_dashboard, mod_konfirmasi) becomes a tab. Nothing dropped.
# ############################################################
def page_transportasi():
    st.markdown('<div class="hero-title">🚢 Transportasi — Monit Transportasi Papua Tengah</div>', unsafe_allow_html=True)

    tab_labels = [
        "⬆️ Upload &amp; Ekstrak", "✏️ Update Manual", "📊 Dashboard",
        "🔎 Konfirmasi Anomali", "🗄️ Database Master",
    ]
    # st.tabs doesn't render HTML, keep plain labels
    tab_labels = [
        "⬆️ Upload & Ekstrak", "✏️ Update Manual", "📊 Dashboard",
        "🔎 Konfirmasi Anomali", "🗄️ Database Master",
    ]
    tabs = st.tabs(tab_labels)

    # ---------------- Tab 1: mod_upload.R — Upload & Ekstrak Data Bulanan Baru ----------------
    with tabs[0]:
        card_open("Upload & Ekstrak Data Bulanan Baru")
        col1, col2 = st.columns(2)
        with col1:
            up_moda = st.selectbox("Moda Transportasi", options=["Laut", "Udara"], key="tp_up_moda")
        with col2:
            up_file = st.file_uploader("Pilih File Excel Bulanan Baru (.xlsx)", type=["xlsx"], key="tp_up_file")

        if st.button("Proses & Update ke Database Master", type="primary", key="tp_up_btn"):
            if up_file is None:
                st.warning("Silakan pilih file Excel terlebih dahulu.")
            else:
                with st.spinner("Memproses file... Mohon tunggu."):
                    data_insert, msg = transport_engine.process_upload(up_file, up_moda)
                if "Sukses" in msg:
                    st.success(msg)
                    if not data_insert.empty:
                        st.dataframe(data_insert, use_container_width=True, hide_index=True)
                else:
                    st.error(msg)
        card_close()

    # ---------------- Tab 2: mod_update.R — Update Data Bulanan Baru (manual form) ----------------
    with tabs[1]:
        card_open("Update Data Bulanan Baru (Input Manual)")
        c1, c2, c3 = st.columns(3)
        with c1:
            um_moda = st.selectbox("Moda Transportasi", options=["Laut", "Udara"], key="tp_um_moda")
        with c2:
            um_bulan = st.selectbox("Bulan", options=list(range(1, 13)),
                                     format_func=month_name_id, key="tp_um_bulan")
        with c3:
            um_tahun = st.selectbox("Tahun", options=list(range(2025, 2031)), index=1, key="tp_um_tahun")

        st.divider()
        st.markdown("##### Masukkan Nilai Data Baru:")

        combo = transport_engine.get_kategori_lokasi(um_moda)
        input_values = []
        if combo.empty:
            st.info("Belum ada kombinasi kategori-lokasi untuk moda ini. Lakukan upload data pada tab "
                    "**Upload & Ekstrak** terlebih dahulu agar form input manual dapat dibangun otomatis.")
        else:
            n_cols = 2
            cols = st.columns(n_cols)
            for i, row in combo.reset_index(drop=True).iterrows():
                label_input = f"{row['kategori']} - {row['lokasi']}"
                with cols[i % n_cols]:
                    val = st.number_input(label_input, value=0.0, key=f"tp_um_val_{um_moda}_{i}")
                input_values.append(val)

        if st.button("Simpan & Gabungkan Data", type="primary", key="tp_um_btn"):
            if combo.empty:
                st.warning("Tidak ada form untuk disimpan.")
            else:
                status = transport_engine.manual_update(um_moda, um_tahun, um_bulan, input_values)
                st.success(status) if "berhasil" in status else st.error(status)
        card_close()

    # ---------------- Tab 3: mod_dashboard.R — Dashboard ----------------
    with tabs[2]:
        df_all_transport = transport_engine.read_all()
        summary, trend = transport_engine.dashboard_summary(df_all_transport)

        st.caption(
            "Ringkasan mengikuti kategori yang tersedia pada skema database master_transportasi "
            "(Berangkat / Datang / Bongkar / Muat)."
        )
        b1, b2, b3, b4 = st.columns(4)
        with b1:
            card_open()
            st.markdown('<span class="stat-label">Penumpang Berangkat</span>', unsafe_allow_html=True)
            st.markdown(f'<span class="stat-value" style="font-size:26px;">{summary["penumpang_berangkat"]:,.0f}</span>', unsafe_allow_html=True)
            card_close()
        with b2:
            card_open()
            st.markdown('<span class="stat-label">Penumpang Datang</span>', unsafe_allow_html=True)
            st.markdown(f'<span class="stat-value" style="font-size:26px;">{summary["penumpang_datang"]:,.0f}</span>', unsafe_allow_html=True)
            card_close()
        with b3:
            card_open()
            st.markdown('<span class="stat-label">Cargo Bongkar</span>', unsafe_allow_html=True)
            st.markdown(f'<span class="stat-value" style="font-size:26px;">{summary["cargo_bongkar"]:,.0f}</span>', unsafe_allow_html=True)
            card_close()
        with b4:
            card_open()
            st.markdown('<span class="stat-label">Cargo Muat</span>', unsafe_allow_html=True)
            st.markdown(f'<span class="stat-value" style="font-size:26px;">{summary["cargo_muat"]:,.0f}</span>', unsafe_allow_html=True)
            card_close()

        card_open("Tren Bulanan", "semua moda & lokasi")
        if trend.empty:
            st.info("Belum ada data untuk ditampilkan. Silakan upload data pada tab **Upload & Ekstrak**.")
        else:
            fig_trend = px.line(
                trend, x="bulan", y="nilai", color="kategori", markers=True,
                color_discrete_map={"Berangkat": PRIMARY, "Datang": "#334155", "Bongkar": POSITIVE, "Muat": NEGATIVE},
            )
            fig_trend.update_traces(line=dict(width=3), marker=dict(size=7))
            fig_trend.update_xaxes(tickmode="array", tickvals=list(range(1, 13)), ticktext=MONTH_NAMES_ID)
            plotly_theme(fig_trend, height=400)
            st.plotly_chart(fig_trend, use_container_width=True)
        card_close()

    # ---------------- Tab 4: mod_konfirmasi.R — Konfirmasi Anomali ----------------
    with tabs[3]:
        card_open("Konfirmasi Anomali Antar Bulan")
        k1, k2, k3 = st.columns(3)
        with k1:
            kf_moda = st.selectbox("Moda", options=["Semua", "Laut", "Udara"], key="tp_kf_moda")
        with k2:
            kf_bulan1 = st.selectbox("Bulan Referensi", options=list(range(1, 13)),
                                      format_func=month_name_id, key="tp_kf_bulan1")
        with k3:
            kf_bulan2 = st.selectbox("Bulan Pembanding", options=list(range(1, 13)),
                                      index=1, format_func=month_name_id, key="tp_kf_bulan2")

        hasil = transport_engine.konfirmasi_anomali(kf_bulan1, kf_bulan2, moda=kf_moda)
        if hasil.empty:
            st.info("Belum ada data untuk dibandingkan. Silakan upload data terlebih dahulu.")
        else:
            styled = hasil.style.background_gradient(
                cmap="RdYlGn", subset=["perubahan_persen"], vmin=-50, vmax=50
            ).format({"nilai_bulan1": "{:,.0f}", "nilai_bulan2": "{:,.0f}", "perubahan_persen": "{:+.2f}%"}, na_rep="-")
            st.dataframe(styled, use_container_width=True, hide_index=True)
            csv_data = hasil.to_csv(index=False).encode("utf-8")
            st.download_button("📥 Download Perbandingan CSV", data=csv_data,
                                file_name=f"konfirmasi_anomali_bulan{kf_bulan1}_vs_{kf_bulan2}.csv",
                                mime="text/csv", key="tp_kf_dl")
        card_close()

    # ---------------- Tab 5: "Lihat Database Master" (app.R nav_panel) ----------------
    with tabs[4]:
        card_open("Isi Database SQLite Saat Ini", "master_transportasi")
        df_master = transport_engine.read_all()
        if df_master.empty:
            st.info("Database master transportasi masih kosong.")
        else:
            search = st.text_input("🔍 Cari (moda / kategori / lokasi)", key="tp_db_search")
            view_df = df_master.copy()
            if search:
                mask = (
                    view_df["moda"].astype(str).str.contains(search, case=False, na=False)
                    | view_df["kategori"].astype(str).str.contains(search, case=False, na=False)
                    | view_df["lokasi"].astype(str).str.contains(search, case=False, na=False)
                )
                view_df = view_df[mask]
            st.dataframe(view_df, use_container_width=True, hide_index=True)
            st.caption(f"Menampilkan {len(view_df):,} dari {len(df_master):,} baris.")
        card_close()


# ============================================================
# ROUTER
# ============================================================
if app == "Pariwisata":
    page_pariwisata()
elif app == "Transportasi":
    page_transportasi()

# ============================================================
# FOOTER
# ============================================================
st.markdown(
    '<p class="app-footer">Pariwisata &amp; Transportasi Papua · Monitoring Platform — data sourced from BPS '
    "provincial hotel occupancy matrices and Monit Transportasi (Laut/Udara)</p>",
    unsafe_allow_html=True,
)
