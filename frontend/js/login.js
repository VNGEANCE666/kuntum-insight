/* ============================================================
   Login page — submit kredensial → POST /api/auth/login → simpan
   token (auth.js) → masuk ke dashboard. (HANDOFF §13)
   ============================================================ */

import { setToken, setUsername, isAuthed } from './auth.js';

const form = document.getElementById('loginForm');
const usernameEl = document.getElementById('username');
const passwordEl = document.getElementById('password');
const pwToggle = document.getElementById('pwToggle');
const errorEl = document.getElementById('loginError');
const submitBtn = document.getElementById('submitBtn');
const submitLabel = document.getElementById('submitLabel');

// Sudah punya token? Langsung masuk tanpa login ulang.
if (isAuthed()) {
  window.location.replace('/');
}

// Tampilkan / sembunyikan password.
pwToggle.addEventListener('click', () => {
  const isHidden = passwordEl.type === 'password';
  passwordEl.type = isHidden ? 'text' : 'password';
  pwToggle.setAttribute('aria-label', isHidden ? 'Sembunyikan password' : 'Tampilkan password');
  pwToggle.innerHTML = isHidden
    ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><path d="M1 1l22 22"/></svg>'
    : '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z"/><circle cx="12" cy="12" r="3"/></svg>';
});

function showError(message) {
  errorEl.textContent = message;
  errorEl.hidden = false;
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  errorEl.hidden = true; // sembunyikan sebentar sebelum kirim

  const username = usernameEl.value.trim();
  const password = passwordEl.value;
  if (!username || !password) {
    showError('Username dan password wajib diisi.');
    return;
  }

  submitBtn.disabled = true;
  submitLabel.textContent = 'Memeriksa…';

  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    const body = await res.json().catch(() => null);

    if (!res.ok) {
      let detail;
      if (res.status === 401) {
        detail = (body && body.detail) || 'Username atau password salah.';
      } else if (res.status === 429) {
        detail = 'Terlalu banyak percobaan. Tunggu beberapa menit lalu coba lagi.';
      } else {
        detail = (body && body.detail) || `Login gagal (HTTP ${res.status}).`;
      }
      showError(detail);
      return;
    }

    const data = (body && body.data) || {};
    setToken(data.token);
    setUsername(data.username || username);
    window.location.replace('/');
  } catch (_) {
    showError('Tidak dapat terhubung ke server. Periksa koneksi Anda.');
  } finally {
    submitBtn.disabled = false;
    submitLabel.textContent = 'Masuk';
  }
});
