# Kuntum Insight - Design System & UI Guide

Dokumen ini berisi panduan desain visual dan arsitektur UI untuk proyek "Kuntum Insight", diimplementasikan sebagai **Single Page Application (SPA)** dengan **Web Custom Frontend** (HTML/CSS/JS atau React) yang mengonsumsi **Backend API (FastAPI)**. Panduan ini didasarkan pada prototipe **Google Stitch AI (ID: `11963094705824021853`)** yang menjadi acuan visual pixel-perfect, dan setiap komponen di sini dipetakan langsung ke kolom aktual di `reviews_clean.csv` serta ke endpoint API dari PRD.md §10.

**Untuk Tim/Asisten Developer:** Dokumen ini adalah spesifikasi UI, bukan implementasi. Setiap elemen visual mencantumkan endpoint API sumber datanya — gunakan `fetch`/AJAX asinkron untuk mengambil data tersebut, jangan melakukan komputasi agregasi di sisi frontend (agregasi sudah dilakukan backend, lihat PRD.md §9.2).

---

## 1. Tema & Konsep Visual
- **Gaya:** Clean, Modern, Analytical Dashboard.
- **Vibe:** Agro-tourism profesional (bersih, natural, mudah dibaca oleh staf non-teknis).
- **Mode:** Light Mode (Terang) dengan dominasi warna putih dan aksen hijau alami.

## 2. Palet Warna (Color Palette)
- **Background Utama:** Putih keabu-abuan terang (Off-white / `#F7F9F8`) agar mata tidak cepat lelah.
- **Background Card/Wadah:** Putih bersih (`#FFFFFF`) untuk memberi kontras tegas pada grafik dan metrik.
- **Warna Utama (Primary/Brand):** Hijau Tua Alami (Kuntum Green — misal `#2C5E43` atau `#3F7A53`). Digunakan untuk header, teks utama, tombol aksi utama, dan grafik utama.
- **Indikator Sentimen** (dipakai konsisten di seluruh aplikasi, sumber: field `sentiment_label` dari respons API):
  - **Positif:** Hijau terang/lembut.
  - **Netral:** Abu-abu / Kuning.
  - **Negatif:** Merah / Oranye kemerahan (Coral).
- **Indikator tambahan — sumber `sentiment_source`:** ulasan dengan `sentiment_source = rating_fallback` (ulasan tanpa teks atau terlalu pendek) diberi ikon/label kecil "dari rating" di sebelah badge sentimen, agar staf memahami bahwa label tersebut tidak berasal dari analisis teks.

**Implementasi:** Palet warna didefinisikan sebagai **CSS custom properties** (`:root { --color-primary: #2C5E43; ... }`) di stylesheet global, dikonsumsi oleh seluruh komponen frontend (baik HTML/CSS/JS vanilla maupun komponen React) — bukan lagi via file konfigurasi Streamlit.

## 3. Tipografi (Typography)
- **Font:** Sans-serif modern dan bersih (Inter atau Roboto, dimuat via Google Fonts atau self-hosted untuk performa).
- **Hirarki:**
  - Judul Halaman (H1): Besar, tebal, berwarna hijau gelap.
  - Sub-judul (H2/H3): Abu-abu tua, memberi konteks pada halaman.
  - Teks Normal: Abu-abu gelap/hitam agar mudah dibaca.

## 4. Arsitektur Frontend (Single Page Application)

### 4.1 Struktur Navigasi & Routing
- Aplikasi adalah **satu halaman (SPA)** dengan routing sisi-klien (mis. React Router bila memakai React, atau History API + JS murni bila vanilla) — **tidak ada full page reload** saat berpindah tab.
- Navigasi utama (top nav atau sidebar, mengikuti prototipe Stitch AI) memiliki 5 rute yang memetakan langsung ke 5 layar prototipe:

| Rute (path) | Halaman Prototipe | Endpoint API Utama |
|---|---|---|
| `/` atau `/overview` | Dashboard Utama (Overview) | `/api/overview/kpi`, `/api/overview/sentiment-distribution`, `/api/overview/rating-distribution`, `/api/overview/sentiment-trend` |
| `/reviews` | Review Explorer | `/api/reviews` |
| `/topics` | Topic & Keyword Insights | `/api/topics` |
| `/recommendations` | Recommendations Page | `/api/recommendations` |
| `/pipeline` | Data Pipeline Status | `/api/pipeline/status` |

### 4.2 Transisi Halaman & Animasi
- **Transisi antar-rute:** fade + slight slide (mis. 200–300ms ease-out) saat berpindah halaman dalam SPA, agar terasa hidup tanpa mengganggu kecepatan navigasi.
- **Loading state:** setiap komponen yang menunggu response API menampilkan skeleton loader (bentuk placeholder abu-abu muda yang meniru siluet kartu/chart/tabel akhirnya) alih-alih spinner generik, agar transisi terasa mulus dan sesuai prototipe.
- **Efek Hover & Klik:** Elemen interaktif (kartu metrik/KPI, baris tabel, tombol filter, tab sentimen) diberi animasi halus saat hover/klik — `transition`, `transform: translateY(...)`, pseudo-class `:hover`/`:active` — agar antarmuka terasa responsif dan tidak kaku.

### 4.3 Pengambilan Data (Fetching)
- Semua data diambil secara **asinkron (AJAX/`fetch`)** dari backend FastAPI setelah komponen di-mount — tidak ada data yang di-hardcode di frontend.
- **Debounce** pada input pencarian (`search`) di Review Explorer (mis. 300ms) sebelum memanggil `/api/reviews`, agar tidak membanjiri backend dengan request per keystroke.
- Filter (`sentiment`, `rating`, `date range`, `has_text_only`) diserialisasi menjadi query string dan dikirim ke `/api/reviews`; perubahan filter memicu fetch ulang dan memperbarui state komponen tabel + paginasi, tanpa reload halaman.
- Gunakan `AbortController` (atau setara) untuk membatalkan request fetch yang sudah usang saat filter berubah cepat berturut-turut, mencegah race condition pada hasil tabel.

## 5. Tata Letak (Layout) & Komponen per Halaman

### A. Dashboard Utama (Overview) — rute `/overview`

**KPI Cards** — setiap kartu menampilkan satu metrik dari `/api/overview/kpi`:

| KPI Card | Field Response | Sumber Kolom Asli |
|---|---|---|
| Total Ulasan | `total_reviews` | `review_id` (count) |
| Rata-rata Rating | `avg_rating` | `rating` |
| % Sentimen Positif/Netral/Negatif | `sentiment_pct.{positif,netral,negatif}` | `sentiment_label` |
| Ulasan dengan Teks vs. Tanpa Teks | `has_text_pct` | `has_text` |
| Rata-rata Panjang Ulasan | `avg_token_count` | `token_count` (hanya `has_text = True`) |
| Ulasan Terpopuler | `most_liked_review` | `likes` |

- **Visual:** Kotak putih dengan sudut membulat (*rounded corners*) dan bayangan halus (*subtle shadow*), efek terangkat sedikit (`translateY(-2px)`) saat hover.

**Charts** (via library charting JS, mis. Chart.js/Recharts/D3 sesuai pilihan stack React/vanilla):

| Grafik | Bentuk | Endpoint | Field Response |
|---|---|---|---|
| Distribusi Sentimen | Donut Chart (Hijau/Abu/Merah) | `/api/overview/sentiment-distribution` | `[{label, count, pct}]` |
| Distribusi Rating | Bar Chart vertikal 1–5 bintang | `/api/overview/rating-distribution` | `[{rating, count}]` |
| Tren Sentimen Bulanan | Line/Area Chart (*spline/smooth*) | `/api/overview/sentiment-trend` | `[{period, granularity, is_approximate, positif, netral, negatif, total, *_avg_month}]` — **plot field `*_avg_month`, BUKAN `positif`/`netral`/`negatif`/`total` mentah** (lihat catatan di bawah) |
| Tren Volume Ulasan | Bar/Area tipis di bawah tren sentimen | `/api/overview/sentiment-trend` (field `total_avg_month`) | sama seperti di atas |

> **⚠️ Wajib dibaca sebelum implementasi chart tren:** endpoint ini mencampur dua granularitas dalam satu array `data` — titik lama (`granularity: "year"`, `is_approximate: true`) dan titik ~12 bulan terakhir (`granularity: "month"`, `is_approximate: false`). Ini bukan bug, melainkan keterbatasan data nyata (lihat PRD.md §5.1: tanggal ulasan lama ter-*collapse* akibat parsing format relatif Google Maps).
>
> **Instruksi implementasi:**
> 1. **Selalu plot field `positif_avg_month`/`netral_avg_month`/`negatif_avg_month`/`total_avg_month`** sebagai nilai utama di sumbu Y — field ini sudah dinormalisasi (titik tahunan dibagi 12) agar sebanding dengan titik bulanan asli. Jangan plot `total`/`positif` mentah, karena titik tahunan (mis. 739) akan membuat titik bulanan (mis. 17) terlihat seperti "anjlok ke nol" padahal cuma beda satuan waktu.
> 2. **Tandai visual titik dengan `is_approximate: true` secara berbeda** — opsi: gaya garis putus-putus (dashed) untuk segmen lama, solid untuk segmen presisi; atau area shading lebih pudar; atau anotasi kecil "estimasi tahunan" di bagian grafik yang relevan. Jangan render kedua segmen dengan gaya identik tanpa pembeda, karena presisi datanya jauh berbeda.
> 3. Sumbu X memakai label `period` apa adanya (mis. `"2023"`, `"2025-09"`) — campuran format tahun & tahun-bulan ini disengaja dan konsisten dengan poin 1-2 di atas.
> 4. Tooltip/hover sebaiknya menampilkan `total` mentah juga (bukan cuma `avg_month`) sebagai info tambahan, dengan keterangan singkat kalau `is_approximate = true` (mis. "≈ estimasi dari data tahunan").
> 5. **⚠️ Sumbu X WAJIB kategorikal (equal-spacing per label), BUKAN skala tanggal riil/kontinu.** Kalau `period` diperlakukan sebagai objek tanggal asli oleh library chart (mis. `Date`/`Timestamp` di JS), ke-12 titik bulanan presisi (yang secara riil hanya mencakup ~1 tahun) akan terjepit jadi garis kecil bergerigi di ujung kanan grafik, karena chart akan mengalokasikan ruang horizontal proporsional terhadap rentang waktu asli (~12 tahun total) — bukan proporsional terhadap jumlah titik data. **Sudah terverifikasi terjadi** saat implementasi pertama di dashboard Streamlit — perbaikannya adalah memperlakukan `period` sebagai label kategori/string biasa (di Chart.js: `type: 'category'` bukan `type: 'time'`; di D3/Recharts: gunakan scaleBand/kategori, bukan scaleTime), sehingga tiap titik data mendapat lebar horizontal yang sama rata.
> 6. **⚠️ Kalau merender dua segmen (estimasi vs presisi) sebagai dua garis/trace terpisah, WAJIB disambung di titik transisi** — tambahkan titik pertama segmen presisi ke ekor segmen estimasi (sebagai titik penghubung, bukan data ganda yang ditampilkan dobel), supaya tidak ada celah kosong di antara garis putus-putus dan garis solid. Tanpa ini, chart akan terlihat "kosong"/terputus tepat di titik peralihan antara data lama dan data baru. **Sudah terverifikasi terjadi & diperbaiki** di dashboard Streamlit — lihat referensi implementasi di `backend_seed/` (kalau ada) atau minta contoh kode ke tim data science jika diperlukan.

### B. Review Explorer — rute `/reviews`

**Kolom tabel** (data dari `/api/reviews`, field per item hasil JOIN `reviews_clean` + `sentiment_results`):

| Kolom Tampilan | Field Response |
|---|---|
| Reviewer | `author` |
| Rating | `rating` (render ⭐) |
| Cuplikan Ulasan | `review_text_original` (bahasa natural untuk staf non-teknis) |
| Sentimen | `sentiment_label` (badge warna) + indikator kecil jika `sentiment_source = rating_fallback` |
| Tanggal | `review_date` (format `dd MMM yyyy`, di-parse di frontend dari ISO string) |
| Likes | `likes` (ikon 👍) |

**Filter** (dikirim sebagai query params ke `/api/reviews`, lihat PRD.md §10):

| Filter UI | Query Param | Tipe Input |
|---|---|---|
| Pencarian teks | `search` | Text input dengan debounce 300ms |
| Sentimen | `sentiment[]` | Multi-select chip (Positif/Netral/Negatif) |
| Rating | `rating_min`, `rating_max` | Range slider 1–5 |
| Rentang Tanggal | `date_from`, `date_to` | Date range picker |
| Hanya ulasan bertext | `has_text_only` | Toggle switch — default **ON** |
| Urutkan berdasarkan | `sort_by` | Dropdown (Terbaru, Terpopuler, Rating Tertinggi/Terendah) |

- **Paginasi:** kontrol next/prev + nomor halaman berdasarkan `meta.total`, `meta.page`, `meta.page_size` dari response `/api/reviews`. Gunakan infinite scroll ATAU paginasi klasik — pilih salah satu sesuai prototipe Stitch AI, jangan campur keduanya.
- Ulasan dengan `has_text = False` yang tidak difilter keluar ditampilkan dengan cuplikan "*(Tidak ada teks ulasan — hanya rating)*" dan badge dari `rating_fallback`.
- Klik satu baris ulasan dapat membuka detail (modal atau panel slide-in, bukan halaman baru) yang memanggil `/api/reviews/{review_id}` — mempertahankan pengalaman SPA tanpa navigasi keluar dari tabel.

### C. Topic & Keyword Insights — rute `/topics`

- **Tab per sentimen** (Positif/Netral/Negatif) — berpindah tab memicu fetch ulang `/api/topics?sentiment_label=...` tanpa reload.
- Horizontal bar chart top-N kata kunci dari field `keyword` + `score` pada response.
- Tema (jika ada field `theme` terisi) ditampilkan sebagai chip/tag yang dapat diklik di atas chart.
- Klik satu tema/kata kunci memanggil `/api/topics/{theme}/reviews?sentiment_label=...` dan menampilkan daftar cuplikan ulasan representatif — atau, alternatifnya, mengarahkan (via client-side routing, bukan reload) ke `/reviews` dengan filter `sentiment` + `search` sudah terisi otomatis sesuai kata kunci/tema yang diklik, memanfaatkan mekanisme filter yang sama seperti §B.

### D. Recommendations Page — rute `/recommendations`

- Kartu rekomendasi (visual serupa KPI card tapi dengan aksen warna Coral/Negatif) dari `/api/recommendations`, masing-masing berisi field:
  - `theme` — nama tema (mis. "Kebersihan Toilet").
  - `review_count` & `trend` — jumlah ulasan terkait & arah tren (naik/turun) dibanding periode sebelumnya.
  - `sample_reviews` — 1–2 cuplikan `review_text_original` sebagai bukti kualitatif.
- Urutan kartu berdasarkan `review_count` menurun (tema paling banyak dikeluhkan tampil paling atas), kecuali API sudah mengurutkan (`/api/recommendations` bertanggung jawab atas urutan; frontend tinggal render sesuai urutan response).

### E. Data Pipeline Status — rute `/pipeline`

- Halaman admin/demo, menampilkan field dari `/api/pipeline/status`: timestamp scraping terakhir, jumlah ulasan baru sejak run terakhir, `model_version` aktif, dan log ringkas tiap tahap pipeline.
- Auto-refresh berkala (mis. polling tiap 30–60 detik via `setInterval` + fetch) opsional, untuk kebutuhan demo langsung — tidak wajib untuk MVP.

## 6. Interaksi & Animasi (Micro-interactions) — Ringkasan Lintas Halaman

- **Hover & Klik:** kartu KPI/rekomendasi terangkat sedikit (`box-shadow` membesar + `translateY(-2px)`), baris tabel highlight lembut saat hover, tombol filter memberi feedback visual instan saat diklik.
- **Transisi Halaman (SPA):** fade + slide antar-rute, konsisten di seluruh aplikasi (lihat §4.2).
- **Loading state:** skeleton loader per komponen, bukan spinner blocking seluruh halaman — memungkinkan bagian lain halaman tetap interaktif sementara satu chart/tabel masih memuat data dari API.
- **Empty state:** setiap tabel/chart/daftar kartu memiliki tampilan kosong yang ramah (ikon + teks singkat, mis. "Belum ada ulasan yang cocok dengan filter ini") saat response API mengembalikan data kosong — bukan area kosong tanpa penjelasan.

## 7. Prinsip Desain Responsif & Performa

- Layout responsif: desktop-first (mengikuti prototipe Stitch AI), dengan breakpoint tablet/mobile untuk staf yang mengakses dari perangkat genggam di lapangan.
- Chart dan tabel dengan volume data besar (ratusan–ribuan baris) selalu menggunakan **paginasi/virtualisasi** di sisi backend (lihat PRD.md §10, param `page`/`page_size`) — frontend tidak pernah meminta seluruh dataset ulasan sekaligus dalam satu request.
- Hasil fetch untuk data yang jarang berubah dalam satu sesi (mis. `/api/topics`, `/api/pipeline/status`) dapat di-cache sebentar di sisi klien (in-memory state, bukan localStorage) untuk mengurangi request berulang saat pengguna bolak-balik antar tab.
