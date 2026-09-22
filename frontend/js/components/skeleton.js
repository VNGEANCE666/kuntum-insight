/* ============================================================
   Skeleton loaders — placeholder abu-abu meniru siluet konten
   akhir (DESIGN §4.2). Bukan spinner generik.
   ============================================================ */

/** Deretan kartu KPI skeleton */
export function kpiRow(count = 6) {
  return `<div class="grid grid--kpi">${Array(count)
    .fill('<div class="skeleton skeleton--kpi"></div>')
    .join('')}</div>`;
}

/** Skeleton kotak chart */
export function chart() {
  return '<div class="skeleton skeleton--chart"></div>';
}

/** Skeleton tabel (baris) */
export function table(rows = 8) {
  let html = '<div class="skeleton-table">';
  for (let i = 0; i < rows; i++) {
    const width = 60 + ((i * 37) % 35);
    html += `<div class="skeleton skeleton--row" style="width:${width}%"></div>`;
  }
  html += '</div>';
  return html;
}

/** Skeleton kartu (untuk rekomendasi) */
export function cards(count = 3) {
  return `<div class="grid grid--3col">${Array(count)
    .fill('<div class="skeleton skeleton--chart"></div>')
    .join('')}</div>`;
}

/** Kombinasi full-page skeleton untuk overview */
export function overview() {
  return `
    ${kpiRow()}
    <div class="grid grid--2col" style="margin-top:16px">
      ${chart()}${chart()}
    </div>
    <div style="margin-top:16px">${chart()}</div>`;
}
