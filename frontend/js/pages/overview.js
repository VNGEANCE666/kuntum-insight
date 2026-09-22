/* ============================================================
   Overview Page — KPI Cards + Sentimen/Rating/Tren Charts
   (DESIGN §5.A)
   ============================================================ */
import { apiGet } from '../api.js';
import { getCache, setCache } from '../state.js';
import * as skel from '../components/skeleton.js';
import { icon } from '../components/icons.js';
import {
  registerChart, destroyCharts,
  SENTIMENT_COLORS, formatNumber, formatPercent,
  SENTIMENT_LABELS, capitalize, escapeHtml, useSharedTicks,
} from '../components/chart-utils.js';

export const overviewPage = {
  render() {
    return `
      <div class="page-header">
        <div>
          <div class="page-header__subtitle">Kuntum Farmfield · Bogor</div>
          <h1 class="page-header__title">Overview — Ringkasan Sentimen</h1>
        </div>
        <button class="btn btn--primary print-btn" onclick="window.print()" title="Cetak atau simpan sebagai PDF">
          ${icon('printer', 'ki-ico--inline')} Cetak Laporan
        </button>
      </div>
      <div id="ov-kpi">${skel.kpiRow(6)}</div>
      <div class="grid grid--2col" style="margin-top:16px">
        <div class="card card--hover" id="ov-sentimen"><div class="card__title">Distribusi Sentimen</div>${skel.chart()}</div>
        <div class="card card--hover" id="ov-rating"><div class="card__title">Distribusi Rating</div>${skel.chart()}</div>
      </div>
      <div class="card card--hover" id="ov-trend" style="margin-top:16px">
        <div class="card__title card__title--with-note">
          Tren Sentimen Bulanan
          <span class="info-note" tabindex="0" aria-label="Tentang tren sentimen">
            ${icon('info', 'info-note__icon')}
            <span class="info-note__tip">Data sebelum 2024-01 adalah estimasi tahunan (Google Maps tak menyimpan tanggal presisi untuk ulasan lama); titik "≈" di tooltip = estimasi tahunan (garis putus-putus).</span>
          </span>
        </div>
        ${skel.chart()}
      </div>
    `;
  },

  async mount(root) {
    destroyCharts();
    await Promise.all([
      this._loadKpi(),
      this._loadSentimentDistribution(),
      this._loadRatingDistribution(),
      this._loadTrend(),
    ]);
  },

  async _loadKpi() {
    try {
      let data = getCache('/api/overview/kpi');
      if (!data) {
        const res = await apiGet('/api/overview/kpi');
        data = res.data;
        setCache('/api/overview/kpi', data, 60000);
      }
      renderKpi(document.getElementById('ov-kpi'), data);
    } catch (e) {
      renderError(document.getElementById('ov-kpi'), e);
    }
  },

  async _loadSentimentDistribution() {
    const el = document.getElementById('ov-sentimen');
    try {
      const res = await apiGet('/api/overview/sentiment-distribution');
      const items = res.data || [];
      renderSentimentDonut(el, items);
    } catch (e) {
      renderError(el, e);
    }
  },

  async _loadRatingDistribution() {
    const el = document.getElementById('ov-rating');
    try {
      const res = await apiGet('/api/overview/rating-distribution');
      const items = res.data || [];
      renderRatingBar(el, items);
    } catch (e) {
      renderError(el, e);
    }
  },

  async _loadTrend() {
    const el = document.getElementById('ov-trend');
    try {
      const res = await apiGet('/api/overview/sentiment-trend');
      const items = res.data || [];
      const meta = res.meta || {};
      renderTrendChart(el, items, meta);
    } catch (e) {
      renderError(el, e);
    }
  },
};

/* ---------- KPI ---------- */
function renderKpi(el, kpi) {
  const r = kpi.sentiment_pct || {};
  const most = kpi.most_liked_review;

  const kpis = [
    { label: 'Total Ulasan', value: formatNumber(kpi.total_reviews), icon: 'count', sub: 'ulasan terhimpun' },
    { label: 'Rata-rata Rating', value: (kpi.avg_rating || 0).toFixed(2), icon: 'star', sub: 'skala 1–5' },
    { label: 'Sentimen Positif', value: formatPercent(r.positif, 0), icon: 'smile', color: 'var(--color-positive)', sub: 'ulasan memuji' },
    { label: 'Sentimen Netral', value: formatPercent(r.netral, 0), icon: 'meh', color: 'var(--color-neutral)', sub: 'ulasan netral' },
    { label: 'Sentimen Negatif', value: formatPercent(r.negatif, 0), icon: 'frown', color: 'var(--color-negative)', sub: 'ulasan mengeluh' },
    { label: 'Ulasan Berteks', value: formatPercent(kpi.has_text_pct, 0), icon: 'text', sub: 'memiliki teks' },
    { label: 'Panjang Rata-rata', value: formatNumber(Math.round(kpi.avg_token_count)), icon: 'length', sub: 'token per ulasan' },
  ];

  el.innerHTML = `
    <div class="grid grid--kpi">
      ${kpis.map((k) => `
        <div class="card card--hover kpi" title="${escapeHtml(k.label)}">
          <div class="kpi__label">${icon(k.icon, 'kpi__icon')} ${escapeHtml(k.label)}</div>
          <div class="kpi__value" ${k.color ? `style="color:${k.color}"` : ''}>${k.value}</div>
          <div class="kpi__sub">${escapeHtml(k.sub)}</div>
        </div>`).join('')}
    </div>
    ${most ? `
      <div class="card card--hover" style="margin-top:16px">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
          <span class="ov-most__icon">${icon('star', '')}</span>
          <div class="card__title" style="margin:0">Ulasan Terpopuler</div>
        </div>
        <p style="font-size:var(--font-size-small)">${escapeHtml(most.review_text_original || '(Tidak ada teks)')}</p>
        <div style="margin-top:8px;font-size:var(--font-size-small);color:var(--color-text-muted)">
          — ${escapeHtml(most.author || 'Anonim')} · ${most.likes} disukai ${icon('thumbsup', 'ki-ico--inline')}
        </div>
      </div>` : ''}`;
}

/* ---------- Sentiment donut ---------- */
function renderSentimentDonut(el, items) {
  const holder = el.querySelector('.chart-wrap, .skeleton');
  if (holder) holder.remove();

  const wrap = document.createElement('div');
  wrap.className = 'chart-wrap chart-wrap--donut';
  el.appendChild(wrap);
  const canvas = document.createElement('canvas');
  wrap.appendChild(canvas);

  const labels = items.map((i) => capitalize(i.label));
  const data = items.map((i) => i.count);
  const colors = items.map((i) => SENTIMENT_COLORS[i.label] || '#ccc');

  registerChart('ov-sentimen', new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data,
        backgroundColor: colors,
        borderWidth: 3,
        borderColor: '#fff',
        hoverOffset: 6,
      }],
    },
    options: {
      maintainAspectRatio: false,
      cutout: '62%',
      plugins: {
        legend: { position: 'bottom', labels: { usePointStyle: true, padding: 14, boxWidth: 8 } },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const item = items[ctx.dataIndex];
              return ` ${capitalize(item.label)}: ${item.count} (${formatPercent(item.pct)})`;
            },
          },
        },
      },
    },
  }));
}

/* ---------- Rating bar ---------- */
function renderRatingBar(el, items) {
  const holder = el.querySelector('.chart-wrap, .skeleton');
  if (holder) holder.remove();

  const wrap = document.createElement('div');
  wrap.className = 'chart-wrap chart-wrap--bar';
  el.appendChild(wrap);
  const canvas = document.createElement('canvas');
  wrap.appendChild(canvas);

  const labels = items.map((i) => `Rating ${i.rating}`);
  const data = items.map((i) => i.count);
  const colors = data.map((_, idx) => {
    const r = items[idx].rating;
    return r <= 2 ? '#F44336' : r === 3 ? '#FFC107' : '#4CAF50';
  });

  registerChart('ov-rating', new Chart(canvas, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data,
        backgroundColor: colors,
        borderRadius: 6,
        maxBarThickness: 56,
      }],
    },
    options: {
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        y: {
          beginAtZero: true,
          ticks: { precision: 0 },
          grid: { color: 'rgba(0,0,0,0.05)' },
        },
        x: { grid: { display: false } },
      },
    },
  }));
}

/**
 * Tren sentimen — WAJIB patuh 6 aturan DESIGN §5.A:
 *  1. Plot field *_avg_month (bukan total mentah)
 *  2. Pembeda visual is_approximate (dashed vs solid) via segment.borderDash
 *  3. Label period apa adanya (campuran "2023" & "2025-06")
 *  4. Tooltip tampilkan total mentah + catatan estimasi
 *  5. Sumbu X KATEGORIKAL (type:'category') — bukan time/linear
 *  6. (Segmen digabung dalam satu dataset → tidak ada celah transisi.)
 *
 * Layout: small multiples — satu mini-chart per sentimen (Positif/Netral/
 * Negatif) dengan sumbu Y OTOMATIS sesuai data masing-masing, supaya pola
 * Netral & Negatif (volume kecil) tetap terbaca walau Positif jauh lebih
 * besar. Data & logika fetch tidak diubah — murni perubahan layout render.
 */
function renderTrendChart(el, items, meta) {
  const holder = el.querySelector('.chart-wrap, .skeleton');
  if (holder) holder.remove();

  // Aturan 5: sumbu X KATEGORIKAL dengan labels period (sama utk ketiga chart)
  const labels = items.map((d) => d.period);

  // Data point ARRAY NILAI SKALAR (bukan objek {x,y}) + labels terpisah.
  // Objek tanpa properti `x` pada skala category membuat Chart.js tidak bisa
  // memosisikan titik (x:null, skip:true) → garis tidak tergambar sama sekali.
  // Properti pelengkap per-titik (approx/total) dibaca dari `items` via
  // dataIndex di callback segment & tooltip di bawah.
  const series = [
    { key: 'positif', color: SENTIMENT_COLORS.positif, label: 'Positif' },
    { key: 'netral', color: SENTIMENT_COLORS.netral, label: 'Netral' },
    { key: 'negatif', color: SENTIMENT_COLORS.negatif, label: 'Negatif' },
  ];

  const grid = document.createElement('div');
  grid.className = 'trend-grid grid grid--3col';
  el.appendChild(grid);

  series.forEach((s) => {
    const mini = document.createElement('div');
    mini.className = 'trend-mini';

    const title = document.createElement('div');
    title.className = 'trend-mini__title';
    title.style.color = s.color;
    title.textContent = s.label;
    mini.appendChild(title);

    const wrap = document.createElement('div');
    wrap.className = 'chart-wrap';
    mini.appendChild(wrap);

    const canvas = document.createElement('canvas');
    wrap.appendChild(canvas);
    grid.appendChild(mini);

    const dataset = {
      label: s.label,
      borderColor: s.color,
      backgroundColor: s.color,
      pointBackgroundColor: s.color,
      fill: false,
      tension: 0.35, // spline halus (DESIGN: Line/Area spline)
      borderWidth: 2.5,
      pointRadius: 3.5,
      pointHoverRadius: 6,
      // Aturan 2 & 6: satu dataset, styling per-segmen kondisional.
      // p0.dataIndex dipakai untuk tahu is_approximate dari `items`.
      segment: {
        borderDash: (ctx) =>
          ctx.p0.raw != null &&
          items[ctx.p0.dataIndex] &&
          items[ctx.p0.dataIndex].is_approximate
            ? [5, 5]
            : undefined,
      },
      data: items.map((d) => d[s.key + '_avg_month'] ?? 0), // Aturan 1: *_avg_month
    };

    // Aturan 5 eksplisit: type:'category' — bukan mengandalkan auto-detect.
    // Setiap mini-chart punya sumbu Y sendiri (beginAtZero) → skala otomatis
    // sesuai data masing-masing, bukan skala seragam antar kelas.
    registerChart('ov-trend-' + s.key, new Chart(canvas, {
      type: 'line',
      data: { labels, datasets: [dataset] },
      options: {
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          // Judul mini-chart sudah jadi label → legend tidak diperlukan
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: (ctx) => {
                const d = items[ctx[0].dataIndex];
                return d.period + (d.is_approximate ? '  (≈ estimasi tahunan)' : '');
              },
              // Aturan 4: tampilkan total mentah juga sebagai info tambahan
              label: (ctx) => {
                const d = items[ctx.dataIndex];
                const approx = d.is_approximate ? ' ≈' : '';
                return ` ${s.label}: ${ctx.parsed.y} rata/bulan (${d[s.key]}${approx})`;
              },
            },
          },
        },
        scales: {
          x: {
            // Aturan 5 (wajib): sumbu kategorikal, equal-spacing per titik.
            // Keterbacaan di mini-chart sempit: hanya render label2 terpilih
            // (maxTicksLimit + afterBuildTicks deterministik), sama persis di
            // ketiga chart agar tetap sejajar; rotasi 45° utk label panjang
            // (mis. "2025-09") tanpa makan ruang horizontal.
            type: 'category',
            labels,
            grid: { display: false },
            afterBuildTicks: useSharedTicks(6),
            ticks: {
              maxTicksLimit: 6,
              autoSkip: true,
              maxRotation: 45,
              minRotation: 45,
            },
          },
          y: {
            beginAtZero: true,
            grid: { color: 'rgba(0,0,0,0.05)' },
            ticks: { precision: 0 },
          },
        },
      },
    }));
  });
}

/* ---------- Error ---------- */
function renderError(el, err) {
  if (err && err.name === 'AbortError') return;
  const id = el && el.id;
  if (el) {
    el.innerHTML = `
      <div class="empty-state">
        <svg class="empty-state__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 8v4M12 16h.01"/></svg>
        <div class="empty-state__title">Gagal memuat data</div>
        <div class="empty-state__text">${escapeHtml(err && err.message ? err.message : 'Terjadi kesalahan koneksi.')}</div>
      </div>`;
  }
}
