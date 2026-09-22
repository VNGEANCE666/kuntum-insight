/* ============================================================
   Pagination component (DESIGN §5.B — paginasi klasik)
   ============================================================ */

/**
 * Render kontrol paginasi.
 * @param {Object} meta — { total, page, page_size }
 * @param {(page:number)=>void} onChange
 * @param {string} [totalLabel] — label untuk info jumlah (mis. "ulasan")
 * @returns {string} HTML string
 */
export function renderPagination(meta, onChange, totalLabel = 'item') {
  const page = meta.page || 1;
  const pageSize = meta.page_size || 20;
  const total = meta.total || 0;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const start = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);

  const pageNumbers = pageList(page, totalPages);

  const html = `
    <div class="pagination">
      <span class="pagination__info">Menampilkan ${start}–${end} dari ${total} ${totalLabel}</span>
      <div class="pagination__controls">
        <button class="pagination__btn" data-page="${page - 1}" ${page <= 1 ? 'disabled' : ''} aria-label="Halaman sebelumnya">
          <span>‹</span>
        </button>
        ${pageNumbers
          .map((p) =>
            p === '...'
              ? '<span class="pagination__ellipsis">…</span>'
              : `<button class="pagination__btn ${p === page ? 'is-active' : ''}" data-page="${p}">${p}</button>`
          )
          .join('')}
        <button class="pagination__btn" data-page="${page + 1}" ${page >= totalPages ? 'disabled' : ''} aria-label="Halaman berikutnya">
          <span>›</span>
        </button>
      </div>
    </div>`;

  // Attach listener setelah elemen masuk DOM
  setTimeout(() => {
    document.querySelectorAll('.pagination__btn[data-page]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const p = parseInt(btn.getAttribute('data-page'), 10);
        if (!isNaN(p) && p >= 1 && p <= totalPages) onChange(p);
      });
    });
  }, 0);

  return html;
}

function pageList(current, totalPages) {
  const pages = [];
  const window = 2;
  for (let p = 1; p <= totalPages; p++) {
    if (p === 1 || p === totalPages || Math.abs(p - current) <= window) {
      pages.push(p);
    } else if (pages[pages.length - 1] !== '...') {
      pages.push('...');
    }
  }
  return pages;
}
