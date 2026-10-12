/* ============================================
   SCREEN MANAGER — Chuyển màn hình
   ============================================ */

let _currentScreen = 'menu';
let _soloBoot = false;
let _multiBoot = false;

function showScreen(name) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));

  const el = document.getElementById(`screen-${name}`);
  if (el) {
    el.classList.add('active');
    _currentScreen = name;
  }

  if (name === 'solo' && !_soloBoot) {
    _soloBoot = true;
    if (typeof initSoloMode === 'function') initSoloMode();
  }

  if (name === 'multi' && !_multiBoot) {
    _multiBoot = true;
    if (typeof initMultiMode === 'function') initMultiMode();
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