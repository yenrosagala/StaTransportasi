import streamlit as st
from modules.admin_page import show_admin_page
from modules.dashboard_page import show_dashboard_page
from modules.report_page import show_report_page
import sys
from pathlib import Path

# Add project root to Python path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))


st.set_page_config(page_title="Dashboard Transportasi Papua", layout="wide")


st.write(sys.executable)
st.write(sys.path)

def main():
    st.sidebar.title("📌 Navigasi")
    page = st.sidebar.radio("Pilih Halaman:", ["Dashboard Visualisasi", "Laporan Komparatif", "Admin & Upload Data"])

    if page == "Dashboard Visualisasi":
        show_dashboard_page()
    elif page == "Laporan Komparatif":
        show_report_page()
    elif page == "Admin & Upload Data":
        show_admin_page()

if __name__ == '__main__':
    main()