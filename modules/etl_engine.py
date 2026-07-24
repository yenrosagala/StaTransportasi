import pandas as pd
import io
import re
from modules.config import get_province_by_kabupaten

def clean_number(val):
    if pd.isna(val):
        return 0.0
    val_str = str(val).strip()
    val_clean = val_str.replace('.', '').replace(',', '.')
    try:
        return float(val_clean)
    except ValueError:
        return 0.0

def extract_code_and_name(text):
    match = re.search(r'\[(.*?)\]\s*(.*)', str(text))
    if match:
        return match.group(1), match.group(2)
    return '', str(text)

def parse_transport_file(file_content, tahun, bulan):
    dfs = pd.read_html(io.BytesIO(file_content))
    df_raw = dfs[0]
    header_str = str(df_raw.columns)

    if 'Transportasi Laut' in header_str:
        table_type = 'transportasi_laut'
        df = process_laut(df_raw, tahun, bulan)
    elif 'Pesawat Terbang' in header_str or 'Bandara' in header_str:
        table_type = 'transportasi_udara'
        df = process_udara(df_raw, tahun, bulan)
    else:
        raise ValueError('Format header tabel tidak dikenali!')

    df['nama_provinsi'] = df['nama_kabkota'].apply(get_province_by_kabupaten)
    return table_type, df

def process_laut(df_raw, tahun, bulan):
    data_rows = df_raw.iloc[0:].values
    parsed_data = []
    for row in data_rows:
        prov_code, _ = extract_code_and_name(row[0])
        kab_code, kab_name = extract_code_and_name(row[1])
        pel_code, pel_name = extract_code_and_name(row[2])
        parsed_data.append({
            'tahun': str(tahun), 'bulan': bulan, 'kode_provinsi': prov_code,
            'kode_kabkota': kab_code, 'nama_kabkota': kab_name, 
            'kode_pelabuhan': pel_code, 'nama_pelabuhan': pel_name,
            'dn_penumpang_turun': int(clean_number(row[4])), 
            'dn_penumpang_naik': int(clean_number(row[5])),
            'dn_bongkar_barang_ton': clean_number(row[6]), 
            'dn_muat_barang_ton': clean_number(row[7])
        })
    return pd.DataFrame(parsed_data)

def process_udara(df_raw, tahun, bulan):
    data_rows = df_raw.iloc[0:].values
    parsed_data = []
    for row in data_rows:
        prov_code, _ = extract_code_and_name(row[0])
        kab_code, kab_name = extract_code_and_name(row[1])
        ban_code, ban_name = extract_code_and_name(row[2])
        parsed_data.append({
            'tahun': str(tahun), 'bulan': bulan, 'kode_provinsi': prov_code,
            'kode_kabkota': kab_code, 'nama_kabkota': kab_name, 
            'kode_bandara': ban_code, 'nama_bandara': ban_name,
            'pesawat_berangkat': int(clean_number(row[4])), 
            'pesawat_datang': int(clean_number(row[5])),
            'penumpang_berangkat': int(clean_number(row[6])), 
            'penumpang_datang': int(clean_number(row[7])),
            'barang_muat_kg': clean_number(row[9]), 
            'barang_bongkar_kg': clean_number(row[10])
        })
    return pd.DataFrame(parsed_data)