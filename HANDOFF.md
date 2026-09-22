# HANDOFF — Kuntum Insight (Notebook ML → Backend/Frontend Web)

Dokumen ini merangkum semua yang perlu diketahui **opencode** (atau AI/developer manapun) untuk membangun backend FastAPI + frontend web custom, berdasarkan output notebook ML yang sudah selesai dijalankan di Colab.

**Baca dokumen dalam urutan ini:**
1. `PRD.md` — spesifikasi produk lengkap, termasuk kontrak endpoint API (§10) dan skema database (§9.3)
2. `DESIGN.md` — spesifikasi UI/UX per halaman, dipetakan ke endpoint API
3. Dokumen ini (`HANDOFF.md`) — status artefak nyata, gotcha teknis, dan langkah konkret

---

## 1. Isi Paket Ini

```
├── PRD.md                          # Kontrak spesifikasi (baca dulu)
├── DESIGN.md                       # Spesifikasi UI per halaman
├── HANDOFF.md                      # Dokumen ini
├── data/
│   └── kuntum_insight.db           # SQLite: reviews_clean, sentiment_results, topic_keywords
├── models/
│   ├── tfidf_vectorizer_v1.pkl
│   ├── sentiment_model_v1.pkl
│   ├── label_map.json
│   └── metadata_v1.json
├── frontend/                       # SPA lengkap (5 halaman) — diserve main.py, lihat §4, §5.5, §11
│   ├── index.html
│   ├── favicon.svg, logo.jpg
│   ├── css/                        # variables, base, layout, components + css/pages/*
│   └── js/                         # app.js, router.js, api.js, state.js + components/* + pages/*
└── backend_seed/
    ├── inference_utils.py          # WAJIB — lihat §3 di bawah
    ├── main.py                     # FastAPI LENGKAP: 10 endpoint kontrak + static frontend, sudah DIUJI
    ├── requirements.txt            # Versi library dipin agar cocok dengan artefak
    └── verify_end_to_end.py        # Verifikasi end-to-end 10 endpoint + static frontend (TestClient)
```

## 2. Status Data Aktual (sudah diverifikasi, bukan dummy)

| Tabel | Jumlah Baris |
|---|---|
| `reviews_clean` | 2.832 |
| `sentiment_results` | 2.832 |
| `topic_keywords` | 75 (25 per kelas sentimen) |

Model: **Logistic Regression**, `model_version = v1`, **macro F1 = 0.523**, akurasi = 87.8%.

Distribusi `sentiment_results`:
- Positif: 2.480 (2.144 dari model teks, 336 dari `rating_fallback`)
- Netral: 220 (188 dari model, 32 dari fallback)
- Negatif: 132 (116 dari model, 16 dari fallback)

> **Catatan untuk developer:** macro F1 0.523 relatif rendah untuk kelas negatif/netral — ini konsekuensi dari data asli yang ±90% berating tinggi (lihat PRD §7.2), bukan bug. Jangan heran kalau prediksi sentimen untuk ulasan ambigu kadang meleset; ini sudah diketahui dan didokumentasikan tim data science-nya.

## 3. ⚠️ Gotcha Teknis Kritis — WAJIB Dibaca Sebelum Coding Backend

### 3.1 Loading model `.pkl` PASTI gagal tanpa langkah khusus

`tfidf_vectorizer_v1.pkl` menyimpan referensi ke dua fungsi Python (`identity_tokenizer`, `identity_preprocessor`) yang didefinisikan di notebook Colab saat training (dianggap Python sebagai modul `__main__`). Kalau langsung di-`joblib.load()` tanpa persiapan, akan muncul:

```
AttributeError: Can't get attribute 'identity_preprocessor' on <module '__main__'>
```

**Solusi yang sudah diuji berhasil** (lihat `backend_seed/main.py` baris awal):

```python
import __main__
from inference_utils import identity_tokenizer, identity_preprocessor
__main__.identity_tokenizer = identity_tokenizer
__main__.identity_preprocessor = identity_preprocessor

import joblib
vectorizer = joblib.load("models/tfidf_vectorizer_v1.pkl")
model = joblib.load("models/sentiment_model_v1.pkl")
```

Sekadar meng-`import` fungsi tersebut **tidak cukup** — harus ditempelkan eksplisit ke `__main__` sebelum `joblib.load()` dipanggil. Ini sudah diverifikasi jalan di `backend_seed/main.py`.

### 3.2 Pin versi scikit-learn

Model dilatih dengan **scikit-learn 1.6.1** di Colab. Gunakan versi yang sama persis di `requirements.txt` backend (`backend_seed/requirements.txt` sudah menyertakan ini) untuk menghindari `InconsistentVersionWarning` dan potensi perbedaan hasil prediksi akibat perbedaan versi internal scikit-learn.

### 3.3 `review_tokens` disimpan sebagai string di SQLite

Kolom `review_tokens` di tabel `reviews_clean` tersimpan sebagai string JSON (bukan list Python asli). Jika backend perlu memakainya (mis. untuk re-ranking kata kunci on-the-fly), parse dulu dengan `json.loads()` — jangan `ast.literal_eval()` karena disimpan via `json.dumps()` di notebook.

### 3.4 Backend TIDAK boleh training ulang

Sesuai PRD §9.2: `model` dan `vectorizer` dimuat sekali saat startup **hanya untuk metadata/inspeksi** (mis. halaman Pipeline Status). MVP ini **tidak** memprediksi ulasan baru secara real-time per-request — semua label sentimen sudah tersimpan final di `sentiment_results`. Kalau backend butuh memprediksi ulasan baru nanti (fitur pasca-MVP), itu perlu didiskusikan ulang di luar scope handoff ini.

## 4. Status Implementasi Backend Seed

`backend_seed/main.py` kini mengimplementasikan **SELURUH 10 endpoint** di kontrak PRD §10, plus 1 endpoint tambahan opsional — **bukan pseudocode, sudah diuji end-to-end** dengan `TestClient` terhadap data asli (2.832 ulasan):

| Endpoint | Status |
|---|---|
| `GET /api/overview/kpi` | ✅ Diuji |
| `GET /api/overview/sentiment-distribution` | ✅ Diuji |
| `GET /api/overview/rating-distribution` | ✅ Diuji |
| `GET /api/overview/sentiment-trend` | ✅ Diuji |
| `GET /api/reviews` (semua filter: search, sentiment[], rating range, date range, has_text_only, sort_by, paginasi) | ✅ Diuji |
| `GET /api/reviews/{review_id}` (termasuk kasus 404) | ✅ Diuji |
| `GET /api/topics` | ✅ Diuji |
| `GET /api/topics/{theme}/reviews` | ✅ Diuji |
| `GET /api/recommendations` | ✅ Diuji |
| `GET /api/pipeline/status` | ✅ Diuji |
| `POST /api/admin/reload-cache` (opsional, PRD §9.4) | ✅ Diuji |

**Status frontend:** frontend SPA (5 halaman: Overview, Review Explorer, Topic Insights, Rekomendasi, Status Pipeline) sudah **selesai dibangun dan diserve oleh `main.py` itu sendiri** lewat `app.mount("/", StaticFiles(directory="frontend", html=True))`. Frontend memakai `fetch()` **path relatif** (`/api/...`) karena berada di origin yang sama dengan backend. Mount static WAJIB didaftarkan di **paling akhir** `main.py` (setelah semua route API) — sudah diterapkan & diverifikasi (lihat §5.5). Detail fitur yang ditambahkan setelah verifikasi awal di §11.

**Yang masih terbuka (opsional):** penyempurnaan detail minor (mis. validasi input lebih ketat, error handling tambahan) — bukan menulis ulang dari nol. Struktur response, nama field, dan logika filter sudah final dan cocok dengan DESIGN.md.

## 5. Gotcha yang SUDAH Diperbaiki di `main.py` Ini (jangan dikembalikan ke versi naif)

### 5.1 ✅ NaN → None (sudah diperbaiki & diverifikasi)
Fungsi `sanitize()` di `main.py` membersihkan semua `NaN`/`NaT` pandas menjadi `None` secara rekursif sebelum masuk response. **Sudah diverifikasi**: response mentah (raw text, bukan hasil parse Python) dites tidak mengandung literal `NaN`, dan `json.loads()` berhasil parse tanpa error. Kalau opencode menambah field baru dari DataFrame, **selalu bungkus lewat `sanitize()` atau `df_to_records()`** — jangan `return df.to_dict(...)` mentah-mentah.

### 5.2 ✅ Loading pickle model (sudah diperbaiki & diverifikasi)
Lihat §3.1 di atas — solusi `__main__` patching sudah diterapkan di baris awal `main.py` dan bekerja.

### 5.3 ✅ CORS environment-aware
`main.py` membaca origin frontend dari env var `FRONTEND_ORIGIN` (default ke port dev umum: 3000/5173). **Set env var ini ke domain asli saat deploy production** — jangan biarkan default localhost dipakai di server publik.

### 5.4 ✅ Reload cache tanpa restart penuh
`POST /api/admin/reload-cache` tersedia untuk skenario PRD §9.4 (update data inkremental) tanpa perlu restart proses FastAPI — cukup panggil endpoint ini setelah skrip batch menulis data baru ke SQLite.

### 5.5 ✅ Static frontend di-mount ke "/" — WAJIB didaftarkan paling akhir
`main.py` kini melayani seluruh `frontend/` lewat `app.mount("/", StaticFiles(directory=..., html=True))`. Aturan wajib: mount "/" harus berada di **baris PALING AKHIR** file, **setelah SEMUA** `@app.get()`/`@app.post()` API — kalau diletakkan lebih awal, ia menjadi catch-all yang menutupi request ke `/api/*` (Starlette mencocokkan route berdasarkan urutan pendaftaran). Sudah diverifikasi dua arah di `verify_end_to_end.py`: (1) `/api/overview/nonexistent` tetap mengembalikan 404, tidak tertelan static; (2) seluruh `/api/*` masih bekerja setelah mount static dipasang. Frontend memakai path relatif (`/api/overview/kpi`) karena satu origin.

## 6. Langkah Konkret untuk Anda Sebelum Menjalankan opencode

1. Taruh seluruh isi paket ini (folder `data/`, `models/`, `backend_seed/`) di root project backend Anda.
2. Beri instruksi ke opencode: *"Backend di backend_seed/main.py sudah lengkap 10 endpoint dan sudah teruji — jangan ditulis ulang dari nol. Baca PRD.md §10 dan DESIGN.md, lalu bangun frontend SPA sesuai DESIGN.md §4–§5 yang meng-konsumsi endpoint-endpoint tersebut. Kalau perlu menyempurnakan backend, pertahankan pola `sanitize()` untuk NaN dan cara loading model di baris awal main.py — itu sudah teruji."*
3. Jalankan `uvicorn main:app --reload` lalu buka `http://127.0.0.1:8000/docs` untuk mengecek semua endpoint bekerja di lingkungan Anda sebelum menyerahkan ke opencode — memastikan tidak ada masalah environment (path file, versi Python, dst.) di luar yang sudah saya uji.
4. Untuk deployment nanti: backend butuh folder `data/` dan `models/` tersedia di server tempat FastAPI berjalan — bukan hanya di repo Git jika `.pkl`/`.db` di-gitignore. Pertimbangkan Git LFS atau storage terpisah jika ukuran file jadi masalah (`kuntum_insight.db` ±2MB, `.pkl` gabungan ±150KB — masih kecil, aman untuk repo biasa).
5. Sebelum opencode mulai membangun frontend, siapkan juga **referensi visual asli** dari prototipe Stitch AI (screenshot/export tiap 5 layar) — DESIGN.md hanya spesifikasi tekstual, tidak cukup untuk hasil "pixel-perfect" tanpa referensi visual nyata (lihat catatan di percakapan sebelumnya).

## 7. ⚠️ Isu Data Ditemukan Setelah Dashboard Berjalan: Tanggal Ulasan Lama Terkompresi

**Gejala yang terlihat di dashboard:** grafik tren sentimen bulanan menunjukkan volume ulasan seolah "menghilang" di 2025-2026, padahal jumlah ulasan sebenarnya di tahun itu cukup wajar (223 di 2025, 115 di 2026 parsial).

**Akar masalah (bukan bug backend/frontend):** Google Maps hanya menampilkan tanggal ulasan lama dalam teks relatif ("N tahun lalu"), bukan tanggal absolut. Scraper (tahap data collection yang sudah selesai jauh sebelum ini) mengonversi teks tsb dengan **tanggal scraping dikurangi N tahun** — bukan tanggal asli ulasan diposting. Akibatnya: **94% dari 2.832 baris (2.661 baris)** semuanya jatuh tepat di tanggal 18-21 Agustus (mengikuti tanggal scraping dijalankan), memampatkan data satu tahun penuh jadi satu titik. Sudah diverifikasi lewat query langsung ke `kuntum_insight.db` — lihat PRD.md §5.1 untuk detail & bukti angka.

**Ini TIDAK BISA diperbaiki dengan scraping ulang** — keterbatasannya ada di sumber data (Google Maps) sendiri, bukan di cara scraper bekerja.

**Perbaikan yang sudah diterapkan (workaround di layer visualisasi):** endpoint `/api/overview/sentiment-trend` di `main.py` sudah direvisi total:
1. Mendeteksi baris kena artefak via pola tanggal (`bulan=8 AND tanggal∈{18,19,20,21}`) — **bukan** sekadar cutoff 365 hari (sempat dicoba, ternyata masih bocor karena artefak "1 tahun lalu" jatuh tepat di tepi window 12 bulan; sudah diperbaiki dengan deteksi pola tanggal yang lebih presisi).
2. Baris kena artefak diagregasi per **tahun** (`granularity: "year"`, `is_approximate: true`); baris dengan tanggal presisi asli (~12 bulan terakhir, 171 baris) diagregasi per **bulan** (`granularity: "month"`, `is_approximate: false`).
3. Field tambahan `*_avg_month` (total tahunan ÷ 12) disediakan agar skala titik tahunan & bulanan **sebanding** saat diplot di satu grafik — tanpa ini, titik tahunan (mis. 739) akan membuat titik bulanan (mis. 17) terlihat seperti anjlok ke nol padahal cuma beda satuan waktu.
4. **Sudah diuji end-to-end**: total across semua titik = 2.832 (cocok, tidak ada data hilang), tidak ada lagi lonjakan/jatuh aneh di sekitar 2025 (rentang avg/bulan konsisten 5-30 dari 2019-2026).

**Yang WAJIB dilakukan opencode di sisi frontend** (lihat DESIGN.md §5.A untuk instruksi lengkap):
- Plot field `*_avg_month`, **bukan** `total`/`positif`/dst. mentah.
- Beri pembeda visual (mis. garis putus-putus) untuk titik dengan `is_approximate: true`.
- Response `meta.note` dari endpoint ini berisi penjelasan yang bisa langsung dipakai sebagai tooltip/caption di dashboard.

**Untuk laporan PKL:** dokumentasikan sebagai keterbatasan data yang diketahui (known limitation), bukan kegagalan sistem — PRD.md §5.1 sudah punya narasi siap pakai untuk bagian metodologi/keterbatasan penelitian.

## 8. ✅ Sudah Diperbaiki: Partikel "nya" Mendominasi Kata Kunci

**Gejala:** token "nya" (partikel Bahasa Indonesia) muncul sebagai kata kunci teratas di ketiga kelas sentimen — tidak membawa makna topik apa pun.

**Perbaikan yang sudah diterapkan langsung ke `data/kuntum_insight.db`** (tanpa perlu retraining model — `sentiment_model_v1.pkl`/`tfidf_vectorizer_v1.pkl` tidak berubah sama sekali): tabel `topic_keywords` diregenerasi dengan daftar stopword tambahan untuk partikel/kata generik (`nya`, `kah`, `lah`, `sih`, `aja`, `apa`, dll. — daftar lengkap di PRD.md §8.5), dan kolom `top_keywords` per-ulasan di `sentiment_results` ikut disegarkan agar konsisten.

**✅ Dicek tidak ada tabrakan dengan perbaikan #7 (tanggal):** kedua perbaikan beroperasi di kolom/tabel yang sepenuhnya independen — perbaikan tanggal murni logika di `main.py` yang membaca `review_date` (tidak pernah berubah), sementara perbaikan kata kunci hanya menyentuh `topic_keywords` dan `sentiment_results.top_keywords`. Sudah diuji ulang **seluruh 10 endpoint** terhadap database yang sudah memuat kedua perbaikan sekaligus — total ulasan tetap 2.832, endpoint tren tanggal tetap benar, tema kustom (`hewan_satwa`, `makanan_kuliner`, `akses_lalulintas`, dll.) tetap terjaga, dan semua response tetap JSON valid.

**⚠️ Yang PERLU Anda tindak lanjuti:** `THEME_DICTIONARY` yang dipakai untuk regenerasi ini adalah **hasil rekonstruksi** dari tema yang sudah tersimpan di database sebelumnya (karena perbaikan dilakukan tanpa akses ke notebook Colab asli Anda) — kemungkinan **tidak selengkap** dictionary asli yang Anda definisikan sendiri di Colab. Kalau Anda masih menyimpan sel notebook dengan `THEME_DICTIONARY` versi lengkap, sebaiknya jalankan ulang regenerasi topik memakai dictionary asli tsb agar tidak ada tema yang hilang secara diam-diam. Detail lengkap di PRD.md §8.5.

## 9. Riwayat Debugging Frontend (Fase Build oleh opencode) — Status: Semua Sudah Diverifikasi ✅

Bagian ini mendokumentasikan bug yang ditemukan **setelah** frontend dibangun opencode dan dashboard dijalankan sungguhan di browser, plus status verifikasinya. Berguna sebagai referensi kalau bug serupa muncul lagi di masa depan (mis. setelah refactor), dan sebagai bahan dokumentasi metodologi untuk laporan akademik PKL.

### 9.1 Bug Render Awal — Konten Semua Halaman Kosong Total

**Gejala:** Sidebar & routing (hash-based) berfungsi, URL berubah sesuai halaman, tapi area konten kosong di SEMUA halaman.

**Root cause:** Fungsi render per-halaman tidak terpanggil oleh router setelah navigasi — bug di `router.js`, bukan di logic fetch/API. Terverifikasi via tab Network browser: nol request Fetch/XHR ke endpoint manapun, padahal kode `apiGet()` sudah ada di tiap file halaman.

**Status:** ✅ Diperbaiki oleh opencode, diverifikasi via screenshot — semua chart/tabel/KPI tampil dengan data asli setelah fix.

### 9.2 Bug Chart Tren Sentimen — Garis Tidak Muncul & Skala Terjepit

Dua masalah ditemukan berurutan setelah data mulai mengalir:
- **Celah kosong di titik transisi** antara segmen data estimasi (`is_approximate=true`, dulu direncanakan render sbg 2 dataset terpisah) dan segmen presisi asli — **diselesaikan dengan pendekatan lebih baik dari rencana awal**: opencode memakai fitur native `segment.borderDash` Chart.js (styling kondisional per-segmen dalam SATU dataset), bukan 2 dataset + titik penghubung manual seperti yang sempat dipakai di versi Streamlit. Ini menghapus total risiko celah kosong secara struktural.
- **Sumbu X sempat berisiko tidak kategorikal** karena format data `{x, y}` object akan memicu Chart.js auto-detect ke skala time/linear (menjejalkan 12 bulan data presisi jadi garis kecil di ujung kanan, persis bug yang pernah terjadi di versi Streamlit). **Dicegah sejak tahap plan**: data disusun sbg `labels` array terpisah dari `data` array bernilai skalar + `scales.x.type: 'category'` eksplisit.

**Status:** ✅ Diverifikasi — chart tren menampilkan proporsi visual yang benar (segmen tahunan & bulanan sama-sama terbaca, sumbu berjarak rata, tidak ada celah).

### 9.3 Tiga Bug di Review Explorer (Ditemukan Bersamaan, Diberi Kode M1/M2/M3)

**M1 — Toggle "Hanya berteks" menampilkan hasil terbalik.**
Root cause: field `has_text` tidak ikut diproyeksikan di endpoint `/api/reviews` (`backend_seed/main.py`, list kolom response) — sehingga `r.has_text` selalu `undefined` di frontend, membuat SEMUA baris (termasuk yang berteks) dianggap "tidak ada teks". Fix: tambahkan `"has_text"` ke list kolom response (perubahan aditif 1 baris, tidak mengubah struktur lain). ✅ Diverifikasi: toggle ON/OFF menghasilkan set data yang benar dan saling melengkapi.

**M2 — Badge sentimen "tampak salah" untuk beberapa ulasan tanpa teks (TERNYATA BUKAN BUG).**
Sempat dicurigai sebagai pelanggaran aturan `rating_fallback` (mis. ulasan rating 5 bintang diberi label "Negatif"). Setelah dicek langsung ke database: **0 dari 384 baris `rating_fallback` melanggar aturan**. Setelah M1 diperbaiki dan teks asli terlihat, ternyata kedua ulasan yang dicurigai justru punya `sentiment_source=model` (bukan fallback) dengan teks yang secara genuin ambigu/negatif meski rating tinggi (mis. "Aku kekopi nakonya, lumayan antri" pada rating 5 — model membaca isi teks, bukan sekadar rating). **Kesimpulan: ini bukti model bekerja sesuai desain**, bukan bug — baik untuk dijadikan contoh kasus di laporan PKL (bagian evaluasi model, PRD §7.2).

**M3 — Tanggal tampil meleset satu hari (off-by-one) dari data asli.**
Root cause: `formatDate()` di `chart-utils.js` memakai `toLocaleDateString()` tanpa `timeZone: 'UTC'` eksplisit — browser di WIB (+7) menggeser tanggal ulasan yang di-post sore/malam UTC ke hari berikutnya. Fix: tambahkan `timeZone: 'UTC'` di opsi formatter. ✅ Diverifikasi dengan kasus spesifik (ulasan "Vera Vera", raw `2026-07-19 18:34:52+00:00` yang sebelumnya tampil "20 Jul", kini benar "19 Jul").

**Catatan tambahan (bukan bug, cukup dicatat):** ditemukan cluster 15 ulasan dengan `review_date` persis sama (19 Juli 2026) dalam jendela data presisi asli (12 bulan terakhir sebelum scraping). **Ini BUKAN bagian dari artefak kompresi tanggal Agustus 18-21 yang didokumentasikan di PRD §5.1** (itu spesifik untuk data lama yang presisinya sudah hilang) — cluster ini ada di rentang data yang sudah dipastikan presisi asli. Kemungkinan pola kunjungan nyata (mis. rombongan/study tour serentak posting ulasan), tapi belum ada konfirmasi pasti. Tidak memerlukan perbaikan kode.

### 9.4 Verifikasi Akhir Menyeluruh

Setelah M1-M3 diperbaiki, seluruh halaman diverifikasi ulang via screenshot nyata (bukan asumsi):
- **Overview**: KPI, donut chart, bar chart, dan chart tren — semua angka konsisten dengan data di database.
- **Review Explorer**: toggle has_text, badge sentimen, tanggal, dan detail panel (termasuk cross-check kata kunci per-ulasan vs top keyword kelasnya di Topic Insights) — semua konsisten.
- **Topic Insights**: ketiga tab (Positif/Netral/Negatif) — skor kata kunci di UI dicocokkan manual dengan hasil query langsung ke `topic_keywords` di database, hasilnya identik.
- **Rekomendasi & Status Pipeline**: konsisten dengan data yang sudah diverifikasi di tahap sebelumnya.

**Kesimpulan status proyek per verifikasi ini: dashboard FastAPI + frontend web custom berfungsi penuh dan sudah melalui proses debugging bertingkat (render → chart → data-layer) dengan setiap temuan diverifikasi memakai bukti konkret (screenshot, query database langsung, Network tab), bukan asumsi.**

Sub-bagian 9.5 & 9.6 di bawah mendokumentasikan bug yang ditemukan & diperbaiki **setelah** verifikasi §9.4 selesai — belum tercatat di versi HANDOFF sebelumnya, ditulis ulang mengikuti format Gejala → Root cause → Fix → Status yang sama dengan M1-M3 di atas.

### 9.5 Bug "[object Object]" di Kartu Rekomendasi (Ditemukan Pasca Verifikasi §9.4)

**Gejala:** kartu pada halaman Rekomendasi menampilkan teks literal `[object Object]` di baris meta atas kartu rekomendasi.

**Root cause:** field `trend` pada response `/api/recommendations` sempat dikirim sebagai **objek** (DESIGN §5.D memperkirakan `trend` = "arah tren naik/turun dibanding periode sebelumnya"), sementara frontend merendernya langsung via `escapeHtml(rec.trend)` — memanggil `String(objek)` menghasilkan literal `"[object Object]"`. Backend kemudian tidak lagi mengirim `trend` (tidak diimplementasikan / dihapus dari response), tapi kode render kartu masih sempat menyentuh field tersebut.

**Fix yang diterapkan:** hapus field `trend` dari response backend `/api/recommendations` (response kini hanya berisi `theme`, `review_count`, `sample_reviews` — cocok dengan implementasi `main.py`), dan beri guard kosong di frontend (`rec.trend ? escapeHtml(rec.trend) : ''`) agar bila field tsb ditambahkan kembali di masa depan tidak pernah tercetak sebagai `[object Object]`.

**Status:** ✅ Diverifikasi — kartu rekomendasi tampil bersih tanpa literal `[object Object]`; konten kartu sepenuhnya berasal dari `review_count` + `sample_reviews`.

### 9.6 Investigasi Kutip Unicode pada Export CSV (Ditemukan Pasca Verifikasi §9.4)

**Gejala:** saat mengekspor ulasan ke CSV ("Unduh CSV" di Review Explorer), muncul kekhawatiran karakter kutip melengkung Unicode (`‘…’` / `“…”`, U+2018–U+201D yang umum di teks ulasan pengguna) akan merusak struktur file / membuat sel bergeser.

**Root cause:** setelah diinvestigasi, **kutip melengkung TIDAK memerlukan escaping** — mereka adalah karakter UTF-8 biasa yang aman di dalam sel CSV dan tidak berinteraksi dengan pembatas kolom. Yang berpotensi merusak struktur baris hanyalah: kutip ganda ASCII (`"`) yang dipakai penanda sel (harus di-double `""` per RFC 4180), tanda koma (`,`) pada teks jika belum dibungkus kutip, dan **baris baru** di dalam teks ulasan (dinormalisasi `.replace(/\r?\n/g, ' ')` menjadi spasi). Masalah nyata yang tersisa saat file dibuka di Excel adalah **encoding UTF-8 tanpa BOM** — Excel salah menebak charset untuk teks beraksara/accent dan kutip Unicode, sehingga muncul karakter rusak.

**Fix yang diterapkan:** `csvEscape()` di `reviews.js` mengikuti **RFC 4180** (bungkus sel berisi koma/kutip/baris baru; escape `"` → `""`), dan file ditulis dengan **prepend BOM `\uFEFF`** pada Blob `text/csv;charset=utf-8` — sehingga Excel/layanan spreadsheet membuka UTF-8 dengan benar (termasuk kutip Unicode & karakter non-ASCII lainnya). Nama file `kuntum-insight-ulasan-YYYY-MM-DD.csv`.

**Status:** ✅ Diverifikasi — struktur file CSV valid (tiap sel yang mengandung koma/kutip/baris baru dibungkus & di-escape benar), BOM ada di awal file sehingga UTF-8 terbaca utuh, dan header/konten konsisten dengan kolom tabel Review Explorer.

## 10. Skema Response API — Referensi Cepat

Semua endpoint list: `{ "data": [...], "meta": { "total": N, "page": ..., "page_size": ... } }`
Semua endpoint tunggal: `{ "data": {...} }`

Lihat PRD.md §10 untuk daftar lengkap endpoint, query params, dan sumber kolom/tabelnya.

## 11. Fitur Frontend & Perubahan yang Ditambahkan Setelah Verifikasi §9.4

Bagian ini mendokumentasikan fitur/keputusan yang **sudah masuk kedalam kode** tapi belum tercatat saat HANDOFF versi §9.4 ditulis. Tidak mengubah atau menggantikan isi §1–§10 — murni tambahan agar dokumentasi sinkron dengan kondisi kode aktual.

### 11.1 Fitur Cetak / Export PDF di Overview
- Tombol **"Cetak Laporan"** (`overview.js`, `print-btn`) memanggil `window.print()` — pengguna bisa menyimpan sebagai PDF dari dialog print browser.
- CSS `@media print` (`css/pages/overview.css`): menyembunyikan tombol cetak & skeleton/empty-state, `page-break-*` / `break-inside: avoid` agar header, kartu KPI, dan chart tidak terpotong antar halaman, memaksa `.trend-grid` tetap 3 kolom (3 mini-chart tercetak sejajar) dengan tinggi chart 180px.

### 11.2 Export CSV di Review Explorer
- Tombol **"Unduh CSV"** (`reviews.js`) mengekspor **hasil filter & halaman saat ini** — kolom: `Reviewer, Rating, Cuplikan Ulasan, Sentimen, Sumber Sentimen, Tanggal, Likes`.
- `sentiment_source` dipetakan ke label ramah manusia (`Dari Rating` / `Model`); tanggal diformat lewat `formatDate()` (WIB); nama file ber-tanggal `kuntum-insight-ulasan-YYYY-MM-DD.csv`.
- Dasar teknis escaping & BOM: lihat §9.6.

### 11.3 Drill-down "Lihat semua ulasan" di Rekomendasi
- Setiap kartu rekomendasi memiliki tombol **"Lihat semua N ulasan"** (`recommendations.js` → `_openThemePanel`) yang membuka slide panel dan memanggil `/api/topics/{theme}/reviews?sentiment_label=negatif&page_size=20`.
- Panel menampilkan 20 ulasan negatif pertama dari tema tsb + info "(menampilkan X dari N)" bila total melebihi 20. Memakai komponen slide-panel `panel.js` yang sama dengan detail Review Explorer (tidak ada navigasi keluar halaman — tetap SPA).

### 11.4 Chart tren sentimen: Small Multiples (3 mini-chart)
- `renderTrendChart` di `overview.js` merender **satu mini line-chart per sentimen** (Positif/Netral/Negatif) berdampingan, masing-masing dengan **sumbu Y otomatis** (`beginAtZero` sesuai datanya sendiri) sehingga pola volume kecil (Netral/Negatif) tetap terbaca walau Positif jauh lebih besar. Ini menggantikan satu chart gabung yang semula direncanakan di DESIGN §5.A (satu chart dengan skala seragam).
- Ke-6 aturan data dari DESIGN §5.A tetap dipatuhi: plot `*_avg_month` (bukan `total` mentah), `segment.borderDash` untuk titik `is_approximate`, label `period` apa adanya, tooltip menampilkan total mentah + `≈`, dan sumbu X `type: 'category'`.
- Tik sumbu X dibuat **seragam & deterministik antar ketiga chart** via `useSharedTicks(6)` / `computeTickIndices()` di `chart-utils.js` — `autoSkip` bawaan Chart.js berjalan independen per-chart dengan lebar berbeda sehingga bisa membuat label tick berlainan antar chart; fungsi ini memilih indeks dengan formula sama sehingga ketiganya selalu sejajar secara horizontal.

### 11.5 Unifikasi Ikon SVG
- `components/icons.js` = satu set ikon SVG inline bergaya Feather/Lucide (`icon()`, `starIcon()`) yang dipakai di **semua** halaman: sidebar, KPI, badge sentimen, tombol, empty-state. Bukan karakter unicode/emoji → rendering konsisten lintas OS/browser dan bisa diwarnai via `currentColor`.
- `renderStars()` (`chart-utils.js`) merender bintang sebagai **SVG** (bukan karakter `★`); badge sentimen memakai ikon polaritas (✓ / – / ✕, `polaritySvg`) plus ikon `rateFallback` sebagai pembeda non-warna (ramah buta warna, DESIGN §2).

### 11.6 Keputusan timezone: Tampilan WIB Konsisten (menyusul pendekatan M3 di §9.3)
- `formatDate()` di `chart-utils.js` kini memakai **`timeZone: 'Asia/Jakarta'` (WIB)**, bukan `UTC` seperti yang didokumentasikan §9.3 M3. Keputusan ini **disengaja**: seluruh data adalah bisnis Indonesia (ulasan pengunjung, timestamp training), sehingga tanggal ditampilkan dalam waktu lokal bisnis. Fungsi baru `formatDateTime()` (format `dd MMM yyyy, HH.mm` WIB) diperkenalkan dan dipakai untuk `trained_at` di halaman Status Pipeline.
- Teks §9.3 M3 **sengaja dibiarkan utuh** sebagai riwayat — catatan ini yang menyusulnya (supersesi). Konsekuensi logis dari keputusan WIB: kasus "Vera Vera" (raw `2026-07-19 18:34:52+00:00`) kembali tampil **"20 Jul"** karena 18:34 UTC = 01:34 WIB (hari berikutnya) — konsisten dengan lensa "hari lokal bisnis", bukan regresi.

### 11.7 Infra Frontend (melengkapi DESIGN, tidak mengubah kontrak API)
- `state.js`: cache in-memory ber-TTL (`getCache`/`setCache`) untuk data yang jarang berubah dalam satu sesi — `/api/overview/kpi`, `/api/recommendations`, `/api/pipeline/status` (DESIGN §7).
- `api.js`: `AbortController` + `abortInFlight()` membatalkan request usang saat filter/pencarian berubah cepat berturut-turut — mencegah race condition (DESIGN §4.3).
- Skeleton loader per komponen (`skeleton.js`), slide panel (`panel.js`), router hash dengan transisi fade/slide + `scrollTo` atas halaman (`router.js`), sidebar collapse (desktop) & drawer (mobile) dengan persistensi `localStorage` (`layout.js`).