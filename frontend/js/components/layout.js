/* ============================================================
   Layout Component — Sidebar Navigation + Topbar + Content
   (DESIGN §4.1)
   ============================================================ */

import { icon } from './icons.js';

const NAV_ITEMS = [
  { path: '/overview', label: 'Overview', icon: 'dashboard' },
  { path: '/reviews', label: 'Review Explorer', icon: 'reviews' },
  { path: '/topics', label: 'Topic Insights', icon: 'tag' },
  { path: '/recommendations', label: 'Rekomendasi', icon: 'lightbulb' },
  { path: '/pipeline', label: 'Status Pipeline', icon: 'activity' },
];

/**
 * Render layout penuh (sidebar + topbar + content) ke #app.
 * @returns {HTMLElement} elemen .main__content
 */
export function renderLayout() {
  const html = `
    <div class="layout">
      <aside class="sidebar" id="sidebar">
        <div class="sidebar__brand">
          <img class="sidebar__brand-icon" src="/logo.jpg" alt="Kuntum" />
          <div class="sidebar__brand-text">
            <div class="sidebar__brand-title">Kuntum Insight</div>
            <div class="sidebar__brand-sub">Analisis Sentimen</div>
          </div>
        </div>
        <nav class="sidebar__nav" aria-label="Navigasi utama">
          ${NAV_ITEMS.map((item) => `
            <a class="sidebar__link" href="#${item.path}" data-nav="${item.path}">
              ${icon(item.icon, 'sidebar__icon')}
              <span class="sidebar__link-label">${item.label}</span>
            </a>`).join('')}
        </nav>
        <button class="sidebar__collapse-btn" id="collapseBtn" title="Perkecil menu" aria-label="Perkecil atau perbesar menu">
          ${icon('chevronRight', '', { strokeWidth: 2 })}
        </button>
      </aside>
      <div class="main">
        <div class="main__topbar">
          <button class="main__menu-btn" id="menuBtn" aria-label="Buka menu">
            ${icon('menu', '', { size: 18, strokeWidth: 2 })}
          </button>
          <div class="main__topbar-title" id="topbarTitle"></div>
        </div>
        <div class="main__content"></div>
      </div>
    </div>`;
  const app = document.getElementById('app');
  app.innerHTML = html;

  // Collapse toggle (desktop)
  const collapseBtn = document.getElementById('collapseBtn');
  collapseBtn.addEventListener('click', () => {
    document.body.classList.toggle('is-collapsed');
    localStorage.setItem('ki.collapsed', document.body.classList.contains('is-collapsed') ? '1' : '0');
  });
  if (localStorage.getItem('ki.collapsed') === '1') {
    document.body.classList.add('is-collapsed');
  }

  // Mobile menu toggle
  const menuBtn = document.getElementById('menuBtn');
  menuBtn.addEventListener('click', () => {
    document.body.classList.toggle('sidebar-open');
  });
  app.addEventListener('click', (e) => {
    if (e.target.closest('.sidebar__link')) {
      document.body.classList.remove('sidebar-open');
    }
  });

  return app.querySelector('.main__content');
}
