/* ============================================================
   Chart utilities — registrasi, cleanup chart per page
   ============================================================ */

const chartRegistry = new Map(); // key -> Chart instance

/**
 * Daftarkan chart agar halaman bisa destroy semua chart
 * sebelum di-remount (mencegah leak/duplikat).
 */
export function registerChart(key, chart) {
  const existing = chartRegistry.get(key);
  if (existing) existing.destroy();
  chartRegistry.set(key, chart);
}

export function destroyCharts() {
  chartRegistry.forEach((chart) => chart.destroy());
  chartRegistry.clear();
}

export const SENTIMENT_COLORS = {
  positif: '#4CAF50',
  netral: '#FFC107',
  negatif: '#F44336',
};

/**
 * Format angka ribuan (mis. 2832 → "2.832", Indonesia lokale-ish).
 */
export function formatNumber(n) {
  if (n === null || n === undefined || isNaN(n)) return '–';
  return Number(n).toLocaleString('id-ID');
}

/**
 * Format persentase (0.8758 → "87,6%").
 */
export function formatPercent(n, digits = 1) {
  if (n === null || n === undefined || isNaN(n)) return '–';
  return (n * 100).toLocaleString('id-ID', { maximumFractionDigits: digits }) + '%';
}

/**
 * Parse tanggal ISO string backend → format "dd MMM yyyy".
 * Backend mengirim mis. "2026-05-20 15:58:17+00:00".
 * Ditampilkan dalam WIB (Asia/Jakarta) secara eksplisit.
 */
export function formatDate(iso, locale = 'id-ID') {
  if (!iso) return '–';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const opts = { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'Asia/Jakarta' };
  return d.toLocaleDateString(locale, opts);
}

/**
 * Format tanggal + waktu ISO → "dd MMM yyyy, HH.mm" (WIB).
 * Digunakan untuk timestamp training model, log, dst.
 * Contoh: "2026-08-24T11:22:58+00:00" → "24 Agu 2026, 18.22"
 */
export function formatDateTime(iso, locale = 'id-ID') {
  if (!iso) return '–';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  // date part: dd MMM yyyy
  const datePart = d.toLocaleDateString(locale, { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'Asia/Jakarta' });
  // time part: HH.mm (pakai titik, bukan colon — konsisten format Indonesia)
  const timePart = d.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Asia/Jakarta' }).replace(':', '.');
  return `${datePart}, ${timePart}`;
}

/**
 * Escape HTML agar teks ulasan aman dirender (hindari XSS dari
 * ulasan berisi markup).
 */
export function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

/**
 * Render rating bintang (1-5) sebagai SVG (bukan karakter unicode ★).
 * Tampil konsisten di semua OS/browser.
 */
export function renderStars(rating) {
  const r = Math.round(rating);
  const fill = (i) => `<svg class="stars__ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4l2.4 5 5.6.8-4 3.9.9 5.5-5-2.6-5 2.6.9-5.5-4-3.9L9.6 9z" fill="${i < r ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
  return `<span class="stars" role="img" aria-label="${r} dari 5 bintang">${Array.from({ length: 5 }, (_, i) => fill(i)).join('')}</span>`;
}

/**
 * Badge sentimen + indikator fallback (DESIGN §2 / §5.B).
 * Ikon polaritas (✓ / – / ✕) menambah pembeda non-warna (ramah buta warna).
 */
export function sentimentBadge(label, source) {
  const ico = polarityIcon(label);
  const badge = `<span class="badge badge--${label || 'netral'}">${ico}<span class="badge__dot dot--${label || 'netral'}"></span>${capitalize(label || 'netral')}</span>`;
  if (source === 'rating_fallback') {
    return `${badge} <span class="badge badge--fallback" title="Label dari rating karena ulasan tanpa teks atau terlalu pendek">dari rating</span>`;
  }
  return badge;
}

function polarityIcon(label) {
  // Normalisasi label (lowercase) → ikon polaritas.
  // positif → check (/), negatif → x (x), lainnya (netral/null) → minus (–).
  const s = String(label || '').toLowerCase();
  const key = s === 'positif' ? 'check' : s === 'negatif' ? 'x' : 'minus';
  return polaritySvg(key);
}

function polaritySvg(key) {
  const d = key === 'check' ? '<path d="M4 12.5 9.5 18 20 6.5"/>'
    : key === 'x' ? '<path d="M6 6l12 12M18 6 6 18"/>'
    : '<path d="M5 12h14"/>';
  return `<svg class="badge__ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
}

export function capitalize(str) {
  return str ? str.charAt(0).toUpperCase() + str.slice(1) : '';
}

export const SENTIMENT_LABELS = {
  positif: 'Positif',
  netral: 'Netral',
  negatif: 'Negatif',
};

/**
 * Indeks label sumbu X yang dirender penuh, DIDETERMINISTIK & SERAGAM antar
 * chart (small multiples). AutoSkip Chart.js jalan independen per-chart
 * dengan lebar berbeda → bisa memunculkan tick yang berlainan tiap chart,
 * merusak penyelarasan horizontal. Fungsi ini memilih indeks yang tersebar
 * merata (seperti naiknya autoSkip) TAPI dari count yang sama dengan formula
 * yang sama → ketiga mini-chart memperlihatkan tick yang sama persis.
 */
export function computeTickIndices(count, maxTicks = 6) {
  if (!count) return [];
  if (count <= maxTicks) return [...Array(count).keys()];
  const step = Math.ceil((count - 1) / (maxTicks - 1));
  const indices = [];
  for (let i = 0; i < count; i += step) indices.push(i);
  if (indices[indices.length - 1] !== count - 1) indices.push(count - 1);
  return indices;
}

/**
 * Pasang afterBuildTicks agar sumbu X hanya merender label pada indeks hasil
 * computeTickIndices — semua chart yang memakainya jadi sejajar (label sama,
 * posisi sama). Dikombinasikan dengan maxTicksLimit sebagai pengaman.
 *
 * Penggunaan di opsi scale:
 *   x: { ticks: { ..., maxTicksLimit: 6 }, afterBuildTicks: useSharedTicks() }
 */
export function useSharedTicks(maxTicks = 6) {
  return (axis) => {
    const labels = axis.chart.data.labels || [];
    const wanted = computeTickIndices(labels.length, maxTicks);
    axis.ticks = axis.ticks.filter((t) => wanted.includes(t.value));
  };
}
