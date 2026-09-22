/* ============================================================
   Icons — Satu set ikon SVG terpadu (gaya Feather/Lucide).
   Bukan emoji/karakter unicode: rendering konsisten di semua
   OS/browser, dan bisa diberi warna via `currentColor`.
   Dipakai oleh seluruh halaman & komponen dashboard.
   ============================================================ */

const ICON_PATHS = {
  /* Navigasi sidebar */
  dashboard: '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
  reviews: '<path d="M21 6a2 2 0 0 0-2-2h-4V3a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v1H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2z"/><path d="M8 10h8M8 14h5"/>',
  tag: '<path d="M20.6 13.4 12 22 2 12V2h10l8.6 8.6a2 2 0 0 1 0 2.8z"/><circle cx="7" cy="7" r="1.4"/>',
  lightbulb: '<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10.5c.6.6 1 1.5 1 2.5h6c0-1 .4-1.9 1-2.5A6 6 0 0 0 12 3z"/>',
  activity: '<path d="M3 12h4l3-8 4 16 3-8h4"/>',

  /* KPI */
  count: '<path d="M4 6h16v12H4zM4 9h16"/>',
  star: '<path d="M12 4l2.4 5 5.6.8-4 3.9.9 5.5-5-2.6-5 2.6.9-5.5-4-3.9L9.6 9z"/>',
  smile: '<circle cx="12" cy="12" r="9"/><path d="M8 14.5a4 4 0 0 0 8 0M9 9.5h.01M15 9.5h.01"/>',
  meh: '<circle cx="12" cy="12" r="9"/><path d="M8 15h8M9 9.5h.01M15 9.5h.01"/>',
  frown: '<circle cx="12" cy="12" r="9"/><path d="M9 11.5h.01M15 11.5h.01M8 15a4 4 0 0 1 8 0"/>',
  text: '<path d="M5 4h14v4H5zM5 10h14M5 14h14M5 18h4"/>',
  length: '<path d="M6 5l12 12M14 7l4-2-2 4M6 17l-2 4 4-2"/>',
  thumbsup: '<path d="M7 11v10M7 11 11 4a2 2 0 0 1 2 1.5V9h6a1.5 1.5 0 0 1 1.5 1.8l-1.6 7a2 2 0 0 1-2 1.7H7"/>',

  /* Sentimen (untuk badge, colorblind-friendly) */
  check: '<path d="M4 12.5 9.5 18 20 6.5"/>',
  minus: '<path d="M5 12h14"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  rateFallback: '<path d="M7 20V8M11 20V4M15 20v-8M19 20V2"/><path d="M3 20h18"/>',

  /* Status / util */
  checkCircle: '<circle cx="12" cy="12" r="9"/><path d="M8.5 12.5 11 15l5-6"/>',
  circle: '<circle cx="12" cy="12" r="8.5"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 16v-4M12 8h.01"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.5-4.5"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
  chevronRight: '<path d="M9 6l6 6-6 6"/>',
  chevronLeft: '<path d="M15 6l-6 6 6 6"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  reload: '<path d="M20 12a8 8 0 1 1-2.5-5.8M20 4v4h-4"/>',
  inbox: '<path d="M3 13h5l2 3h4l2-3h5M5 13l1.2-6.5A2 2 0 0 1 8.2 5h7.6a2 2 0 0 1 2 1.5L19 13"/><path d="M3 13v5a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5"/>',
  alertCircle: '<circle cx="12" cy="12" r="9"/><path d="M12 8v4M12 16h.01"/>',
  printer: '<polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
};

/**
 * Render ikon SVG inline.
 * @param {string} name  — kunci pada ICON_PATHS
 * @param {string} [cls] — class ekstra (mis. untuk ukuran/posisi)
 * @param {Object} [opts] — { size, strokeWidth }
 * @returns {string} string SVG yang siap disisipkan ke HTML
 */
export function icon(name, cls = '', opts = {}) {
  const d = ICON_PATHS[name] || ICON_PATHS.info;
  const sw = opts.strokeWidth || 1.8;
  return `<svg class="ki-ico ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${sw}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
}

/** Icon khusus rating bintang (bukan karakter unicode), utk rating widget. */
export function starIcon(filled = true, cls = '') {
  const path = filled
    ? '<path d="M12 4l2.4 5 5.6.8-4 3.9.9 5.5-5-2.6-5 2.6.9-5.5-4-3.9L9.6 9z"/>'
    : '<path d="M12 4l2.4 5 5.6.8-4 3.9.9 5.5-5-2.6-5 2.6.9-5.5-4-3.9L9.6 9z" fill="none" stroke="currentColor"/>';
  return `<svg class="ki-ico ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${path}</svg>`;
}