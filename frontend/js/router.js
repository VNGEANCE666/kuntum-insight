/* ============================================================
   Router — Hash-based SPA router (DESIGN §4.1, §4.2)
   Tidak ada full page reload saat berpindah tab.
   ============================================================ */

const routes = {};

let currentRoute = null;

/**
 * Daftarkan handler render (dan mount) untuk sebuah route.
 * @param {string} path
 * @param {() => Promise<string> | string} renderFn — mengembalikan HTML string (atau Promise-nya)
 * @param {(root:HTMLElement)=>void} [mountedFn] — dipanggil setelah HTML masuk DOM
 */
export function register(path, renderFn, mountedFn) {
  routes[path] = { render: renderFn, mount: mountedFn };
}

function normalizePath(hash) {
  let path = hash.replace(/^#/, '') || '/overview';
  if (!path.startsWith('/')) path = '/' + path;
  // Ambil hanya bagian path (abaikan query string untuk routing)
  const qIndex = path.indexOf('?');
  return qIndex === -1 ? path : path.slice(0, qIndex);
}

export function getCurrentRoute() {
  return currentRoute;
}

/**
 * Navigasi ke route tertentu. Route default = /overview (DESIGN §4.1).
 */
export function navigate(path) {
  window.location.hash = path;
}

export function parseQueryFromHash() {
  const hash = window.location.hash || '#/overview';
  const qIndex = hash.indexOf('?');
  if (qIndex === -1) return {};
  return new URLSearchParams(hash.slice(qIndex + 1));
}

export function setQueryForCurrent(updateFn) {
  const params = parseQueryFromHash();
  updateFn(params);
  const qs = params.toString();
  const path = normalizePath(window.location.hash || '#/overview');
  window.location.hash = qs ? `${path}?${qs}` : path;
}

async function renderRoute() {
  const path = normalizePath(window.location.hash);
  const route = routes[path];

  const app = document.getElementById('app');
  if (!route) {
    routeNotFound(app);
    return;
  }

  if (path !== currentRoute) {
    // Fade + slide keluar halaman lama sebelum render halaman baru (§4.2)
    const contentInner = document.querySelector('.main__content-inner');
    if (contentInner) {
      contentInner.style.transition = 'opacity 150ms ease-out, transform 150ms ease-out';
      contentInner.style.opacity = '0';
      contentInner.style.transform = 'translateY(8px)';
      await new Promise((r) => setTimeout(r, 150));
    }
  }

  currentRoute = path;
  const contentEl = document.querySelector('.main__content');
  const html = await route.render();
  contentEl.innerHTML = `<div class="main__content-inner">${html}</div>`;

  const inner = contentEl.querySelector('.main__content-inner');
  updateActiveNav(path);
  window.scrollTo({ top: 0, behavior: 'smooth' });

  // Beri tahu halaman lain (mis. topbar title) tentang route aktif
  window.dispatchEvent(new CustomEvent('route-changed', { detail: { path } }));

  // Trigger lifecycle "mounted" — elemen sudah masuk DOM
  if (route.mount) {
    route.mount(inner);
  }
}

function updateActiveNav(path) {
  document.querySelectorAll('.sidebar__link').forEach((el) => {
    const href = el.getAttribute('href');
    el.classList.toggle('is-active', href === `#${path}`);
  });
}

function routeNotFound(app) {
  app.innerHTML = `
    <div class="layout">
      <div class="main">
        <div class="main__content" style="padding:60px 24px">
          <div class="card" style="text-align:center;max-width:420px;margin:0 auto">
            <h2>Halaman tidak ditemukan</h2>
            <p style="margin:12px 0">Rute yang Anda tuju tidak tersedia.</p>
            <button class="btn btn--primary" onclick="location.hash='#/overview'">Kembali ke Overview</button>
          </div>
        </div>
      </div>
    </div>`;
}

/**
 * Init router di dalam elemen layout yang sudah dirender oleh layout.js.
 * Setelah init, router mengontrol isi .main__content.
 */
export function initRouter(rootEl) {
  let contentEl = rootEl.querySelector('.main__content');
  if (!contentEl) contentEl = rootEl;

  window.addEventListener('hashchange', renderRoute);
  document.body.addEventListener('click', (e) => {
    // Kelola navigasi SPA untuk semua tautan internal bertipe #/...
    const anchor = e.target.closest('a[href^="#/"]');
    if (anchor) {
      e.preventDefault();
      location.hash = anchor.getAttribute('href');
    }
  });

  // Render route pertama
  renderRoute();
  return contentEl;
}
