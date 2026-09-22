/* ============================================================
   App Entry — init layout, router, daftarkan semua halaman
   ============================================================ */
import { renderLayout } from './components/layout.js';
import { register, initRouter } from './router.js';
import * as skeleton from './components/skeleton.js';
import { overviewPage } from './pages/overview.js';
import { reviewsPage } from './pages/reviews.js';
import { topicsPage } from './pages/topics.js';
import { recommendationsPage } from './pages/recommendations.js';
import { pipelinePage } from './pages/pipeline.js';

// Ekspos skeleton global agar tersedia di halaman.
window.skeleton = skeleton;

const contentEl = renderLayout();

const PAGE_TITLES = {
  '/overview': 'Overview — Kuntum Insight',
  '/reviews': 'Review Explorer',
  '/topics': 'Topic & Keyword Insights',
  '/recommendations': 'Rekomendasi',
  '/pipeline': 'Status Pipeline',
};

function setTopbar(path) {
  const el = document.getElementById('topbarTitle');
  if (el) el.textContent = PAGE_TITLES[path] || 'Kuntum Insight';
}

// Daftarkan route + lifecycle mount. renderFn mengembalikan HTML string
// (skeleton awal); mountFn mem-fetch data & mengganti konten.
register('/overview', () => overviewPage.render(), (root) => overviewPage.mount(root));
register('/reviews', () => reviewsPage.render(), (root) => reviewsPage.mount(root));
register('/topics', () => topicsPage.render(), (root) => topicsPage.mount(root));
register('/recommendations', () => recommendationsPage.render(), (root) => recommendationsPage.mount(root));
register('/pipeline', () => pipelinePage.render(), (root) => pipelinePage.mount(root));

window.addEventListener('route-changed', (e) => setTopbar(e.detail.path));

initRouter(contentEl);
