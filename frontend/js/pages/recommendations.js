/* ============================================================
   Recommendations Page — Kartu rekomendasi actionable (DESIGN §5.D)
   ============================================================ */
import { apiGet } from '../api.js';
import * as skel from '../components/skeleton.js';
import { getCache, setCache } from '../state.js';
import { icon } from '../components/icons.js';
import { openPanel, closePanel } from '../components/panel.js';
import { capitalize, escapeHtml, formatDate } from '../components/chart-utils.js';

const THEME_LABELS = {
  akses_lalulintas: 'Akses & Lalu Lintas',
  fasilitas: 'Fasilitas',
  harga: 'Harga',
  makanan_kuliner: 'Makanan & Kuliner',
  pelayanan_staf: 'Pelayanan Staf',
  hewan_satwa: 'Hewan & Satwa',
  anak_keluarga: 'Anak & Keluarga',
};

export const recommendationsPage = {
  render() {
    return `
      <div class="page-header">
        <h1>Rekomendasi Perbaikan</h1>
        <p class="page-header__subtitle">Tema keluhan yang paling sering muncul dari ulasan negatif, diurutkan dari yang terbanyak.</p>
      </div>
      <div id="rec-list">${skel.cards(3)}</div>
    `;
  },

  async mount(root) {
    let data = getCache('/api/recommendations');
    if (!data) {
      try {
        const res = await apiGet('/api/recommendations', { top_n: 6 });
        data = res.data || [];
        setCache('/api/recommendations', data, 120000);
      } catch (e) {
        const el = document.getElementById('rec-list');
        if (el) {
          el.innerHTML = `<div class="empty-state">${icon('alertCircle', 'empty-state__icon')}<div class="empty-state__title">Gagal memuat rekomendasi</div><div class="empty-state__text">${escapeHtml(e.message || 'Error')}</div></div>`;
        }
        return;
      }
    }

    const el = document.getElementById('rec-list');
    if (!data.length) {
      el.innerHTML = `
        <div class="empty-state">
          ${icon('lightbulb', 'empty-state__icon')}
          <div class="empty-state__title">Belum ada rekomendasi</div>
          <div class="empty-state__text">Tidak ada tema keluhan yang terdeteksi saat ini.</div>
        </div>`;
      return;
    }

    el.innerHTML = `
      <div class="grid grid--3col">
        ${data.map((rec, idx) => {
          const label = THEME_LABELS[rec.theme] || capitalize(String(rec.theme).replace(/_/g, ' '));
          return `
            <article class="card rec-card" style="border-top:4px solid var(--color-coral);animation-delay:${idx * 40}ms">
              <div class="rec-card__badge">Keluhan</div>
              <h3 style="margin-bottom:6px">${escapeHtml(label)}</h3>
              <div class="rec-card__meta">
                <span class="rec-card__count">${rec.review_count} ulasan terkait</span>
                <span class="rec-card__trend">${rec.trend ? escapeHtml(rec.trend) : ''}</span>
              </div>
              <div class="rec-card__samples">
                ${(rec.sample_reviews || []).slice(0, 2).map((s) => `
                  <div class="review-quote" style="border-left-color:var(--color-coral)">
                    <p>${escapeHtml(s.text || '(Tidak ada teks)')}</p>
                    ${s.review_date ? `<div class="review-quote__date">${formatDate(s.review_date)}</div>` : ''}
                  </div>`).join('') || '<p class="rec-card__nosample">Tidak ada cuplikan teks.</p>'}
              </div>
              <div class="rec-card__action">
                <button class="btn btn--ghost btn--sm rec-drill-btn" data-theme="${escapeHtml(rec.theme)}" data-count="${rec.review_count}">
                  Lihat semua ${rec.review_count} ulasan ${icon('chevronRight', 'ki-ico--inline')}
                </button>
              </div>
            </article>`;
        }).join('')}
      </div>
      <div class="card" style="margin-top:16px;background:var(--color-coral-soft);border-color:var(--color-coral)">
        <p style="font-size:var(--font-size-small);color:#7B1FA2;display:flex;align-items:flex-start;gap:8px">${icon('lightbulb', 'ki-ico--inline')} <span><strong>Catatan:</strong> Rekomendasi disusun dari agregasi tema ulasan negatif. Setiap kartu menunjukkan jumlah ulasan & contoh bukti untuk bahan tindak lanjut manajemen.</span></p>
      </div>`;

    el.querySelectorAll('.rec-drill-btn').forEach((btn) => {
      btn.addEventListener('click', () => this._openThemePanel(btn.dataset.theme, parseInt(btn.dataset.count, 10) || 0));
    });
  },

  async _openThemePanel(theme, totalCount) {
    const label = THEME_LABELS[theme] || capitalize(String(theme).replace(/_/g, ' '));

    openPanel(`
      <div class="slide-panel__header">
        <div>
          <div style="font-size:var(--font-size-small);color:var(--color-text-muted);margin-bottom:4px">Ulasan negatif — tema</div>
          <strong style="font-size:1.05rem">${escapeHtml(label)}</strong>
        </div>
        <button class="slide-panel__close" id="rec-panel-close" aria-label="Tutup">${icon('close', '', { strokeWidth: 2 })}</button>
      </div>
      <div class="slide-panel__body" id="rec-panel-body">
        ${skel.table(4)}
      </div>
    `);

    const closeBtn = document.getElementById('rec-panel-close');
    if (closeBtn) closeBtn.addEventListener('click', () => closePanel());

    try {
      const res = await apiGet(`/api/topics/${encodeURIComponent(theme)}/reviews`, {
        sentiment_label: 'negatif',
        page_size: 20,
      });
      const reviews = res.data || [];
      const meta = res.meta || {};
      const body = document.getElementById('rec-panel-body');
      if (!body) return;

      if (!reviews.length) {
        body.innerHTML = `<div class="empty-state">${icon('inbox', 'empty-state__icon')}<div class="empty-state__title">Tidak ada ulasan negatif</div></div>`;
        return;
      }

      body.innerHTML = `
        <div style="font-size:var(--font-size-small);color:var(--color-text-muted);margin-bottom:12px">${meta.total || reviews.length} ulasan negatif ditemukan${meta.total > reviews.length ? ` (menampilkan ${reviews.length} dari ${meta.total})` : ''}</div>
        ${reviews.map((r) => `
          <div class="review-quote">
            <p>${escapeHtml(r.review_text_original || '(Tidak ada teks)')}</p>
            <div class="review-quote__meta">
              <span>${escapeHtml(r.author || 'Anonim')} · ${r.rating != null ? Math.round(r.rating) + '/5' : ''}</span>
              <span class="review-quote__date">${formatDate(r.review_date)}</span>
            </div>
          </div>`).join('')}
      `;
    } catch (e) {
      const body = document.getElementById('rec-panel-body');
      if (body) body.innerHTML = `<div class="empty-state">${icon('alertCircle', 'empty-state__icon')}<div class="empty-state__title">Gagal memuat ulasan</div><div class="empty-state__text">${escapeHtml(e.message || 'Error')}</div></div>`;
    }
  },
};
