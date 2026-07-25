"""
Modul Generator Narasi AI (Gemini) untuk Aplikasi Streamlit BPS
Berdasarkan hasil diskusi teknis:
1. Pemanggilan AI dipindahkan setelah tabel selesai (Batch per Moda).
2. Penyimpanan hasil menggunakan st.session_state (Cache) agar tidak generate ulang saat rerun.
3. Penanganan error secara transparan tanpa menyembunyikannya.
4. Pembersihan dan penyempurnaan prompt untuk narasi formal 2 paragraf.
"""

import os
import re
import time
import logging
from collections import defaultdict
import streamlit as st
import pandas as pd
import numpy as np

# Coba import Google GenAI SDK terbaru
try:
    from google import genai
except ImportError:
    genai = None

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)


def ensure_narasi_cache():
    """Memastikan session state untuk cache narasi tersedia."""
    if "narasi_cache" not in st.session_state:
        st.session_state["narasi_cache"] = {}


def normalize_label(label):
    """Normalisasi label indikator untuk pencocokan parser."""
    return re.sub(r"\s+", " ", str(label).strip().lower())


def get_cache_key(prov, moda, col_target, bln, thn):
    """Menghasilkan unique cache key per indikator."""
    return f"{prov}|{moda}|{col_target}|{bln}|{thn}"


def get_gemini_api_keys():
    """Mengambil API key Gemini dari Streamlit secrets atau environment variables."""
    keys = []

    def add_value(v):
        if not v:
            return
        if isinstance(v, str):
            v = v.strip()
            if v:
                keys.append(v)
        elif isinstance(v, (list, tuple)):
            for x in v:
                add_value(x)
        else:
            s = str(v).strip()
            if s:
                keys.append(s)

    try:
        add_value(st.secrets.get("GEMINI_API_KEYS"))
        add_value(st.secrets.get("GEMINI_API_KEY"))
        add_value(st.secrets.get("GOOGLE_API_KEY"))
        add_value(st.secrets.get("API_GEMINI_KEYS"))
        add_value(st.secrets.get("API_GEMINI_KEY"))
    except Exception as e:
        logger.exception("Gagal membaca Streamlit secrets: %s", e)

    add_value(os.getenv("GEMINI_API_KEY"))
    add_value(os.getenv("GOOGLE_API_KEY"))

    # Hapus duplikat
    return list(dict.fromkeys(keys))


def parse_narasi_sections(raw_text):
    """
    Mem-parsing teks batch dari Gemini berdasarkan heading:
    === NAMA INDIKATOR ===
    """
    hasil = {}
    if not raw_text:
        return hasil

    teks = str(raw_text).strip()
    pola = r"(?m)^===\s*(.+?)\s*===\s*$"
    parts = re.split(pola, teks)

    for i in range(1, len(parts), 2):
        label = normalize_label(parts[i])
        isi = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if label and isi:
            hasil[label] = isi

    return hasil


def parse_two_paragraphs(text):
    """Memastikan teks terpecah menjadi minimal 2 paragraf."""
    if not text or not str(text).strip():
        return None, None

    parts = [p.strip() for p in str(text).strip().split("\n\n") if p.strip()]
    if len(parts) >= 2:
        return parts[0], "\n\n".join(parts[1:])
    if len(parts) == 1:
        return parts[0], ""
    return None, None


def generate_narrative_ai_batch(items, prov, moda, bln, thn, prev_bln, prev_thn, model_name="gemini-2.5-flash"):
    """
    Melakukan generate narasi secara batch (1 request per moda) untuk efisiensi waktu 
    dan menghindari beban request berulang pada loop tabel.
    """
    ensure_narasi_cache()
    cache = st.session_state["narasi_cache"]
    hasil = {}

    pending = []
    for item in items:
        key = item["cache_key"]
        if key in cache:
            hasil[key] = {"text": cache[key], "source": "Cache"}
        else:
            pending.append(item)

    if not pending:
        return hasil

    if genai is None:
        st.error("Library `google-genai` belum terinstal di lingkungan Python.")
        return hasil

    api_keys = get_gemini_api_keys()
    if not api_keys:
        st.error("API key Gemini tidak ditemukan. Harap atur di Streamlit Secrets atau Environment Variables.")
        return hasil

    # Susun data sections untuk batch prompt
    data_sections = []
    for item in pending:
        data_sections.append(f"### {item['label']}\n{item['table_markdown']}")

    prompt = f"""
Bertindaklah sebagai analis data senior di Badan Pusat Statistik (BPS) yang profesional namun komunikatif.

Tugas:
Buat narasi untuk SETIAP indikator di bawah ini berdasarkan tabel data yang disediakan.

Aturan output:
- Keluarkan hanya bagian-bagian narasi, tanpa kalimat pengantar atau penutup umum.
- Untuk setiap indikator, gunakan format heading tepat seperti ini:
=== NAMA INDIKATOR ===
Paragraf pertama (membahas kondisi bulan berjalan, perubahan terhadap bulan sebelumnya / m-t-m, dan faktor menonjol).

Paragraf kedua (membahas kumulatif Januari-{bln} {thn}, perbandingan periode tahun sebelumnya / y-o-y, dan ringkasan interpretasi).

- Setiap indikator wajib terdiri dari tepat 2 paragraf.
- Gunakan bahasa formal, angka format Indonesia, dan jangan sebutkan bahwa Anda adalah AI.

Konteks umum:
- Provinsi: {prov}
- Moda: {moda}
- Periode: {bln} {thn}
- Pembanding: {prev_bln} {prev_thn}

Data per indikator:
{chr(10).join(data_sections)}
"""

    last_error = None

    for key in api_keys:
        start = time.perf_counter()
        try:
            client = genai.Client(api_key=key.strip())
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=2048,
                ),
            )

            raw_text = getattr(response, "text", None)
            if not raw_text or not str(raw_text).strip():
                raise ValueError("Respons Gemini kosong.")

            parsed = parse_narasi_sections(raw_text)

            for item in pending:
                cache_key = item["cache_key"]
                label_norm = normalize_label(item["label"])
                section = parsed.get(label_norm)

                if section:
                    p1, p2 = parse_two_paragraphs(section)
                    text_final = "\n\n".join([p for p in [p1, p2] if p]).strip()
                    if text_final:
                        hasil[cache_key] = {"text": text_final, "source": "Gemini AI"}
                        cache[cache_key] = text_final
                    else:
                        hasil[cache_key] = {"text": None, "source": "Gemini AI"}
                else:
                    hasil[cache_key] = {"text": None, "source": "Gemini AI"}

            elapsed = time.perf_counter() - start
            logger.info("Generate narasi batch moda %s selesai dalam %.2f detik", moda, elapsed)
            return hasil

        except Exception as e:
            last_error = e
            logger.exception("Gagal generate narasi batch untuk moda %s: %s", moda, e)
            continue

    st.error(f"Gagal generate narasi AI untuk moda {moda}. Error terakhir: {last_error}")
    return hasil


def render_narasi_setelah_tabel(all_collected_data):
    """
    Fungsi eksekusi yang dipanggil setelah seluruh tabel selesai dirender.
    Mengelompokkan data per moda dan memicu `generate_narrative_ai_batch`.
    """
    if not all_collected_data:
        return

    grouped = defaultdict(list)
    for item in all_collected_data:
        grouped[item["moda"]].append(item)

    st.markdown("---")
    st.subheader("🤖 Narasi Analisis Otomatis (BPS)")

    for moda, items in grouped.items():
        items = sorted(items, key=lambda x: x.get("table_no") or 0)
        if not items:
            continue

        with st.spinner(f"Sedang memproses narasi AI untuk {moda}..."):
            batch_result = generate_narrative_ai_batch(
                items=items,
                prov=items[0]["prov"],
                moda=moda,
                bln=items[0]["bln"],
                thn=items[0]["thn"],
                prev_bln=items[0]["prev_bln"],
                prev_thn=items[0]["prev_thn"],
            )

        st.markdown(f"#### Moda: {moda}")

        for item in items:
            cache_key = item["cache_key"]
            res = batch_result.get(cache_key, {})
            narasi_teks = res.get("text")
            sumber = res.get("source", "Unknown")

            with st.container():
                st.markdown(f"**Indikator: {item['label']}** *(Sumber: {sumber})*")
                if narasi_teks:
                    st.write(narasi_teks)
                else:
                    st.warning("Narasi belum tersedia atau gagal digenerate.")
                st.markdown("")
