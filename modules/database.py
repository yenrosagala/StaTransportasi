from sqlalchemy import create_engine, text
import pandas as pd
import streamlit as st

def get_engine():
    # Ambil connection string dari st.secrets atau environment variable
    db_url = st.secrets.get("DATABASE_URL")
    
    # Fallback jika menggunakan format postgres:// ubah jadi postgresql://
    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
        
    return create_engine(db_url)

def init_db():
    """Initializes the required database tables if they do not exist."""
    engine = get_engine()
    with engine.begin() as conn:
        # Create wilayah table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS public.wilayah (
                kode_kabkota bigint NOT NULL,
                nama_kabkota text,
                kode_provinsi bigint,
                nama_provinsi text,
                CONSTRAINT wilayah_pkey PRIMARY KEY (kode_kabkota)
            );
        """))
        
        # Create transportasi_laut table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS public.transportasi_laut (
                tahun bigint NOT NULL,
                bulan text NOT NULL,
                kode_provinsi bigint,
                nama_provinsi text,
                kode_kabkota bigint,
                nama_kabkota text,
                kode_pelabuhan bigint NOT NULL,
                nama_pelabuhan text,
                dn_penumpang_turun bigint,
                dn_penumpang_naik bigint,
                dn_bongkar_barang_ton double precision,
                dn_muat_barang_ton double precision,
                ln_penumpang_turun bigint,
                ln_penumpang_naik bigint,
                ln_bongkar_barang_ton double precision,
                ln_muat_barang_ton double precision,
                CONSTRAINT transportasi_laut_pkey PRIMARY KEY (tahun, bulan, kode_pelabuhan)
            );
        """))

        # Create transportasi_udara table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS public.transportasi_udara (
                tahun bigint NOT NULL,
                bulan text NOT NULL,
                kode_provinsi bigint,
                nama_provinsi text,
                kode_kabkota bigint,
                nama_kabkota text,
                kode_bandara bigint NOT NULL,
                nama_bandara text,
                pesawat_berangkat bigint,
                pesawat_datang bigint,
                penumpang_berangkat bigint,
                penumpang_datang bigint,
                penumpang_transit bigint,
                barang_muat_kg double precision,
                barang_bongkar_kg double precision,
                bagasi_muat_kg double precision,
                bagasi_bongkar_kg double precision,
                pos_muat_kg double precision,
                pos_bongkar_kg double precision,
                CONSTRAINT transportasi_udara_pkey PRIMARY KEY (tahun, bulan, kode_bandara)
            );
        """))

        # Create akomodasi table (Pariwisata / Hotel Occupancy data — TPK & RLMTGAB)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS public.akomodasi (
                kd_prov text,
                kd_kab text,
                jenis_akomodasi text,
                kelas_akomodasi integer,
                mktj double precision,
                mkts double precision,
                mtgab double precision,
                tpk double precision,
                rlmtgab double precision,
                tahun integer NOT NULL,
                bulan integer NOT NULL
            );
        """))

def init_narrative_table():
    """Creates the shared AI-narrative cache table used by BOTH the
    Transportasi pages (dashboard_page.py / report_page.py) and the
    Pariwisata (Akomodasi) page. A single generic (report_type, period_key)
    key lets every page cache its own narratives in one place."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ai_narratives (
                report_type TEXT NOT NULL,
                period_key TEXT NOT NULL,
                narrative_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (report_type, period_key)
            )
        """))

def delete_db():
    """Drops all tables from the PostgreSQL database."""
    engine = get_engine()
    try:
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS public.transportasi_udara CASCADE;"))
            conn.execute(text("DROP TABLE IF EXISTS public.transportasi_laut CASCADE;"))
            conn.execute(text("DROP TABLE IF EXISTS public.wilayah CASCADE;"))
            conn.execute(text("DROP TABLE IF EXISTS public.akomodasi CASCADE;"))
            conn.execute(text("DROP TABLE IF EXISTS ai_narratives CASCADE;"))
            conn.execute(text("DROP TABLE IF EXISTS ai_narratives_cache CASCADE;"))
        return True
    except Exception as e:
        st.error(f"Failed to delete database tables: {e}")
        return False
