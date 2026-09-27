/* ============================================================
   Auth — penyimpanan token + kredensial sesi (HANDOFF §13).
   Token JWT-signed disimpan di localStorage; semua akses API
   otomatis membawa header Authorization: Bearer <token>.
   ============================================================ */

const TOKEN_KEY = 'kuntum.insight.token';
const USERNAME_KEY = 'kuntum.insight.username';
const LOGIN_PAGE = '/login.html';

const safe = {
  get(key) { try { return localStorage.getItem(key); } catch (_) { return null; } },
  set(key, value) { try { localStorage.setItem(key, value); } catch (_) { /* private mode */ } },
  remove(key) { try { localStorage.removeItem(key); } catch (_) { /* private mode */ } },
};

export function getToken() {
  return safe.get(TOKEN_KEY) || '';
}

export function setToken(token) {
  safe.set(TOKEN_KEY, token);
}

export function getUsername() {
  return safe.get(USERNAME_KEY) || '';
}

export function setUsername(username) {
  safe.set(USERNAME_KEY, username);
}

export function clearToken() {
  safe.remove(TOKEN_KEY);
  safe.remove(USERNAME_KEY);
}

export function isAuthed() {
  return Boolean(getToken());
}

/** Redirect ke halaman login tanpa mem-bypass guard via path check. */
export function redirectToLogin() {
  if (window.location.pathname === LOGIN_PAGE) return;
  window.location.replace(LOGIN_PAGE);
}

/** Header Authorization untuk fetch; kosong untuk endpoint login itu sendiri. */
export function authHeaders(endpoint = '') {
  const token = getToken();
  if (token && !endpoint.startsWith('/api/auth/login')) {
    return { Authorization: `Bearer ${token}` };
  }
  return {};
}

/** Tangani 401 dari backend: bersihkan token & lempar ke login. */
export function handleUnauthorized() {
  clearToken();
  redirectToLogin();
}

/** Logout: revoke token di backend (jti deny-list), hapus sesi lokal, kembali ke login. */
export async function logout() {
  try {
    await fetch('/api/auth/logout', {
      method: 'POST',
      headers: authHeaders(),
    });
  } finally {
    clearToken();
    redirectToLogin();
  }
}
