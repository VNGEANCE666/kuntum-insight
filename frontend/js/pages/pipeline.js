/* ============================================================
   Pipeline Status — Status teknis pipeline (DESIGN §5.E, admin/demo)
   ============================================================ */
import { apiGet } from '../api.js';
import * as skel from '../components/skeleton.js';
import { getCache, setCache } from '../state.js';
import { icon } from '../components/icons.js';
import { formatNumber, formatPercent, formatDateTime, escapeHtml } from '../components/chart-utils.js';

export const pipelinePage = {
  render() {
    return `
      <div class="page-header">
        <h1>Status Pipeline Data</h1>
        <p class="page-header__subtitle">Ringkasan teknis proses data & model untuk demo/admin.</p>
      </div>
      <div id="pipe-status">${skel.cards(3)}</div>
    `;
  },

  async mount(root) {
    let data = getCache('/api/pipeline/status');
    if (!data) {
      try {
        const res = await apiGet('/api/pipeline/status');
        data = res.data;
        setCache('/api/pipeline/status', data, 60000);
      } catch (e) {
        const el = document.getElementById('pipe-status');
        if (el) {
          el.innerHTML = `<div class="empty-state">${icon('alertCircle', 'empty-state__icon')}<div class="empty-state__title">Gagal memuat status pipeline</div><div class="empty-state__text">${escapeHtml(e.message || 'Error')}</div></div>`;
        }
        return;
      }
    }

    const el = document.getElementById('pipe-status');

    el.innerHTML = `
      <div class="grid grid--3col">
        <div class="card pipe-card">
          <div class="pipe-card__key">Versi Model</div>
          <div class="pipe-card__value">${escapeHtml(data.model_version || '–')}</div>
          <div class="pipe-card__hint">artefak yang dimuat saat startup</div>
        </div>
        <div class="card pipe-card">
          <div class="pipe-card__key">Algoritma</div>
          <div class="pipe-card__value pipe-card__value--sm">${escapeHtml(data.algorithm || '–')}</div>
          <div class="pipe-card__hint">class-weight balanced</div>
        </div>
        <div class="card pipe-card">
          <div class="pipe-card__key">Total Ulasan di DB</div>
          <div class="pipe-card__value">${formatNumber(data.total_reviews_in_db)}</div>
          <div class="pipe-card__hint">reviews_clean + sentiment_results</div>
        </div>
        <div class="card pipe-card">
          <div class="pipe-card__key">Macro F1-score</div>
          <div class="pipe-card__value">${data.macro_f1 != null ? (data.macro_f1 * 100).toFixed(1) + '%' : '–'}</div>
          <div class="pipe-card__hint">dari evaluasi model</div>
        </div>
        <div class="card pipe-card">
          <div class="pipe-card__key">Akurasi</div>
          <div class="pipe-card__value">${data.accuracy != null ? (data.accuracy * 100).toFixed(1) + '%' : '–'}</div>
          <div class="pipe-card__hint">akurasi keseluruhan</div>
        </div>
        <div class="card pipe-card">
          <div class="pipe-card__key">Dilatih pada</div>
          <div class="pipe-card__value pipe-card__value--sm">${formatDateTime(data.trained_at)}</div>
          <div class="pipe-card__hint">timestamp training model</div>
        </div>
      </div>

      <div class="card" style="margin-top:16px">
        <div class="card__title">Ringkasan Pipeline</div>
        <div class="pipeline-steps">
          ${pipelineStep(true, 'Data Collection', 'Playwright scraper', 'Selesai')}
          ${pipelineStep(true, 'Data Cleaning', 'case folding · stemming · stopword', 'Selesai')}
          ${pipelineStep(true, 'Labeling & Training', 'weak supervision → model v1', 'Selesai')}
          ${pipelineStep(true, 'Inference Batch', 'label tersimpan di sentiment_results', 'Selesai')}
          ${pipelineStep(true, 'Serving API', 'FastAPI · data in-memory', 'Aktif')}
        </div>
      </div>`;
  },
};

function pipelineStep(done, title, desc, status) {
  return `
    <div class="pipeline-step">
      <div class="pipeline-step__mark ${done ? 'is-done' : ''}">${done ? icon('check', '', { strokeWidth: 2.4 }) : icon('circle', '', { strokeWidth: 2 })}</div>
      <div class="pipeline-step__body">
        <div class="pipeline-step__title">${escapeHtml(title)}</div>
        <div class="pipeline-step__desc">${escapeHtml(desc)}</div>
      </div>
      <span class="pipeline-step__status">${escapeHtml(status)}</span>
    </div>`;
}
