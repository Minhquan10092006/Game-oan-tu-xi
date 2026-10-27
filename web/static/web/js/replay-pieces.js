/* Local vector pieces shared by all three replay viewers. No external assets. */
(() => {
  const ns = 'http://www.w3.org/2000/svg';
  const pieces = {
    rock: {name: 'Búa', path: 'M9 28 6 20V12Q6 8 10 8H24Q28 8 28 12V21L24 28ZM12 8V16M18 8V16M24 8V16M6 17H15Q19 17 19 21V23H12'},
    paper: {name: 'Bao', path: 'M11 29 5 18Q4 15 7 14L12 20V7Q12 3 15 5V16 4Q18 1 20 5V16 6Q23 3 25 7V17 10Q28 8 29 12V22L25 29ZM12 20V23'},
    scissors: {name: 'Kéo', path: 'M13 21 26 5M20 21 8 5M16.5 16.5 20 21M13 21A5 5 0 1 0 13 27 5 5 0 0 0 13 21M20 21A5 5 0 1 1 20 27 5 5 0 0 1 20 21'}
  };
  function paint(cell, piece) {
    const info = pieces[piece.type];
    const token = document.createElement('span');
    token.className = 'replay-token';
    token.dataset.owner = piece.owner === 'P1' ? 'P1' : 'P2';
    token.setAttribute('role', 'img');
    const label = `${piece.owner === 'P1' ? 'P1' : 'P2'} · ${info?.name || 'Quân không xác định'}`;
    token.setAttribute('aria-label', label);
    cell.title = label;
    if (info) {
      const svg = document.createElementNS(ns, 'svg');
      svg.setAttribute('viewBox', '0 0 34 34');
      svg.setAttribute('aria-hidden', 'true');
      const path = document.createElementNS(ns, 'path');
      path.setAttribute('d', info.path);
      path.setAttribute('stroke-width', '2.5');
      svg.append(path);
      token.append(svg);
    } else token.textContent = '?';
    cell.replaceChildren(token);
    return token;
  }
  window.ReplayPieces = {paint};
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.pixel-cell.P1, .pixel-cell.P2').forEach(cell => {
      const type = {B: 'rock', Ba: 'paper', K: 'scissors'}[cell.textContent.trim()];
      if(type)paint(cell,{type, owner:cell.classList.contains('P1')?'P1':'P2'});
    });
    document.querySelectorAll('#replay-board, #ops-replay-board, body.replay-page #board').forEach(board => {
      const legend = document.createElement('div');
      legend.className = 'replay-legend';
      for (const owner of ['P1', 'P2']) {
        const text = document.createElement('span');
        text.dataset.owner = owner;
        text.textContent = owner === 'P1' ? '● P1 · Cam' : '■ P2 · Xanh';
        legend.append(text);
      }
      const types = document.createElement('span');
      types.textContent = 'Búa › Kéo › Bao › Búa';
      legend.append(types);
      board.before(legend);
    });
  });
})();
