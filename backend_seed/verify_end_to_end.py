"""Verifikasi end-to-end (auth-aware): login dulu, semua panggilan API pakai Bearer.

Menjalankan TestClient main.app (lifespan load_all_data). Alur:
  1. POST /api/auth/login -> token.
  2. Semua endpoint /api/* dipanggil dengan header Authorization: Bearer <token>.
  3. Cek keamanan: tanpa token -> 401, password salah -> 401, logout -> token invalid.

Kredensial login diambil dari env var VERIFY_USER / VERIFY_PASS (bila di-set).
Tanpa env var, memakai akun default admin/admin (portal — hanya cocok bila
backend_seed/auth.json masih berisi akun default tsb).
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from fastapi.testclient import TestClient
import main

TEST_USER = os.environ.get("VERIFY_USER", "admin")
TEST_PASS = os.environ.get("VERIFY_PASS", "admin")

results = []

def check(name, cond, extra=""):
    results.append((name, bool(cond), extra))

with TestClient(main.app) as client:
    # ---- 1. Blok tanpa token: harus 401 ----
    r = client.get("/api/overview/kpi")
    check("tanpa token -> 401 kpi", r.status_code == 401, f"got {r.status_code}")

    # ---- 2. Login salah -> 401 ----
    r = client.post("/api/auth/login", json={"username": TEST_USER, "password": "salah123"})
    check("login password salah -> 401", r.status_code == 401, f"got {r.status_code}")

    # ---- 3. Login benar -> token ----
    r = client.post("/api/auth/login", json={"username": TEST_USER, "password": TEST_PASS})
    login_ok = r.status_code == 200 and "token" in r.json().get("data", {})
    check(f"login {TEST_USER} -> 200 + token", login_ok, f"got {r.status_code}")
    token = r.json()["data"]["token"] if login_ok else ""
    headers = {"Authorization": f"Bearer {token}"}

    # ---- 4. /api/auth/me dengan token ----
    r = client.get("/api/auth/me", headers=headers)
    check("/api/auth/me (token valid)",
          r.status_code == 200 and r.json().get("data", {}).get("username") == TEST_USER)

    # ---- 5. Endpoint data dengan token ----
    r = client.get("/api/overview/kpi", headers=headers)
    check("overview/kpi (with token)",
          r.status_code == 200 and r.json()["data"]["total_reviews"] == 2832)

    # ---- 5a. Filter periode (revisi dosen poin 1): date_from menyusutkan KPI ----
    r = client.get("/api/overview/kpi", params={"date_from": "2022-01-01"}, headers=headers)
    filtered_total = r.json()["data"]["total_reviews"] if r.status_code == 200 else 0
    check("overview/kpi date_from=2022 (5 tahun)",
          r.status_code == 200 and 0 < filtered_total < 2832,
          f"total={filtered_total}")

    r = client.get("/api/overview/sentiment-distribution", headers=headers)
    check("sentiment-distribution", r.status_code == 200 and len(r.json()["data"]) == 3)

    r = client.get("/api/overview/rating-distribution", headers=headers)
    check("rating-distribution", r.status_code == 200 and len(r.json()["data"]) == 5)

    r = client.get("/api/topics", params={"sentiment_label": "negatif", "top_n": 5}, headers=headers)
    check("topics (negatif, top_n=5)", r.status_code == 200 and len(r.json()["data"]) == 5)

    # ---- 5b. Konsistensi tema (revisi dosen poin 3b): keyword "tiket" -> theme tiket_masuk ----
    r = client.get("/api/topics", params={"sentiment_label": "negatif", "top_n": 25}, headers=headers)
    top_neg = r.json()["data"] if r.status_code == 200 else []
    tiket_row = next((x for x in top_neg if x.get("keyword") == "tiket"), None)
    check("topics negatif: tiket -> theme tiket_masuk",
          tiket_row is not None and tiket_row.get("theme") == "tiket_masuk",
          str(tiket_row.get("theme") if tiket_row else None))

    r = client.get("/api/topics", params={"sentiment_label": "invalid"}, headers=headers)
    check("topics invalid -> 400", r.status_code == 400)

    r = client.get("/api/reviews", params={"page": 1, "page_size": 5}, headers=headers)
    check("reviews page1 has_text_only", r.status_code == 200 and len(r.json()["data"]) == 5)

    r = client.get("/api/reviews", params={"page": 1, "page_size": 5, "has_text_only": False}, headers=headers)
    check("reviews semua (termasuk tanpa teks)", r.status_code == 200 and r.json()["meta"]["total"] == 2832)

    r = client.get("/api/recommendations", headers=headers)
    check("recommendations", r.status_code == 200 and len(r.json()["data"]) > 0)

    r = client.get("/api/pipeline/status", headers=headers)
    check("pipeline/status", r.status_code == 200 and r.json()["data"]["model_version"] == "v1")

    # ---- 6. Static tetap jalan ----
    r = client.get("/")
    check("halaman depan (/)", r.status_code == 200 and "<title>" in r.text)
    r = client.get("/css/pages/login.css")
    check("static login.css", r.status_code == 200)

    # ---- 7. Logout -> token dicabut ----
    r = client.post("/api/auth/logout", headers=headers)
    check("logout -> 200", r.status_code == 200, f"got {r.status_code}")
    r = client.get("/api/auth/me", headers=headers)
    check("me setelah logout -> 401", r.status_code == 401, f"got {r.status_code}")

for name, ok, extra in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {extra}".rstrip())

fails = [n for n, ok, _ in results if not ok]
print(f"\nTOTAL: {len(results)}  PASS: {len(results) - len(fails)}  FAIL: {len(fails)}")
if fails:
    print("GAGAL:", ", ".join(fails))
    sys.exit(1)
print("SEMUA LULUS")
