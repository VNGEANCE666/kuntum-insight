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
@app.get("/api/overview/sentiment-distribution", dependencies=[Depends(require_auth)])
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
@app.get("/api/overview/rating-distribution", dependencies=[Depends(require_auth)])
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
# 9. /api/recommendations
# ---------------------------------------------------------------------------
@app.get("/api/recommendations", dependencies=[Depends(require_auth)])
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
