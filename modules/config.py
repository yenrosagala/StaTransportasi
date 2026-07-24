import pandas as pd
import re

# 1. Pemetaan Provinsi & Kabupaten Terbaru
PEMETAAN_WILAYAH = {
    'Papua': ['KABUPATEN BIAK NUMFOR', 'KABUPATEN JAYAPURA', 'KABUPATEN KEEROM', 'KABUPATEN KEPULAUAN YAPEN', 'KABUPATEN MAMBERAMO RAYA', 'KABUPATEN SARMI', 'KABUPATEN SUPIORI', 'KABUPATEN WAROPEN', 'KOTA JAYAPURA'],
    'Papua Selatan': ['KABUPATEN ASMAT', 'KABUPATEN BOVEN DIGOEL', 'KABUPATEN MAPPI', 'KABUPATEN MERAUKE'],
    'Papua Tengah': ['KABUPATEN DEIYAI', 'KABUPATEN DOGIYAI', 'KABUPATEN INTAN JAYA', 'KABUPATEN MIMIKA', 'KABUPATEN NABIRE', 'KABUPATEN PANIAI', 'KABUPATEN PUNCAK', 'KABUPATEN PUNCAK JAYA'],
    'Papua Pegunungan': ['KABUPATEN JAYAWIJAYA', 'KABUPATEN LANNY JAYA', 'KABUPATEN MAMBERAMO TENGAH', 'KABUPATEN NDUGA', 'KABUPATEN PEGUNUNGAN BINTANG', 'KABUPATEN TOLIKARA', 'KABUPATEN YAHUKIMO', 'KABUPATEN YALIMO']
}

# 2. Pemetaan Detail Lokasi Komprehensif
MAPPING_LOKASI_KAB_PROV = {
    'MOPPAH': {'kab': 'KABUPATEN MERAUKE', 'prov': 'PAPUA SELATAN'},
    'OKABA': {'kab': 'KABUPATEN MERAUKE', 'prov': 'PAPUA SELATAN'},
    'WAMENA': {'kab': 'KABUPATEN JAYAWIJAYA', 'prov': 'PAPUA PEGUNUNGAN'},
    'SENTANI': {'kab': 'KABUPATEN JAYAPURA', 'prov': 'PAPUA'},
    'NABIRE': {'kab': 'KABUPATEN NABIRE', 'prov': 'PAPUA TENGAH'},
    'STEVANUS RUMBEWAS': {'kab': 'KABUPATEN KEPULAUAN YAPEN', 'prov': 'PAPUA'},
    'FRANS KAISIEPO': {'kab': 'KABUPATEN BIAK NUMFOR', 'prov': 'PAPUA'},
    'ENAROTALI': {'kab': 'KABUPATEN PANIAI', 'prov': 'PAPUA TENGAH'},
    'ZUGAPA BILORAI': {'kab': 'KABUPATEN INTAN JAYA', 'prov': 'PAPUA TENGAH'},
    'MULIA': {'kab': 'KABUPATEN PUNCAK JAYA', 'prov': 'PAPUA TENGAH'},
    'MOZES KILANGIN': {'kab': 'KABUPATEN MIMIKA', 'prov': 'PAPUA TENGAH'},
    'MINDIPTANAH': {'kab': 'KABUPATEN BOVEN DIGOEL', 'prov': 'PAPUA SELATAN'},
    'TANAH MERAH': {'kab': 'KABUPATEN BOVEN DIGOEL', 'prov': 'PAPUA SELATAN'},
    'BOMAKIA': {'kab': 'KABUPATEN BOVEN DIGOEL', 'prov': 'PAPUA SELATAN'},
    'KEPI': {'kab': 'KABUPATEN MAPPI', 'prov': 'PAPUA SELATAN'},
    'BADE': {'kab': 'KABUPATEN MAPPI', 'prov': 'PAPUA SELATAN'},
    'EWER': {'kab': 'KABUPATEN ASMAT', 'prov': 'PAPUA SELATAN'},
    'KAMUR': {'kab': 'KABUPATEN ASMAT', 'prov': 'PAPUA SELATAN'},
    'DEKAI': {'kab': 'KABUPATEN YAHUKIMO', 'prov': 'PAPUA PEGUNUNGAN'},
    'OKSIBIL': {'kab': 'KABUPATEN PEGUNUNGAN BINTANG', 'prov': 'PAPUA PEGUNUNGAN'},
    'BATOM': {'kab': 'KABUPATEN PEGUNUNGAN BINTANG', 'prov': 'PAPUA PEGUNUNGAN'},
    'KARUBAGA': {'kab': 'KABUPATEN TOLIKARA', 'prov': 'PAPUA PEGUNUNGAN'},
    'MARARENA': {'kab': 'KABUPATEN SARMI', 'prov': 'PAPUA'},
    'KASONAWEJA': {'kab': 'KABUPATEN MAMBERAMO RAYA', 'prov': 'PAPUA'},
    'ILLAGA': {'kab': 'KABUPATEN PUNCAK', 'prov': 'PAPUA TENGAH'},
    'SINAK': {'kab': 'KABUPATEN PUNCAK', 'prov': 'PAPUA TENGAH'},
    'BEOGA': {'kab': 'KABUPATEN PUNCAK', 'prov': 'PAPUA TENGAH'},
    'MOANAMANI': {'kab': 'KABUPATEN DOGIYAI', 'prov': 'PAPUA TENGAH'},
    'MERAUKE': {'kab': 'KABUPATEN MERAUKE', 'prov': 'PAPUA SELATAN'},
    'NABIRE / TELUK KINI': {'kab': 'KABUPATEN NABIRE', 'prov': 'PAPUA TENGAH'},
    'SERUI': {'kab': 'KABUPATEN KEPULAUAN YAPEN', 'prov': 'PAPUA'},
    'BIAK': {'kab': 'KABUPATEN BIAK NUMFOR', 'prov': 'PAPUA'},
    'AMAMAPARE': {'kab': 'KABUPATEN MIMIKA', 'prov': 'PAPUA TENGAH'},
    'POMAKO': {'kab': 'KABUPATEN MIMIKA', 'prov': 'PAPUA TENGAH'},
    'HABESILAM': {'kab': 'KABUPATEN MAPPI', 'prov': 'PAPUA SELATAN'},
    'AGATS': {'kab': 'KABUPATEN ASMAT', 'prov': 'PAPUA SELATAN'},
    'ATSY': {'kab': 'KABUPATEN ASMAT', 'prov': 'PAPUA SELATAN'},
    'SARMI': {'kab': 'KABUPATEN SARMI', 'prov': 'PAPUA'},
    'WAREN': {'kab': 'KABUPATEN WAROPEN', 'prov': 'PAPUA'},
    'JAYAPURA': {'kab': 'KOTA JAYAPURA', 'prov': 'PAPUA'}
}

def get_location_metadata(name):
    name_clean = str(name).upper().strip()
    for key, meta in MAPPING_LOKASI_KAB_PROV.items():
        if key in name_clean:
            return meta
    return {'kab': None, 'prov': 'PAPUA'}

def get_province_by_kabupaten(kab_name):
    kab_clean = str(kab_name).upper().strip()
    for prov, kabs in PEMETAAN_WILAYAH.items():
        if kab_clean in [k.upper() for k in kabs]:
            return prov.upper()
    return 'PAPUA'