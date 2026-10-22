/* Optional motion preference; essential content and navigation work without JS. */
(() => {
  const buttons = document.querySelectorAll('[data-motion-toggle]');
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  let paused = reduced.matches;
  try { paused = paused || localStorage.getItem('ott-motion') === 'paused'; } catch (_) {}
  function render() {
    document.body.dataset.motion = paused ? 'paused' : 'playing';
    buttons.forEach(button => {
      button.setAttribute('aria-pressed', String(paused));
      button.textContent = paused ? 'Bật hiệu ứng' : 'Dừng hiệu ứng';
    });
  }
  buttons.forEach(button => button.addEventListener('click', () => {
    paused = !paused;
    try { localStorage.setItem('ott-motion', paused ? 'paused' : 'playing'); } catch (_) {}
    render();
  }));
  reduced.addEventListener('change', event => { if (event.matches) { paused = true; render(); } });
  render();
})();
