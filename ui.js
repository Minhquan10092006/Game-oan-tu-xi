/* ============================================
   OẲN TÙ TÌ 2.0 — UI CONTROLLER (SOLO MODE)
   ============================================ */

let game = null;
let selectedCell = null;
let validMoves = [];
let lastMove = null;
let soloInitialized = false;

let boardEl, turnTextEl, turnNumberEl, turnOrbEl, statusEl, moveLogEl;
let p1InfoEl, p2InfoEl, p1PiecesEl, p2PiecesEl;
let victoryOverlay, victoryTitle, victoryMessage;

function initSoloMode() {
  if (soloInitialized) return;
  soloInitialized = true;

  boardEl = document.getElementById('board');
  turnTextEl = document.getElementById('turn-text');
  turnNumberEl = document.getElementById('turn-number');
  turnOrbEl = document.getElementById('turn-orb');
  statusEl = document.getElementById('status-message');
  moveLogEl = document.getElementById('move-log');
  p1InfoEl = document.getElementById('player1-info');
  p2InfoEl = document.getElementById('player2-info');
  p1PiecesEl = document.getElementById('p1-pieces');
  p2PiecesEl = document.getElementById('p2-pieces');
  victoryOverlay = document.getElementById('victory-overlay');
  victoryTitle = document.getElementById('victory-title');
  victoryMessage = document.getElementById('victory-message');

  requestAnimationFrame(() => {
    initBackgroundCanvas();
    buildCoordLabels();
    newGame();
  });

  document.addEventListener('keydown', onKeyDown);
}

// ---- Background canvas ----
let _bgInitialized = false;
function initBackgroundCanvas() {
  if (_bgInitialized) return;
  _bgInitialized = true;

  const canvas = document.getElementById('bg-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const particles = [];
  let w, h;

  function resize() {
    w = canvas.width = window.innerWidth;
    h = canvas.height = window.innerHeight;
  }
  resize();
  window.addEventListener('resize', resize);

  for (let i = 0; i < 50; i++) {
    particles.push({
      x: Math.random() * w,
      y: Math.random() * h,
      r: Math.random() * 2 + 0.5,
      dx: (Math.random() - 0.5) * 0.3,
      dy: (Math.random() - 0.5) * 0.3,
      opacity: Math.random() * 0.3 + 0.1,
      hue: Math.random() * 60 + 230,
    });
  }

  (function animate() {
    ctx.clearRect(0, 0, w, h);
    ctx.strokeStyle = 'rgba(148, 163, 184, 0.02)';
    const gs = 60;
    for (let x = 0; x < w; x += gs) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
    }
    for (let y = 0; y < h; y += gs) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
    }
    for (const p of particles) {
      p.x += p.dx; p.y += p.dy;
      if (p.x < 0) p.x = w; if (p.x > w) p.x = 0;
      if (p.y < 0) p.y = h; if (p.y > h) p.y = 0;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = `hsla(${p.hue}, 60%, 65%, ${p.opacity})`;
      ctx.fill();
    }
    requestAnimationFrame(animate);
  })();
}

// ---- Coord labels ----
function buildCoordLabels() {
  const topLabels = document.getElementById('top-labels');
  const bottomLabels = document.getElementById('bottom-labels');
  const leftLabels = document.getElementById('left-labels');
  const rightLabels = document.getElementById('right-labels');
  if (!topLabels) return;

  topLabels.innerHTML = '';
  bottomLabels.innerHTML = '';
  leftLabels.innerHTML = '';
  rightLabels.innerHTML = '';

  for (let c = 0; c < 9; c++) {
    const col = c + 1;
    topLabels.innerHTML += `<span>${col}</span>`;
    bottomLabels.innerHTML += `<span>${col}</span>`;
  }
  for (let r = 0; r < 9; r++) {
    const row = r + 1;
    leftLabels.innerHTML += `<span>${row}</span>`;
    rightLabels.innerHTML += `<span>${row}</span>`;
  }
}

// ---- Board rendering ----
function renderBoard() {
  if (!boardEl) return;
  boardEl.innerHTML = '';

  for (let r = 0; r < 9; r++) {
    for (let c = 0; c < 9; c++) {
      const cell = document.createElement('div');
      cell.className = 'cell';
      cell.id = `cell-${r}-${c}`;
      cell.dataset.row = r;
      cell.dataset.col = c;
      cell.classList.add((r + c) % 2 === 0 ? 'light' : 'dark');

      if (r === GOALS[1].row && c === GOALS[1].col) {
        cell.classList.add('goal-p1');
        cell.dataset.tooltip = 'Đích P1 (9,9)';
      }
      if (r === GOALS[2].row && c === GOALS[2].col) {
        cell.classList.add('goal-p2');
        cell.dataset.tooltip = 'Đích P2 (1,1)';
      }

      if (lastMove) {
        if (r === lastMove.fromRow && c === lastMove.fromCol) cell.classList.add('last-from');
        if (r === lastMove.toRow && c === lastMove.toCol) cell.classList.add('last-to');
      }

      if (selectedCell && r === selectedCell.row && c === selectedCell.col) {
        cell.classList.add('selected');
      }

      const moveInfo = validMoves.find(m => m.toRow === r && m.toCol === c);
      if (moveInfo) {
        if (moveInfo.isBlocked) cell.classList.add('blocked');
        else if (moveInfo.isCapture) cell.classList.add('valid-attack');
        else cell.classList.add('valid-move');
      }

      const piece = game.getPiece(r, c);
      if (piece) {
        const pieceEl = document.createElement('span');
        pieceEl.className = `piece p${piece.player}`;
        pieceEl.textContent = piece.emoji;
        pieceEl.dataset.tooltip = `${piece.player === 1 ? 'P1' : 'P2'} ${pieceNameVi(piece.type)}`;
        cell.appendChild(pieceEl);
      }

      cell.addEventListener('click', () => onCellClick(r, c));
      boardEl.appendChild(cell);
    }
  }
}

// ---- Click handling ----
function onCellClick(row, col) {
  if (!game || game.gameOver) return;
  const piece = game.getPiece(row, col);

  if (selectedCell) {
    const move = validMoves.find(m => m.toRow === row && m.toCol === col && !m.isBlocked);
    if (move) {
      executePlayerMove(selectedCell.row, selectedCell.col, row, col, move);
      return;
    }
  }

  if (piece && piece.player === game.currentPlayer) {
    selectPiece(row, col);
    return;
  }
  deselectPiece();
}

function selectPiece(row, col) {
  selectedCell = { row, col };
  validMoves = game.getValidMoves(row, col);
  renderBoard();

  const piece = game.getPiece(row, col);
  const movable = validMoves.filter(m => !m.isBlocked);
  if (movable.length === 0) {
    setStatus(`${PIECE_EMOJI[piece.type]} ${pieceNameVi(piece.type)} — Không có nước đi hợp lệ`);
  } else {
    const attacks = movable.filter(m => m.isCapture).length;
    const normal = movable.length - attacks;
    let msg = `${PIECE_EMOJI[piece.type]} ${pieceNameVi(piece.type)} — ${normal} nước đi`;
    if (attacks > 0) msg += `, ${attacks} ăn quân`;
    setStatus(msg);
  }
}

function deselectPiece() {
  selectedCell = null;
  validMoves = [];
  renderBoard();
  setStatus('Chọn một quân cờ để di chuyển');
}

function executePlayerMove(fromRow, fromCol, toRow, toCol) {
  const moveRecord = game.executeMove(fromRow, fromCol, toRow, toCol);
  if (!moveRecord) return;

  lastMove = moveRecord;
  selectedCell = null;
  validMoves = [];

  renderBoard();
  animateMove(toRow, toCol, moveRecord.isCapture);
  addMoveLog(moveRecord);
  updateInfoBar();

  if (game.gameOver) {
    setTimeout(() => showVictory(), 600);
  } else {
    setStatus(`Lượt Player ${game.currentPlayer} — Chọn quân cờ`);
  }
}

function animateMove(row, col, isCapture) {
  const cellEl = document.getElementById(`cell-${row}-${col}`);
  const pieceEl = cellEl?.querySelector('.piece');
  if (pieceEl) {
    pieceEl.classList.add('just-moved');
    setTimeout(() => pieceEl.classList.remove('just-moved'), 500);
  }
  if (isCapture) {
    cellEl?.classList.add('capture-flash');
    setTimeout(() => cellEl?.classList.remove('capture-flash'), 600);
  }
}

function updateInfoBar() {
  if (!turnTextEl) return;
  turnTextEl.textContent = `Lượt Player ${game.currentPlayer}`;
  turnNumberEl.textContent = `Turn ${game.turnNumber}`;
  turnOrbEl.className = `turn-orb ${game.currentPlayer === 2 ? 'p2' : ''}`;

  p1InfoEl.classList.toggle('active-player', game.currentPlayer === 1);
  p2InfoEl.classList.toggle('active-player', game.currentPlayer === 2);

  const p1c = game.countPieces(1);
  const p2c = game.countPieces(2);
  p1PiecesEl.innerHTML = `
    <span class="piece-badge rock">🪨×${p1c.rock}</span>
    <span class="piece-badge paper">📄×${p1c.paper}</span>
    <span class="piece-badge scissors">✂️×${p1c.scissors}</span>
  `;
  p2PiecesEl.innerHTML = `
    <span class="piece-badge rock">🪨×${p2c.rock}</span>
    <span class="piece-badge paper">📄×${p2c.paper}</span>
    <span class="piece-badge scissors">✂️×${p2c.scissors}</span>
  `;
}

function setStatus(msg) {
  if (statusEl) statusEl.textContent = msg;
}

function addMoveLog(moveRecord) {
  if (!moveLogEl) return;
  const { player, turnNumber, piece, fromRow, fromCol, toRow, toCol, isCapture, captured } = moveRecord;
  const from = toDisplay(fromRow, fromCol);
  const to = toDisplay(toRow, toCol);
  const pName = pieceNameVi(piece.type);
  const emoji = PIECE_EMOJI[piece.type];

  let text = `${emoji} ${pName} ${from} → ${to}`;
  let captureText = '';
  if (isCapture && captured) {
    captureText = ` ⚔️ ăn ${PIECE_EMOJI[captured.type]} ${pieceNameVi(captured.type)}`;
  }

  const entry = document.createElement('div');
  entry.className = `log-entry p${player}-entry`;
  entry.innerHTML = `
    <span class="log-turn">#${turnNumber}</span>
    <span class="log-move">${text}${captureText ? `<span class="log-capture">${captureText}</span>` : ''}</span>
  `;
  moveLogEl.appendChild(entry);
  moveLogEl.scrollTop = moveLogEl.scrollHeight;
}

// ---- Victory ----
function showVictory() {
  if (!victoryOverlay) return;
  victoryOverlay.classList.remove('hidden');
  victoryTitle.textContent = `🎉 Player ${game.winner} Chiến Thắng!`;
  victoryMessage.textContent = game.winReason;
  createVictoryParticles();
}

function hideVictory() {
  if (victoryOverlay) victoryOverlay.classList.add('hidden');
}

function createVictoryParticles() {
  const container = document.getElementById('victory-particles');
  if (!container) return;
  container.innerHTML = '';
  const colors = ['#f59e0b', '#ef4444', '#3b82f6', '#10b981', '#8b5cf6', '#ec4899'];

  for (let i = 0; i < 30; i++) {
    const particle = document.createElement('div');
    const color = colors[Math.floor(Math.random() * colors.length)];
    const size = Math.random() * 8 + 4;
    const x = Math.random() * 100;
    const delay = Math.random() * 2;
    const duration = Math.random() * 2 + 2;
    particle.style.cssText = `
      position: absolute;
      width: ${size}px; height: ${size}px;
      background: ${color};
      border-radius: ${Math.random() > 0.5 ? '50%' : '2px'};
      left: ${x}%; top: -10px;
      opacity: 0.8;
      animation: confettiFall ${duration}s ease-in ${delay}s infinite;
    `;
    container.appendChild(particle);
  }

  if (!document.getElementById('confetti-style')) {
    const style = document.createElement('style');
    style.id = 'confetti-style';
    style.textContent = `
      @keyframes confettiFall {
        0% { transform: translateY(0) rotate(0deg); opacity: 1; }
        100% { transform: translateY(500px) rotate(720deg); opacity: 0; }
      }
    `;
    document.head.appendChild(style);
  }
}

// ---- Controls ----
function newGame() {
  game = new GameState();
  selectedCell = null;
  validMoves = [];
  lastMove = null;
  if (moveLogEl) moveLogEl.innerHTML = '';
  hideVictory();
  renderBoard();
  updateInfoBar();
  setStatus('Ván mới! Player 1 đi trước — Chọn quân cờ');
}

function undoMove() {
  if (!game || game.moveHistory.length === 0) {
    setStatus('Không có nước đi nào để hoàn tác');
    return;
  }
  const wasGameOver = game.gameOver;
  const undone = game.undoLastMove();
  if (!undone) return;
  if (wasGameOver) hideVictory();

  selectedCell = null;
  validMoves = [];
  lastMove = game.moveHistory.length > 0 ? game.moveHistory[game.moveHistory.length - 1] : null;

  const lastLog = moveLogEl?.lastElementChild;
  if (lastLog) lastLog.remove();

  renderBoard();
  updateInfoBar();
  setStatus(`Đã hoàn tác — Lượt Player ${game.currentPlayer}`);
}

// ---- Keyboard ----
function onKeyDown(e) {
  const soloScreen = document.getElementById('screen-solo');
  if (!soloScreen || !soloScreen.classList.contains('active')) return;

  if (e.key === 'Escape') deselectPiece();
  if (e.key === 'z' && (e.ctrlKey || e.metaKey)) {
    e.preventDefault(); undoMove();
  }
  if (e.key === 'n' && (e.ctrlKey || e.metaKey)) {
    e.preventDefault(); newGame();
  }
}