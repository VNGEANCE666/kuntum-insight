"""Verifikasi end-to-end: seluruh endpoint API + static frontend (TestClient)."""
import os
import sys
from pathlib import Path

# CWD harus berada di ROOT project (tempat data/ dan models/ berada) karena
# DB_PATH = "data/kuntum_insight.db" & MODELS_DIR = "models" relatif ke sana.
# main.py berada di backend_seed/, jadi naik satu level dari file ini.
ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "backend_seed"))

from fastapi.testclient import TestClient
import main

results = []
def check(name, cond, extra=""):
    results.append((name, bool(cond), extra))

# Gunakan context manager agar lifespan (load_all_data) turut dijalankan.
with TestClient(main.app) as client:
    # ---- API endpoints ----
    r = client.get("/api/overview/kpi")
    check("overview/kpi", r.status_code == 200 and r.json()["data"]["total_reviews"] == 2832)

    r = client.get("/api/overview/sentiment-distribution")
    check("sentiment-distribution", r.status_code == 200 and len(r.json()["data"]) == 3)

    r = client.get("/api/overview/rating-distribution")
    check("rating-distribution", r.status_code == 200 and len(r.json()["data"]) == 5)

    r = client.get("/api/overview/sentiment-trend")
    trend_data = r.json().get("data", [])
    has_year = any(d["granularity"] == "year" and d["is_approximate"] for d in trend_data)
    has_month = any(d["granularity"] == "month" and not d["is_approximate"] for d in trend_data)
    has_avg = all("positif_avg_month" in d and "total_avg_month" in d for d in trend_data)
    check("sentiment-trend (mixed granularity)", r.status_code == 200 and has_year and has_month)
    check("sentiment-trend (has *_avg_month)", has_avg)
    check("sentiment-trend (total across points=2832)", sum(d["total"] for d in trend_data) == 2832)

    r = client.get("/api/reviews", params={"page": 1, "page_size": 5})
    check("reviews (page1, has_text_only default true)",
          r.status_code == 200 and len(r.json()["data"]) == 5 and r.json()["meta"]["total"] == 2776)

    r = client.get("/api/reviews", params={"page": 1, "page_size": 5, "has_text_only": False})
    check("reviews (page1, semua termasuk tanpa teks)", r.status_code == 200 and r.json()["meta"]["total"] == 2832)

    r = client.get("/api/reviews", params={**{"sentiment[]": ["negatif"]}, "page_size": 5})
    check("reviews (filter sentiment negatif)", r.status_code == 200 and r.json()["meta"]["total"] >= 100)

    r = client.get("/api/reviews", params={"search": "ramai", "page_size": 5})
    check("reviews (search)", r.status_code == 200)

    r = client.get("/api/reviews/00000000-0000-0000-0000-000000000000")
    check("reviews 404", r.status_code == 404)

    detail_id = client.get("/api/reviews", params={"page_size": 1}).json()["data"][0]["review_id"]
    r = client.get(f"/api/reviews/{detail_id}")
    check("reviews detail", r.status_code == 200 and "top_keywords" in r.json()["data"])

    r = client.get("/api/topics", params={"sentiment_label": "negatif", "top_n": 5})
    check("topics", r.status_code == 200 and len(r.json()["data"]) == 5)

    r = client.get("/api/topics", params={"sentiment_label": "invalid"})
    check("topics invalid 400", r.status_code == 400)

    r = client.get("/api/topics/harga/reviews", params={"sentiment_label": "negatif"})
    check("topics/{theme}/reviews", r.status_code == 200)

    r = client.get("/api/recommendations")
    recs = r.json().get("data", [])
    check("recommendations", r.status_code == 200 and len(recs) > 0)

    r = client.get("/api/pipeline/status")
    check("pipeline/status", r.status_code == 200 and r.json()["data"]["model_version"] == "v1")

    # ---- Static frontend ----
    r = client.get("/")
    check("static / (index.html)", r.status_code == 200 and "<title>" in r.text)

    r = client.get("/css/variables.css")
    check("static css", r.status_code == 200)

    r = client.get("/js/app.js")
    check("static js (module)", r.status_code == 200)


    r = client.get("/api/overview/nonexistent")
    check("unknown api => 404 (not swallowed by static)", r.status_code == 404)

    # Pastikan setelah mount static, API masih jalan (urutan benar)
    r = client.get("/api/overview/kpi")
    check("api still works after static mount", r.status_code == 200)

for name, ok, extra in results:
    print(("PASS" if ok else "FAIL"), "-", name, extra)

fails = [n for n, ok, _ in results if not ok]
print("\n=====")
print(f"TOTAL: {len(results)}  PASS: {len(results)-len(fails)}  FAIL: {len(fails)}")
if fails:
    print("FAILED:", fails)
    sys.exit(1)
print("SEMUA LULUS")
