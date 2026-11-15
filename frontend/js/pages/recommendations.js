/* ============================================================
   Recommendations Page — Kesimpulan + Saran + Bukti (DESIGN §5.D)
   Setiap kartu: kesimpulan otomatis dari data, saran perbaikan,
   lalu topik & cuplikan ulasan asli sebagai bukti.
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
  tiket_masuk: 'Tiket / Biaya Masuk',
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
        <p class="page-header__subtitle">Kesimpulan tiap tema keluhan, saran perbaikan, dan bukti ulasan pendukung.</p>
      </div>
      <div id="rec-summary"></div>
      <div id="rec-list">${skel.cards(3)}</div>
    `;
  },

  async mount(root) {
    let payload = getCache('/api/recommendations');
    if (!payload) {
      try {
        const res = await apiGet('/api/recommendations', { top_n: 8 });
        payload = { items: res.data || [], meta: res.meta || {} };
        setCache('/api/recommendations', payload, 120000);
      } catch (e) {
        const el = document.getElementById('rec-list');
        if (el) {
          el.innerHTML = `<div class="empty-state">${icon('alertCircle', 'empty-state__icon')}<div class="empty-state__title">Gagal memuat rekomendasi</div><div class="empty-state__text">${escapeHtml(e.message || 'Error')}</div></div>`;
        }
        return;
      }
    }

    const items = payload.items || [];
    const meta = payload.meta || {};
    const summaryEl = document.getElementById('rec-summary');
    const el = document.getElementById('rec-list');

    if (!items.length) {
      if (summaryEl) summaryEl.innerHTML = '';
      el.innerHTML = `
        <div class="empty-state">
          ${icon('lightbulb', 'empty-state__icon')}
          <div class="empty-state__title">Belum ada rekomendasi</div>
          <div class="empty-state__text">Tidak ada tema keluhan yang terdeteksi saat ini.</div>
        </div>`;
      return;
    }

    if (summaryEl && meta.summary) {
      summaryEl.innerHTML = `
        <div class="card rec-summary">
          <div class="rec-summary__icon">${icon('lightbulb')}</div>
          <div>
            <div class="rec-summary__title">Ringkasan</div>
            <p class="rec-summary__text">${escapeHtml(meta.summary)}</p>
          </div>
        </div>`;
    }

    el.innerHTML = `
      <div class="grid grid--2col">
        ${items.map((rec, idx) => this._renderCard(rec, meta, idx)).join('')}
      </div>
      <div class="card rec-note">
        ${icon('info', 'rec-note__icon')}
        <span><strong>Catatan metode:</strong> ${escapeHtml(meta.methodology || 'Jumlah ulasan dan bukti dihitung dari himpunan ulasan yang sama.')} Kesimpulan disusun otomatis dari data (bukan karangan); klik "Lihat semua" untuk menelusuri seluruh ulasan negatif tema terkait.</span>
      </div>`;

    el.querySelectorAll('.rec-drill-btn').forEach((btn) => {
      btn.addEventListener('click', () => this._openThemePanel(btn.dataset.theme, parseInt(btn.dataset.count, 10) || 0));
    });
  },

  _renderCard(rec, meta, idx) {
    const label = rec.label || THEME_LABELS[rec.theme] || capitalize(String(rec.theme).replace(/_/g, ' '));
    const priority = rec.priority || '';
    const priorityClass = priority ? `rec-priority--${priority.toLowerCase()}` : '';
    const totalNegative = meta.negative_total;
    const share = rec.share_pct != null ? rec.share_pct : null;

    const strength = rec.evidence_strength || '';
    const strengthLabel = { kuat: 'Bukti kuat', sedang: 'Bukti sedang', terbatas: 'Bukti terbatas' }[strength] || '';
    const strengthClass = strength ? `rec-evidence-badge--${strength}` : '';

    const keywords = (rec.keywords || []).map((k) => {
      const count = k.count != null ? `<span class="rec-keyword__count">${k.count}</span>` : '';
      return `<span class="rec-keyword" title="${k.count != null ? `${k.count} ulasan menyebut istilah ini` : ''}">${escapeHtml(k.keyword)}${count}</span>`;
    }).join('');

    const samples = (rec.sample_reviews || []).map((s) => {
      const matched = (s.matched_terms || []).map((t) => escapeHtml(t)).join(', ');
      return `
      <div class="review-quote" style="border-left-color:var(--color-coral)">
        <p>${escapeHtml(s.text || '(Tidak ada teks)')}</p>
        <div class="review-quote__meta">
          <span>${s.rating != null ? Math.round(s.rating) + '/5' : ''}${s.author ? ` · ${escapeHtml(s.author)}` : ''}</span>
          ${s.review_date ? `<span class="review-quote__date">${formatDate(s.review_date)}</span>` : ''}
        </div>
        ${matched ? `<div class="rec-match">Cocok: ${matched}</div>` : ''}
      </div>`;
    }).join('');

    return `
      <article class="card rec-card" style="border-top:4px solid var(--color-coral);animation-delay:${idx * 40}ms">
        <div class="rec-card__head">
          <span class="rec-card__badge">Keluhan</span>
          ${priority ? `<span class="rec-priority ${priorityClass}">Prioritas ${escapeHtml(priority)}</span>` : ''}
        </div>
        <h3 class="rec-card__title">${escapeHtml(label)}</h3>
        <div class="rec-card__meta">
          <span class="rec-card__count">${rec.review_count} ulasan menyebut tema ini</span>
          ${share != null && totalNegative ? `<span class="rec-card__share">${share}% dari ${totalNegative} ulasan negatif</span>` : ''}
        </div>

        <div class="rec-insight">
          <div class="rec-block__label">${icon('info', 'rec-block__icon')} Kesimpulan</div>
          <p class="rec-block__text">${escapeHtml(rec.insight || '—')}</p>
        </div>

        <div class="rec-action">
          <div class="rec-block__label">${icon('lightbulb', 'rec-block__icon')} Saran Perbaikan</div>
          <p class="rec-block__text">${escapeHtml(rec.action || '—')}</p>
        </div>

        <div class="rec-evidence">
          <div class="rec-block__label">Bukti — topik terkait</div>
          <div class="rec-keywords">${keywords || '<span class="rec-card__nosample">—</span>'}</div>

          <div class="rec-block__label rec-block__label--row">
            <span>Bukti — cuplikan ulasan</span>
            ${strengthLabel ? `<span class="rec-evidence-badge ${strengthClass}">${strengthLabel}</span>` : ''}
          </div>
          <div class="rec-card__samples">
            ${samples || '<p class="rec-card__nosample">Tidak ada cuplikan teks.</p>'}
          </div>
        </div>

        <div class="rec-card__action">
          <button class="btn btn--ghost btn--sm rec-drill-btn" data-theme="${escapeHtml(rec.theme)}" data-count="${rec.review_count}">
            Lihat semua ${rec.review_count} ulasan ${icon('chevronRight', 'ki-ico--inline')}
          </button>
        </div>
      </article>`;
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
