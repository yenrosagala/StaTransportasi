import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import text
from modules.database import get_engine, delete_db
from modules.etl_engine import parse_transport_file, detect_file_metadata
from modules.config import PEMETAAN_WILAYAH

MONTH_MAP = {'Januari': 1, 'Februari': 2, 'Maret': 3, 'April': 4, 'Mei': 5, 'Juni': 6,
             'Juli': 7, 'Agustus': 8, 'September': 9, 'Oktober': 10, 'November': 11, 'Desember': 12}
MONTH_LIST = list(MONTH_MAP.keys())


def compute_upload_stats(table_type, df):
    """Statistik ringkas atas data hasil parsing, untuk ditampilkan sebelum disimpan."""
    stats = {
        'jumlah_baris': len(df),
        'jumlah_provinsi': df['nama_provinsi'].nunique() if 'nama_provinsi' in df.columns else 0,
    }
    if table_type == 'transportasi_udara':
        stats['total_penumpang'] = df['penumpang_berangkat'].sum() + df['penumpang_datang'].sum()
        stats['total_barang'] = df['barang_muat_kg'].sum() + df['barang_bongkar_kg'].sum()
        stats['satuan_barang'] = 'kg'
        stats['jumlah_lokasi'] = df['nama_bandara'].nunique()
        stats['label_lokasi'] = 'Bandara'
    else:
        stats['total_penumpang'] = df['dn_penumpang_naik'].sum() + df['dn_penumpang_turun'].sum()
        stats['total_barang'] = df['dn_muat_barang_ton'].sum() + df['dn_bongkar_barang_ton'].sum()
        stats['satuan_barang'] = 'ton'
        stats['jumlah_lokasi'] = df['nama_pelabuhan'].nunique()
        stats['label_lokasi'] = 'Pelabuhan'
    return stats


def count_existing_rows(engine, table_type, tahun, bulan):
    try:
        result = pd.read_sql(
            text(f"SELECT COUNT(*) as n FROM {table_type} WHERE CAST(tahun AS TEXT) = :tahun AND bulan = :bulan"),
            engine, params={"tahun": str(tahun), "bulan": bulan}
        )
        return int(result['n'].iloc[0])
    except Exception:
        return 0


def show_series_chart_section():
    """Memberi admin akses membuat grafik time series dengan memilih
    provinsi, kabupaten/kota, dan variabel indikator secara bebas."""
    engine = get_engine()

    col1, col2, col3 = st.columns(3)
    with col1:
        moda = st.selectbox("Moda Transportasi", ["Transportasi Udara", "Transportasi Laut"], key="series_moda")
    with col2:
        provinsi = st.selectbox("Provinsi", list(PEMETAAN_WILAYAH.keys()), key="series_provinsi")
    with col3:
        kabupaten_options = ["SEMUA"] + PEMETAAN_WILAYAH[provinsi]
        kabupaten = st.selectbox("Kabupaten/Kota", kabupaten_options, key="series_kabupaten")

    var_options = {
        "Transportasi Udara": [
            'penumpang_berangkat', 'penumpang_datang', 'penumpang_transit',
            'barang_muat_kg', 'barang_bongkar_kg', 'bagasi_muat_kg', 'bagasi_bongkar_kg',
            'pos_muat_kg', 'pos_bongkar_kg', 'pesawat_berangkat', 'pesawat_datang'
        ],
        "Transportasi Laut": [
            'dn_penumpang_turun', 'dn_penumpang_naik', 'dn_bongkar_barang_ton', 'dn_muat_barang_ton',
            'ln_penumpang_turun', 'ln_penumpang_naik', 'ln_bongkar_barang_ton', 'ln_muat_barang_ton'
        ]
    }
    variabel = st.selectbox("Variabel", var_options[moda], key="series_variabel")

    if st.button("📈 Tampilkan Grafik Series", key="series_generate"):
        table = "transportasi_udara" if moda == "Transportasi Udara" else "transportasi_laut"

        query = f"SELECT * FROM {table} WHERE UPPER(nama_provinsi) = :provinsi"
        params = {"provinsi": provinsi.upper()}
        if kabupaten != "SEMUA":
            kab_clean = kabupaten.replace('KABUPATEN ', '').replace('KOTA ', '').strip()
            query += " AND (UPPER(nama_kabkota) = :kab_full OR UPPER(nama_kabkota) = :kab_clean)"
            params["kab_full"] = kabupaten.upper()
            params["kab_clean"] = kab_clean.upper()

        df = pd.read_sql(text(query), engine, params=params)

        if df.empty:
            st.warning("⚠️ Tidak ada data untuk kombinasi filter yang dipilih.")
            return

        df['month_num'] = df['bulan'].map(MONTH_MAP)
        df['tahun_int'] = df['tahun'].astype(int)
        df['periode'] = df['bulan'] + " " + df['tahun'].astype(str)

        df_plot = (
            df.groupby(['tahun_int', 'month_num', 'periode'])[variabel]
            .sum()
            .reset_index()
            .sort_values(['tahun_int', 'month_num'])
        )

        wilayah_label = provinsi if kabupaten == "SEMUA" else kabupaten

        fig = px.line(
            df_plot, x='periode', y=variabel,
            title=f"Tren {variabel.replace('_', ' ').title()} di {wilayah_label} ({moda})",
            markers=True, template='plotly_white'
        )
        fig.update_layout(xaxis_title="Periode", yaxis_title=variabel.replace('_', ' ').title())
        st.plotly_chart(fig, width='stretch)

        with st.expander("📋 Lihat Data di Balik Grafik"):
            st.dataframe(
                df_plot.rename(columns={'periode': 'Periode', variabel: variabel.replace('_', ' ').title()})
                       .drop(columns=['tahun_int', 'month_num']),
                width='stretch
            )


def show_admin_page():
    st.title("🔐 Admin Dashboard: Authenticated Access")

    # 1. Login System
    if 'admin_logged_in' not in st.session_state:
        st.session_state['admin_logged_in'] = False

    if not st.session_state['admin_logged_in']:
        with st.form("login_form"):
            st.subheader("Login Admin")
            password = st.text_input("Masukkan Kata Sandi", type="password")
            submit_button = st.form_submit_button("Login")

            if submit_button:
                if password == "papua123":
                    st.session_state['admin_logged_in'] = True
                    st.success("Akses Diterima!")
                    st.rerun()
                else:
                    st.error("Kata sandi salah!")
        return

    # Logout Button at the top right
    if st.sidebar.button("Log Out Admin"):
        st.session_state['admin_logged_in'] = False
        st.rerun()

    st.success("🔓 Anda masuk sebagai Admin.")

    # 2. Database Maintenance Section
    with st.expander("⚠️ Zone Danger: Manage Database"):
        st.subheader("🗑️ Hapus Data Berdasarkan Filter")
        st.caption("Pilih moda, provinsi, tahun, dan bulan dari data yang ingin dihapus. Pilih \"SEMUA\" untuk tidak membatasi filter tersebut.")

        engine_del = get_engine()

        del1, del2, del3, del4 = st.columns(4)
        with del1:
            moda_del_label = st.selectbox(
                "Moda Transportasi (Hapus Data)", ["Transportasi Udara", "Transportasi Laut"], key="del_moda"
            )
            table_del = "transportasi_udara" if moda_del_label == "Transportasi Udara" else "transportasi_laut"
        with del2:
            provinsi_del = st.selectbox("Provinsi (Filter Hapus)", ["SEMUA"] + list(PEMETAAN_WILAYAH.keys()), key="del_provinsi")
        with del3:
            try:
                years_df = pd.read_sql(text(f"SELECT DISTINCT tahun FROM {table_del}"), engine_del)
                year_options = ["SEMUA"] + sorted(years_df['tahun'].astype(str).unique().tolist())
            except Exception:
                year_options = ["SEMUA"]
            tahun_del = st.selectbox("Tahun (Filter Hapus)", year_options, key="del_tahun")
        with del4:
            bulan_del = st.selectbox(
                "Bulan (Filter Hapus)", ["SEMUA"] + list(MONTH_MAP.keys()), key="del_bulan"
            )

        conditions = []
        params_del = {}
        if provinsi_del != "SEMUA":
            conditions.append("UPPER(nama_provinsi) = :provinsi")
            params_del["provinsi"] = provinsi_del.upper()
        if tahun_del != "SEMUA":
            conditions.append("CAST(tahun AS TEXT) = :tahun")
            params_del["tahun"] = str(tahun_del)
        if bulan_del != "SEMUA":
            conditions.append("bulan = :bulan")
            params_del["bulan"] = bulan_del

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        try:
            count_result = pd.read_sql(
                text(f"SELECT COUNT(*) as n FROM {table_del} WHERE {where_clause}"),
                engine_del, params=params_del
            )
            jumlah_baris_del = int(count_result['n'].iloc[0])
        except Exception as e:
            st.error(f"Gagal membaca data: {e}")
            jumlah_baris_del = 0

        if jumlah_baris_del == 0:
            st.info("Tidak ada data yang cocok dengan filter di atas.")
        else:
            if not conditions:
                st.error(f"🚨 Tidak ada filter aktif — **SEMUA {jumlah_baris_del} baris** pada tabel `{table_del}` akan terhapus!")
            else:
                st.warning(f"⚠️ **{jumlah_baris_del} baris data** pada tabel `{table_del}` cocok dengan filter di atas dan akan dihapus permanen.")

            confirm_del = st.checkbox(
                "Saya yakin ingin menghapus data ini secara permanen.", key="confirm_delete_filtered"
            )
            if st.button("🗑️ Hapus Data Sesuai Filter", disabled=not confirm_del, key="btn_delete_filtered"):
                try:
                    with engine_del.begin() as conn:
                        conn.execute(text(f"DELETE FROM {table_del} WHERE {where_clause}"), params_del)
                    st.success(f"✅ Berhasil menghapus {jumlah_baris_del} baris data dari `{table_del}`.")
                    st.session_state.pop("confirm_delete_filtered", None)
                    st.rerun()
                except Exception as e:
                    st.error(f"Gagal menghapus data: {e}")

        st.divider()
        with st.expander("🚨 Opsi Ekstrem: Hapus SELURUH Database (Semua Tabel & Periode)"):
            st.warning("Tindakan ini akan menghapus seluruh file database, termasuk semua moda dan semua periode!")
            if st.button("Reset/Delete Seluruh Database"):
                if delete_db():
                    st.success("Database berhasil dihapus seluruhnya!")
                else:
                    st.info("File database tidak ditemukan.")

    # 3. Manual Data Correction Section
    st.subheader("🛠️ Koreksi Data Manual")
    with st.expander("Buka Editor Database"):
        engine = get_engine()
        col_edit1, col_edit2, col_edit3 = st.columns(3)
        with col_edit1:
            table_edit = st.selectbox("Pilih Tabel", ["transportasi_udara", "transportasi_laut"])
        with col_edit2:
            year_edit = st.text_input("Tahun (Contoh: 2026)", "2026")
        with col_edit3:
            month_edit = st.selectbox("Bulan", ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"], key="edit_month")

        if st.button("Cari Data"):
            query = text(f"SELECT * FROM {table_edit} WHERE CAST(tahun AS TEXT) = :tahun AND bulan = :bulan")
            df_to_edit = pd.read_sql(query, engine, params={"tahun": year_edit, "bulan": month_edit})
            if df_to_edit.empty:
                st.warning("Data tidak ditemukan untuk periode tersebut.")
            else:
                st.session_state['df_to_edit'] = df_to_edit

        if 'df_to_edit' in st.session_state:
            edited_df = st.data_editor(st.session_state['df_to_edit'], width='stretch, num_rows="dynamic")

            if st.button("Simpan Perubahan"):
                try:
                    with engine.begin() as conn:
                        del_query = text(f"DELETE FROM {table_edit} WHERE CAST(tahun AS TEXT) = :tahun AND bulan = :bulan")
                        conn.execute(del_query, {"tahun": year_edit, "bulan": month_edit})
                        edited_df.to_sql(table_edit, conn, if_exists='append', index=False)
                    st.success("✅ Perubahan berhasil disimpan ke database!")
                    del st.session_state['df_to_edit']
                except Exception as e:
                    st.error(f"Gagal menyimpan data: {e}")

    st.divider()

    # 4. Grafik Series Section
    st.subheader("📈 Buat Grafik Series")
    st.caption("Pilih provinsi, kabupaten/kota, dan variabel untuk melihat tren data antar periode.")
    with st.expander("Buka Pembuat Grafik", expanded=True):
        show_series_chart_section()

    st.divider()

    # 5. Upload Section
    st.subheader("📥 Update Database (Upload Data)")
    st.caption(
        "Unggah satu atau beberapa file sekaligus. Sistem otomatis mendeteksi moda transportasi, "
        "tahun, dan bulan dari isi file — Anda cukup memverifikasi sebelum diproses."
    )

    uploaded_files = st.file_uploader(
        "Pilih satu atau beberapa file Excel BPS", type=['xls', 'xlsx'],
        accept_multiple_files=True, key="upload_files_multi"
    )

    if uploaded_files:
        current_names = tuple(f.name for f in uploaded_files)
        if st.session_state.get('upload_file_names') != current_names:
            st.session_state['upload_file_names'] = current_names
            meta_list = []
            for f in uploaded_files:
                file_bytes = f.read()
                meta = detect_file_metadata(file_bytes)
                meta_list.append({
                    'nama_file': f.name,
                    'file_bytes': file_bytes,
                    'table_type': meta['table_type'],
                    'tahun': meta['tahun'] if meta['tahun'] else 2026,
                    'bulan': meta['bulan'] if meta['bulan'] else 'Januari',
                })
            st.session_state['upload_meta'] = meta_list
            st.session_state.pop('upload_preview', None)

        st.markdown("#### 1️⃣ Verifikasi Deteksi Otomatis")
        st.caption("Periksa moda, tahun, dan bulan yang terdeteksi dari tiap file. Ubah tahun/bulan jika perlu.")

        for i, m in enumerate(st.session_state['upload_meta']):
            c1, c2, c3 = st.columns([3, 1, 1.3])
            with c1:
                st.markdown(f"**📄 {m['nama_file']}**")
                if m['table_type'] == 'transportasi_udara':
                    st.caption("Moda terdeteksi: ✈️ **Transportasi Udara**")
                elif m['table_type'] == 'transportasi_laut':
                    st.caption("Moda terdeteksi: 🚢 **Transportasi Laut**")
                else:
                    st.error("Moda tidak terdeteksi — format header tidak dikenali, file ini akan dilewati.")
            with c2:
                m['tahun'] = st.number_input("Tahun", min_value=2020, max_value=2035, value=int(m['tahun']), key=f"upload_tahun_{i}")
            with c3:
                m['bulan'] = st.selectbox("Bulan", MONTH_LIST, index=MONTH_LIST.index(m['bulan']), key=f"upload_bulan_{i}")
            st.divider()

        valid_meta = [m for m in st.session_state['upload_meta'] if m['table_type'] is not None]

        if valid_meta and st.button("🔍 Analisis & Tampilkan Statistik", key="btn_analyze_upload"):
            engine = get_engine()
            preview = []
            for m in valid_meta:
                try:
                    table_type, df_parsed = parse_transport_file(m['file_bytes'], m['tahun'], m['bulan'])
                    preview.append({
                        'nama_file': m['nama_file'], 'table_type': table_type,
                        'tahun': m['tahun'], 'bulan': m['bulan'],
                        'df': df_parsed, 'stats': compute_upload_stats(table_type, df_parsed),
                        'existing_rows': count_existing_rows(engine, table_type, m['tahun'], m['bulan']),
                        'error': None,
                    })
                except Exception as e:
                    preview.append({
                        'nama_file': m['nama_file'], 'table_type': None,
                        'tahun': m['tahun'], 'bulan': m['bulan'],
                        'df': None, 'stats': None, 'existing_rows': 0, 'error': str(e),
                    })
            st.session_state['upload_preview'] = preview

        if 'upload_preview' in st.session_state:
            preview = st.session_state['upload_preview']
            st.markdown("#### 2️⃣ Pratinjau & Statistik Data")

            any_valid = False
            for p in preview:
                moda_label = ("✈️ Transportasi Udara" if p['table_type'] == 'transportasi_udara'
                              else "🚢 Transportasi Laut" if p['table_type'] == 'transportasi_laut'
                              else "⚠️ Gagal Diproses")
                with st.expander(f"{moda_label} — {p['nama_file']} ({p['bulan']} {p['tahun']})", expanded=True):
                    if p['error']:
                        st.error(f"Gagal memproses file: {p['error']}")
                        continue

                    any_valid = True
                    if p['existing_rows'] > 0:
                        st.warning(
                            f"⚠️ Sudah ada **{p['existing_rows']} baris data** untuk {p['bulan']} {p['tahun']} "
                            f"pada tabel ini. Data lama akan **ditimpa** jika dilanjutkan."
                        )
                    else:
                        st.info("✅ Periode ini belum ada di database (data baru).")

                    s = p['stats']
                    mcol = st.columns(4)
                    mcol[0].metric("Jumlah Baris", f"{s['jumlah_baris']:,}")
                    mcol[1].metric("Total Penumpang", f"{s['total_penumpang']:,.0f} orang")
                    mcol[2].metric("Total Barang", f"{s['total_barang']:,.2f} {s['satuan_barang']}")
                    mcol[3].metric(f"Jumlah {s['label_lokasi']}", s['jumlah_lokasi'])

                    st.dataframe(p['df'], width='stretch, height=200)

            if any_valid:
                st.markdown("#### 3️⃣ Konfirmasi")
                overwrite = st.checkbox(
                    "Timpa data lama jika periode yang sama sudah ada di database", value=True, key="upload_overwrite"
                )
                confirm = st.checkbox(
                    "Saya sudah memeriksa statistik di atas dan yakin untuk menyimpan data ini ke database.",
                    key="upload_confirm_checkbox"
                )

                if st.button("✅ Simpan ke Database", key="btn_save_upload", disabled=not confirm):
                    engine = get_engine()
                    success_count = 0
                    for p in preview:
                        if p['error']:
                            continue
                        try:
                            with engine.begin() as conn:
                                if overwrite:
                                    conn.execute(
                                        text(f"DELETE FROM {p['table_type']} WHERE CAST(tahun AS TEXT) = :tahun AND bulan = :bulan"),
                                        {"tahun": str(p['tahun']), "bulan": p['bulan']}
                                    )
                                p['df'].to_sql(p['table_type'], conn, if_exists='append', index=False)
                            st.success(f"✅ {p['nama_file']} berhasil disimpan ke `{p['table_type']}` ({p['bulan']} {p['tahun']}).")
                            success_count += 1
                        except Exception as e:
                            st.error(f"Gagal menyimpan {p['nama_file']}: {e}")

                    if success_count > 0:
                        st.balloons()
                        for k in ['upload_file_names', 'upload_meta', 'upload_preview']:
                            st.session_state.pop(k, None)
    else:
        st.info("Unggah satu atau beberapa file Excel BPS untuk memulai proses update database.")
