/* ============================================
   OẲN TÙ TÌ 2.0 — MULTIPLAYER VIEW
   ============================================ */

let socket = null;
const slots = [];
let multiInitialized = false;
const ROOM_CODES = ['A1', 'A2', 'A3', 'A4'];

function initMultiMode() {
  if (multiInitialized) return;
  multiInitialized = true;

  socket = io();

  document.querySelectorAll('.mini-game').forEach((el, idx) => {
    slots.push({
      el,
      roomCode: ROOM_CODES[idx] || null,
      state: null,
      boardEl: null,
      playersEl: null,
      turnEl: null,
      gameOverEl: null,
      myPlayerNumber: null,
      _sel: null,
    });
    el.classList.add('empty');
  });

  socket.on('connect', () => {
    setMultiStatus('✅ Đã kết nối — đang theo dõi');
    socket.emit('spectate', { codes: ROOM_CODES });
    setInterval(() => {
      if (socket.connected) socket.emit('spectate', { codes: ROOM_CODES });
    }, 3000);
  });

  socket.on('connect_error', () => setMultiStatus('❌ Lỗi kết nối server'));
  socket.on('disconnect', () => setMultiStatus('⚠️ Mất kết nối'));

  socket.on('spectate_snapshot', (rooms) => {
    rooms.forEach(state => {
      const slot = slots.find(s => s.roomCode === state.code);
      if (slot) { slot.state = state; renderSlot(slot); }
    });
  });

  socket.on('move_made', ({ code, move, state }) => {
    const slot = slots.find(s => s.roomCode === code);
    if (!slot) return;
    slot.state = state;
    renderSlot(slot);
    flashMove(slot, move);
  });

  socket.on('room_reset', ({ code, state }) => {
    const slot = slots.find(s => s.roomCode === code);
    if (!slot) return;
    slot.state = state;
    renderSlot(slot);
  });

  socket.on('room_deleted', ({ code }) => {
    const slot = slots.find(s => s.roomCode === code);
    if (!slot) return;
    slot.state = null;
    slot.el.innerHTML = '';
    slot.el.classList.add('empty');
    slot.boardEl = null;
  });

  socket.on('room_update', ({ code, state }) => {
    const slot = slots.find(s => s.roomCode === code);
    if (!slot) return;
    slot.state = state;
    renderSlot(slot);
  });

  document.getElementById('btn-join').addEventListener('click', joinRoom);
}

function renderSlot(slot) {
  if (!slot.state) return;
  slot.el.classList.remove('empty');
  if (!slot.boardEl) buildSlotDOM(slot);

  const s = slot.state;
  const [n1, n2] = s.names || ['P1', 'P2'];

  slot.playersEl.innerHTML = `
    <div class="mg-player ${s.currentPlayer === 1 ? 'active-p1' : ''}">
      <span>🔴</span><span class="name">${escapeHtml(n1 || 'P1')}</span>
    </div>
    <div class="mg-player ${s.currentPlayer === 2 ? 'active-p2' : ''}">
      <span class="name">${escapeHtml(n2 || 'P2')}</span><span>🔵</span>
    </div>
  `;

  slot.turnEl.innerHTML = `
    <span class="turn-orb ${s.currentPlayer === 2 ? 'p2' : ''}"></span>
    Turn ${s.turnNumber} — P${s.currentPlayer}
  `;

  renderMiniBoard(slot, s);

  if (s.gameOver) {
    if (!slot.gameOverEl) {
      slot.gameOverEl = document.createElement('div');
      slot.gameOverEl.className = 'mg-gameover';
      slot.el.appendChild(slot.gameOverEl);
    }
    const winnerName = (s.names && s.names[s.winner - 1]) || `P${s.winner}`;
    slot.gameOverEl.innerHTML = `
      <div class="winner">🏆 ${escapeHtml(winnerName)} thắng!</div>
      <div class="reason">${escapeHtml(s.winReason)}</div>
    `;
  } else if (slot.gameOverEl) {
    slot.gameOverEl.remove();
    slot.gameOverEl = null;
  }
}

function buildSlotDOM(slot) {
  slot.el.innerHTML = `
    <div class="mg-info-bar">
      <div class="mg-players" style="display:flex;gap:4px;flex:1;justify-content:space-between;"></div>
      <div class="mg-turn"></div>
    </div>
    <div class="mg-board-wrap">
      <div class="mg-board"></div>
    </div>
  `;
  slot.playersEl = slot.el.querySelector('.mg-players');
  slot.turnEl = slot.el.querySelector('.mg-turn');
  slot.boardEl = slot.el.querySelector('.mg-board');

  slot.boardEl.addEventListener('click', (e) => {
    if (!slot.myPlayerNumber) return;
    const cell = e.target.closest('.cell');
    if (!cell) return;
    const idx = Array.from(slot.boardEl.children).indexOf(cell);
    const row = Math.floor(idx / 9);
    const col = idx % 9;
    handleBoardClick(slot, row, col);
  });
}

function renderMiniBoard(slot, s) {
  const board = slot.boardEl;
  board.innerHTML = '';

  for (let r = 0; r < 9; r++) {
    for (let c = 0; c < 9; c++) {
      const cell = document.createElement('div');
      cell.className = 'cell ' + ((r + c) % 2 === 0 ? 'light' : 'dark');

      if (r === GOALS[1].row && c === GOALS[1].col) cell.classList.add('goal-p1');
      if (r === GOALS[2].row && c === GOALS[2].col) cell.classList.add('goal-p2');

      if (s.lastMove) {
        if (r === s.lastMove.fromRow && c === s.lastMove.fromCol) cell.classList.add('last-from');
        if (r === s.lastMove.toRow && c === s.lastMove.toCol) cell.classList.add('last-to');
      }

      if (slot._sel && slot._sel.row === r && slot._sel.col === c) {
        cell.classList.add('selected');
      }

      const p = s.board[r][c];
      if (p) {
        const pe = document.createElement('span');
        pe.className = `piece p${p.player}`;
        pe.textContent = PIECE_EMOJI[p.type];
        cell.appendChild(pe);
      }
      board.appendChild(cell);
    }
  }
}

function flashMove(slot, move) {
  if (!slot.boardEl) return;
  const cell = slot.boardEl.children[move.toRow * 9 + move.toCol];
  if (!cell) return;
  if (move.isCapture) {
    cell.classList.add('capture-flash');
    setTimeout(() => cell.classList.remove('capture-flash'), 600);
  }
  const piece = cell.querySelector('.piece');
  if (piece) {
    piece.classList.add('just-moved');
    setTimeout(() => piece.classList.remove('just-moved'), 500);
  }
}

function joinRoom() {
  if (!socket) return;
  const code = document.getElementById('mp-room-code').value.trim().toUpperCase();
  const name = document.getElementById('mp-name').value.trim() || 'Player';
  if (!code) return setMultiStatus('⚠️ Nhập mã phòng');

  socket.emit('join_room', { code, name }, (res) => {
    if (res?.error) return setMultiStatus('❌ ' + res.error);
    setMultiStatus(`✅ Đã vào phòng ${code} — Bạn là P${res.playerNumber}`);

    let slot = slots.find(s => s.roomCode === code);
    if (!slot) {
      slot = slots.find(s => !s.state) || slots[0];
      slot.roomCode = code;
    }
    slot.state = res.state;
    slot.myPlayerNumber = res.playerNumber;
    renderSlot(slot);
  });
}

function handleBoardClick(slot, row, col) {
  const s = slot.state;
  if (!s || s.gameOver) return;
  if (s.currentPlayer !== slot.myPlayerNumber) {
    setMultiStatus('⏳ Đang chờ đối thủ...');
    return;
  }

  const p = s.board[row][col];

  if (!slot._sel) {
    if (p && p.player === slot.myPlayerNumber) {
      slot._sel = { row, col };
      renderMiniBoard(slot, s);
    }
    return;
  }

  const from = slot._sel;
  socket.emit('make_move', {
    fromRow: from.row,
    fromCol: from.col,
    toRow: row,
    toCol: col,
  }, (res) => {
    if (res?.error) {
      setMultiStatus('❌ ' + res.error);
      slot._sel = null;
      renderMiniBoard(slot, slot.state);
    } else {
      slot._sel = null;
    }
  });
}

function setMultiStatus(msg) {
  const el = document.getElementById('mp-status');
  if (el) el.textContent = msg;
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}