/* ============================================================
   State — Cache in-memory untuk data yang jarang berubah
   dalam satu sesi (DESIGN §7). Bukan localStorage.
   ============================================================ */

const cache = new Map();
const defaultTtl = 120000; // 2 menit default

/**
 * Get data yang di-cache.
 * @param {string} key
 * @returns {any|null}
 */
export function getCache(key) {
  const entry = cache.get(key);
  if (!entry) return null;
  if (Date.now() > entry.expires) {
    cache.delete(key);
    return null;
  }
  return entry.value;
}

/**
 * Simpan data ke cache dengan TTL tertentu.
 * @param {string} key
 * @param {any} value
 * @param {number} [ttl] — millisecond
 */
export function setCache(key, value, ttl = defaultTtl) {
  cache.set(key, { value, expires: Date.now() + ttl });
}

/**
 * Hapus semua cache. Dipanggil setelah reload cache backend.
 */
export function clearCache() {
  cache.clear();
}
