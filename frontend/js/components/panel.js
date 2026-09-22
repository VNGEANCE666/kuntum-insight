/* ============================================================
   Slide-in panel (DESIGN §5.B — detail tanpa navigasi keluar)
   ============================================================ */

export function openPanel(contentHtml) {
  closePanel();

  const overlay = document.createElement('div');
  overlay.className = 'panel-overlay';
  overlay.id = 'panelOverlay';

  const panel = document.createElement('div');
  panel.className = 'slide-panel';
  panel.id = 'slidePanel';
  panel.setAttribute('role', 'dialog');
  panel.setAttribute('aria-modal', 'true');
  panel.innerHTML = `
    <div class="slide-panel__body">${contentHtml}</div>`;

  overlay.addEventListener('click', closePanel);
  document.addEventListener('keydown', onKey);

  document.body.appendChild(overlay);
  document.body.appendChild(panel);
  document.body.style.overflow = 'hidden';

  // Force reflow lalu trigger transisi masuk
  requestAnimationFrame(() => {
    overlay.classList.add('is-open');
    panel.classList.add('is-open');
  });
}

function onKey(e) {
  if (e.key === 'Escape') closePanel();
}

export function closePanel() {
  const overlay = document.getElementById('panelOverlay');
  const panel = document.getElementById('slidePanel');
  if (!overlay && !panel) return;

  document.removeEventListener('keydown', onKey);
  document.body.style.overflow = '';
  if (overlay) overlay.classList.remove('is-open');
  if (panel) panel.classList.remove('is-open');

  setTimeout(() => {
    if (overlay) overlay.remove();
    if (panel) panel.remove();
  }, 220);
}
