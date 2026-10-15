/* ============================================
   SCREEN MANAGER — Chuyển màn hình
   ============================================ */

let _currentScreen = 'menu';

function showScreen(name) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));

  const el = document.getElementById(`screen-${name}`);
  if (el) {
    el.classList.add('active');
    _currentScreen = name;
  }

  if (name === 'solo') {
    if (typeof initSoloMode === 'function') {
      initSoloMode();
    } else {
      window.addEventListener('DOMContentLoaded', () => {
        if (typeof initSoloMode === 'function') initSoloMode();
      });
    }
  }

  if (name === 'multi') {
    if (typeof initMultiMode === 'function') {
      initMultiMode();
    } else {
      window.addEventListener('DOMContentLoaded', () => {
        if (typeof initMultiMode === 'function') initMultiMode();
      });
    }
  }

  history.replaceState(null, '', name === 'menu' ? location.pathname : `#${name}`);
}

window.addEventListener('DOMContentLoaded', () => {
  const hash = location.hash.replace('#', '');
  if (['solo', 'multi'].includes(hash)) {
    showScreen(hash);
  } else {
    showScreen('menu');
  }
});