/* ============================================================
   Topic & Keyword Insights — Tab per sentimen, bar chart,
   theme chips, drill-down ulasan representatif (DESIGN §5.C)
   ============================================================ */
import { apiGet, abortInFlight } from '../api.js';
import * as skel from '../components/skeleton.js';
import { icon } from '../components/icons.js';
import { registerChart, destroyCharts, SENTIMENT_COLORS, capitalize, escapeHtml } from '../components/chart-utils.js';

const DEFAULT_SENTIMENT = 'negatif';

let activeSentiment = DEFAULT_SENTIMENT;
let activeTheme = null;
let activeKeyword = null;

// Nama tema yang diketahui, agar dikelompokkan menjadi chip (dari data tabel
// tema yang sudah terkonfirmasi di HANDOFF.md §8 / topik kustom).
const KNOWN_THEMES = {
  harga: 'Harga',
  fasilitas: 'Fasilitas',
  makanan_kuliner: 'Makanan & Kuliner',
  akses_lalulintas: 'Akses & Lalu Lintas',
  pelayanan_staf: 'Pelayanan Staf',
  hewan_satwa: 'Hewan & Satwa',
  anak_keluarga: 'Anak & Keluarga',
};

export const topicsPage = {
  render() {
    return `
      <div class="page-header">
        <h1>Topic & Keyword Insights</h1>
        <p class="page-header__subtitle">Kata kunci dan tema dominan dari setiap kelas sentimen.</p>
      </div>
      <div class="topic-tabs">
        ${['positif', 'netral', 'negatif'].map((s) => `
          <button class="topic-tab topic-tab--${s}" data-topic="${s}">
            <span class="badge__dot dot--${s}"></span>${capitalize(s)}
          </button>`).join('')}
      </div>
      <div class="topic-body" style="margin-top:16px">
        ${skel.chart()}
      </div>
      <div class="card" id="theme-region" style="margin-top:16px;display:none"></div>
      <div class="card" id="drill-region" style="margin-top:16px;display:none"></div>
    `;
  },

  mount(root) {
    destroyCharts();
    activeSentiment = DEFAULT_SENTIMENT;
    activeTheme = null;
    activeKeyword = null;

    root.querySelectorAll('.topic-tab').forEach((btn) => {
      btn.classList.toggle('is-active', btn.dataset.topic === activeSentiment);
      btn.addEventListener('click', () => {
        activeSentiment = btn.dataset.topic;
        activeTheme = null;
        activeKeyword = null;
        root.querySelectorAll('.topic-tab').forEach((b) => b.classList.toggle('is-active', b === btn));
        this._loadTopics();
      });
    });

    this._loadTopics();
  },

  async _loadTopics() {
    const body = rootRegion();
    body.innerHTML = skel.chart();

    const region = document.getElementById('theme-region');
    const drill = document.getElementById('drill-region');
    if (region) region.style.display = 'none';
    if (drill) drill.style.display = 'none';

    try {
      const res = await apiGet('/api/topics', { sentiment_label: activeSentiment, top_n: 20 });
      const items = res.data || [];

      // Kelompokkan tema yang ada untuk chip
      const themeSet = new Set();
      items.forEach((i) => { if (i.theme) themeSet.add(i.theme); });

      this._renderBarChart(items);
      this._renderThemeChips([...themeSet], activeKeyword);
    } catch (e) {
      if (e.name === 'AbortError') return;
      body.innerHTML = `<div class="empty-state">${icon('alertCircle', 'empty-state__icon')}<div class="empty-state__title">Gagal memuat topik</div><div class="empty-state__text">${escapeHtml(e.message || 'Error')}</div></div>`;
    }
  },

  _renderBarChart(items) {
    const body = rootRegion();
    // hapus skeleton sebelumnya
    body.querySelector('.skeleton')?.remove();
    body.querySelector('.chart-wrap')?.remove();

    const wrap = document.createElement('div');
    wrap.className = 'chart-wrap chart-wrap--bar topic-chart';
    wrap.style.height = Math.max(240, items.length * 26 + 60) + 'px';
    body.appendChild(wrap);
    const canvas = document.createElement('canvas');
    wrap.appendChild(canvas);

    // Horizontal bar → labels di sumbu Y, nilai di sumbu X
    const labels = items.map((i) => i.keyword);
    const data = items.map((i) => i.score);
    const color = SENTIMENT_COLORS[activeSentiment] || '#888';

    registerChart(`topics-${activeSentiment}`, new Chart(canvas, {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          label: `Skor TF-IDF · ${capitalize(activeSentiment)}`,
          data,
          backgroundColor: color,
          borderRadius: 4,
          maxBarThickness: 18,
        }],
      },
      options: {
        indexAxis: 'y',
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { beginAtZero: true, grid: { color: 'rgba(0,0,0,0.05)' } },
          y: { grid: { display: false } },
        },
      },
    }));
  },

  _renderThemeChips(themes, selectedKeyword) {
    const region = document.getElementById('theme-region');
    if (!region) return;

    if (!themes.length) {
      region.style.display = 'none';
      return;
    }
    region.style.display = '';
    region.innerHTML = `
      <div class="card__title" style="font-size:var(--font-size-small);text-transform:uppercase;letter-spacing:0.03em;margin-bottom:10px">Tema Terkait</div>
      <div class="chips">
        ${themes.map((t) => {
          const label = KNOWN_THEMES[t] || capitalize(String(t).replace(/_/g, ' '));
          return `<button class="chip ${t === activeTheme ? 'is-active' : ''}" data-theme="${escapeHtml(t)}">${escapeHtml(label)}</button>`;
        }).join('')}
      </div>`;

    region.querySelectorAll('.chip[data-theme]').forEach((chip) => {
      chip.addEventListener('click', () => {
        const t = chip.dataset.theme;
        // Toggle: klik tema lagi untuk membatalkan / menampilkan semua
        const wasActive = activeTheme === t;
        activeTheme = wasActive ? null : t;
        chip.classList.toggle('is-active', !wasActive);

        if (activeTheme) {
          // Tampilkan ulasan representatif tema ini
          this._loadThemeReviews(t);
        } else {
          hideDrill();
        }
      });
    });
  },

  async _loadThemeReviews(theme) {
    const drill = document.getElementById('drill-region');
    if (!drill) return;
    drill.style.display = '';
    drill.innerHTML = `<div class="card__title" style="margin-bottom:12px">Ulasan tentang <strong>${escapeHtml((KNOWN_THEMES[theme] || theme).toLowerCase())}</strong> · sentimen ${capitalize(activeSentiment)}</div>${skel.table(4)}`;

    try {
      const res = await apiGet(`/api/topics/${encodeURIComponent(theme)}/reviews`, {
        sentiment_label: activeSentiment,
        page_size: 8,
      });
      const reviews = res.data || [];
      if (!reviews.length) {
        drill.innerHTML = `<div class="empty-state">${icon('inbox', 'empty-state__icon')}<div class="empty-state__title">Tidak ada ulasan untuk tema ini</div></div>`;
        return;
      }
      drill.innerHTML = `
        <div class="card__title" style="margin-bottom:12px">Ulasan tentang <strong>${escapeHtml((KNOWN_THEMES[theme] || theme).toLowerCase())}</strong> · sentimen ${capitalize(activeSentiment)}</div>
        ${reviews.map((r) => `
          <div class="review-quote">
            <p>${escapeHtml(r.review_text_original || '(Tidak ada teks)')}</p>
            <div style="margin-top:6px;font-size:var(--font-size-small);color:var(--color-text-muted)">— ${escapeHtml(r.author || 'Anonim')} (rating ${r.rating}/5)</div>
          </div>`).join('')}`;
    } catch (e) {
      if (e.name === 'AbortError') return;
      drill.innerHTML = `<div class="empty-state">${icon('alertCircle', 'empty-state__icon')}<div class="empty-state__title">Gagal memuat ulasan tema</div></div>`;
    }
  },
};

function rootRegion() {
  return document.querySelector('.topic-body');
}

function hideDrill() {
  const drill = document.getElementById('drill-region');
  if (drill) { drill.style.display = 'none'; drill.innerHTML = ''; }
}
