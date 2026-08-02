import os
import io
import sqlite3
import numpy as np
import pandas as pd
import logging
from google import genai
from contextlib import contextmanager
import streamlit as st

# Setup standard logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ETLEngine:
    def __init__(self, db_name='etl_data.db', general_table_name='all_data'):
        self.db_name = db_name
        self.general_table_name = general_table_name
        self._initialize_db()

    @contextmanager
    def _get_connection(self):
        """Context manager for safe SQLite connection handling and cleanup."""
        conn = sqlite3.connect(self.db_name, timeout=10.0)
        try:
            yield conn
        finally:
            conn.close()

    def _initialize_db(self):
        """Ensures base data and AI narrative cache tables exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.general_table_name} (
                    kd_prov TEXT,
                    kd_kab TEXT,
                    jenis_akomodasi TEXT,
                    kelas_akomodasi INTEGER,
                    mktj REAL,
                    mkts REAL,
                    mtgab REAL,
                    tpk REAL,
                    rlmtgab REAL,
                    year INTEGER,
                    month INTEGER
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ai_narratives (
                    province TEXT,
                    year INTEGER,
                    month INTEGER,
                    jenis_akomodasi TEXT,
                    indicator TEXT,
                    narrative TEXT,
                    PRIMARY KEY (province, year, month, jenis_akomodasi, indicator)
                )
            """)
            conn.commit()

    def _transform_data(self, df, year=None, month=None):
        df_transformed = df.copy()
        df_transformed.columns = df_transformed.columns.astype(str).str.strip().str.lower()

        prov_col_candidates = ['kd_prov', 'kd_provinsi', 'kode_prov', 'provinsi']
        actual_prov_col = next((col for col in prov_col_candidates if col in df_transformed.columns), None)

        for base_col in ['mktj', 'mkts', 'mtgab', 'tpk', 'rlmtgab']:
            col_b = f'{base_col}_b'
            col_nb = f'{base_col}_nb'
            if col_b in df_transformed.columns and col_nb in df_transformed.columns:
                df_transformed[base_col] = (
                    pd.to_numeric(df_transformed[col_b], errors='coerce').fillna(0) +
                    pd.to_numeric(df_transformed[col_nb], errors='coerce').fillna(0)
                )

        desired_cols = [
            'kd_kab', 'jenis_akomodasi', 'kelas_akomodasi',
            'mktj', 'mkts', 'mtgab', 'tpk', 'rlmtgab'
        ]
        if actual_prov_col:
            desired_cols.append(actual_prov_col)

        if year is not None:
            df_transformed['year'] = year
            desired_cols.append('year')
        if month is not None:
            df_transformed['month'] = month
            desired_cols.append('month')

        existing_cols = [col for col in desired_cols if col in df_transformed.columns]
        df_transformed = df_transformed[existing_cols]

        if actual_prov_col and actual_prov_col != 'kd_prov':
            df_transformed = df_transformed.rename(columns={actual_prov_col: 'kd_prov'})

        if 'kd_prov' in df_transformed.columns:
            df_transformed['kd_prov'] = pd.to_numeric(df_transformed['kd_prov'], errors='coerce')
            valid_provinces = [94, 95, 96, 97]
            
            df_transformed = df_transformed[df_transformed['kd_prov'].isin(valid_provinces)]

            prov_mapping = {
                94: 'Papua',
                95: 'Papua Selatan',
                96: 'Papua Tengah',
                97: 'Papua Pegunungan',
            }
            df_transformed['kd_prov'] = df_transformed['kd_prov'].map(prov_mapping)

        if 'jenis_akomodasi' in df_transformed.columns:
            jenis_mapping = {1: 'Hotel Bintang', 2: 'Hotel Non Bintang'}
            df_transformed['jenis_akomodasi'] = (
                pd.to_numeric(df_transformed['jenis_akomodasi'], errors='coerce')
                .map(jenis_mapping)
                .fillna(df_transformed['jenis_akomodasi'].astype(str))
            )

        numeric_cols = ['mktj', 'mkts', 'mtgab', 'tpk', 'rlmtgab', 'kelas_akomodasi']
        for col in numeric_cols:
            if col in df_transformed.columns:
                df_transformed[col] = pd.to_numeric(df_transformed[col], errors='coerce').fillna(0)

        subset_cols = [col for col in ['kd_prov', 'kd_kab', 'jenis_akomodasi', 'kelas_akomodasi', 'year', 'month'] if col in df_transformed.columns]
        if subset_cols:
            df_transformed = df_transformed.drop_duplicates(subset=subset_cols, keep='last')

        return df_transformed.reset_index(drop=True)

    def etl_pipeline(self, uploaded_file, sheet_name='Prov_Jenis_Kelas', year=None, month=None):
        filename = getattr(uploaded_file, 'name', 'uploaded_file.xlsx')
        try:
            bytes_data = uploaded_file.getvalue() if hasattr(uploaded_file, 'getvalue') else uploaded_file.read()
            buffer = io.BytesIO(bytes_data)
            excel_file = pd.ExcelFile(buffer)
            if sheet_name not in excel_file.sheet_names:
                logger.error(f"Sheet '{sheet_name}' not found in '{filename}'.")
                return
            df_extracted = pd.read_excel(excel_file, sheet_name=sheet_name)
        except Exception as e:
            logger.error(f'Error extracting data from {filename}: {e}')
            return

        df_transformed = self._transform_data(df_extracted, year=year, month=month)
        if df_transformed.empty:
            logger.warning(f"File '{filename}' yielded 0 rows.")
            return

        with self._get_connection() as conn:
            cursor = conn.cursor()
            if year is not None and month is not None:
                cursor.execute(f"DELETE FROM {self.general_table_name} WHERE year = ? AND month = ?", (year, month))
                conn.commit()
            df_transformed.to_sql(self.general_table_name, conn, if_exists='append', index=False)
            logger.info(f"Successfully loaded {len(df_transformed)} rows.")


def get_gemini_client():
    # 1. Try fetching from Streamlit secrets list first
    api_keys = []
    try:
        if "GEMINI_API_KEYS" in st.secrets:
            api_keys = list(st.secrets["GEMINI_API_KEYS"])
    except Exception:
        pass
        
    # 2. Fallback to single environment variable or secrets if list is empty
    if not api_keys:
        env_key = os.getenv('GEMINI_API_KEY') or st.secrets.get('GEMINI_API_KEY')
        if env_key:
            api_keys = [env_key]

    if not api_keys:
        return None

    # Try initializing the client with the keys in sequence
    for key in api_keys:
        if key and str(key).strip():
            try:
                return genai.Client(api_key=str(key).strip())
            except Exception:
                continue
                
    return None

def generate_akomodasi_tables(etl_engine_instance, province, year, month):
    client = get_gemini_client()

    prev_month = (month - 1) if month > 1 else 12
    prev_year = year if month > 1 else (year - 1)
    last_year = year - 1

    province_str = str(province).strip()

    # Define base_prompt_text AFTER its dependent variables are initialized
    base_prompt_text = (
            "Anda adalah Kepala Pusat Statistik / Penasihat Kebijakan Utama yang menyusun ringkasan eksekutif strategis berstandar tinggi bagi Dewan Pimpinan dan Pengambil Kebijakan.\n"
            f"Buatlah narasi Executive Summary tingkat tinggi yang padat dan tajam (tepat 2 paragraf) untuk indikator statistik Wilayah Provinsi {province} periode komparasi {year} {month} terhadap {prev_year} {prev_month}.\n\n"
            "Pedoman & Fokus Penulisan:\n"
            "- Paragraf 1: Analisis komprehensif kinerja bulanan (Month-to-Month/MTM), arah tren sektoral, serta kontribusi agregat dari wilayah-wilayah utama dalam hierarki BRS.\n"
            "- Paragraf 2: Analisis mendalam kinerja kumulatif (Year-to-Date / Year-on-Year), pembacaan deviasi pertumbuhan, serta signifikansi fluktuasi antarwilayah dalam kerangka ekonomi regional.\n"
            "- Gunakan diksi birokratik profesional, objektif, analitis, dengan standarisasi format angka Indonesia.\n"
            "- Jangan sertakan pengantar, sapaan, catatan kaki, ataupun penutup. Langsung berikan 2 paragraf teks yang dipisahkan oleh satu baris kosong (\\n\\n).\n\n"
            "Sumber Data Tabel:\n"
            f"{province_str}"
    )

    query = f"""
        SELECT * FROM {etl_engine_instance.general_table_name}
        WHERE TRIM(CAST(kd_prov AS TEXT)) = ? AND year IN (?, ?, ?) AND month IN (?, ?)
    """
    
    with etl_engine_instance._get_connection() as conn:
        df_all = pd.read_sql_query(query, conn, params=(province_str, year, prev_year, last_year, month, prev_month))

    import streamlit as st

    if df_all.empty:
        st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)
        st.warning(f'No data found matching parameters for Province: {province}')
        st.markdown('</div>', unsafe_allow_html=True)
        return

    df_current = df_all[(df_all['year'] == year) & (df_all['month'] == month)]
    df_prev = df_all[(df_all['year'] == prev_year) & (df_all['month'] == prev_month)]
    df_last = df_all[(df_all['year'] == last_year) & (df_all['month'] == month)]

    if df_current.empty:
        st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)
        st.warning(f'No current period data found for {province} on {month}/{year}.')
        st.markdown('</div>', unsafe_allow_html=True)
        return

    st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)
    st.markdown(f"<h3 style='margin-top: 0; color: #0f172a;'>📋 Executive Summary — {province} ({month}/{year})</h3>", unsafe_allow_html=True)
    st.markdown("<p style='color: #64748b; font-size: 14px;'>Analisis metrik akomodasi, tingkat penghunian kamar (TPK), dan lama menginap.</p>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    indicators = ['tpk', 'rlmtgab']
    jenis_types = sorted(df_current['jenis_akomodasi'].dropna().unique().tolist())

    for indicator in indicators:
        for jenis in jenis_types:
            st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)
            st.markdown(f"<h4 style='color: #1e293b; margin-top: 0;'>Indicator: {indicator.upper()} — {jenis}</h4>", unsafe_allow_html=True)
            st.divider()

            cur_sub = df_current[df_current['jenis_akomodasi'] == jenis][['kelas_akomodasi', indicator]].rename(columns={indicator: 'current'})
            prev_sub = df_prev[df_prev['jenis_akomodasi'] == jenis][['kelas_akomodasi', indicator]].rename(columns={indicator: 'prev'})
            last_sub = df_last[df_last['jenis_akomodasi'] == jenis][['kelas_akomodasi', indicator]].rename(columns={indicator: 'last_year'})

            merged = cur_sub.merge(prev_sub, on='kelas_akomodasi', how='outer').merge(last_sub, on='kelas_akomodasi', how='outer')
            merged = merged.dropna(subset=['kelas_akomodasi'])
            
            merged['change_prev'] = np.where(merged['prev'].notna(), merged['current'] - merged['prev'], np.nan)
            merged['change_last'] = np.where(merged['last_year'].notna(), merged['current'] - merged['last_year'], np.nan)

            def format_kelas(val):
                if pd.isna(val):
                    return 'Undefined Class'
                try:
                    int_val = int(val)
                except (ValueError, TypeError):
                    return str(val)
                    
                if jenis == 'Hotel Bintang':
                    return f"Bintang {int_val}"
                elif jenis == 'Hotel Non Bintang':
                    return f"Kelas {int_val}"
                else:
                    return str(int_val)

            merged['nama_kelas_akomodasi'] = merged['kelas_akomodasi'].apply(format_kelas)
            display_df = merged[['nama_kelas_akomodasi', 'last_year', 'prev', 'current', 'change_prev', 'change_last']].set_index('nama_kelas_akomodasi').round(2)

            avg_row = pd.DataFrame({
                'last_year': [display_df['last_year'].mean()],
                'prev': [display_df['prev'].mean()],
                'current': [display_df['current'].mean()],
                'change_prev': [display_df['change_prev'].mean()],
                'change_last': [display_df['change_last'].mean()]
            }, index=['Average']).round(2)

            final_table = pd.concat([display_df, avg_row])
            for col in ['change_prev', 'change_last']:
                final_table[col] = final_table[col].apply(lambda x: f'{x:+.2f} pts' if pd.notna(x) else '-')

            # Check if admin wants to force regeneration via button click
            regen_key = f"regen_{province}_{year}_{month}_{jenis}_{indicator}"
            is_admin = st.session_state.get("role") == "admin"
            
            if is_admin:
                if st.button(f"🔄 Regenerate AI Narrative ({jenis} - {indicator.upper()})", key=regen_key):
                    with etl_engine_instance._get_connection() as conn:
                        conn.execute(
                            "DELETE FROM ai_narratives WHERE province = ? AND year = ? AND month = ? AND jenis_akomodasi = ? AND indicator = ?",
                            (province, year, month, jenis, indicator)
                        )
                        conn.commit()
                    st.rerun()

            cached_narrative = None
            # Fixed typo from etl_engineinstance to etl_engine_instance
            with etl_engine_instance._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT narrative FROM ai_narratives 
                       WHERE province = ? AND year = ? AND month = ? AND jenis_akomodasi = ? AND indicator = ?""",
                    (province, year, month, jenis, indicator)
                )
                row = cursor.fetchone()
                if row:
                    cached_narrative = row[0]

            if cached_narrative:
                st.markdown(f'<div style="background: #f8fafc; padding: 16px; border-radius: 10px; border-left: 4px solid #f59e0b; margin-bottom: 16px;"><strong>🤖 AI Narrative (Retrieved from Database):</strong><br>{cached_narrative}</div>', unsafe_allow_html=True)
            else:
                if client:
                    prompt = f"Table summary for {indicator.upper()} ({jenis}) in {province}:\n" + final_table.to_markdown() + "\n" + base_prompt_text
                    try:
                        with st.spinner(f'Generating AI narrative for {jenis} {indicator.upper()}...'):
                            response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                            narrative_text = response.text
                            
                            with etl_engine_instance._get_connection() as conn:
                                conn.execute(
                                    """INSERT OR REPLACE INTO ai_narratives (province, year, month, jenis_akomodasi, indicator, narrative)
                                       VALUES (?, ?, ?, ?, ?, ?)""",
                                    (province, year, month, jenis, indicator, narrative_text)
                                )
                                conn.commit()

                            st.markdown(f'<div style="background: #f8fafc; padding: 16px; border-radius: 10px; border-left: 4px solid #f59e0b; margin-bottom: 16px;"><strong>🤖 AI Narrative (Freshly Generated):</strong><br>{narrative_text}</div>', unsafe_allow_html=True)
                    except Exception as e:
                        st.error(f'AI error: {e}')
                else:
                    st.info('AI narrative skipped (Gemini client unconfigured).')

            st.dataframe(final_table, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)