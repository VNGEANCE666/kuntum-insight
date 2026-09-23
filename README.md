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

## Deploy ke internet

Satu proses FastAPI melayani sekaligus API + frontend (satu origin), jadi tidak
ada konfigurasi CORS tambahan di produksi mana pun.

### Opsi 1 — Cloudflare Tunnel dari laptop (paling cepat, tanpa kartu)

URL publik sementara (`*.trycloudflare.com`), gratis, tanpa akun/kartu. Laptop
harus menyala dan URL berubah setiap restart.

```powershell
.\scripts\start_public.ps1
```

Script otomatis: jalankan `uvicorn` (port 8000) → buat tunnel → tampilkan URL
publik dan file `cloudflared` diunduh sendiri ke `%LOCALAPPDATA%\cloudflared`
bila belum ada. Referensi perintah manual (bila ingin dijalankan sendiri):

```powershell
$env:PYTHONPATH="backend_seed"
uvicorn backend_seed.main:app --host 127.0.0.1 --port 8000
# di terminal terpisah:
cloudflared tunnel --url http://127.0.0.1:8000
```

Untuk URL yang **stabil** (tidak berubah), butuh akun Cloudflare + domain pribadi
(named tunnel), atau akun ngrok free (satu static domain `*.ngrok-free.app`,
kapasitas 1 GB/bulan).

### Opsi 2 — PythonAnywhere free (always-on, tanpa kartu)

URL stabil di `https://<username>.pythonanywhere.com` — **sudah live di
`https://vngnc.pythonanywhere.com`** (seluruh endpoint + frontend terverifikasi
200). FastAPI via ASGI (beta). Pembatasan free tier: disk 512 MiB, CPU 100
detik/hari, 1 web app (unused web app berakhir setelah 1 bulan).

> ⚠️ Subdomain **terikat username** (`vngnc.pythonanywhere.com`): username tidak
> bisa diganti, dan domain lain di `*.pythonanywhere.com` ditolak oleh API
> (400). Custom domain butuh akun berbayar. Rincian + cara deploy via API
> (otomasi) di HANDOFF.md §12.

1. Daftar akun gratis di [pythonanywhere.com](https://www.pythonanywhere.com) (tanpa kartu).
2. **Account → API token** → buat token (dibaca otomatis dari Bash console).
3. Buka **Bash console**, lalu:
   ```bash
   pip install --user pythonanywhere
   git clone https://github.com/VNGEANCE666/kuntum-insight.git
   mkvirtualenv --python=python3.12 kuntum
   workon kuntum
   pip install --no-cache-dir -r backend_seed/requirements.txt
   ```
   > `scikit-learn==1.6.1` wajib Python ≤3.12 — jangan buat venv dengan Python
   > 3.13+. Calonnya besar tapi muat di 512 MiB; hindari `pip cache`.
4. Buat situs ASGI (ganti `USERNAME`):
   ```bash
   pa website create --domain USERNAME.pythonanywhere.com \
     --command '/home/USERNAME/.virtualenvs/kuntum/bin/uvicorn --app-dir /home/USERNAME/kuntum-insight/backend_seed --uds ${DOMAIN_SOCKET} main:app'
   ```
5. Cek log `/var/log/USERNAME.pythonanywhere.com.server.log` — tanda sukses:
   `[startup] 2832 ulasan dimuat, model versi v1 siap.`
6. Setelah perubahan kode: `pa website reload --domain USERNAME.pythonanywhere.com`.

> `--app-dir backend_seed` membuat `from inference_utils import ...` (patch
> `__main__` untuk `joblib.load()`, HANDOFF §3.1) bekerja tanpa PYTHONPATH, dan
> `BASE_DIR` di `main.py` membuat `data/` & `models/` ditemukan terlepas dari CWD.

### Opsi 3 — Render (perlu kartu kredit; tidak wajib dibaca)

`render.yaml` di root tetap disimpan sebagai **referensi konfigurasi**. Saat ini
Render mewajibkan kartu kredit bahkan untuk Web Service free (dan rute Blueprint
juga), jadi bukan lagi opsi "tanpa kartu". Jika suatu saat kartu tersedia,
pakai nilai dari `render.yaml`: Build `pip install -r backend_seed/requirements.txt`,
Start `uvicorn backend_seed.main:app --host 0.0.0.0 --port $PORT`, env
`PYTHONPATH=backend_seed` dan `PYTHON_VERSION=3.12.3`.

**Perilaku free tier Render:** service tidur ±15 menit tanpa kunjungan; cold start
30–60 detik di kunjungan pertama.

## Verifikasi end-to-end

Skrip smoke test seluruh 10 endpoint + static frontend terhadap data asli:

```bash
python backend_seed/verify_end_to_end.py
```

## Catatan

- **Gotcha teknis kritis** (loading `.pkl`, CORS, static mount, NaN → None) ada di HANDOFF.md §3 & §5 — baca sebelum menyentuh `main.py`.
- **Keterbatasan data yang diketahui:** ±94% tanggal ulasan lama terkompresi akibat parsing format relatif Google Maps (PRD §5.1 & HANDOFF §7) — sudah di-handle di endpoint `sentiment-trend`.
- `data/` dan `models/` sengaja di-commit ke repo agar paket ini **self-contained** (ukuran total masih kecil, tanpa Git LFS).