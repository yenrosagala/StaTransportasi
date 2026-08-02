import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
import geopandas as gpd

from modules import akomodasi_engine as eng

TARGET_PROVINCES = ["Papua", "Papua Tengah", "Papua Pegunungan", "Papua Selatan"]
LEFT_PROVINCES = ["Papua Tengah", "Papua Selatan"]
RIGHT_PROVINCES = ["Papua", "Papua Pegunungan"]
JENIS_LABELS = {"Hotel Bintang": "Klasifikasi Bintang", "Hotel Non Bintang": "Klasifikasi NonBintang"}
PRIMARY, MAP_BG = "#F59E0B", "#0B0F14"


def month_name(m):
    return pd.to_datetime(str(int(m)), format="%m").strftime("%B") if m else ""


@st.cache_data(ttl=300)
def _load_geodata():
    return gpd.read_parquet("papua_provinces.parquet")


def _is_admin():
    return st.session_state.get("admin_logged_in", False)


def render_province_card(province, df_cur, df_prev):
    rows_html = ""
    for jenis, jenis_label in JENIS_LABELS.items():
        cur_val = df_cur[(df_cur["kd_prov"] == province) & (df_cur["jenis_akomodasi"] == jenis)]["val"]
        prev_val = df_prev[(df_prev["kd_prov"] == province) & (df_prev["jenis_akomodasi"] == jenis)]["val"]
        cur_val = cur_val.mean() if not cur_val.empty else np.nan
        prev_val = prev_val.mean() if not prev_val.empty else np.nan
        delta = ((cur_val - prev_val) / prev_val * 100) if pd.notna(cur_val) and pd.notna(prev_val) and prev_val != 0 else np.nan
        value_display = f"{cur_val:.2f}%" if pd.notna(cur_val) else "—"
        if pd.isna(delta):
            delta_html = '<span style="color:#94A3B8;font-size:12px;">‒ N/A</span>'
        else:
            arrow = "▲" if delta >= 0 else "▼"
            color = "#10B981" if delta >= 0 else "#EF4444"
            delta_html = f'<span style="color:{color};font-weight:700;font-size:12px;">{arrow} {abs(delta):.1f}%</span>'
        rows_html += f"""
        <div style="display:flex;justify-content:space-between;align-items:center;padding:10px 4px;border-bottom:1px solid #F1F5F9;">
            <div><span style="font-size:11px;color:#64748B;display:block;">{jenis_label}</span>
            <span style="font-size:17px;font-weight:700;color:#0F172A;">{value_display}</span></div>
            {delta_html}
        </div>"""
    st.markdown(
        f"""<div style="border:1px solid #E2E8F0;border-radius:12px;overflow:hidden;margin-bottom:14px;">
        <div style="background:{PRIMARY};color:#fff;font-weight:700;font-size:12px;text-align:center;padding:8px;text-transform:uppercase;">{province}</div>
        <div style="padding:0 12px;">{rows_html}</div></div>""",
        unsafe_allow_html=True,
    )


def show_pariwisata_page():
    st.title("🏨 Pariwisata — Dashboard Akomodasi (TPK & RLMTGAB)")

    df_info = eng.get_filter_options()
    prov_list = sorted(df_info["kd_prov"].dropna().astype(str).unique().tolist()) if not df_info.empty else []
    year_list = sorted(df_info["tahun"].dropna().astype(int).unique().tolist()) if not df_info.empty else []
    month_list = sorted(df_info["bulan"].dropna().astype(int).unique().tolist()) if not df_info.empty else []

    tab_labels = ["🏠 Home", "🗺️ Infographic Stat Map", "📈 Trends", "📋 Report (AI Narrative)"]
    if _is_admin():
        tab_labels.append("🛠️ Admin ETL Upload")
    tabs = st.tabs(tab_labels)
    tmap = dict(zip(tab_labels, tabs))

    # ---------------- Home ----------------
    with tmap["🏠 Home"]:
        if df_info.empty:
            st.info(
                "Belum ada data akomodasi yang diunggah. Login sebagai admin pada halaman "
                "**Analisis Series & Admin**, lalu buka tab **Admin ETL Upload** di sini untuk mengunggah data pertama."
            )
        else:
            latest_year, latest_month = year_list[-1], month_list[-1]
            df_latest = eng.query_period(tahun=latest_year, bulan=latest_month)
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Provinsi Terpantau", len(TARGET_PROVINCES))
            m2.metric("Periode Terbaru", f"{month_name(latest_month)} {latest_year}")
            m3.metric("Rata-rata TPK", f"{df_latest['tpk'].mean():.1f}%" if not df_latest.empty else "—")
            m4.metric("Rata-rata RLMTGAB", f"{df_latest['rlmtgab'].mean():.1f} malam" if not df_latest.empty else "—")
            st.info(
                f"Data mencakup periode **{month_name(month_list[0])} {year_list[0]}** s.d. "
                f"**{month_name(month_list[-1])} {year_list[-1]}**, {len(prov_list)} provinsi, "
                "klasifikasi Hotel Bintang / Non Bintang."
            )

    # ---------------- Infographic Stat Map ----------------
    with tmap["🗺️ Infographic Stat Map"]:
        if not month_list:
            st.info("Belum ada data untuk ditampilkan pada peta.")
        else:
            f1, f2, f3 = st.columns(3)
            with f1:
                map_indicator = st.selectbox(
                    "Indikator", options=[("tpk", "TPK (Occupancy Rate)"), ("rlmtgab", "RLMTGAB (Length of Stay)")],
                    format_func=lambda x: x[1], key="pw_map_ind",
                )[0]
            with f2:
                map_year = st.selectbox("Tahun", options=year_list, index=len(year_list) - 1, key="pw_map_year")
            with f3:
                map_month = st.selectbox("Bulan", options=month_list, format_func=month_name, key="pw_map_month")

            prev_month = map_month - 1 if map_month > 1 else 12
            prev_year = map_year if map_month > 1 else map_year - 1

            df_cur_raw = eng.query_period(tahun=map_year, bulan=map_month)
            df_prev_raw = eng.query_period(tahun=prev_year, bulan=prev_month)

            if df_cur_raw.empty:
                st.warning("Tidak ada data untuk periode ini.")
            else:
                df_cur = df_cur_raw.groupby(["kd_prov", "jenis_akomodasi"], as_index=False)[map_indicator].mean().rename(columns={map_indicator: "val"})
                df_prev = (df_prev_raw.groupby(["kd_prov", "jenis_akomodasi"], as_index=False)[map_indicator].mean().rename(columns={map_indicator: "val"})
                           if not df_prev_raw.empty else pd.DataFrame(columns=["kd_prov", "jenis_akomodasi", "val"]))

                col_left, col_map, col_right = st.columns([1.1, 2.2, 1.1])
                with col_left:
                    for p in LEFT_PROVINCES:
                        render_province_card(p, df_cur, df_prev)
                with col_map:
                    try:
                        gdf = _load_geodata()
                        merged = gdf.merge(df_cur.groupby("kd_prov")["val"].mean().reset_index(),
                                            left_on="PROVINSI", right_on="kd_prov", how="inner")
                        merged = merged[merged["PROVINSI"].isin(TARGET_PROVINCES)]
                        proj = merged.to_crs(epsg=32753)
                        cent = proj.geometry.centroid.to_crs(epsg=4326)
                        merged["lat"], merged["lon"] = cent.y, cent.x

                        fig = px.choropleth(
                            merged, geojson=merged.geometry, locations=merged.index, color="val",
                            color_continuous_scale=[[0, "#3A2A0E"], [0.5, PRIMARY], [1, "#FDE68A"]],
                            hover_name="PROVINSI", hover_data={"val": ":.2f"},
                        )
                        sc = px.scatter_geo(merged, lat="lat", lon="lon", text="PROVINSI")
                        sc.update_traces(marker=dict(size=11, color="#FDE68A", line=dict(width=1.5, color=MAP_BG)),
                                          textfont=dict(color="#F1F5F9", size=10))
                        for tr in sc.data:
                            fig.add_trace(tr)
                        fig.update_geos(fitbounds="locations", visible=False, bgcolor="rgba(0,0,0,0)")
                        fig.update_layout(showlegend=False, height=460, paper_bgcolor="rgba(0,0,0,0)",
                                           margin=dict(l=0, r=0, t=10, b=0))
                        st.plotly_chart(fig, use_container_width=True)
                    except Exception as e:
                        st.warning(f"Peta tidak dapat dimuat: {e}")

                    csv = df_cur.to_csv(index=False).encode("utf-8")
                    st.download_button("📥 Download Ringkasan CSV", data=csv,
                                        file_name=f"akomodasi_{map_indicator}_{map_year}_{map_month}.csv",
                                        mime="text/csv", use_container_width=True)
                with col_right:
                    for p in RIGHT_PROVINCES:
                        render_province_card(p, df_cur, df_prev)

    # ---------------- Trends ----------------
    with tmap["📈 Trends"]:
        if not prov_list:
            st.info("Belum ada data untuk ditampilkan.")
        else:
            v1, v2 = st.columns(2)
            with v1:
                viz_prov = st.selectbox("Provinsi", options=prov_list, key="pw_v_prov")
            with v2:
                viz_year = st.selectbox("Tahun", options=year_list, key="pw_v_year")

            df_agg = eng.query_period(kd_prov=viz_prov, tahun=viz_year)
            if df_agg.empty:
                st.info("Belum ada data tren untuk provinsi dan tahun ini.")
            else:
                trend = df_agg.groupby(["jenis_akomodasi", "bulan"], as_index=False)[["tpk", "rlmtgab"]].mean().sort_values("bulan")
                for jenis in trend["jenis_akomodasi"].unique():
                    sub = trend[trend["jenis_akomodasi"] == jenis]
                    melted = sub.melt(id_vars=["bulan"], value_vars=["tpk", "rlmtgab"], var_name="Indikator", value_name="Nilai")
                    melted["Indikator"] = melted["Indikator"].replace({"tpk": "TPK (%)", "rlmtgab": "RLMTGAB (malam)"})
                    fig = px.line(melted, x="bulan", y="Nilai", color="Indikator", markers=True,
                                  title=f"{jenis} — {viz_prov} ({viz_year})",
                                  color_discrete_map={"TPK (%)": PRIMARY, "RLMTGAB (malam)": "#334155"})
                    fig.update_traces(line=dict(width=3), marker=dict(size=7))
                    fig.update_layout(height=380, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                    st.plotly_chart(fig, use_container_width=True)

    # ---------------- Report (AI narrative) ----------------
    with tmap["📋 Report (AI Narrative)"]:
        if not prov_list:
            st.info("Belum ada data untuk laporan.")
        else:
            r1, r2, r3 = st.columns(3)
            with r1:
                rep_prov = st.selectbox("Provinsi", options=prov_list, key="pw_rep_prov")
            with r2:
                rep_year = st.selectbox("Tahun", options=year_list, key="pw_rep_year")
            with r3:
                rep_month = st.selectbox("Bulan", options=month_list, format_func=month_name, key="pw_rep_month")

            if rep_prov and rep_year and rep_month:
                _render_report(rep_prov, rep_year, rep_month)

    # ---------------- Admin ETL Upload (admin only) ----------------
    if _is_admin():
        with tmap["🛠️ Admin ETL Upload"]:
            st.caption(
                "Login admin ini sama dengan login pada halaman **Analisis Series & Admin** "
                "(sekali login, berlaku di seluruh aplikasi)."
            )
            uploaded_files = st.file_uploader(
                "Upload File Excel Sumber (Sheet 'Prov_Jenis_Kelas') — bisa lebih dari satu file",
                type=["xlsx"], accept_multiple_files=True, key="pw_admin_upload",
            )
            c1, c2 = st.columns(2)
            with c1:
                target_year = st.number_input("Tahun Target", value=2026, key="pw_admin_year")
            with c2:
                target_month = st.selectbox("Bulan Target", options=list(range(1, 13)), format_func=month_name, key="pw_admin_month")

            if st.button("🚀 Proses & Simpan ke Database", type="primary", key="pw_admin_btn"):
                if not uploaded_files:
                    st.warning("Silakan unggah minimal satu file Excel.")
                else:
                    n_ok = 0
                    for f in uploaded_files:
                        ok, msg = eng.etl_pipeline(f, year=int(target_year), month=int(target_month))
                        (st.success if ok else st.error)(msg)
                        n_ok += int(ok)
                    if n_ok:
                        st.balloons()
                        eng.get_filter_options.clear() if hasattr(eng.get_filter_options, "clear") else None
                        st.cache_data.clear()


def _render_report(province, year, month):
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    last_year = year - 1

    df_current = eng.query_period(kd_prov=province, tahun=year, bulan=month)
    df_prev = eng.query_period(kd_prov=province, tahun=prev_year, bulan=prev_month)
    df_last = eng.query_period(kd_prov=province, tahun=last_year, bulan=month)

    if df_current.empty:
        st.warning(f"Tidak ada data periode berjalan untuk {province} pada {month}/{year}.")
        return

    st.markdown(f"### 📋 Executive Summary — {province} ({month_name(month)} {year})")
    st.caption("Analisis metrik akomodasi, tingkat penghunian kamar (TPK), dan lama menginap (RLMTGAB).")

    client = eng.get_gemini_client()
    indicators = ["tpk", "rlmtgab"]
    jenis_types = sorted(df_current["jenis_akomodasi"].dropna().unique().tolist())

    base_prompt = (
        "Anda adalah Kepala Pusat Statistik / Penasihat Kebijakan Utama yang menyusun ringkasan eksekutif "
        "strategis berstandar tinggi bagi Dewan Pimpinan dan Pengambil Kebijakan.\n"
        f"Buatlah narasi Executive Summary tingkat tinggi yang padat dan tajam (tepat 2 paragraf) untuk "
        f"indikator statistik Wilayah Provinsi {province} periode komparasi {year}-{month} terhadap {prev_year}-{prev_month}.\n\n"
        "Pedoman: Paragraf 1 = kinerja bulanan (MTM) & tren sektoral. Paragraf 2 = kinerja kumulatif (YoY) & "
        "deviasi pertumbuhan. Gunakan diksi birokratik profesional dan format angka Indonesia. Jangan sertakan "
        "pengantar/penutup — langsung 2 paragraf dipisah satu baris kosong."
    )

    for indicator in indicators:
        for jenis in jenis_types:
            with st.container(border=True):
                st.markdown(f"#### Indikator: {indicator.upper()} — {jenis}")

                cur = df_current[df_current["jenis_akomodasi"] == jenis][["kelas_akomodasi", indicator]].rename(columns={indicator: "current"})
                prv = df_prev[df_prev["jenis_akomodasi"] == jenis][["kelas_akomodasi", indicator]].rename(columns={indicator: "prev"}) if not df_prev.empty else pd.DataFrame(columns=["kelas_akomodasi", "prev"])
                lst = df_last[df_last["jenis_akomodasi"] == jenis][["kelas_akomodasi", indicator]].rename(columns={indicator: "last_year"}) if not df_last.empty else pd.DataFrame(columns=["kelas_akomodasi", "last_year"])

                merged = cur.merge(prv, on="kelas_akomodasi", how="outer").merge(lst, on="kelas_akomodasi", how="outer")
                merged = merged.dropna(subset=["kelas_akomodasi"])
                merged["change_prev"] = np.where(merged["prev"].notna(), merged["current"] - merged["prev"], np.nan)
                merged["change_last"] = np.where(merged["last_year"].notna(), merged["current"] - merged["last_year"], np.nan)

                def format_kelas(val, jenis=jenis):
                    if pd.isna(val):
                        return "Undefined Class"
                    try:
                        iv = int(val)
                    except (ValueError, TypeError):
                        return str(val)
                    return f"Bintang {iv}" if jenis == "Hotel Bintang" else f"Kelas {iv}"

                merged["nama_kelas"] = merged["kelas_akomodasi"].apply(format_kelas)
                disp = merged[["nama_kelas", "last_year", "prev", "current", "change_prev", "change_last"]].set_index("nama_kelas").round(2)
                avg_row = pd.DataFrame({c: [disp[c].mean()] for c in disp.columns}, index=["Average"]).round(2)
                final_table = pd.concat([disp, avg_row])
                for c in ["change_prev", "change_last"]:
                    final_table[c] = final_table[c].apply(lambda x: f"{x:+.2f} pts" if pd.notna(x) else "-")

                report_type = f"akomodasi_{jenis}_{indicator}"
                period_key = f"{province}|{year}|{month}"

                if _is_admin():
                    if st.button(f"🔄 Regenerate ({jenis} - {indicator.upper()})", key=f"pw_regen_{report_type}_{period_key}"):
                        eng.delete_narrative(report_type, period_key)
                        st.rerun()

                cached = eng.get_cached_narrative(report_type, period_key)
                if cached:
                    st.markdown(f'<div style="background:#f8fafc;padding:14px;border-radius:10px;border-left:4px solid {PRIMARY};">'
                                f'<strong>🤖 Narasi AI (dari cache):</strong><br>{cached}</div>', unsafe_allow_html=True)
                elif client:
                    prompt = f"Table summary for {indicator.upper()} ({jenis}) in {province}:\n" + final_table.to_markdown() + "\n" + base_prompt
                    try:
                        with st.spinner(f"Menyusun narasi {jenis} {indicator.upper()}..."):
                            resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
                            narrative = resp.text
                            eng.save_narrative(report_type, period_key, narrative)
                        st.markdown(f'<div style="background:#f8fafc;padding:14px;border-radius:10px;border-left:4px solid {PRIMARY};">'
                                    f'<strong>🤖 Narasi AI (baru dibuat):</strong><br>{narrative}</div>', unsafe_allow_html=True)
                    except Exception as e:
                        st.error(f"Gagal membuat narasi AI: {e}")
                else:
                    st.info("Narasi AI dilewati (Gemini client belum dikonfigurasi).")

                st.dataframe(final_table, use_container_width=True)
