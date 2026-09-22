/* ============================================================
   Review Explorer — Tabel ulasan + filter + pagination + detail
   (DESIGN §5.B)
   ============================================================ */
import { apiGet, createController, abortInFlight } from '../api.js';
import * as skel from '../components/skeleton.js';
import { renderPagination } from '../components/pagination.js';
import { openPanel } from '../components/panel.js';
import { icon } from '../components/icons.js';
import {
  renderStars, sentimentBadge, formatDate, escapeHtml, capitalize,
  SENTIMENT_LABELS,
} from '../components/chart-utils.js';

const PAGE_SIZE = 20;

let state = {
  search: '',
  sentiments: [],
  ratingMin: 1,
  ratingMax: 5,
  dateFrom: '',
  dateTo: '',
  hasTextOnly: true,
  sortBy: 'terbaru',
  page: 1,
  total: 0,
  loading: false,
  data: [],
};

/** Escape nilai untuk CSV standar (RFC 4180): bungkus kutip jika mengandung
 *  koma, kutip ganda, atau baris baru; escape kutip ganda → dua kutip ganda. */
function csvEscape(val) {
  if (val == null) return '';
  const s = String(val).replace(/\r?\n/g, ' ');
  if (s.includes(',') || s.includes('"') || s.includes('\n')) {
    return '"' + s.replace(/"/g, '""') + '"';
  }
  return s;
}

let debounceTimer = null;
let searchInput = null;

export const reviewsPage = {
  render() {
    return `
      <div class="page-header">
        <h1>Review Explorer</h1>
        <p class="page-header__subtitle">Jelajahi dan saring ulasan pengunjung Kuntum Farmfield.</p>
      </div>
      <div class="card filter-card">
        <div class="filter-bar">
          <div class="filter-bar__search">
            ${icon('search', '')}
            <input type="text" id="re-search" class="input" placeholder="Cari kata kunci dalam ulasan…" autocomplete="off" />
          </div>
          <div class="filter-bar__controls">
            <select id="re-sort" class="select">
              <option value="terbaru">Terbaru</option>
              <option value="terpopuler">Terpopuler</option>
              <option value="rating_tertinggi">Rating Tertinggi</option>
              <option value="rating_terendah">Rating Terendah</option>
            </select>
            <label class="toggle">
              <input type="checkbox" id="re-hastext" checked />
              <span class="toggle__track"></span>
              Hanya berteks
            </label>
          </div>
        </div>
        <div class="filter-bar filter-bar--lower">
          <div class="chips" id="re-sentiment-chips">
            ${['positif', 'netral', 'negatif'].map((s) => `
              <button class="chip chip--${s}" data-sentiment="${s}">
                <span class="badge__dot dot--${s}"></span>${SENTIMENT_LABELS[s]}
              </button>`).join('')}
          </div>
          <div class="filter-bar__rating">
            <span class="filter-label">Rating:</span>
            <input type="range" id="re-rating-min" min="1" max="5" step="1" value="1" />
            <span id="re-rating-min-val">1</span>–<span id="re-rating-max-val">5</span>
            <input type="range" id="re-rating-max" min="1" max="5" step="1" value="5" />
          </div>
          <div class="filter-bar__dates">
            <input type="date" id="re-date-from" class="input" />
            <span>—</span>
            <input type="date" id="re-date-to" class="input" />
          </div>
          <button class="btn btn--ghost btn--sm" id="re-reset">Reset</button>
          <button class="btn btn--ghost btn--sm" id="re-csv" title="Unduh hasil filter saat ini sebagai CSV">${icon('download', 'ki-ico--inline')} Unduh CSV</button>
        </div>
      </div>
      <div class="card table-card" style="margin-top:16px">
        <div id="re-table-wrap">${skel.table(10)}</div>
      </div>
    `;
  },

  mount(root) {
    this._bindEvents(root);

    // Filter-fill awal (bisa di-set dari rute topic drill-down)
    this._applyInitialFromRoute();
    this._fetch();
  },

  _bindEvents(root) {
    searchInput = root.querySelector('#re-search');
    searchInput.addEventListener('input', () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        state.search = searchInput.value.trim();
        state.page = 1;
        this._fetch();
      }, 300); // Debounce 300ms (DESIGN §4.3)
    });

    root.querySelector('#re-sort').addEventListener('change', (e) => {
      state.sortBy = e.target.value;
      state.page = 1;
      this._fetch();
    });

    root.querySelector('#re-hastext').addEventListener('change', (e) => {
      state.hasTextOnly = e.target.checked;
      state.page = 1;
      this._fetch();
    });

    root.querySelectorAll('#re-sentiment-chips .chip').forEach((chip) => {
      chip.addEventListener('click', () => {
        const s = chip.dataset.sentiment;
        const idx = state.sentiments.indexOf(s);
        if (idx === -1) state.sentiments.push(s);
        else state.sentiments.splice(idx, 1);
        chip.classList.toggle('is-active', state.sentiments.includes(s));
        state.page = 1;
        this._fetch();
      });
    });

    const minEl = root.querySelector('#re-rating-min');
    const maxEl = root.querySelector('#re-rating-max');
    const minVal = root.querySelector('#re-rating-min-val');
    const maxVal = root.querySelector('#re-rating-max-val');

    minEl.addEventListener('input', () => {
      let v = parseInt(minEl.value, 10);
      if (v > state.ratingMax) v = state.ratingMax;
      minEl.value = v;
      minVal.textContent = v;
      state.ratingMin = v;
      state.page = 1;
      this._fetch();
    });
    maxEl.addEventListener('input', () => {
      let v = parseInt(maxEl.value, 10);
      if (v < state.ratingMin) v = state.ratingMin;
      maxEl.value = v;
      maxVal.textContent = v;
      state.ratingMax = v;
      state.page = 1;
      this._fetch();
    });

    root.querySelector('#re-date-from').addEventListener('change', (e) => {
      state.dateFrom = e.target.value || '';
      state.page = 1;
      this._fetch();
    });
    root.querySelector('#re-date-to').addEventListener('change', (e) => {
      state.dateTo = e.target.value || '';
      state.page = 1;
      this._fetch();
    });

    root.querySelector('#re-reset').addEventListener('click', () => {
      state = { ...state, search: '', sentiments: [], ratingMin: 1, ratingMax: 5, dateFrom: '', dateTo: '', sortBy: 'terbaru', page: 1, hasTextOnly: true };
      searchInput.value = '';
      root.querySelector('#re-sort').value = 'terbaru';
      root.querySelector('#re-hastext').checked = true;
      root.querySelector('#re-date-from').value = '';
      root.querySelector('#re-date-to').value = '';
      minEl.value = '1'; maxEl.value = '5';
      minVal.textContent = '1'; maxVal.textContent = '5';
      root.querySelectorAll('#re-sentiment-chips .chip').forEach((c) => c.classList.remove('is-active'));
      this._fetch();
    });

    root.querySelector('#re-csv').addEventListener('click', () => this._downloadCSV());
  },

  _applyInitialFromRoute() {
    // Placeholder: bisa diisi dari route query bila future drill-down
    // dari Topics perlu prefill. Saat ini tidak ada prefill khusus.
  },

  _downloadCSV() {
    const rows = state.data;
    if (!rows || !rows.length) return;

    const header = ['Reviewer', 'Rating', 'Cuplikan Ulasan', 'Sentimen', 'Sumber Sentimen', 'Tanggal', 'Likes'];
    const lines = [header.map(csvEscape).join(',')];

    for (const r of rows) {
      const sentimentSource = r.sentiment_source === 'rating_fallback' ? 'Dari Rating' : 'Model';
      lines.push([
        csvEscape(r.author),
        r.rating != null ? Math.round(r.rating) : '',
        csvEscape(r.review_text_original),
        csvEscape(capitalize(r.sentiment_label || 'netral')),
        csvEscape(sentimentSource),
        csvEscape(formatDate(r.review_date)),
        r.likes != null ? r.likes : 0,
      ].join(','));
    }

    const today = new Date().toISOString().slice(0, 10);
    const filename = `kuntum-insight-ulasan-${today}.csv`;

    const bom = '\uFEFF';
    const blob = new Blob([bom + lines.join('\n')], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  },

  async _fetch() {
    // Batalkan request usang sebelum fetch baru (DESIGN §4.3)
    abortInFlight();
    const controller = createController();
    state.loading = true;
    this._showLoading();

    const params = {
      search: state.search || undefined,
      'sentiment[]': state.sentiments.length ? state.sentiments : undefined,
      rating_min: state.ratingMin,
      rating_max: state.ratingMax,
      date_from: state.dateFrom ? state.dateFrom + 'T00:00:00Z' : undefined,
      date_to: state.dateTo ? state.dateTo + 'T23:59:59Z' : undefined,
      has_text_only: state.hasTextOnly,
      sort_by: state.sortBy,
      page: state.page,
      page_size: PAGE_SIZE,
    };

    try {
      const res = await apiGet('/api/reviews', params, { signal: controller.signal });
      state.total = res.meta.total;
      state.data = res.data || [];
      this._renderTable(state.data, res.meta);
      this._renderPagination(res.meta);
    } catch (e) {
      if (e.name === 'AbortError') return;
      this._renderError(e);
    } finally {
      state.loading = false;
    }
  },

  _showLoading() {
    const wrap = document.getElementById('re-table-wrap');
    if (wrap) wrap.innerHTML = skel.table(10);
  },

  _renderTable(data, meta) {
    const wrap = document.getElementById('re-table-wrap');
    if (!wrap) return;

    if (!data.length) {
      wrap.innerHTML = `
        <div class="empty-state">
          ${icon('inbox', 'empty-state__icon')}
          <div class="empty-state__title">Belum ada ulasan yang cocok</div>
          <div class="empty-state__text">Coba ubah kata kunci atau filter Anda untuk melihat hasil lain.</div>
        </div>`;
      return;
    }

    const rows = data
      .map((r) => {
        const text = r.has_text ? r.review_text_original : '(Tidak ada teks ulasan — hanya rating)';
        const snippet = truncate(text, 120);
        return `
          <tr class="review-row" data-id="${escapeHtml(r.review_id)}">
            <td class="col-author"><strong>${escapeHtml(r.author || 'Anonim')}</strong></td>
            <td>${renderStars(r.rating)}</td>
            <td class="col-text">${escapeHtml(snippet)}</td>
            <td>${sentimentBadge(r.sentiment_label, r.sentiment_source)}</td>
            <td class="col-date">${formatDate(r.review_date)}</td>
            <td class="col-likes">${icon('thumbsup', 'ki-ico--inline')} ${r.likes != null ? r.likes : 0}</td>
            <td class="col-cta"><button class="btn btn--ghost btn--sm" data-detail="${escapeHtml(r.review_id)}">Detail</button></td>
          </tr>`;
      })
      .join('');

    wrap.innerHTML = `
      <div class="table-scroll">
        <table class="reviews-table">
          <thead>
            <tr>
              <th>Reviewer</th>
              <th>Rating</th>
              <th>Cuplikan Ulasan</th>
              <th>Sentimen</th>
              <th>Tanggal</th>
              <th>Likes</th>
              <th></th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;

    // Bind klik baris & tombol detail
    wrap.querySelectorAll('[data-detail]').forEach((btn) => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        this._openDetail(btn.dataset.detail);
      });
    });
    wrap.querySelectorAll('.review-row').forEach((row) => {
      row.addEventListener('click', () => this._openDetail(row.dataset.id));
    });
  },

  _renderPagination(meta) {
    const card = document.querySelector('.table-card');
    if (!card) return;
    let existing = card.querySelector('.pagination');
    if (existing) existing.remove();

    const holder = document.createElement('div');
    holder.innerHTML = renderPagination(meta, (page) => {
      state.page = page;
      this._fetch();
    }, 'ulasan');
    card.appendChild(holder.firstChild);
  },

  _renderError(e) {
    const wrap = document.getElementById('re-table-wrap');
    if (!wrap) return;
    wrap.innerHTML = `
      <div class="empty-state">
        ${icon('alertCircle', 'empty-state__icon')}
        <div class="empty-state__title">Gagal memuat ulasan</div>
        <div class="empty-state__text">${escapeHtml(e.message || 'Terjadi kesalahan koneksi.')}</div>
      </div>`;
  },

  async _openDetail(reviewId) {
    openPanel(`
      <div style="position:sticky;top:0;background:#fff;padding:0 0 12px;display:flex;justify-content:space-between;align-items:center;flex-direction:column">
        <div class="skeleton skeleton--title" style="width:100%"></div>
      </div>
      <div class="skeleton skeleton--text"></div>
      <div class="skeleton skeleton--text" style="width:80%"></div>
    `);

    try {
      const res = await apiGet(`/api/reviews/${encodeURIComponent(reviewId)}`);
      const r = res.data;
      const panel = document.getElementById('slidePanel');
      if (!panel) return;
      panel.innerHTML = `
        <div class="slide-panel__header">
          <div>
            <div style="font-size:var(--font-size-small);color:var(--color-text-muted);margin-bottom:4px">Detail Ulasan</div>
            <strong style="font-size:1.05rem">${escapeHtml(r.author || 'Anonim')}</strong>
            <div style="margin-top:6px;display:flex;align-items:center;gap:10px;flex-wrap:wrap">
              ${renderStars(r.rating)}
              ${sentimentBadge(r.sentiment_label, r.sentiment_source)}
            </div>
          </div>
<button class="slide-panel__close" id="detail-close" aria-label="Tutup">
            ${icon('close', '', { strokeWidth: 2 })}
          </button>
        </div>
        <div class="slide-panel__body">
          ${detailRow('Tanggal', formatDate(r.review_date))}
          ${detailRow('Rating', `${r.rating} bintang (${r.likes} disukai)`)}

          <div class="detail-block">
            <div class="detail-block__label">Ulasan</div>
            <p class="detail-block__value">${escapeHtml(r.review_text_original || '(Tidak ada teks ulasan — hanya rating)')}</p>
          </div>

          <div class="detail-block">
            <div class="detail-block__label">Teks bersih (untuk model)</div>
            <p class="detail-block__value">${escapeHtml(r.review_text_clean || '–')}</p>
          </div>

          <div class="detail-block">
            <div class="detail-block__label">Kata kunci</div>
            <div class="chips" style="margin-top:6px">
              ${(r.top_keywords || []).slice(0, 12).map((k) => `<span class="theme-tag">${escapeHtml(k)}</span>`).join('') || '<span style="font-size:var(--font-size-small);color:var(--color-text-light)">Tidak ada</span>'}
            </div>
          </div>

          <div class="detail-block" style="border-top:1px solid var(--color-border);padding-top:12px;margin-top:12px">
            ${detailRow('Sumber sentimen', r.sentiment_source === 'model' ? 'Model (analisis teks)' : 'Rating (tanpa teks)')}
            ${detailRow('Bobot sentimen', r.sentiment_confidence != null ? (r.sentiment_confidence * 100).toFixed(1) + '%' : '–')}
            ${detailRow('Versi model', r.model_version || '–')}
          </div>
        </div>`;

      const closeBtn = panel.querySelector('#detail-close');
      if (closeBtn) closeBtn.addEventListener('click', () => { panel.classList.remove('is-open'); });
    } catch (e) {
      const panel = document.getElementById('slidePanel');
      if (panel) {
        panel.innerHTML = `<div class="slide-panel__body"><div class="empty-state">${icon('alertCircle', 'empty-state__icon')}<div class="empty-state__title">Gagal memuat detail</div><div class="empty-state__text">${escapeHtml(e.message || 'Error')}</div></div></div>`;
      }
    }
  },
};

function detailRow(label, value) {
  return `
    <div style="display:flex;justify-content:space-between;gap:12px;padding:6px 0">
      <span style="color:var(--color-text-muted);font-size:var(--font-size-small)">${escapeHtml(label)}</span>
      <span style="font-weight:500;text-align:right;font-size:var(--font-size-small)">${escapeHtml(String(value))}</span>
    </div>`;
}

function truncate(str, len) {
  if (!str) return '';
  return str.length > len ? str.slice(0, len).trimEnd() + '…' : str;
}
