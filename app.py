import streamlit as st
from modules.admin_page import show_series_admin_page
from modules.dashboard_page import show_dashboard_page
from modules.report_page import show_report_page
from modules.pariwisata_page import show_pariwisata_page
from modules.database import init_db, init_narrative_table

st.set_page_config(page_title="Dashboard Transportasi & Pariwisata Papua", layout="wide")


@st.cache_resource
def _ensure_schema():
    """Runs once per app process: creates all tables (transportasi_*,
    akomodasi, wilayah, ai_narratives) if they don't exist yet."""
    init_db()
    init_narrative_table()
    return True


_ensure_schema()


def main():
    st.sidebar.title("📌 Navigasi")
    page = st.sidebar.radio(
        "Pilih Halaman:",
        ["Dashboard Visualisasi", "Laporan Perkembangan", "Pariwisata (Akomodasi)", "Analisis Series & Admin"],
    )

    if page == "Dashboard Visualisasi":
        show_dashboard_page()
    elif page == "Laporan Perkembangan":
        show_report_page()
    elif page == "Pariwisata (Akomodasi)":
        show_pariwisata_page()
    elif page == "Analisis Series & Admin":
        show_series_admin_page()

if __name__ == '__main__':
    main()
