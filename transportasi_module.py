"""
transportasi_module.py
-----------------------
Python re-implementation of the R/Shiny "Monit Transportasi" modules
(mod_upload.R, mod_update.R, mod_dashboard.R, mod_konfirmasi.R) so the whole
transportation-monitoring app can run as a page inside the merged Streamlit app.

Database: uses the SAME database referenced by the original R project
("Monit Transportasi/transportasi.db"), table `master_transportasi`
(schema: moda, kategori, lokasi, tahun, bulan, nilai) — the long/tidy format
used by mod_upload.R, mod_update.R and seeding.R.
"""

import io
import os
import sqlite3
from contextlib import contextmanager

import numpy as np
import pandas as pd

MONTH_NAMES_ID = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]


def month_name_id(m):
    try:
        return MONTH_NAMES_ID[int(m) - 1]
    except Exception:
        return ""


class TransportasiEngine:
    """Mirrors the SQLite access pattern used by ETLEngine in my_module.py,
    but targets the transportation database used by the original R app."""

    def __init__(self, db_path="Monit Transportasi/transportasi.db",
                 table_name="master_transportasi"):
        self.db_path = db_path
        self.table_name = table_name
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._initialize_db()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        try:
            yield conn
        finally:
            conn.close()

    def _initialize_db(self):
        with self._get_connection() as conn:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    moda TEXT,
                    kategori TEXT,
                    lokasi TEXT,
                    tahun INTEGER,
                    bulan INTEGER,
                    nilai REAL
                )
            """)
            conn.commit()

    # ------------------------------------------------------------------
    # Shared read helper
    # ------------------------------------------------------------------
    def read_all(self):
        with self._get_connection() as conn:
            try:
                return pd.read_sql_query(f"SELECT * FROM {self.table_name}", conn)
            except Exception:
                return pd.DataFrame(columns=["id", "moda", "kategori", "lokasi", "tahun", "bulan", "nilai"])

    # ==================================================================
    # mod_upload.R  ->  Upload & Ekstrak Data Bulanan Baru
    # ==================================================================
    def process_upload(self, uploaded_file, moda):
        """Replicates mod_upload_server's observeEvent(input$proses, ...).
        Returns (data_insert_df, status_message)."""
        try:
            bytes_data = uploaded_file.getvalue() if hasattr(uploaded_file, "getvalue") else uploaded_file.read()
            buffer = io.BytesIO(bytes_data)

            if moda == "Udara":
                # R: skip = 3  -> pandas skiprows counts the same number of rows
                df_raw = pd.read_excel(buffer, sheet_name=0, skiprows=3, header=None)
                # R (1-indexed) columns 5,7,9,10,13,14,16,17 -> 0-indexed here
                c5, c7, c9, c10 = 4, 6, 8, 9
                c13, c14, c16, c17 = 12, 13, 15, 16

                df = df_raw[df_raw[c7].notna()].copy()
                mask = (df[c5].astype(str).str.upper() == "NABIRE") | (df[c7].astype(str).str.upper() == "NABIRE")
                df = df[mask]
                if df.empty:
                    return pd.DataFrame(), "File terbaca, namun tidak ditemukan baris data lokasi target (Nabire/Mimika)."

                df_filtered = pd.DataFrame({
                    "lokasi": df[c7].astype(str),
                    "tahun": pd.to_numeric(df[c9], errors="coerce"),
                    "bulan": pd.to_numeric(df[c10], errors="coerce"),
                    "penumpang_berangkat": pd.to_numeric(df[c13], errors="coerce"),
                    "penumpang_datang": pd.to_numeric(df[c14], errors="coerce"),
                    "barang_bongkar": pd.to_numeric(df[c16], errors="coerce"),
                    "barang_muat": pd.to_numeric(df[c17], errors="coerce"),
                })
                df_filtered["lokasi"] = "Bandara " + df_filtered["lokasi"]

                kategori_map = {
                    "penumpang_berangkat": "Berangkat",
                    "penumpang_datang": "Datang",
                    "barang_bongkar": "Bongkar",
                    "barang_muat": "Muat",
                }
                melted = df_filtered.melt(
                    id_vars=["lokasi", "tahun", "bulan"],
                    value_vars=list(kategori_map.keys()),
                    var_name="kategori_raw", value_name="nilai",
                )
                melted["moda"] = "Udara"
                melted["kategori"] = melted["kategori_raw"].map(kategori_map)
                melted["nilai"] = melted["nilai"].fillna(0)
                data_insert = melted[["moda", "kategori", "lokasi", "tahun", "bulan", "nilai"]]

            elif moda == "Laut":
                # R: skip = 5
                df_raw = pd.read_excel(buffer, sheet_name=0, skiprows=5, header=None)
                c5, c6, c7, c9 = 4, 5, 6, 8
                c17, c18, c21, c22 = 16, 17, 20, 21

                df = df_raw[df_raw[c9].notna()].copy()
                mask = df[c9].astype(str).str.upper().str.contains("NABIRE|MIMIKA", na=False)
                df = df[mask]
                if df.empty:
                    return pd.DataFrame(), "File terbaca, namun tidak ditemukan baris data lokasi target (Nabire/Mimika)."

                df_filtered = pd.DataFrame({
                    "lokasi_raw": df[c9].astype(str),
                    "tahun": pd.to_numeric(df[c6], errors="coerce"),
                    "bulan": pd.to_numeric(df[c7], errors="coerce"),
                    "barang_bongkar": pd.to_numeric(df[c17], errors="coerce"),
                    "barang_muat": pd.to_numeric(df[c18], errors="coerce"),
                    "penumpang_datang": pd.to_numeric(df[c21], errors="coerce"),
                    "penumpang_berangkat": pd.to_numeric(df[c22], errors="coerce"),
                })

                def norm_lokasi(x):
                    u = str(x).upper()
                    if "MIMIKA" in u:
                        return "1. Mimika"
                    if "NABIRE" in u:
                        return "2. Nabire"
                    return x

                df_filtered["lokasi"] = df_filtered["lokasi_raw"].apply(norm_lokasi)

                kategori_map = {
                    "barang_bongkar": "Bongkar",
                    "barang_muat": "Muat",
                    "penumpang_datang": "Datang",
                    "penumpang_berangkat": "Berangkat",
                }
                melted = df_filtered.melt(
                    id_vars=["lokasi", "tahun", "bulan"],
                    value_vars=list(kategori_map.keys()),
                    var_name="kategori_raw", value_name="nilai",
                )
                melted["moda"] = "Laut"
                melted["kategori"] = melted["kategori_raw"].map(kategori_map)
                melted["nilai"] = melted["nilai"].fillna(0)
                data_insert = melted[["moda", "kategori", "lokasi", "tahun", "bulan", "nilai"]]

            else:
                return pd.DataFrame(), "Moda tidak dikenali."

            if data_insert.empty:
                return pd.DataFrame(), "File terbaca, namun tidak ditemukan baris data lokasi target (Nabire/Mimika)."

            target_tahun = data_insert["tahun"].iloc[0]
            target_bulan = data_insert["bulan"].iloc[0]
            if pd.isna(target_tahun) or pd.isna(target_bulan):
                return pd.DataFrame(), "Kolom Bulan atau Tahun terdeteksi sebagai NA."

            target_tahun, target_bulan = int(target_tahun), int(target_bulan)

            with self._get_connection() as conn:
                conn.execute(
                    f"DELETE FROM {self.table_name} WHERE moda = ? AND tahun = ? AND bulan = ?",
                    (moda, target_tahun, target_bulan),
                )
                data_insert.to_sql(self.table_name, conn, if_exists="append", index=False)
                conn.commit()

            msg = (f"Sukses! Data Moda {moda} Bulan {target_bulan} ({month_name_id(target_bulan)}) "
                   f"Tahun {target_tahun} berhasil diperbarui ke database master.")
            return data_insert, msg

        except Exception as e:
            return pd.DataFrame(), f"Terjadi kesalahan pembacaan file: {e}"

    # ==================================================================
    # mod_update.R  ->  Update Data Bulanan Baru (manual form)
    # ==================================================================
    def get_kategori_lokasi(self, moda):
        with self._get_connection() as conn:
            try:
                return pd.read_sql_query(
                    f"SELECT DISTINCT kategori, lokasi FROM {self.table_name} WHERE moda = ?",
                    conn, params=(moda,),
                )
            except Exception:
                return pd.DataFrame(columns=["kategori", "lokasi"])

    def manual_update(self, moda, tahun, bulan, values):
        """values: list of nilai aligned row-by-row with get_kategori_lokasi(moda)."""
        res = self.get_kategori_lokasi(moda)
        if res.empty:
            return "Tidak ditemukan kombinasi kategori-lokasi untuk moda ini di database. Lakukan upload awal terlebih dahulu."

        data_baru = res.copy()
        data_baru["moda"] = moda
        data_baru["tahun"] = int(tahun)
        data_baru["bulan"] = int(bulan)
        data_baru["nilai"] = values
        data_baru = data_baru[["moda", "kategori", "lokasi", "tahun", "bulan", "nilai"]]

        with self._get_connection() as conn:
            conn.execute(
                f"DELETE FROM {self.table_name} WHERE moda=? AND tahun=? AND bulan=?",
                (moda, int(tahun), int(bulan)),
            )
            data_baru.to_sql(self.table_name, conn, if_exists="append", index=False)
            conn.commit()
        return "Data berhasil diperbarui ke database master!"

    # ==================================================================
    # mod_dashboard.R  ->  Dashboard value boxes + tren bulanan
    # ==================================================================
    def dashboard_summary(self, df=None):
        """NOTE: master_transportasi tracks Berangkat/Datang (penumpang) and
        Bongkar/Muat (barang) per kategori — there is no ship-count column in
        this schema, so the 3 original value boxes (Kapal Datang / Penumpang
        Naik / Cargo Bongkar) are mapped onto the closest available metrics:
        Penumpang Berangkat, Penumpang Datang, Cargo Bongkar, Cargo Muat."""
        if df is None:
            df = self.read_all()
        if df.empty:
            return {"penumpang_berangkat": 0, "penumpang_datang": 0, "cargo_bongkar": 0, "cargo_muat": 0}, pd.DataFrame()
        summary = {
            "penumpang_berangkat": df.loc[df["kategori"] == "Berangkat", "nilai"].sum(),
            "penumpang_datang": df.loc[df["kategori"] == "Datang", "nilai"].sum(),
            "cargo_bongkar": df.loc[df["kategori"] == "Bongkar", "nilai"].sum(),
            "cargo_muat": df.loc[df["kategori"] == "Muat", "nilai"].sum(),
        }
        trend = (
            df.groupby(["bulan", "kategori"], as_index=False)["nilai"].sum()
        )
        return summary, trend

    # ==================================================================
    # mod_konfirmasi.R  ->  Konfirmasi Anomali (bandingkan dua bulan)
    # ==================================================================
    def konfirmasi_anomali(self, bulan1, bulan2, moda=None, df=None):
        if df is None:
            df = self.read_all()
        if df.empty:
            return pd.DataFrame()
        if moda and moda != "Semua":
            df = df[df["moda"] == moda]

        b1 = (
            df[df["bulan"] == int(bulan1)]
            .groupby(["moda", "kategori", "lokasi"], as_index=False)["nilai"]
            .sum().rename(columns={"nilai": "nilai_bulan1"})
        )
        b2 = (
            df[df["bulan"] == int(bulan2)]
            .groupby(["moda", "kategori", "lokasi"], as_index=False)["nilai"]
            .sum().rename(columns={"nilai": "nilai_bulan2"})
        )
        merged = pd.merge(b1, b2, on=["moda", "kategori", "lokasi"], how="outer")
        merged["perubahan_persen"] = np.where(
            merged["nilai_bulan1"].notna() & (merged["nilai_bulan1"] != 0),
            ((merged["nilai_bulan2"] - merged["nilai_bulan1"]) / merged["nilai_bulan1"] * 100).round(2),
            np.nan,
        )
        return merged.sort_values(["moda", "kategori", "lokasi"]).reset_index(drop=True)
