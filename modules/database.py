from sqlalchemy import create_engine, text
import pandas as pd
import os

DB_PATH = 'transportasi_papua.db'
ENGINE = create_engine(f'sqlite:///{DB_PATH}')

def get_engine():
    return ENGINE

def init_db():
    # Tables are created automatically by pandas.to_sql, 
    # but this can be used for explicit schema setup if needed.
    pass

def init_narrative_table():
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ai_narratives_cache (
                provinsi TEXT,
                moda TEXT,
                indikator TEXT,
                tahun INTEGER,
                bulan TEXT,
                narrative_text TEXT,
                source TEXT,
                PRIMARY KEY (provinsi, moda, indikator, tahun, bulan)
            )
        """))

def delete_db():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        return True
    return False
