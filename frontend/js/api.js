/* ============================================================
   API Service — Semua fetch memakai path RELATIF (satu origin
   dengan backend via mount StaticFiles).
   ============================================================ */

// Set controller yang sedang aktif untuk request yang "dapat dibatalkan"
// (mis. pencarian Review Explorer yang di-debounce). Default: kosong.
const cancellable = new Set();

/**
 * Buat AbortController baru untuk sebuah request yang boleh dibatalkan
 * (mis. filter yang berubah cepat). Panggil abortInFlight() sebelum
 * memulai request berikutnya agar request usang dibatalkan.
 * @returns {AbortController}
 */
export function createController() {
  const controller = new AbortController();
  cancellable.add(controller);
  return controller;
}

/**
 * Batalkan semua request yang masih berjalan dan ditandai cancellable.
 * Dipakai Review Explorer sebelum fetch baru saat filter berubah cepat
 * (DESIGN §4.3 — mencegah race condition). Request biasa (paralel, mis.
 * Overview) TIDAK masuk set ini, jadi tidak saling mengganggu.
 */
export function abortInFlight() {
  cancellable.forEach((c) => c.abort());
  cancellable.clear();
}

/**
 * Ambil data dari endpoint backend.
 * @param {string} endpoint — contoh '/api/overview/kpi'
 * @param {Object} [params] — object query params. Nilai array menjadi
 *   params berulang (mis. sentiment[]=positif&sentiment[]=negatif).
 * @param {Object} [opts] — { signal } untuk AbortController kustom.
 * @returns {Promise<any>} — payload response { data, ... }
 */
export async function apiGet(endpoint, params = {}, opts = {}) {
  const url = buildUrl(endpoint, params);
  const signal = opts.signal || undefined;

  try {
    const res = await fetch(url, { signal, headers: { Accept: 'application/json' } });
    if (!res.ok) {
      let detail = `Error ${res.status}`;
      try {
        const body = await res.json();
        if (body && body.detail) detail = body.detail;
      } catch (_) {
        /* ignore non-JSON error body */
      }
      throw new ApiError(res.status, detail);
    }
    return await res.json();
  } finally {
    if (signal && signal.aborted && cancellable.has(signal)) {
      cancellable.delete(signal);
    }
  }
}

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
    this.name = 'ApiError';
  }
}

/**
 * Bangun URL query string dari object params.
 * - Array → params berulang (FastAPI list query dengan alias []).
 * - null/undefined/'' → dilewati.
 */
function buildUrl(endpoint, params) {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params || {})) {
    if (value === undefined || value === null) continue;
    if (Array.isArray(value)) {
      value.forEach((v) => {
        if (v !== undefined && v !== null && v !== '') qs.append(key, v);
      });
    } else if (value !== '') {
      qs.append(key, String(value));
    }
  }
  const qStr = qs.toString();
  return qStr ? `${endpoint}?${qStr}` : endpoint;
}
