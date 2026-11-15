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

import base64
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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
# Di production, WAJIB isi env var FRONTEND_ORIGIN dengan domain asli.
# Seluruh endpoint /api/* (kecuali /api/auth/login) kini WAJIB memakai token
# login — frontend & backend satu-origin, jadi CORS hanya relevan di dev.
FRONTEND_ORIGINS = os.environ.get(
    "FRONTEND_ORIGIN",
    "http://localhost:3000,http://localhost:5173,http://127.0.0.1:5173",
).split(",")

state: dict[str, Any] = {}

# ---------------------------------------------------------------------------
# Autentikasi — token HMAC-stateless, stdlib SAJA (tanpa dependency baru).
# Detil desain, alur kerja, dan gotcha: HANDOFF.md §13.
#
#   - Kredensial & server_secret tersimpan di backend_seed/auth.json (gitignored).
#   - Password di-hash PBKDF2-SHA256 (hashlib); token ditandatangani HMAC-SHA256
#     memakai server_secret dan berisi username + exp (kedaluwarsa).
#   - auth.json belum ada → dibuat otomatis admin/admin (DEV DEFAULT) + peringatan.
#     Produksi WAJIB menjalankan `python scripts/set_auth.py` di server.
# ---------------------------------------------------------------------------
AUTH_CONFIG_PATH = BASE_DIR / "backend_seed" / "auth.json"
DEFAULT_SESSION_TTL = int(os.environ.get("SESSION_TTL_SECONDS", "86400"))  # 24 jam


def _pbkdf2_hex(password: str, salt_hex: str, iterations: int) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt_hex), iterations
    ).hex()


def load_or_create_auth_config() -> dict:
    if AUTH_CONFIG_PATH.exists():
        return json.loads(AUTH_CONFIG_PATH.read_text(encoding="utf-8"))
    salt = secrets.token_hex(16)
    cfg = {
        "server_secret": secrets.token_hex(32),
        "iterations": 100_000,
        "session_ttl_seconds": DEFAULT_SESSION_TTL,
        "users": [
            {
                "username": "admin",
                "salt": salt,
                "password_hash": _pbkdf2_hex("admin", salt, 100_000),
            }
        ],
    }
    AUTH_CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    print("=" * 72)
    print("PERINGATAN: auth.json tidak ditemukan — dibuat AKUN DEFAULT:")
    print("  username : admin")
    print("  password : admin")
    print("  Ganti segera untuk produksi:  python scripts/set_auth.py")
    print("=" * 72)
    return cfg


def _secret_bytes() -> bytes:
    return bytes.fromhex(state["auth"]["server_secret"])


def sign_token(payload: dict) -> str:
    header_b64 = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).decode().rstrip("=")
    sig = hmac.new(_secret_bytes(), header_b64.encode(), hashlib.sha256).hexdigest()
    return f"{header_b64}.{sig}"


def verify_token(token: str) -> dict | None:
    parts = token.split(".")
    if len(parts) != 2:
        return None
    header_b64, sig = parts
    expected = hmac.new(_secret_bytes(), header_b64.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        header_b64 += "=" * (-len(header_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(header_b64.encode()))
    except Exception:
        return None
    if isinstance(payload, dict) and payload.get("exp", 0) > time.time():
        return payload
    return None


# Limiter percobaan login sederhana di memori (tanpa DB): {key: [timestamp gagal]}
login_attempts: dict[str, list[float]] = {}

# Revoke logout (in-memory): token stateless JWT tidak bisa "dihapus",
# jadi logout = deny-list id token (jti). Isi set ini membuat semua
# akses dengan token tersebut 401 (HANDOFF §13).
_revoked_jtis: set[str] = set()


def _login_blocked(key: str, limit: int = 5, window: int = 900) -> bool:
    now = time.time()
    recent = [t for t in login_attempts.get(key, []) if now - t < window]
    login_attempts[key] = recent
    return len(recent) >= limit


def _record_failure(key: str):
    login_attempts.setdefault(key, []).append(time.time())


def require_auth(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Login diperlukan.")
    payload = verify_token(authorization[len("Bearer "):])
    if payload is None:
        raise HTTPException(
            status_code=401, detail="Token tidak valid atau kedaluwarsa."
        )
    if payload.get("jti") in _revoked_jtis:
        raise HTTPException(
            status_code=401, detail="Sesi sudah dicabut (logout). Silakan login ulang."
        )
    return payload


class LoginBody(BaseModel):
    username: str
    password: str


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


DATE_FILTER_HELP = (
    "Format ISO (YYYY-MM-DD atau YYYY-MM-DD HH:MM:SS). Jika hanya date_from atau date_to "
    "yang diisi, sisi lainnya tidak dibatasi."
)


def _apply_date_filter(df: pd.DataFrame, date_from: str | None = None, date_to: str | None = None) -> pd.DataFrame:
    """Filter baris berdasarkan review_date (UTC). Input luar harus sudah memiliki kolom review_date."""
    if date_from:
        df = df[df["review_date"] >= pd.Timestamp(date_from, tz="UTC")]
    if date_to:
        df = df[df["review_date"] <= pd.Timestamp(date_to, tz="UTC")]
    return df


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

    state["auth"] = load_or_create_auth_config()


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
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# 1. /api/overview/kpi
# ---------------------------------------------------------------------------
@app.get("/api/overview/kpi", dependencies=[Depends(require_auth)])
def get_overview_kpi(
    date_from: str | None = Query(default=None, description=DATE_FILTER_HELP),
    date_to: str | None = Query(default=None, description=DATE_FILTER_HELP),
):
    df = _apply_date_filter(state["reviews_clean"], date_from, date_to)
    merged = _apply_date_filter(state["merged"], date_from, date_to)

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
@app.get("/api/overview/sentiment-distribution", dependencies=[Depends(require_auth)])
def get_sentiment_distribution(
    include_fallback: bool = True,
    date_from: str | None = Query(default=None, description=DATE_FILTER_HELP),
    date_to: str | None = Query(default=None, description=DATE_FILTER_HELP),
):
    merged = _apply_date_filter(state["merged"], date_from, date_to)
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
@app.get("/api/overview/rating-distribution", dependencies=[Depends(require_auth)])
def get_rating_distribution(
    date_from: str | None = Query(default=None, description=DATE_FILTER_HELP),
    date_to: str | None = Query(default=None, description=DATE_FILTER_HELP),
):
    df = _apply_date_filter(state["reviews_clean"], date_from, date_to)
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
@app.get("/api/overview/sentiment-trend", dependencies=[Depends(require_auth)])
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


@app.get("/api/reviews", dependencies=[Depends(require_auth)])
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
@app.get("/api/reviews/{review_id}", dependencies=[Depends(require_auth)])
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
@app.get("/api/topics", dependencies=[Depends(require_auth)])
def get_topics(sentiment_label: str = "positif", top_n: int = 20):
    if sentiment_label not in {"positif", "netral", "negatif"}:
        raise HTTPException(status_code=400, detail="sentiment_label harus positif/netral/negatif")

    df = state["topic_keywords"]
    subset = df[df["sentiment_label"] == sentiment_label].sort_values("score", ascending=False).head(top_n)
    return {"data": df_to_records(subset)}


# ---------------------------------------------------------------------------
# 8. /api/topics/{theme}/reviews
# ---------------------------------------------------------------------------
@app.get("/api/topics/{theme}/reviews", dependencies=[Depends(require_auth)])
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
# 9. /api/recommendations — kartu rekomendasi berbasis kesimpulan + bukti
# ---------------------------------------------------------------------------
THEME_LABELS = {
    "harga": "Harga",
    "tiket_masuk": "Tiket / Biaya Masuk",
    "fasilitas": "Fasilitas",
    "hewan_satwa": "Hewan & Satwa",
    "makanan_kuliner": "Makanan & Kuliner",
    "pelayanan_staf": "Pelayanan Staf",
    "anak_keluarga": "Anak & Keluarga",
    "akses_lalulintas": "Akses & Lalu Lintas",
}

# Interpretasi singkat per tema — dipakai menyusun kalimat kesimpulan.
THEME_INTERPRETATION = {
    "harga": "keluhan berpusat pada persepsi harga yang dianggap kurang sepadan dengan pengalaman yang didapat",
    "tiket_masuk": "keluhan menyoroti biaya masuk yang dianggap memberatkan pengunjung",
    "fasilitas": "keluhan menyoroti kondisi atau ketersediaan fasilitas yang belum memadai",
    "hewan_satwa": "keluhan terkait kondisi, kebersihan, atau interaksi dengan satwa",
    "makanan_kuliner": "keluhan menyoroti kualitas, variasi, atau harga makanan dan kuliner",
    "pelayanan_staf": "keluhan menyoroti keramahan, kecepatan, atau responsivitas staf",
    "anak_keluarga": "keluhan terkait fasilitas atau keamanan untuk anak dan keluarga",
    "akses_lalulintas": "keluhan terkait kemacetan, akses jalan, atau area parkir",
}

# Usulan tindakan (rekomendasi perbaikan) per tema.
THEME_ACTION = {
    "harga": "Evaluasi kewajaran harga dan komunikasikan nilai (fasilitas/pengalaman) yang didapat pengunjung.",
    "tiket_masuk": "Tinjau kebijakan harga tiket masuk dan pertimbangkan paket atau promo yang lebih ramah pengunjung.",
    "fasilitas": "Audit dan jadwalkan perawatan fasilitas, prioritaskan yang paling sering dikeluhkan.",
    "hewan_satwa": "Tingkatkan kebersihan kandang, kesejahteraan satwa, dan atur alur interaksi pengunjung.",
    "makanan_kuliner": "Tinjau kualitas dan variasi menu serta kewajaran harga, tambahkan pilihan terjangkau.",
    "pelayanan_staf": "Latih keramahan, kecepatan, dan responsivitas staf dalam melayani pengunjung.",
    "anak_keluarga": "Lengkapi fasilitas ramah anak dan tingkatkan aspek keamanan untuk keluarga.",
    "akses_lalulintas": "Perbaiki petunjuk arah, manajemen parkir, dan akses transportasi menuju lokasi.",
}

# ---------------------------------------------------------------------------
# Lapisan relevansi tema (Revisi 3).
#
# Tujuan: memastikan angka "N ulasan terkait" dan bukti ulasan berasal dari
# himpunan yang SAMA, sehingga tidak mungkin muncul ulasan yang tidak relevan.
# `topic_keywords` dari model terlalu umum untuk sebagian tema (mis. hanya
# "makan", "tempat", "kurang"), sehingga dicocokkan ulang memakai istilah inti
# tema + frasa pengecualian di bawah ini.
# ---------------------------------------------------------------------------
THEME_RELEVANCE = {
    "harga": {
        "include": [
            r"harga", r"mahal", r"kemahalan", r"overprice", r"over price",
            r"worth it", r"biaya", r"tarif", r"80\s?rb", r"80\s?ribu",
            r"70\s?rb", r"70\s?ribu",
        ],
        "exclude": [],
    },
    "tiket_masuk": {
        "include": [
            r"tiket", r"biaya masuk", r"harga masuk", r"tiket masuk", r"htp",
            r"biaya tiket", r"harga tiket",
        ],
        "exclude": [r"tiket parkir", r"karcis parkir"],
    },
    "makanan_kuliner": {
        "include": [
            r"kuliner", r"resto", r"restoran", r"warung", r"kafe", r"cafe",
            r"menu", r"makanan", r"minuman", r"snack", r"jajanan", r"porsi",
            r"rasa", r"nasi", r"kantin", r"tempat makan", r"makan siang",
            r"sarapan",
        ],
        "exclude": [
            r"makan\s+hewan", r"kasih\s+makan",
            r"makan(?:an)?\s+(?:sapi|hewan|kelinci|ikan|ternak|ayam|kambing)",
            r"pakan", r"memancing", r"pancing", r"makan\s+rumput",
        ],
    },
    "fasilitas": {
        "include": [
            r"fasilitas", r"toilet", r"wc", r"musholla", r"mushola",
            r"gazebo", r"kursi", r"bangunan", r"tempat sampah",
            r"kolam", r"wahana", r"sarana",
        ],
        "exclude": [],
    },
    "hewan_satwa": {
        "include": [
            r"hewan", r"satwa", r"kelinci", r"marmut", r"hamster", r"kandang",
            r"sapi", r"kambing", r"ayam", r"bebek", r"ikan", r"kuda", r"kura",
            r"burung", r"rusa",
        ],
        "exclude": [],
    },
    "pelayanan_staf": {
        "include": [
            r"petugas", r"staf", r"karyawan", r"pelayan", r"pegawai",
            r"resepsionis", r"satpam", r"teller", r"pelayanan", r"komunikatif",
            r"jutek", r"kasar", r"ramah", r"dilayani", r"melayani",
        ],
        "exclude": [],
    },
    "anak_keluarga": {
        "include": [
            r"anak", r"keluarga", r"balita", r"stroller", r"edukasi",
            r"wisata keluarga", r"ramah anak", r"anak kecil",
        ],
        "exclude": [],
    },
    "akses_lalulintas": {
        "include": [
            r"macet", r"kemacetan", r"akses", r"jalan", r"gerbang",
            r"lalu lintas", r"transportasi", r"angkutan", r"ojek", r"bus",
            r"kendaraan", r"parkir", r"pak ogah",
        ],
        "exclude": [r"jalan[- ]jalan", r"jalan santai"],
    },
}

# Sinyal keluhan — dipakai untuk memeringkat bukti, bukan untuk menghitung jumlah.
NEGATIVE_CUES = re.compile(
    r"\b(tidak|tak|kurang|gak|ga|nggak|enggak|belum|sayang|mahal|kemahalan|"
    r"kotor|kurus|kering|jelek|sempit|sedikit|banyak|kecewa|buruk|parah|rusak|"
    r"bau|panas|telat|lama|antre|antri|tutup|bohong|kasar|jutek|overprice|"
    r"sepi|terbengkalai|mengecewakan|mengcewakan)\b",
    re.IGNORECASE,
)

METHODOLOGY_NOTE = (
    "Jumlah ulasan per tema dihitung dari ulasan negatif yang memuat istilah inti tema "
    "dan tidak memuat frasa ambigu (mis. 'kasih makan hewan' untuk Makanan & Kuliner). "
    "Satu ulasan dapat menyebut lebih dari satu tema, sehingga jumlah antar-tema tidak "
    "dijumlahkan menjadi 132. Bukti ulasan diambil dari himpunan yang sama dengan angka tersebut."
)


def _compile_theme_relevance() -> dict:
    compiled = {}
    for theme, spec in THEME_RELEVANCE.items():
        include = re.compile(
            "|".join(f"(?<![A-Za-z])(?:{p})(?![A-Za-z])" for p in spec["include"]),
            re.IGNORECASE,
        )
        exclude = (
            re.compile(
                "|".join(f"(?<![A-Za-z])(?:{p})(?![A-Za-z])" for p in spec["exclude"]),
                re.IGNORECASE,
            )
            if spec.get("exclude")
            else None
        )
        compiled[theme] = (include, exclude)
    return compiled


THEME_RELEVANCE_COMPILED = _compile_theme_relevance()


def _match_theme(text: str, theme: str) -> list[str]:
    """Kembalikan istilah tema yang cocok pada teks (kosong = tidak relevan)."""
    if not text:
        return []
    include, exclude = THEME_RELEVANCE_COMPILED.get(theme, (None, None))
    if include is None:
        return []
    if exclude and exclude.search(text):
        return []
    terms = []
    for match in include.finditer(text):
        term = match.group(0).lower()
        if term not in terms:
            terms.append(term)
    return terms


def _format_id_float(value: float, digits: int = 1) -> str:
    """Format angka desimal gaya Indonesia (koma sebagai pemisah)."""
    return f"{value:.{digits}f}".replace(".", ",")


def _priority_for(count: int) -> str:
    """Prioritas berbasis jumlah ulasan tervalidasi (ambang didokumentasikan di HANDOFF §15)."""
    if count >= 20:
        return "Tinggi"
    if count >= 15:
        return "Sedang"
    return "Rendah"


def _evidence_strength(count: int) -> str:
    if count >= 20:
        return "kuat"
    if count >= 15:
        return "sedang"
    return "terbatas"


@app.get("/api/recommendations", dependencies=[Depends(require_auth)])
def get_recommendations(top_n: int = 8):
    """Kartu rekomendasi: angka dan bukti dihitung dari himpunan ulasan yang sama."""
    from collections import Counter

    topic_df = state["topic_keywords"]
    merged = state["merged"]

    negative = merged[merged["sentiment_label"] == "negatif"].copy()
    total_negative = int(len(negative))

    prepared = []
    for _, row in negative.iterrows():
        raw = row["review_text_original"]
        text = (str(raw) if pd.notna(raw) else "").strip()
        if text:
            prepared.append((row, text))

    # Hitung kecocokan semua tema per ulasan sekali, untuk mengukur "fokus":
    # ulasan yang menyebut banyak tema berbeda tidak diprioritaskan sebagai bukti
    # untuk satu tema tertentu.
    per_review = {}
    for row, text in prepared:
        lower = text.lower()
        hits = {}
        for theme_name in THEME_RELEVANCE:
            terms = _match_theme(lower, theme_name)
            if terms:
                hits[theme_name] = terms
        per_review[row["review_id"]] = hits

    negatif_themes = (
        topic_df[(topic_df["sentiment_label"] == "negatif") & (topic_df["theme"].notna())]
        .groupby("theme")["score"].sum()
        .sort_values(ascending=False)
    )

    def pick_samples(matched_rows: list, limit: int = 3) -> list[dict]:
        """Pilih bukti dari himpunan tervalidasi: istilah tema + sinyal keluhan.

        Bila tersedia cukup kandidat rating <= 3, sampel positif (rating 4-5)
        tidak ditampilkan agar bukti konsisten dengan label negatif.
        """
        candidates, seen = [], set()
        for row, text, terms, total_terms in matched_rows:
            key = re.sub(r"\s+", " ", text.lower())[:100]
            if key in seen:
                continue
            seen.add(key)
            rating = int(row["rating"]) if pd.notna(row["rating"]) else None
            has_cue = 1.0 if NEGATIVE_CUES.search(text) else 0.0
            is_low = rating is not None and rating <= 3
            length_pref = min(len(text), 400) / 400.0
            word_count = max(len(text.split()), 1)
            density_bonus = min(1.5, (len(terms) / word_count) * 15.0)
            focus = len(terms) / total_terms if total_terms else 0.0
            score = (
                2.0 * min(len(terms), 4)
                + 1.5 * has_cue
                + (1.0 if is_low else 0.0)
                + length_pref
                + density_bonus
                + 3.0 * focus
            )
            candidates.append({
                "score": score,
                "rating": rating,
                "is_low": is_low,
                "has_cue": has_cue > 0,
                "row": row,
                "text": text,
                "terms": terms,
            })

        low = [c for c in candidates if c["is_low"]]
        pool = low if len(low) >= limit else candidates
        with_cue = [c for c in pool if c["has_cue"]]
        if len(with_cue) >= limit:
            pool = with_cue
        pool.sort(key=lambda c: (-c["score"], c["rating"] if c["rating"] is not None else 9))

        samples = []
        for cand in pool[:limit]:
            row = cand["row"]
            date_val = row["review_date"]
            samples.append({
                "text": cand["text"],
                "review_date": str(date_val) if pd.notna(date_val) else None,
                "rating": int(row["rating"]) if pd.notna(row["rating"]) else None,
                "author": str(row["author"]) if pd.notna(row["author"]) else None,
                "matched_terms": cand["terms"],
            })
        return samples

    recommendations = []
    for theme in negatif_themes.index:
        if theme not in THEME_RELEVANCE:
            continue

        matched_rows = []
        for row, text in prepared:
            hits = per_review[row["review_id"]]
            terms = hits.get(theme)
            if terms:
                matched_rows.append((row, text, terms, sum(len(v) for v in hits.values())))
        count = len(matched_rows)
        if count == 0:
            continue

        term_freq = Counter()
        for _, _, terms, _ in matched_rows:
            for term in set(terms):
                term_freq[term] += 1
        top_keywords = [
            {"keyword": term, "count": freq}
            for term, freq in term_freq.most_common(3)
        ]

        ratings = pd.to_numeric(
            pd.Series([row["rating"] for row, _, _, _ in matched_rows]), errors="coerce"
        ).dropna()
        avg_rating = float(ratings.mean()) if len(ratings) else None
        low_rating_pct = float((ratings <= 2).mean() * 100) if len(ratings) else None

        label = THEME_LABELS.get(theme, str(theme).replace("_", " ").title())
        interpretation = THEME_INTERPRETATION.get(
            theme, "keluhan terkait aspek ini perlu ditindaklanjuti"
        )
        action = THEME_ACTION.get(
            theme, "Tindak lanjuti keluhan terkait aspek ini sesuai temuan di lapangan."
        )

        kw_names = [k["keyword"] for k in top_keywords]
        if len(kw_names) >= 3:
            kw_text = f"“{kw_names[0]}”, “{kw_names[1]}”, dan “{kw_names[2]}”"
        elif len(kw_names) == 2:
            kw_text = f"“{kw_names[0]}” dan “{kw_names[1]}”"
        elif kw_names:
            kw_text = f"“{kw_names[0]}”"
        else:
            kw_text = "—"

        share_pct = (count / total_negative * 100) if total_negative else 0.0
        if avg_rating is not None:
            rating_text = (
                f"{_format_id_float(low_rating_pct)}% di antaranya memberi rating 1–2 "
                f"(rata-rata {_format_id_float(avg_rating)}/5)"
            )
        else:
            rating_text = "data rating tidak tersedia"

        insight = (
            f"Dari {total_negative} ulasan negatif, {count} di antaranya menyebut {label} "
            f"({_format_id_float(share_pct)}%). {rating_text}. "
            f"Istilah yang paling sering muncul: {kw_text}. Artinya, {interpretation}."
        )

        strength = _evidence_strength(count)
        sample_limit = 3 if strength != "terbatas" else 2
        recommendations.append({
            "theme": theme,
            "label": label,
            "review_count": count,
            "share_pct": round(share_pct, 1),
            "avg_rating": round(avg_rating, 2) if avg_rating is not None else None,
            "low_rating_pct": round(low_rating_pct, 1) if low_rating_pct is not None else None,
            "keywords": top_keywords,
            "insight": insight,
            "action": action,
            "priority": _priority_for(count),
            "evidence_strength": strength,
            "sample_reviews": pick_samples(matched_rows, sample_limit),
        })

    recommendations.sort(key=lambda r: r["review_count"], reverse=True)

    summary = None
    if recommendations:
        top3_text = ", ".join(
            f"{r['label']} ({r['review_count']})" for r in recommendations[:3]
        )
        summary = (
            f"Terdapat {total_negative} ulasan negatif. Tema yang paling sering disebut: "
            f"{top3_text}. Kesimpulan tiap tema dihitung dari ulasan yang menyebut istilah "
            f"inti tema; bukti ulasan diambil dari himpunan yang sama."
        )

    return sanitize({
        "data": recommendations[:top_n],
        "meta": {
            "negative_total": total_negative,
            "theme_total": len(recommendations),
            "summary": summary,
            "methodology": METHODOLOGY_NOTE,
        },
    })


# ---------------------------------------------------------------------------
# 10. /api/pipeline/status
# ---------------------------------------------------------------------------
@app.get("/api/pipeline/status", dependencies=[Depends(require_auth)])
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
@app.post("/api/admin/reload-cache", dependencies=[Depends(require_auth)])
def reload_cache():
    load_all_data()
    return {"data": {"status": "reloaded", "total_reviews": int(len(state["reviews_clean"]))}}


# ---------------------------------------------------------------------------
# Autentikasi — login (publik), me / logout (perlu token).
# Wajib berada SEBELUM mount static "/".
# ---------------------------------------------------------------------------
@app.post("/api/auth/login")
def auth_login(body: LoginBody):
    key = body.username
    if _login_blocked(key):
        raise HTTPException(
            status_code=429,
            detail="Terlalu banyak percobaan gagal. Tunggu beberapa menit lalu coba lagi.",
        )
    user = next(
        (u for u in state["auth"]["users"] if u["username"] == body.username), None
    )
    if user is None or not hmac.compare_digest(
        _pbkdf2_hex(body.password, user["salt"], state["auth"]["iterations"]),
        user["password_hash"],
    ):
        _record_failure(key)
        raise HTTPException(status_code=401, detail="Username atau password salah.")

    ttl = int(state["auth"].get("session_ttl_seconds", DEFAULT_SESSION_TTL))
    token = sign_token(
        {
            "username": body.username,
            "jti": secrets.token_hex(16),
            "iat": int(time.time()),
            "exp": int(time.time()) + ttl,
        }
    )
    return {"data": {"token": token, "username": body.username, "expires_in": ttl}}


@app.get("/api/auth/me")
def auth_me(user: dict = Depends(require_auth)):
    return {"data": {"username": user["username"]}}


@app.post("/api/auth/logout", dependencies=[Depends(require_auth)])
def auth_logout(authorization: str | None = Header(default=None)):
    payload = verify_token((authorization or "").removeprefix("Bearer "))
    if payload and payload.get("jti"):
        _revoked_jtis.add(payload["jti"])
    return {"data": {"status": "logged_out"}}


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
