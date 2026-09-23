"""
main.py — Backend FastAPI Kuntum Insight (referensi lengkap untuk opencode).

Mengimplementasikan SELURUH 10 endpoint kontrak di PRD.md §10, sudah diuji
end-to-end dengan data asli (kuntum_insight.db + artefak model v1).

Prinsip yang WAJIB dipertahankan (jangan diubah tanpa alasan kuat):
1. FastAPI HANYA serving layer — tidak ada training/fitting di sini (PRD §9.2).
2. Data & model dimuat SEKALI saat startup ke memori (lihat `lifespan`).
3. Semua NaN/NaT dari pandas WAJIB dibersihkan ke None sebelum masuk response
   JSON (lihat `sanitize()`) — NaN mentah membuat body JSON tidak valid dan
   akan membuat `JSON.parse()` di frontend gagal total.

Cara jalan (lokal):
    pip install -r requirements.txt
    uvicorn main:app --reload
    # lalu buka http://127.0.0.1:8000/docs untuk menguji semua endpoint
"""

import json
import math
import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

# WAJIB: tempelkan fungsi ke __main__ SEBELUM joblib.load() pada vectorizer.
# Lihat inference_utils.py untuk penjelasan lengkap kenapa ini diperlukan.
import __main__
from inference_utils import identity_tokenizer, identity_preprocessor
__main__.identity_tokenizer = identity_tokenizer
__main__.identity_preprocessor = identity_preprocessor

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data/kuntum_insight.db"
MODELS_DIR = BASE_DIR / "models"

# CORS: di development, izinkan origin frontend lokal umum (Vite/CRA/Next).
# Di production, WAJIB isi env var FRONTEND_ORIGIN dengan domain asli
# (jangan pernah pakai "*" di production karena API ini publik/tanpa auth).
FRONTEND_ORIGINS = os.environ.get(
    "FRONTEND_ORIGIN",
    "http://localhost:3000,http://localhost:5173,http://127.0.0.1:5173",
).split(",")

state: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Helper: bersihkan NaN/NaT/np.nan menjadi None secara rekursif.
# Wajib dipanggil sebelum me-return dict/list apa pun sebagai response JSON.
# ---------------------------------------------------------------------------
def sanitize(obj: Any) -> Any:
    if isinstance(obj, float) and math.isnan(obj):
        return None
    if isinstance(obj, (np.floating,)):
        return None if math.isnan(float(obj)) else float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, pd.Timestamp):
        return None if pd.isna(obj) else obj.isoformat()
    if obj is pd.NaT:
        return None
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize(v) for v in obj]
    return obj


def df_to_records(df: pd.DataFrame) -> list[dict]:
    """Konversi DataFrame ke list-of-dict yang aman untuk JSON (tanpa NaN mentah)."""
    return sanitize(df.to_dict(orient="records"))


# ---------------------------------------------------------------------------
# Startup / shutdown — muat data & artefak SEKALI ke memori (PRD §9.2)
# ---------------------------------------------------------------------------
def load_all_data():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    reviews_clean = pd.read_sql("SELECT * FROM reviews_clean", conn)
    sentiment_results = pd.read_sql("SELECT * FROM sentiment_results", conn)
    topic_keywords = pd.read_sql("SELECT * FROM topic_keywords", conn)
    conn.close()

    reviews_clean["review_date"] = pd.to_datetime(reviews_clean["review_date"], utc=True, errors="coerce")

    merged = reviews_clean.merge(sentiment_results, on="review_id", how="left")

    state["reviews_clean"] = reviews_clean
    state["sentiment_results"] = sentiment_results
    state["topic_keywords"] = topic_keywords
    state["merged"] = merged

    state["vectorizer"] = joblib.load(MODELS_DIR / "tfidf_vectorizer_v1.pkl")
    state["model"] = joblib.load(MODELS_DIR / "sentiment_model_v1.pkl")
    with open(MODELS_DIR / "label_map.json") as f:
        state["label_map"] = json.load(f)
    with open(MODELS_DIR / "metadata_v1.json") as f:
        state["model_metadata"] = json.load(f)


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_all_data()
    print(f"[startup] {len(state['reviews_clean'])} ulasan dimuat, "
          f"model versi {state['model_metadata']['model_version']} siap.")
    yield
    state.clear()


app = FastAPI(title="Kuntum Insight API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# 1. /api/overview/kpi
# ---------------------------------------------------------------------------
@app.get("/api/overview/kpi")
def get_overview_kpi():
    df = state["reviews_clean"]
    merged = state["merged"]

    sentiment_pct = merged["sentiment_label"].value_counts(normalize=True).round(4).to_dict()
    most_liked = df.loc[df["likes"].idxmax()] if df["likes"].notna().any() and df["likes"].max() > 0 else None

    result = {
        "total_reviews": int(len(df)),
        "avg_rating": round(float(df["rating"].mean()), 2),
        "sentiment_pct": sentiment_pct,
        "has_text_pct": round(float(df["has_text"].mean()), 4),
        "avg_token_count": round(float(df.loc[df["has_text"] == True, "token_count"].mean()), 2),
        "most_liked_review": (
            {
                "review_id": most_liked["review_id"],
                "author": most_liked["author"],
                "likes": int(most_liked["likes"]),
                "review_text_original": most_liked["review_text_original"],
            }
            if most_liked is not None else None
        ),
    }
    return {"data": sanitize(result)}


# ---------------------------------------------------------------------------
# 2. /api/overview/sentiment-distribution
# ---------------------------------------------------------------------------
@app.get("/api/overview/sentiment-distribution")
def get_sentiment_distribution(include_fallback: bool = True):
    merged = state["merged"]
    df = merged if include_fallback else merged[merged["sentiment_source"] == "model"]

    counts = df["sentiment_label"].value_counts()
    total = int(counts.sum())
    result = [
        {"label": label, "count": int(count), "pct": round(count / total, 4) if total else 0}
        for label, count in counts.items()
    ]
    return {"data": result}


# ---------------------------------------------------------------------------
# 3. /api/overview/rating-distribution
# ---------------------------------------------------------------------------
@app.get("/api/overview/rating-distribution")
def get_rating_distribution():
    df = state["reviews_clean"]
    counts = df["rating"].value_counts().sort_index()
    result = [{"rating": float(rating), "count": int(count)} for rating, count in counts.items()]
    return {"data": result}


# ---------------------------------------------------------------------------
# 4. /api/overview/sentiment-trend
#
# CATATAN PENTING (lihat HANDOFF.md §7 & PRD.md §5.1 untuk detail lengkap):
# ~88% data (ulasan yang di-scrape saat tanggalnya masih berformat relatif
# Google Maps, mis. "3 tahun lalu") KEHILANGAN presisi bulan/hari — semuanya
# ter-collapse ke satu tanggal per tahun saat proses cleaning upstream
# mengonversi teks relatif tsb menjadi tanggal absolut. Hanya ulasan dari
# ~12 bulan terakhir sebelum scraping (yang formatnya masih presisi hari/
# minggu di Google Maps) yang benar-benar valid di granularitas bulan.
#
# Endpoint ini TIDAK memperbaiki data yang hilang (tidak mungkin, sumbernya
# sudah hilang sejak scraping) — melainkan menyesuaikan granularitas agar
# TIDAK MENYESATKAN: data lama ditampilkan per TAHUN (perkiraan, apa adanya),
# data 12 bulan terakhir ditampilkan per BULAN (presisi asli). Setiap titik
# diberi flag `is_approximate` agar frontend bisa menandainya secara visual
# (mis. garis putus-putus) — lihat DESIGN.md §5.A untuk panduan render.
# ---------------------------------------------------------------------------
@app.get("/api/overview/sentiment-trend")
def get_sentiment_trend(date_from: str | None = None, date_to: str | None = None):
    df = state["merged"].dropna(subset=["review_date"]).copy()

    if date_from:
        df = df[df["review_date"] >= pd.Timestamp(date_from, tz="UTC")]
    if date_to:
        df = df[df["review_date"] <= pd.Timestamp(date_to, tz="UTC")]

    max_date = state["merged"]["review_date"].max()

    # Deteksi baris yang kena artefak kompresi tanggal (lihat HANDOFF.md §7):
    # scraper mengonversi teks relatif Google Maps ("N tahun lalu") menjadi
    # tanggal absolut berbasis tanggal SCRAPING (bulan Agustus, tanggal 18-21),
    # bukan tanggal asli ulasan diposting. Baris dengan pola bulan=Agustus &
    # tanggal∈{18,19,20,21} adalah tanda pasti artefak ini — TERVERIFIKASI
    # mencakup ~94% dari seluruh data (2.661 dari 2.832 baris), termasuk yang
    # jatuh di "1 tahun lalu" (Agustus tahun scraping - 1). Deteksi ini LEBIH
    # AKURAT daripada sekadar cutoff 365 hari, karena artefaknya bisa
    # menyentuh bulan yang masih dalam rentang "12 bulan terakhir".
    is_fake_date = (df["review_date"].dt.month == 8) & (df["review_date"].dt.day.isin([18, 19, 20, 21]))

    old_df = df[is_fake_date].copy()
    recent_df = df[~is_fake_date].copy()

    def aggregate(sub_df, period_fmt, is_approximate):
        if sub_df.empty:
            return []
        sub_df["period"] = sub_df["review_date"].dt.to_period(period_fmt).astype(str)
        pivot = sub_df.pivot_table(
            index="period", columns="sentiment_label", values="review_id", aggfunc="count", fill_value=0
        )
        for col in ["positif", "netral", "negatif"]:
            if col not in pivot.columns:
                pivot[col] = 0
        pivot["total"] = pivot[["positif", "netral", "negatif"]].sum(axis=1)
        pivot = pivot.sort_index().reset_index()
        pivot["is_approximate"] = is_approximate
        pivot["granularity"] = "year" if period_fmt == "Y" else "month"

        if period_fmt == "Y":
            # Titik tahunan: sertakan estimasi rata-rata/bulan agar SKALA sebanding
            # dengan titik bulanan asli di bagian lain grafik (lihat DESIGN.md §5.A
            # untuk instruksi frontend: pakai *_avg_month sebagai nilai default yang
            # diplot, bukan total tahunan mentah, supaya garis tren tidak menyesatkan
            # secara visual walau granularitas sudah benar).
            for col in ["positif", "netral", "negatif", "total"]:
                pivot[f"{col}_avg_month"] = (pivot[col] / 12).round(2)
        else:
            for col in ["positif", "netral", "negatif", "total"]:
                pivot[f"{col}_avg_month"] = pivot[col]  # sudah bulanan, tidak perlu dibagi

        cols = ["period", "granularity", "is_approximate",
                "positif", "netral", "negatif", "total",
                "positif_avg_month", "netral_avg_month", "negatif_avg_month", "total_avg_month"]
        return pivot[cols].to_dict(orient="records")

    points = aggregate(old_df, "Y", True) + aggregate(recent_df, "M", False)

    return {
        "data": sanitize(points),
        "meta": {
            "detection_method": "month=8 AND day in [18,19,20,21] dianggap tanggal artefak (lihat komentar kode)",
            "note": (
                "Titik dengan is_approximate=true berasal dari ulasan yang tanggal "
                "aslinya sudah hilang saat scraping (Google Maps hanya menampilkan "
                "teks relatif seperti 'N tahun lalu' untuk ulasan lama) — hanya "
                "granularitas tahun yang bisa dipercaya untuk titik-titik tsb. "
                "Titik is_approximate=false (12 bulan terakhir sebelum scraping) "
                "memiliki presisi bulan yang valid. Frontend SEBAIKNYA memplot "
                "field *_avg_month (bukan total mentah) di chart tren utama, agar "
                "skala titik tahunan (dibagi 12) dan bulanan (asli) sebanding "
                "secara visual — lihat DESIGN.md §5.A."
            ),
        },
    }


# ---------------------------------------------------------------------------
# 5. /api/reviews  (paginated, dengan seluruh filter sesuai DESIGN.md §5.B)
# ---------------------------------------------------------------------------
VALID_SORT = {
    "terbaru": ("review_date", False),
    "terpopuler": ("likes", False),
    "rating_tertinggi": ("rating", False),
    "rating_terendah": ("rating", True),
}


@app.get("/api/reviews")
def get_reviews(
    search: str | None = None,
    sentiment: list[str] | None = Query(default=None, alias="sentiment[]"),
    rating_min: float = 1,
    rating_max: float = 5,
    date_from: str | None = None,
    date_to: str | None = None,
    has_text_only: bool = True,
    sort_by: str = "terbaru",
    page: int = 1,
    page_size: int = 20,
):
    df = state["merged"].copy()

    if has_text_only:
        df = df[df["has_text"] == True]

    df = df[(df["rating"] >= rating_min) & (df["rating"] <= rating_max)]

    if sentiment:
        df = df[df["sentiment_label"].isin(sentiment)]

    if date_from:
        df = df[df["review_date"] >= pd.Timestamp(date_from, tz="UTC")]
    if date_to:
        df = df[df["review_date"] <= pd.Timestamp(date_to, tz="UTC")]

    if search:
        df = df[df["review_text_original"].str.contains(search, case=False, na=False)]

    sort_col, ascending = VALID_SORT.get(sort_by, VALID_SORT["terbaru"])
    df = df.sort_values(sort_col, ascending=ascending)

    total = len(df)
    start = (page - 1) * page_size
    page_df = df.iloc[start:start + page_size]

    records = page_df[[
        "review_id", "author", "rating", "review_text_original",
        "sentiment_label", "sentiment_source", "review_date", "likes",
        "has_text",
    ]].copy()
    records["review_date"] = records["review_date"].astype(str)

    return {
        "data": df_to_records(records),
        "meta": {"total": int(total), "page": page, "page_size": page_size},
    }


# ---------------------------------------------------------------------------
# 6. /api/reviews/{review_id}
# ---------------------------------------------------------------------------
@app.get("/api/reviews/{review_id}")
def get_review_detail(review_id: str):
    df = state["merged"]
    row = df[df["review_id"] == review_id]
    if row.empty:
        raise HTTPException(status_code=404, detail="Ulasan tidak ditemukan")

    record = row.iloc[0].copy()
    record["review_date"] = str(record["review_date"])
    # top_keywords disimpan sebagai string JSON — parse agar frontend dapat array asli
    try:
        record["top_keywords"] = json.loads(record["top_keywords"]) if record["top_keywords"] else []
    except (TypeError, json.JSONDecodeError):
        record["top_keywords"] = []
    # review_tokens juga string JSON di reviews_clean
    try:
        record["review_tokens"] = json.loads(record["review_tokens"]) if record["review_tokens"] else []
    except (TypeError, json.JSONDecodeError):
        record["review_tokens"] = []

    return {"data": sanitize(record.to_dict())}


# ---------------------------------------------------------------------------
# 7. /api/topics
# ---------------------------------------------------------------------------
@app.get("/api/topics")
def get_topics(sentiment_label: str = "positif", top_n: int = 20):
    if sentiment_label not in {"positif", "netral", "negatif"}:
        raise HTTPException(status_code=400, detail="sentiment_label harus positif/netral/negatif")

    df = state["topic_keywords"]
    subset = df[df["sentiment_label"] == sentiment_label].sort_values("score", ascending=False).head(top_n)
    return {"data": df_to_records(subset)}


# ---------------------------------------------------------------------------
# 8. /api/topics/{theme}/reviews
# ---------------------------------------------------------------------------
@app.get("/api/topics/{theme}/reviews")
def get_reviews_by_theme(theme: str, sentiment_label: str = "negatif", page: int = 1, page_size: int = 10):
    topic_df = state["topic_keywords"]
    keywords_for_theme = topic_df[
        (topic_df["theme"] == theme) & (topic_df["sentiment_label"] == sentiment_label)
    ]["keyword"].tolist()

    if not keywords_for_theme:
        return {"data": [], "meta": {"total": 0, "page": page, "page_size": page_size}}

    merged = state["merged"]
    subset = merged[merged["sentiment_label"] == sentiment_label].copy()

    def has_theme_keyword(tokens_json):
        try:
            tokens = json.loads(tokens_json) if tokens_json else []
        except (TypeError, json.JSONDecodeError):
            return False
        return any(k in tokens for k in keywords_for_theme)

    subset = subset[subset["review_tokens"].apply(has_theme_keyword)]
    total = len(subset)
    start = (page - 1) * page_size
    page_df = subset.iloc[start:start + page_size]

    records = page_df[["review_id", "author", "rating", "review_text_original", "review_date"]].copy()
    records["review_date"] = records["review_date"].astype(str)

    return {
        "data": df_to_records(records),
        "meta": {"total": int(total), "page": page, "page_size": page_size},
    }


# ---------------------------------------------------------------------------
# 9. /api/recommendations
# ---------------------------------------------------------------------------
@app.get("/api/recommendations")
def get_recommendations(top_n: int = 5):
    topic_df = state["topic_keywords"]
    merged = state["merged"]

    negatif_themes = (
        topic_df[(topic_df["sentiment_label"] == "negatif") & (topic_df["theme"].notna())]
        .groupby("theme")["score"].sum()
        .sort_values(ascending=False)
        .head(top_n)
    )

    recommendations = []
    for theme, _ in negatif_themes.items():
        keywords_for_theme = topic_df[
            (topic_df["theme"] == theme) & (topic_df["sentiment_label"] == "negatif")
        ]["keyword"].tolist()

        subset = merged[merged["sentiment_label"] == "negatif"].copy()

        def has_kw(tokens_json, kws=keywords_for_theme):
            try:
                tokens = json.loads(tokens_json) if tokens_json else []
            except (TypeError, json.JSONDecodeError):
                return False
            return any(k in tokens for k in kws)

        theme_reviews = subset[subset["review_tokens"].apply(has_kw)]
        theme_reviews_sorted = theme_reviews.sort_values("review_date", ascending=False)
        samples = theme_reviews_sorted.head(2)

        recommendations.append({
            "theme": theme,
            "review_count": int(len(theme_reviews)),
            "sample_reviews": [
                {"text": row["review_text_original"], "review_date": str(row["review_date"])}
                for _, row in samples.iterrows()
            ],
        })

    recommendations.sort(key=lambda r: r["review_count"], reverse=True)
    return {"data": sanitize(recommendations)}


# ---------------------------------------------------------------------------
# 10. /api/pipeline/status
# ---------------------------------------------------------------------------
@app.get("/api/pipeline/status")
def get_pipeline_status():
    result = {
        "model_version": state["model_metadata"]["model_version"],
        "algorithm": state["model_metadata"]["algorithm"],
        "macro_f1": state["model_metadata"]["macro_f1"],
        "accuracy": state["model_metadata"]["accuracy"],
        "trained_at": state["model_metadata"]["trained_at"],
        "total_reviews_in_db": int(len(state["reviews_clean"])),
    }
    return {"data": sanitize(result)}


# ---------------------------------------------------------------------------
# (Opsional, PRD §9.4) — reload cache in-memory tanpa restart proses penuh,
# dipanggil setelah skrip batch update menulis data baru ke SQLite.
# ---------------------------------------------------------------------------
@app.post("/api/admin/reload-cache")
def reload_cache():
    load_all_data()
    return {"data": {"status": "reloaded", "total_reviews": int(len(state["reviews_clean"]))}}


# ---------------------------------------------------------------------------
# Static Files (Frontend SPA)
#
# PENTING: Mount "/" harus berada di PALING AKHIR file — setelah SEMUA
# @app.get()/@app.post() API didaftarkan. Jika mount "/" diletakkan lebih
# awal, ia menjadi catch-all yang menutupi request ke /api/* (Starlette
# mencocokkan route berdasarkan urutan pendaftaran).
#
# Frontend memakai fetch() path RELATIF (mis. "/api/overview/kpi") karena
# frontend & backend berada dalam satu origin lewat mount ini.
# ---------------------------------------------------------------------------
from fastapi.staticfiles import StaticFiles

FRONTEND_DIR = BASE_DIR / "frontend"
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
