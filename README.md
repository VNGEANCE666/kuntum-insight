# Kuntum Insight — Dashboard Analisis Sentimen Ulasan Google Maps

Studi kasus: **Kuntum Farmfield, Bogor** — Praktik Lapang (PKL) Ilmu Komputer, FMIPA, Universitas Pakuan, oleh Rifqi Fairuzzabady (NPM 065123034).

Arsitektur **client-server**: backend FastAPI membaca data ulasan + artefak model ML (sudah dilatih di notebook Colab) dari database SQLite, lalu frontend web SPA custom (HTML/CSS/JS murni + Chart.js) mengonsumsi endpoint-nya.

## Struktur

```
├── PRD.md          # Spesifikasi produk, kontrak endpoint API (§10), skema DB (§9.3)
├── DESIGN.md       # Spesifikasi UI/UX per halaman, dipetakan ke endpoint API
├── HANDOFF.md      # Status artefak nyata, gotcha teknis, riwayat debugging
├── data/
│   └── kuntum_insight.db   # SQLite: reviews_clean, sentiment_results, topic_keywords (2.832 ulasan)
├── models/                  # Artefak model v1 (Logistic Regression, macro F1 0.523)
│   ├── tfidf_vectorizer_v1.pkl
│   ├── sentiment_model_v1.pkl
│   ├── label_map.json
│   └── metadata_v1.json
├── backend_seed/            # FastAPI lengkap (10 endpoint + static frontend) + verifikasi E2E
└── frontend/                # SPA 5 halaman (Overview, Review Explorer, Topic Insights,
                             # Rekomendasi, Status Pipeline)
```

> **Baca dokumen dalam urutan ini:** `PRD.md` → `DESIGN.md` → `HANDOFF.md`.

## Menjalankan

1. Pasang dependensi:

   ```bash
   pip install -r backend_seed/requirements.txt
   ```

2. Jalankan backend dari **root project** (path `data/` dan `models/` relatif terhadap CWD; `main.py` sekaligus melayani frontend via `app.mount("/", StaticFiles("frontend"))`):

   PowerShell:
   ```powershell
   $env:PYTHONPATH="backend_seed"
   uvicorn backend_seed.main:app --reload
   ```
   Bash/cmd:
   ```bash
   PYTHONPATH=backend_seed uvicorn backend_seed.main:app --reload
   ```

3. Buka:
   - Frontend: `http://127.0.0.1:8000/`
   - Dokumentasi API: `http://127.0.0.1:8000/docs`

## Verifikasi end-to-end

Skrip smoke test seluruh 10 endpoint + static frontend terhadap data asli:

```bash
python backend_seed/verify_end_to_end.py
```

## Catatan

- **Gotcha teknis kritis** (loading `.pkl`, CORS, static mount, NaN → None) ada di HANDOFF.md §3 & §5 — baca sebelum menyentuh `main.py`.
- **Keterbatasan data yang diketahui:** ±94% tanggal ulasan lama terkompresi akibat parsing format relatif Google Maps (PRD §5.1 & HANDOFF §7) — sudah di-handle di endpoint `sentiment-trend`.
- `data/` dan `models/` sengaja di-commit ke repo agar paket ini **self-contained** (ukuran total masih kecil, tanpa Git LFS).