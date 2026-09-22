# Product Requirements Document (PRD)
## Kuntum Insight — Data Pipeline & Analisis Sentimen Ulasan Google Maps

**Studi Kasus:** Kuntum Farmfield, Bogor
**Disusun oleh:** Rifqi Fairuzzabady (NPM 065123034)
**Program Studi:** Ilmu Komputer, FMIPA, Universitas Pakuan
**Konteks:** Praktik Lapang (PKL) — 30 hari kerja, hybrid
**Status Revisi:** v3 — Pivot arsitektur dari Streamlit ke Client-Server (FastAPI + Custom Web Frontend)

**Catatan untuk Tim Pengembang (Pembagian Kerja Lintas-AI):**
Dokumen ini adalah kontrak spesifikasi antara dua jalur pengerjaan:
- **Notebook ML (`.ipynb`)** — eksperimen, training, dan evaluasi model, dikerjakan terpisah dari layanan API (lihat §7–§9). Kode untuk bagian ini dirumuskan pada sesi/prompt terpisah.
- **Backend (FastAPI) & Frontend (Web Custom)** — dirakit oleh tim/asisten AI developer berdasarkan kontrak endpoint di §10 dan pemetaan kolom di §5 & DESIGN.md. Backend **tidak pernah melakukan training** — hanya memuat artefak model yang sudah jadi (lihat §9.2).

---

## 1. Latar Belakang & Masalah

Kuntum Farmfield menerima banyak ulasan pengunjung di Google Maps, namun data ini belum dimanfaatkan secara sistematis untuk mengevaluasi kualitas layanan. Pengelola tidak memiliki cara cepat untuk mengetahui:
- Berapa proporsi ulasan positif, netral, dan negatif
- Topik/aspek apa yang paling sering dikeluhkan atau dipuji
- Tren kepuasan pelanggan dari waktu ke waktu
- Rekomendasi tindakan konkret berdasarkan data ulasan

**Masalah inti:** Tidak ada sistem otomatis yang mengubah ulasan mentah menjadi insight yang dapat ditindaklanjuti oleh manajemen.

---

## 2. Tujuan Produk

1. Mengotomasi pengambilan data ulasan Google Maps Kuntum Farmfield. ✅ **Selesai**
2. Membersihkan dan menstrukturkan data ulasan berbahasa Indonesia. ✅ **Selesai**
3. Mengklasifikasikan sentimen tiap ulasan (positif/netral/negatif). 🔄 **Sedang berjalan** (notebook, terpisah dari layanan API)
4. Menyajikan hasil dalam web dashboard interaktif, pixel-perfect sesuai prototipe Stitch AI, yang mudah dipahami staf non-teknis. ⏳ **Belum dimulai** — arsitektur diputuskan: **Client-Server (FastAPI + Web Custom)**
5. Menghasilkan rekomendasi perbaikan layanan berbasis data. ⏳ **Belum dimulai**

---

## 3. Target Pengguna

| Persona | Kebutuhan |
|---|---|
| **Manajer Operasional Kuntum Farmfield** | Ringkasan cepat kepuasan pengunjung, tanpa perlu membaca semua ulasan satu per satu |
| **Staf Layanan Pelanggan** | Tahu keluhan spesifik apa yang sering muncul untuk ditindaklanjuti |
| **Mahasiswa (Rifqi)** | Sistem yang dapat didemonstrasikan sebagai bukti hasil PKL dan bahan laporan akademik |

---

## 4. Ruang Lingkup

### In-Scope
- ✅ Scraping ulasan Google Maps (rating, teks, tanggal, nama reviewer)
- ✅ Preprocessing teks Bahasa Indonesia (case folding, stemming Sastrawi, stopword removal, tokenisasi)
- 🔄 Klasifikasi sentimen (scikit-learn: TF-IDF + Logistic Regression, atau model lain sesuai eksperimen) — dikerjakan di notebook, terpisah dari API
- 🔄 Topic/keyword extraction (TF-IDF ranking atau gensim) — dikerjakan di notebook, terpisah dari API
- ⏳ Penyimpanan data terstruktur (SQLite)
- ⏳ **Backend API (FastAPI)** — memuat data & artefak model, melayani request JSON
- ⏳ **Frontend Web Custom** (HTML/CSS/JS atau React), Single Page Application, pixel-perfect sesuai prototipe Stitch AI (ID: `11963094705824021853`)
- ⏳ Rekomendasi otomatis berbasis klaster sentimen negatif

### Out-of-Scope
- Sistem reservasi/CRM (dikerjakan mahasiswa lain — Hariffa)
- Balasan otomatis ke ulasan Google Maps
- Analisis sentimen multi-bahasa (fokus Bahasa Indonesia)
- Real-time streaming (cukup batch update berkala)
- Training atau retraining model di dalam proses backend API (lihat §9.2 — dilarang secara eksplisit)

---

## 5. Status Data Saat Ini — `reviews_clean.csv`

Tahap **Data Collection** dan **Data Cleaning** telah selesai dan menghasilkan satu dataset bersih siap-modeling dengan struktur berikut:

| Kolom | Tipe | Deskripsi | Catatan Kualitas Data |
|---|---|---|---|
| `review_id` | string | ID unik ulasan dari Google Maps (encoded) | Primary key |
| `place_id` | string | ID lokasi Google Maps | Konstan (satu lokasi: Kuntum Farmfield) |
| `author` | string | Nama reviewer | — |
| `rating` | float (1–5) | Rating bintang | **Sangat timpang**: mayoritas rating 4–5 (±90%), rating 1–2 hanya sebagian kecil — berdampak langsung ke strategi labeling & evaluasi model (lihat §7.2) |
| `review_text_original` | string | Teks ulasan asli (belum diproses) | Sebagian kosong — berkorelasi dengan `has_text = False` |
| `has_text` | boolean | Penanda apakah ulasan memiliki teks | Sebagian kecil ulasan **hanya berupa rating tanpa teks** — tidak bisa diproses NLP, ditangani terpisah |
| `review_date` | datetime (ISO, timezone-aware) | Tanggal ulasan diposting | Rentang multi-tahun — dasar untuk analisis tren |
| `likes` | int | Jumlah "helpful/like" pada ulasan | Bisa dipakai sebagai bobot relevansi/insight, bukan fitur sentimen |
| `review_text_clean` | string | Teks hasil case folding, penghapusan karakter non-alfabet, stemming Sastrawi, stopword removal | Fitur teks utama untuk modeling |
| `review_tokens` | string (list-like, hasil `json.dumps`/`str(list)`) | Token hasil tokenisasi dari `review_text_clean` | Perlu di-parse ulang (`ast.literal_eval`/`json.loads`) sebelum dipakai; sudah bersih dari stopword |
| `token_count` | int | Jumlah token per ulasan | Berguna untuk filtering ulasan terlalu pendek untuk diklasifikasi secara andal |

**Implikasi desain penting yang muncul dari data aktual (tidak berubah oleh pivot arsitektur):**
1. **Tidak ada label sentimen eksplisit** di dataset — perlu strategi *weak supervision* dari `rating` sebagai proxy awal (lihat §7.1).
2. **Ketimpangan kelas (class imbalance)** yang tajam pada `rating` akan terbawa ke distribusi kelas sentimen jika proxy rating dipakai mentah-mentah — mitigasi wajib direncanakan.
3. **Ulasan tanpa teks (`has_text = False`)** tidak bisa melewati pipeline NLP; harus di-*branch* terpisah dan diberi label sentimen dari `rating` saja (bukan dari model teks).
4. **Ulasan sangat pendek** (`token_count` rendah, termasuk 0) berisiko menghasilkan prediksi sentimen yang tidak andal — perlu ambang batas minimum token untuk masuk ke pipeline klasifikasi berbasis teks.

### 5.1 ⚠️ Keterbatasan Data: Kompresi Tanggal Akibat Parsing Format Relatif Google Maps

**Ditemukan setelah dashboard berjalan (Agustus 2026):** kolom `review_date` untuk **±94% dari seluruh data (2.661 dari 2.832 baris)** tidak mencerminkan tanggal asli ulasan diposting.

**Penyebab:** Google Maps hanya menampilkan tanggal ulasan lama dalam format relatif (mis. "3 tahun lalu"), bukan tanggal absolut. Scraper (tahap §4 yang sudah "selesai") mengonversi teks relatif ini menjadi tanggal absolut dengan cara **tanggal scraping dikurangi N tahun** — bukan tanggal asli. Akibatnya, seluruh ulasan dari satu tahun penuh (yang aslinya tersebar di 12 bulan) ter-*collapse* menjadi satu titik tanggal saja (terverifikasi jatuh di tanggal 18-21 Agustus, sesuai tanggal scraping dijalankan).

**Dampak:**
- Granularitas **bulan/hari untuk data sebelum ~September 2025 tidak bisa dipercaya** — hanya **tahun**-nya yang merupakan estimasi wajar.
- Hanya ulasan dari **~12 bulan terakhir sebelum scraping** (yang di Google Maps masih ditampilkan dengan presisi hari/minggu) yang memiliki tanggal bulan/hari yang valid.
- **Tidak bisa diperbaiki dengan re-scraping** — Google Maps memang secara native tidak mengekspos tanggal presisi untuk ulasan lama; ini bukan bug scraper, melainkan keterbatasan sumber data.

**Mitigasi yang diterapkan (workaround di layer visualisasi, lihat DESIGN.md §5.A & kode `main.py`):**
- Backend mendeteksi baris yang terkena artefak ini via pola tanggal (`bulan = Agustus` DAN `tanggal ∈ {18,19,20,21}` — pola spesifik yang cocok dengan tanggal scraping berlangsung), lalu mengagregasinya per **tahun** (bukan bulan).
- Ulasan dengan tanggal asli presisi (~12 bulan terakhir) tetap diagregasi per **bulan**.
- Setiap titik data diberi flag `is_approximate` agar frontend bisa menampilkannya secara berbeda (mis. gaya garis berbeda) — lihat DESIGN.md §5.A.
- Endpoint juga menyediakan field `*_avg_month` (total tahunan dibagi 12) agar skala titik tahunan dan bulanan **sebanding secara visual** dalam satu grafik tren yang sama.

**Untuk laporan akademik PKL:** dokumentasikan ini sebagai **keterbatasan data yang diketahui (known data limitation)**, bukan kegagalan pipeline — cantumkan di bagian metodologi/keterbatasan penelitian.

---

## 6. Keputusan Pivot Arsitektur: Client-Server

**Keputusan:** Streamlit **dibuang sepenuhnya**. Alasan: Streamlit tidak dapat mereproduksi tampilan pixel-perfect dari prototipe Stitch AI (ID: `11963094705824021853`), yang menjadi acuan visual wajib untuk demo akademik & serah-terima ke Kuntum Farmfield.

**Arsitektur baru:**

```
┌───────────────────────────┐        HTTP/JSON (fetch/AJAX)       ┌───────────────────────────┐
│  FRONTEND (Web Custom)     │ ───────────────────────────────────▶│  BACKEND (FastAPI)         │
│  - HTML/CSS/JS atau React  │ ◀───────────────────────────────────│  - Endpoint JSON (§10)     │
│  - Single Page Application │                                      │  - Memuat data + model .pkl│
│  - Pixel-perfect vs Stitch │                                      │    ke memori saat startup  │
│    AI mockup               │                                      │  - TIDAK melakukan training │
└───────────────────────────┘                                      └─────────────┬─────────────┘
                                                                                    │ baca saat startup
                                                                                    ▼
                                                                     ┌───────────────────────────┐
                                                                     │  SQLite (reviews_clean +    │
                                                                     │  sentiment_results)         │
                                                                     │  + models/*.pkl, *.json     │
                                                                     └─────────────┬─────────────┘
                                                                                    ▲
                                                                                    │ diproduksi oleh
                                                                     ┌─────────────┴─────────────┐
                                                                     │  NOTEBOOK ML (.ipynb)        │
                                                                     │  Eksplorasi, training,       │
                                                                     │  evaluasi — TERPISAH TOTAL   │
                                                                     │  dari proses backend API     │
                                                                     └───────────────────────────┘
```

**Prinsip pemisahan lingkungan kerja (wajib dipatuhi tim/asisten developer):**
1. **Notebook ML** adalah satu-satunya tempat training terjadi. Ia berjalan secara manual/offline (Colab atau Jupyter lokal), tidak pernah dijalankan otomatis oleh backend.
2. **Backend FastAPI** murni sebagai **serving layer**: memuat `reviews_clean` + `sentiment_results` (dari SQLite) dan artefak model (`.pkl`) ke memori saat proses startup, lalu merespons request API secara instan dari data yang sudah dimuat.
3. Kedua lingkungan **berbagi kontrak data** yang sama: skema SQLite (§8.2) dan skema artefak model (§7.4) — perubahan skema di salah satu pihak harus disinkronkan ke pihak lain melalui dokumen ini.

---

## 7. Spesifikasi Model Analisis Sentimen (Notebook ML — Tidak Berubah)

> Bagian ini **tidak berubah** oleh pivot arsitektur. Seluruh logika ini dikerjakan di `.ipynb`, sepenuhnya independen dari backend API.

### 7.1 Strategi Labeling (Weak Supervision dari Rating)

Karena dataset tidak memiliki kolom label sentimen, label awal diturunkan dari `rating` sebagai proxy, lalu divalidasi/dikoreksi secara manual pada sampel:

| Rating | Label Proxy Awal |
|---|---|
| 4–5 | Positif |
| 3 | Netral |
| 1–2 | Negatif |

**Langkah validasi wajib:**
- Ambil **sampel acak stratified** (mis. 150–300 ulasan, proporsional per kelas) dari `review_text_clean` beserta `rating`-nya, lalu **anotasi manual** untuk mengecek konsistensi rating vs. isi teks (kasus umum: rating 5 tapi teks berisi keluhan spesifik, atau rating 3 karena alasan non-layanan seperti harga).
- Ulasan dengan `has_text = False` **tidak ikut proses ini** — sentimennya langsung memakai `sentiment_source = rating_fallback` berdasarkan tabel di atas, tanpa klasifikasi teks.
- Ulasan dengan `token_count` di bawah ambang batas (misal < 3 token efektif) diberi bendera `low_confidence` dan sebaiknya tetap memakai fallback dari rating, bukan prediksi model teks.

### 7.2 Penanganan Ketimpangan Kelas

Distribusi `rating` di data aktual sangat condong ke 4–5, sehingga proxy label sentimen juga akan didominasi kelas Positif. Untuk menghindari model yang bias (selalu memprediksi "Positif"):
- Gunakan **stratified train/validation/test split** agar proporsi kelas konsisten di tiap subset.
- Terapkan **class weighting** (`class_weight="balanced"` pada Logistic Regression) sebagai baseline.
- Uji **oversampling kelas minoritas** (mis. SMOTE pada representasi TF-IDF, atau *random oversampling* teks) sebagai eksperimen lanjutan.
- **Metrik evaluasi wajib bukan hanya akurasi**: prioritaskan **macro F1-score** dan **precision/recall per kelas**, khususnya kelas Negatif — karena kelas inilah yang paling bernilai bisnis (dasar rekomendasi perbaikan layanan) walau jumlahnya paling sedikit.

### 7.3 Fitur & Representasi Teks

- **Sumber fitur utama:** `review_text_clean` (untuk TF-IDF berbasis karakter/n-gram kata) dan/atau `review_tokens` (list token yang sudah bersih, dipakai langsung sebagai *pre-tokenized input* ke `TfidfVectorizer(tokenizer=..., preprocessor=None, lowercase=False)` agar tidak melakukan tokenisasi ganda).
- **Skema fitur:** TF-IDF dengan kombinasi unigram + bigram (`ngram_range=(1,2)`), `min_df` disesuaikan hasil eksperimen untuk membuang token langka/typo residual (mis. `raaa` pada contoh data).
- **Fitur tambahan opsional (numerik, digabung via `FeatureUnion`/`ColumnTransformer`):**
  - `token_count` — proxy panjang ulasan, berkorelasi dengan kekayaan informasi sentimen.
  - `likes` — sinyal tambahan (opsional, perlu diuji apakah menambah nilai atau justru bias).

### 7.4 Algoritma & Eksperimen

- **Baseline:** TF-IDF + Logistic Regression (`class_weight="balanced"`, multi-class `multinomial`).
- **Alternatif pembanding:** Linear SVM, Multinomial Naive Bayes, atau (jika waktu memungkinkan) fine-tuning ringan model transformer Bahasa Indonesia (IndoBERT) sebagai perbandingan performa vs. kompleksitas — dicatat sebagai eksperimen opsional, bukan wajib mengingat batasan waktu 30 hari PKL.
- **Validasi:** k-fold cross-validation (stratified) pada data hasil anotasi/proxy, dilaporkan bersama confusion matrix per kelas.
- **Output artefak (kontrak dengan backend, lihat §9.2):** `tfidf_vectorizer.pkl`, `sentiment_model.pkl`, `label_map.json` (mapping index kelas ↔ label string), disimpan di direktori `models/` dengan penanda versi (mis. `sentiment_model_v1.pkl`). Direktori `models/` inilah yang **dibaca (read-only)** oleh backend FastAPI saat startup.

### 7.5 Output Inference (Dijalankan Sekali di Notebook / Skrip Batch Terpisah, Bukan di Request API)

Untuk setiap ulasan di `reviews_clean`:
1. Jika `has_text = False` atau `token_count` di bawah ambang → `sentiment_source = rating_fallback`, label dari tabel §7.1, `sentiment_confidence = null`.
2. Jika teks memadai → jalankan vectorizer + model `.pkl` → `sentiment_label`, `sentiment_confidence` (probabilitas kelas terpilih), `sentiment_source = model`.
3. Tulis hasil ke tabel `sentiment_results` di SQLite.

> **Penting:** Proses ini adalah **batch job**, dijalankan dari notebook/skrip terpisah setiap kali ada data baru atau model baru — **bukan** logika yang dieksekusi per-request oleh FastAPI. FastAPI hanya membaca hasil yang sudah tersimpan di `sentiment_results`.

---

## 8. Spesifikasi Ekstraksi Topik & Kata Kunci (Notebook ML — Tidak Berubah)

### 8.1 Sumber Data
Menggunakan `review_tokens` (sudah bersih dari stopword & hasil stemming) sebagai input utama — **bukan** `review_text_original` atau `review_text_clean` mentah, agar konsisten dan menghindari pemrosesan ulang.

### 8.2 Pendekatan
- **Metode utama:** TF-IDF ranking per kelompok sentimen (positif/netral/negatif) — hitung skor TF-IDF token secara terpisah untuk masing-masing subset `sentiment_label`, ambil top-N token per kelas sebagai "kata kunci dominan".
- **Metode pelengkap (opsional):** topic modeling dengan `gensim` (LDA) pada korpus `review_tokens` kelas Negatif secara khusus, untuk mengelompokkan keluhan menjadi tema (mis. kebersihan, pelayanan staf, fasilitas, harga).
- **Pengelompokan tema manual (dictionary-based) sebagai pelengkap otomatis:** definisikan daftar kata kunci per tema (mis. `{"kebersihan": ["bersih","kotor","sampah",...], "harga": ["mahal","murah","tiket","harga",...]}`) untuk memetakan token dominan ke tema yang mudah dipahami staf non-teknis.

### 8.3 Output
Untuk setiap kelas sentimen: daftar top-N kata kunci + skor, dan (jika memakai LDA) daftar tema dengan token representatif. Hasil ini disimpan dalam dua bentuk yang keduanya dikonsumsi backend:
- **Per-ulasan:** kolom `top_keywords` (JSON list) di tabel `sentiment_results`.
- **Agregat korpus:** tabel `topic_keywords` baru (lihat §8.4) — dihitung sekali per training run, dibaca langsung oleh endpoint `/api/topics` tanpa komputasi ulang saat request.

### 8.4 Skema Tabel Tambahan: `topic_keywords`

| Kolom | Tipe | Keterangan |
|---|---|---|
| `sentiment_label` | string | `positif` / `netral` / `negatif` |
| `keyword` | string | Token/kata kunci |
| `score` | float | Skor TF-IDF agregat |
| `theme` | string (nullable) | Tema hasil pemetaan dictionary-based, jika ada |
| `model_version` | string | Versi ekstraksi yang menghasilkan baris ini |

### 8.5 ⚠️ Perbaikan Diterapkan: Partikel Bahasa Indonesia Mendominasi Kata Kunci

**Ditemukan setelah dashboard berjalan:** token "nya" (partikel posesif/enklitik, mis. dari "tempatnya", "harganya") muncul sebagai kata kunci **teratas di ketiga kelas sentimen** — padahal tidak membawa makna topik/aspek apa pun.

**Penyebab:** Sastrawi (stemmer Bahasa Indonesia) kadang memisahkan partikel "-nya" dari kata induknya jadi token tersendiri, bukan menghapusnya sebagai stopword. Karena hampir semua ulasan Bahasa Indonesia mengandung akhiran ini, token "nya" mendominasi secara statistik di TF-IDF ranking.

**Perbaikan yang diterapkan (di tahap ekstraksi topik saja — TIDAK menyentuh model klasifikasi sentimen `sentiment_model_v1.pkl`, sehingga tidak perlu retraining):** tambahkan daftar stopword khusus ekstraksi topik untuk membuang partikel/kata generik yang terbukti tidak informatif:

```python
TOPIC_STOPWORDS = {
    # Partikel/enklitik Bahasa Indonesia
    "nya", "kah", "lah", "pun", "deh", "sih", "dong", "nih", "kok", "toh", "kan",
    # Kata ganti/tanya/sambung generik yang terbukti muncul tapi tidak informatif
    "aja", "apa", "sama", "gak", "ga", "buat", "jadi", "dalam",
    "banyak", "sangat", "terlalu", "utk", "yg", "dg", "dr",
    # English filler yang lolos (ulasan berbahasa Inggris)
    "not", "for", "the", "and", "is", "are", "to", "of", "in",
}
```

Diteruskan sebagai parameter `stop_words` ke `TfidfVectorizer` di fungsi `top_keywords_per_class` (§8.2) — sklearn tetap menerapkan filter ini walau tokenizer-nya kustom (`identity_tokenizer`), karena filtering stopword terjadi setelah tahap tokenisasi.

**⚠️ Catatan penting soal `THEME_DICTIONARY`:** perbaikan ini dijalankan langsung terhadap `kuntum_insight.db` yang sudah ada (tanpa akses ke notebook Colab asli), sehingga `THEME_DICTIONARY` yang dipakai adalah **hasil rekonstruksi** dari tema yang sudah tersimpan di `topic_keywords` sebelum perbaikan — **bukan** salinan persis dari dictionary asli yang Anda definisikan/perluas sendiri di Colab. Rekonstruksi ini kemungkinan **tidak lengkap** (hanya mencakup kata kunci yang kebetulan sudah masuk top-25 sebelumnya; entri tema yang Anda definisikan tapi belum pernah nangkring di top-25 tidak akan ikut terekonstruksi). **Rekomendasi:** simpan salinan `THEME_DICTIONARY` asli dari notebook Colab Anda (copy-paste sel kodenya) sebagai referensi tetap, supaya perbaikan/regenerasi topik di masa depan tidak kembali kehilangan kustomisasi tema Anda.

---

## 9. Alur Kerja & Data Pipeline Produksi (Revisi Arsitektur)

### 9.1 Tahap Selesai (Recap)
- **Scraping**: data mentah diambil dari Google Maps (rating, teks, tanggal, reviewer, likes).
- **Cleaning**: deduplikasi, penanganan missing value, case folding, penghapusan karakter non-alfabet, stemming & stopword removal (Sastrawi), tokenisasi → menghasilkan `reviews_clean.csv`.

### 9.2 Prinsip Utama: FastAPI Adalah Serving Layer, Bukan Training Layer

**FastAPI backend SAMA SEKALI TIDAK melakukan training, fitting vectorizer, atau komputasi ML berat apa pun saat menerima request.** Tanggung jawabnya hanya:

1. **Saat startup aplikasi (sekali saja):**
   - Memuat `reviews_clean` + `sentiment_results` + `topic_keywords` dari SQLite ke struktur data in-memory (mis. pandas DataFrame atau cache dict), agar query filter/agregasi cepat tanpa round-trip disk berulang.
   - Memuat artefak `tfidf_vectorizer.pkl`, `sentiment_model.pkl`, `label_map.json` dari `models/` ke memori — **hanya untuk kebutuhan ditampilkan/dijelaskan** (mis. metadata versi model di halaman Pipeline Status), bukan untuk memprediksi ulasan baru secara real-time (di luar scope MVP; lihat §9.4 jika dibutuhkan ke depan).
2. **Saat menerima request dari frontend:**
   - Melakukan filter, sorting, agregasi ringan pada data yang sudah ada di memori (mis. hitung distribusi sentimen sesuai filter tanggal/rating yang diminta).
   - Mengembalikan response JSON sesuai kontrak endpoint (§10).
3. **Tidak pernah:** memanggil `.fit()`, melatih ulang model, menjalankan Sastrawi stemming on-the-fly, atau menghitung ulang TF-IDF dari nol per request.

### 9.3 Skema Database (SQLite)

- **`reviews`** (raw) — hasil scraping mentah, sebelum cleaning.
- **`reviews_clean`** (processed) — mengikuti skema aktual: `review_id, place_id, author, rating, review_text_original, has_text, review_date, likes, review_text_clean, review_tokens, token_count`.
- **`sentiment_results`** — relasi 1:1 ke `reviews_clean` via `review_id`:

  | Kolom | Tipe | Keterangan |
  |---|---|---|
  | `review_id` | FK → reviews_clean | |
  | `sentiment_label` | string | `positif` / `netral` / `negatif` |
  | `sentiment_confidence` | float | Skor probabilitas kelas terpilih |
  | `sentiment_source` | string | `model` (dari klasifier teks) atau `rating_fallback` |
  | `top_keywords` | string (JSON list) | Kata kunci dominan hasil ekstraksi topik untuk ulasan tsb. |
  | `model_version` | string | Versi artefak model yang dipakai |
  | `predicted_at` | datetime | Timestamp prediksi dijalankan |

- **`topic_keywords`** — lihat §8.4.

### 9.4 Update Data Berkala (Batch, Bukan Real-Time)

- Skrip scraping inkremental (terpisah dari FastAPI) berhenti otomatis saat menemui `review_id` yang sudah ada di tabel `reviews`.
- Ulasan baru diproses lewat **fungsi cleaning yang identik** dengan notebook (modul bersama `cleaning_utils.py`), lalu diprediksi menggunakan artefak `.pkl` (via skrip batch, bukan endpoint API) dan ditulis ke `sentiment_results`.
- Setelah batch update selesai, FastAPI perlu **restart** (atau menyediakan endpoint admin `/api/admin/reload-cache` — opsional) agar cache in-memory-nya menyerap data terbaru dari SQLite.

---

## 10. Kontrak Endpoint API (FastAPI) — untuk Tim Backend & Frontend

Base path: `/api`. Semua endpoint mengembalikan JSON. Pemetaan lengkap ke elemen UI per halaman ada di DESIGN.md §4.

| Endpoint | Method | Deskripsi | Query Params Utama | Sumber Kolom/Tabel |
|---|---|---|---|---|
| `/api/overview/kpi` | GET | Ringkasan KPI untuk halaman Overview | `date_from`, `date_to` (opsional) | `reviews_clean` (`review_id`, `rating`, `has_text`, `token_count`, `likes`), `sentiment_results` (`sentiment_label`) |
| `/api/overview/sentiment-distribution` | GET | Data donut chart distribusi sentimen | `include_fallback` (bool) | `sentiment_results.sentiment_label`, `sentiment_source` |
| `/api/overview/rating-distribution` | GET | Data bar chart distribusi rating | — | `reviews_clean.rating` |
| `/api/overview/sentiment-trend` | GET | Data tren sentimen bulanan | `date_from`, `date_to` | `reviews_clean.review_date` × `sentiment_results.sentiment_label` |
| `/api/reviews` | GET | Daftar ulasan untuk Review Explorer (paginated) | `search`, `sentiment[]`, `rating_min`, `rating_max`, `date_from`, `date_to`, `has_text_only` (bool), `sort_by`, `page`, `page_size` | `reviews_clean` (semua kolom) JOIN `sentiment_results` |
| `/api/reviews/{review_id}` | GET | Detail satu ulasan | — | `reviews_clean` JOIN `sentiment_results` |
| `/api/topics` | GET | Kata kunci & tema dominan per sentimen | `sentiment_label`, `top_n` | `topic_keywords` |
| `/api/topics/{theme}/reviews` | GET | Ulasan representatif untuk satu tema | `sentiment_label` | `sentiment_results.top_keywords` + `reviews_clean` |
| `/api/recommendations` | GET | Kartu rekomendasi actionable | — | `topic_keywords` (filter `sentiment_label = negatif`) + agregasi tren dari `review_date` |
| `/api/pipeline/status` | GET | Status pipeline untuk halaman admin/demo | — | Metadata: timestamp scraping terakhir, jumlah baris `reviews` vs `reviews_clean`, `model_version` aktif |

**Konvensi response:** setiap endpoint list mengembalikan `{ "data": [...], "meta": { "total": N, "page": ..., "page_size": ... } }`; endpoint tunggal mengembalikan `{ "data": {...} }`. Error mengikuti format standar FastAPI (`{"detail": "..."}`) dengan HTTP status code yang sesuai.

---

## 11. Kebutuhan Non-Fungsional

| Aspek | Ketentuan |
|---|---|
| Bahasa UI | Bahasa Indonesia |
| Platform | Web-based, Client-Server: Backend FastAPI + Frontend Web Custom (HTML/CSS/JS atau React), dapat di-deploy terpisah (mis. backend di VPS/Render, frontend statis di Vercel/Netlify) |
| Performa | Backend merespons request dari data in-memory (bukan query disk berulang) agar frontend terasa instan; mendukung ratusan–ribuan ulasan tanpa lag |
| Reproducibility | Semua notebook & script dapat dijalankan ulang dengan dataset baru; fungsi cleaning dibagikan antara notebook & pipeline batch produksi |
| Dokumentasi | Setiap tahap pipeline (termasuk keputusan labeling, mitigasi class imbalance, dan kontrak API) didokumentasikan untuk laporan akademik PKL |
| Kontrak Lintas Tim | Perubahan skema database atau endpoint API harus diperbarui di dokumen ini (§9.3, §10) agar notebook ML dan frontend/backend tetap sinkron |

---

## 12. Tech Stack

- **Scraping:** Playwright-based scraper (custom, anti-deteksi) — ✅ selesai
- **Eksplorasi & Training:** Jupyter Notebook (`.ipynb`) — terpisah total dari layanan API
- **ETL & Cleaning:** pandas, Sastrawi — ✅ selesai (fungsi diekstrak ke modul bersama `cleaning_utils.py`, dipakai ulang oleh skrip batch produksi)
- **Modeling:** scikit-learn (TF-IDF, Logistic Regression/SVM/NB), opsional gensim (LDA), opsional IndoBERT sebagai pembanding — diekspor via `joblib`/`pickle`
- **Storage:** SQLite
- **Backend API:** **FastAPI** — serving layer murni, memuat data & artefak model ke memori saat startup
- **Frontend:** **Web Custom** (HTML/CSS/JS atau React), Single Page Application, pixel-perfect mengikuti prototipe Stitch AI (ID: `11963094705824021853`)
- **Bahasa:** Python (scraping, cleaning, modeling, backend) + JavaScript/TypeScript (frontend)

---

## 13. Metrik Keberhasilan

1. Pipeline berjalan otomatis dari data bersih hingga tersedia via API (data collection & cleaning sudah terbukti berjalan; modeling, inference, dan serving API menyusul).
2. Model sentimen mencapai **macro F1-score** yang layak didokumentasikan (target awal ≥75% akurasi, disesuaikan dengan hasil eksperimen — dengan catatan performa kelas Negatif dievaluasi terpisah mengingat ketimpangan kelas).
3. Frontend web dapat diakses dan dipahami tanpa penjelasan teknis oleh staf Kuntum Farmfield, dengan tampilan sesuai prototipe Stitch AI.
4. Backend API merespons request dengan latensi rendah (data in-memory, tanpa training/komputasi berat per request).
5. Minimal 3–5 rekomendasi actionable dihasilkan dari data ulasan negatif, didukung kata kunci/tema hasil ekstraksi topik.

---

## 14. Timeline Ringkas (30 Hari Kerja, Hybrid) — Status Terbaru

| Minggu | Fokus | Status |
|---|---|---|
| 1 | Observasi lapangan, setup environment, mulai data collection | ✅ Selesai |
| 2 | Data cleaning, pipeline ETL, eksplorasi awal | ✅ Selesai (`reviews_clean.csv` dihasilkan) |
| 3 | Labeling/anotasi, training & evaluasi model sentimen, topic extraction (notebook) | 🔄 Sedang berjalan |
| 4 | Pembangunan backend FastAPI + frontend Web Custom, validasi onsite, finalisasi & dokumentasi | ⏳ Belum dimulai |

---

## 15. Struktur Halaman untuk Prototipe (Google Stitch, ID: `11963094705824021853`)

Dashboard "Kuntum Insight" dipecah menjadi 5 layar, masing-masing dipetakan ke endpoint API di §10 (detail elemen visual & kolom lihat DESIGN.md §4):

1. **Dashboard Utama (Overview)** — KPI & ringkasan sentimen → `/api/overview/*`
2. **Review Explorer** — tabel ulasan yang dapat difilter → `/api/reviews`
3. **Topic & Keyword Insights** — kata kunci & tema per sentimen → `/api/topics`
4. **Recommendations Page** — rekomendasi actionable → `/api/recommendations`
5. **Data Pipeline Status** — status teknis pipeline (untuk admin/demo) → `/api/pipeline/status`

---
