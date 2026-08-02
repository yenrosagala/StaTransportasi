"""
akomodasi_engine.py
--------------------
ETL + query helpers for the Pariwisata (Akomodasi / hotel occupancy — TPK &
RLMTGAB) data. This is the Postgres equivalent of the old sqlite-based
`ETLEngine` in the root `my_module.py`. It uses `modules/database.py`
(the same `get_engine()` SQLAlchemy/PostgreSQL connection used by the
Transportasi pages) as the single source of database access, and shares the
`ai_narratives` cache table with dashboard_page.py / report_page.py.
"""

import io
import logging

import numpy as np
import pandas as pd
import streamlit as st
from sqlalchemy import text

from modules.database import get_engine

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TABLE_NAME = "akomodasi"


# ==============================================================================
# ETL
# ==============================================================================
def _transform_data(df, year=None, month=None):
    df_transformed = df.copy()
    df_transformed.columns = df_transformed.columns.astype(str).str.strip().str.lower()

    prov_col_candidates = ['kd_prov', 'kd_provinsi', 'kode_prov', 'provinsi']
    actual_prov_col = next((col for col in prov_col_candidates if col in df_transformed.columns), None)

    for base_col in ['mktj', 'mkts', 'mtgab', 'tpk', 'rlmtgab']:
        col_b, col_nb = f'{base_col}_b', f'{base_col}_nb'
        if col_b in df_transformed.columns and col_nb in df_transformed.columns:
            df_transformed[base_col] = (
                pd.to_numeric(df_transformed[col_b], errors='coerce').fillna(0)
                + pd.to_numeric(df_transformed[col_nb], errors='coerce').fillna(0)
            )

    desired_cols = ['kd_kab', 'jenis_akomodasi', 'kelas_akomodasi', 'mktj', 'mkts', 'mtgab', 'tpk', 'rlmtgab']
    if actual_prov_col:
        desired_cols.append(actual_prov_col)
    if year is not None:
        df_transformed['tahun'] = int(year)
        desired_cols.append('tahun')
    if month is not None:
        df_transformed['bulan'] = int(month)
        desired_cols.append('bulan')

    existing_cols = [c for c in desired_cols if c in df_transformed.columns]
    df_transformed = df_transformed[existing_cols]

    if actual_prov_col and actual_prov_col != 'kd_prov':
        df_transformed = df_transformed.rename(columns={actual_prov_col: 'kd_prov'})

    if 'kd_prov' in df_transformed.columns:
        df_transformed['kd_prov'] = pd.to_numeric(df_transformed['kd_prov'], errors='coerce')
        df_transformed = df_transformed[df_transformed['kd_prov'].isin([94, 95, 96, 97])]
        prov_mapping = {94: 'Papua', 95: 'Papua Selatan', 96: 'Papua Tengah', 97: 'Papua Pegunungan'}
        df_transformed['kd_prov'] = df_transformed['kd_prov'].map(prov_mapping)

    if 'jenis_akomodasi' in df_transformed.columns:
        jenis_mapping = {1: 'Hotel Bintang', 2: 'Hotel Non Bintang'}
        df_transformed['jenis_akomodasi'] = (
            pd.to_numeric(df_transformed['jenis_akomodasi'], errors='coerce')
            .map(jenis_mapping)
            .fillna(df_transformed['jenis_akomodasi'].astype(str))
        )

    for col in ['mktj', 'mkts', 'mtgab', 'tpk', 'rlmtgab', 'kelas_akomodasi']:
        if col in df_transformed.columns:
            df_transformed[col] = pd.to_numeric(df_transformed[col], errors='coerce').fillna(0)

    subset_cols = [c for c in ['kd_prov', 'kd_kab', 'jenis_akomodasi', 'kelas_akomodasi', 'tahun', 'bulan']
                   if c in df_transformed.columns]
    if subset_cols:
        df_transformed = df_transformed.drop_duplicates(subset=subset_cols, keep='last')

    return df_transformed.reset_index(drop=True)


def etl_pipeline(uploaded_file, sheet_name='Prov_Jenis_Kelas', year=None, month=None):
    """Parses one Excel file and upserts it into the `akomodasi` table
    (Postgres, via modules/database.get_engine()). Existing rows for the
    same (tahun, bulan) are replaced — same overwrite semantics as the
    Transportasi ETL in admin_page.py."""
    filename = getattr(uploaded_file, 'name', 'uploaded_file.xlsx')
    try:
        bytes_data = uploaded_file.getvalue() if hasattr(uploaded_file, 'getvalue') else uploaded_file.read()
        buffer = io.BytesIO(bytes_data)
        excel_file = pd.ExcelFile(buffer)
        if sheet_name not in excel_file.sheet_names:
            return False, f"Sheet '{sheet_name}' tidak ditemukan dalam '{filename}'."
        df_extracted = pd.read_excel(excel_file, sheet_name=sheet_name)
    except Exception as e:
        return False, f"Gagal membaca file '{filename}': {e}"

    df_transformed = _transform_data(df_extracted, year=year, month=month)
    if df_transformed.empty:
        return False, f"File '{filename}' tidak menghasilkan baris data yang valid (cek kolom kd_prov/tahun/bulan)."

    try:
        engine = get_engine()
        with engine.begin() as conn:
            if year is not None and month is not None:
                conn.execute(
                    text(f"DELETE FROM {TABLE_NAME} WHERE tahun = :tahun AND bulan = :bulan"),
                    {"tahun": int(year), "bulan": int(month)},
                )
            df_transformed.to_sql(TABLE_NAME, conn, if_exists='append', index=False)
        return True, f"Berhasil memuat {len(df_transformed)} baris dari '{filename}' ke database ({year}-{month})."
    except Exception as e:
        return False, f"Gagal menyimpan ke database: {e}"


# ==============================================================================
# QUERY HELPERS
# ==============================================================================
def get_filter_options():
    engine = get_engine()
    try:
        return pd.read_sql(text(f"SELECT DISTINCT kd_prov, jenis_akomodasi, tahun, bulan FROM {TABLE_NAME}"), engine)
    except Exception:
        return pd.DataFrame(columns=["kd_prov", "jenis_akomodasi", "tahun", "bulan"])


def query_period(kd_prov=None, tahun=None, bulan=None):
    engine = get_engine()
    query = f"SELECT * FROM {TABLE_NAME}"
    conditions, params = [], {}
    if kd_prov is not None:
        conditions.append("kd_prov = :kd_prov")
        params["kd_prov"] = kd_prov
    if tahun is not None:
        conditions.append("tahun = :tahun")
        params["tahun"] = int(tahun)
    if bulan is not None:
        conditions.append("bulan = :bulan")
        params["bulan"] = int(bulan)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    try:
        return pd.read_sql(text(query), engine, params=params)
    except Exception:
        return pd.DataFrame()


def count_existing_rows(tahun, bulan):
    engine = get_engine()
    try:
        r = pd.read_sql(
            text(f"SELECT COUNT(*) AS n FROM {TABLE_NAME} WHERE tahun = :tahun AND bulan = :bulan"),
            engine, params={"tahun": int(tahun), "bulan": int(bulan)},
        )
        return int(r["n"].iloc[0])
    except Exception:
        return 0


# ==============================================================================
# GEMINI CLIENT
# ==============================================================================
def get_gemini_client():
    from google import genai
    api_keys = []

    def add_value(v):
        if not v:
            return
        if isinstance(v, str):
            v = v.strip()
            if v:
                api_keys.append(v)
        elif isinstance(v, (list, tuple)):
            for x in v:
                add_value(x)
        else:
            s = str(v).strip()
            if s:
                api_keys.append(s)

    try:
        add_value(st.secrets.get("GEMINI_API_KEYS"))
        add_value(st.secrets.get("GEMINI_API_KEY"))
        add_value(st.secrets.get("GOOGLE_API_KEY"))
    except Exception as e:
        logger.info("Secrets Gemini tidak ditemukan (%s).", e)

    for key in api_keys:
        try:
            return genai.Client(api_key=key)
        except Exception:
            continue
    return None


# ==============================================================================
# SHARED NARRATIVE CACHE  (table: ai_narratives — shared with Transportasi pages)
# ==============================================================================
def get_cached_narrative(report_type, period_key):
    try:
        engine = get_engine()
        df = pd.read_sql(
            text("SELECT narrative_text FROM ai_narratives WHERE report_type = :rt AND period_key = :pk"),
            engine, params={"rt": report_type, "pk": period_key},
        )
        if not df.empty:
            return df["narrative_text"].iloc[0]
    except Exception as e:
        logger.warning("Gagal mengambil narasi cache: %s", e)
    return None


def save_narrative(report_type, period_key, narrative_text):
    try:
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO ai_narratives (report_type, period_key, narrative_text, created_at)
                    VALUES (:rt, :pk, :txt, CURRENT_TIMESTAMP)
                    ON CONFLICT (report_type, period_key)
                    DO UPDATE SET narrative_text = EXCLUDED.narrative_text, created_at = CURRENT_TIMESTAMP
                """),
                {"rt": report_type, "pk": period_key, "txt": narrative_text},
            )
    except Exception as e:
        logger.error("Gagal menyimpan narasi cache: %s", e)


def delete_narrative(report_type, period_key):
    try:
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM ai_narratives WHERE report_type = :rt AND period_key = :pk"),
                {"rt": report_type, "pk": period_key},
            )
    except Exception as e:
        logger.error("Gagal menghapus narasi cache: %s", e)
