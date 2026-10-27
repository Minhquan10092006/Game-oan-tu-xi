/* Apply before first paint, including standalone replay pages. */
(() => {
  const system = matchMedia('(prefers-color-scheme: dark)');
  let saved;
  try { saved = localStorage.getItem('ott-theme'); } catch (_) {}
  function apply(theme) {
    const dark = theme === 'dark';
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', dark ? '#2b211f' : '#d0b79e');
    document.querySelectorAll('[data-theme-toggle]').forEach(button => {
      button.setAttribute('aria-pressed', String(dark));
      button.setAttribute('aria-label', dark ? 'Chuyển sang chế độ sáng' : 'Chuyển sang chế độ tối');
      button.textContent = dark ? '☀ Sáng' : '☾ Tối';
    });
  }
  apply(['light', 'dark'].includes(saved) ? saved : system.matches ? 'dark' : 'light');
  document.addEventListener('DOMContentLoaded', () => {
    apply(document.documentElement.dataset.theme);
    document.querySelectorAll('[data-theme-toggle]').forEach(button => button.addEventListener('click', () => {
      saved = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
      try { localStorage.setItem('ott-theme', saved); } catch (_) {}
      apply(saved);
    }));
  });
  system.addEventListener('change', event => { if (!saved) apply(event.matches ? 'dark' : 'light'); });
  window.addEventListener('storage', event => {
    if (event.key === 'ott-theme') {
      saved = event.newValue;
      apply(['light', 'dark'].includes(saved) ? saved : system.matches ? 'dark' : 'light');
    }
  });
})();
