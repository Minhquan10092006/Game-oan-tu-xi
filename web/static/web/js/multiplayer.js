/* ============================================
   OẲN TÙ TÌ 2.0 — MULTIPLAYER VIEW (DJANGO CHANNELS)
   ============================================ */

let socket = null;
const slots = [];
let multiInitialized = false;
let spectateInterval = null;
let currentJoinedRoom = null;
const ROOM_CODES = ['A1', 'A2', 'A3', 'A4'];

// Tên hiển thị cho loại quân (tiếng Việt)
const PIECE_NAME = { rock: 'Búa', paper: 'Bao', scissors: 'Kéo' };

// Chuyển tọa độ 0-indexed → ký hiệu bàn cờ "A1" … "I9"
function toNotation(row, col) {
  return String.fromCharCode(65 + col) + (row + 1);
}

/**
 * GameSocket: Client WebSocket tương thích chuẩn Django Channels.
 * Tự động chọn ws:// hoặc wss://, tự động fallback nếu mở file:// hoặc qua Live Server.
 */
class GameSocket {
  constructor() {
    this.ws = null;
    this.handlers = {};
    this.pendingCallbacks = {};
    this.callbackId = 0;
    this.connected = false;
    this.reconnectTimer = null;
    this.pingTimer = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 30;
    this.isManualClose = false;
    this.connect();
  }

  getWsUrl() {
    let host = window.location.host;
    let protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // Fallback nếu mở qua file:// hoặc port ngoài Django (vd: Live Server 5500, hay node 3000)
    if (!host || window.location.protocol === 'file:' || host.includes(':5500') || host.includes(':3000')) {
      host = '127.0.0.1:8000';
      protocol = 'ws:';
    }
    return `${protocol}//${host}/ws/multiplayer/`;
  }

  connect() {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    const url = this.getWsUrl();
    setMultiStatus('🔄 Đang kết nối máy chủ Django...');

    try {
      this.ws = new WebSocket(url);
    } catch (e) {
      console.warn('Lỗi khởi tạo WebSocket:', e);
      this._emit('connect_error', e);
      this._scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      this.connected = true;
      this.reconnectAttempts = 0;
      this._startPing();
      this._emit('connect');
    };

    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg._reqId !== undefined && this.pendingCallbacks[msg._reqId]) {
          const cb = this.pendingCallbacks[msg._reqId];
          delete this.pendingCallbacks[msg._reqId];
          cb(msg);
        }
        if (msg.event) {
          const payload = msg.payload !== undefined ? msg.payload : msg;
          this._emit(msg.event, payload);
        }
      } catch (err) {
        console.error('Lỗi nhận dữ liệu WebSocket:', err);
      }
    };

    this.ws.onerror = (err) => {
      this._emit('connect_error', err);
    };

    this.ws.onclose = () => {
      const wasConnected = this.connected;
      this.connected = false;
      this._stopPing();
      if (wasConnected) {
        this._emit('disconnect');
      }
      if (!this.isManualClose) {
        this._scheduleReconnect();
      }
    };
  }

  _startPing() {
    this._stopPing();
    this.pingTimer = setInterval(() => {
      if (this.connected && this.ws?.readyState === WebSocket.OPEN) {
        this.emit('ping');
      }
    }, 25000);
  }

  _stopPing() {
    if (this.pingTimer) {
      clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
  }

  _scheduleReconnect() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      this._emit('reconnect_failed');
      return;
    }
    this.reconnectAttempts++;
    const delay = Math.min(1000 * Math.pow(1.3, this.reconnectAttempts - 1), 5000);
    this.reconnectTimer = setTimeout(() => {
      this.connect();
    }, delay);
  }

  on(event, handler) {
    if (!this.handlers[event]) {
      this.handlers[event] = [];
    }
    this.handlers[event].push(handler);
  }

  _emit(event, ...args) {
    if (this.handlers[event]) {
      this.handlers[event].forEach(fn => {
        try {
          fn(...args);
        } catch (e) {
          console.error(`Lỗi trong handler event '${event}':`, e);
        }
      });
    }
  }

  emit(event, data = {}, callback = null) {
    if (!this.connected || !this.ws || this.ws.readyState !== WebSocket.OPEN) {
      if (typeof callback === 'function') {
        callback({ error: 'Chưa kết nối máy chủ Django' });
      }
      return;
    }
    const payload = { event, ...data };
    if (typeof callback === 'function') {
      const reqId = ++this.callbackId;
      this.pendingCallbacks[reqId] = callback;
      payload._reqId = reqId;
    }
    this.ws.send(JSON.stringify(payload));
  }

  close() {
    this.isManualClose = true;
    this._stopPing();
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    if (this.ws) this.ws.close();
  }
}

/**
 * Tính toán các nước đi hợp lệ theo luật Oẳn Tù Tì
 */
function getValidMoves(board, row, col, player) {
  const piece = board[row]?.[col];
  if (!piece || piece.player !== player) return [];

  const moves = [];
  const BEATS_RULE = { rock: 'scissors', scissors: 'paper', paper: 'rock' };

  for (let dr = -1; dr <= 1; dr++) {
    for (let dc = -1; dc <= 1; dc++) {
      if (dr === 0 && dc === 0) continue;
      const tr = row + dr;
      const tc = col + dc;
      if (tr < 0 || tr > 8 || tc < 0 || tc > 8) continue;

      const target = board[tr][tc];
      if (!target) {
        moves.push({ row: tr, col: tc, isAttack: false });
      } else {
        if (target.player === piece.player) continue;
        if (target.type === piece.type) continue;
        if (BEATS_RULE[piece.type] === target.type) {
          moves.push({ row: tr, col: tc, isAttack: true });
        }
      }
    }
  }
  return moves;
}

// ── Khởi tạo chế độ Multiplayer ──────────────────────────────────────

function initMultiMode() {
  if (multiInitialized) {
    if (socket && !socket.connected) socket.connect();
    return;
  }
  multiInitialized = true;

  // Điền sẵn tên người dùng nếu có
  const nameInput = document.getElementById('mp-name');
  if (nameInput && !nameInput.value) {
    const savedName = localStorage.getItem('mp_player_name');
    const authUsername = document.body?.dataset?.username;
    nameInput.value = authUsername || savedName || 'Player 1';
  }

  // Tạo các slot nếu chưa có
  if (slots.length === 0) {
    document.querySelectorAll('.mini-game').forEach((el, idx) => {
      slots.push({
        el,
        roomCode: ROOM_CODES[idx] || null,
        state: null,
        boardEl: null,
        playersEl: null,
        turnEl: null,
        gameOverEl: null,
        spectatorEl: null,
        spectatorModeEl: null,
        moveLogEl: null,
        actionsEl: null,
        turnBannerEl: null,
        myPlayerNumber: null,
        isSpectating: false,
        _sel: null,
        _validMoves: [],
      });
      el.classList.add('empty');

      // Click vào slot để tự động chọn phòng
      el.addEventListener('click', (e) => {
        if (e.target.closest('.mg-quick-btn') || e.target.closest('.cell')) return;
        const codeInput = document.getElementById('mp-room-code');
        if (codeInput && ROOM_CODES[idx]) {
          codeInput.value = ROOM_CODES[idx];
          setMultiStatus(`👉 Đã chọn phòng ${ROOM_CODES[idx]} — Nhấn 'Vào phòng' để chơi`);
        }
      });
    });
  }

  // Kết nối WebSocket
  if (!socket) {
    socket = new GameSocket();
  } else if (!socket.connected) {
    socket.connect();
  }

  // ── Lắng nghe sự kiện Socket ───────────────────────────────────────

  socket.on('connect', () => {
    setMultiStatus('✅ Đã kết nối Django — Đang theo dõi các phòng');
    socket.emit('spectate', { codes: ROOM_CODES });
    if (!spectateInterval) {
      spectateInterval = setInterval(() => {
        if (socket && socket.connected) {
          socket.emit('spectate', { codes: ROOM_CODES });
        }
      }, 3000);
    }
  });

  socket.on('connect_error', () => {
    setMultiStatus('❌ Đang chờ kết nối máy chủ Django (port 8000)...');
  });

  socket.on('disconnect', () => {
    setMultiStatus('⚠️ Mất kết nối — Đang thử lại...');
  });

  socket.on('reconnect_failed', () => {
    setMultiStatus('❌ Không thể kết nối lại. Hãy đảm bảo lệnh "python manage.py runserver" đang chạy.');
  });

  socket.on('spectate_snapshot', (rooms) => {
    rooms.forEach(state => {
      const slot = slots.find(s => s.roomCode === state.code);
      if (slot) {
        slot.state = state;
        renderSlot(slot);
      }
    });
  });

  socket.on('move_made', ({ code, move, state }) => {
    const slot = slots.find(s => s.roomCode === code);
    if (!slot) return;
    slot.state = state;
    slot._sel = null;
    slot._validMoves = [];
    renderSlot(slot);
    flashMove(slot, move);
    appendMoveLog(slot, move);
  });

  socket.on('room_reset', ({ code, state }) => {
    const slot = slots.find(s => s.roomCode === code);
    if (!slot) return;
    slot.state = state;
    slot._sel = null;
    slot._validMoves = [];
    if (slot.moveLogEl) slot.moveLogEl.innerHTML = '';
    renderSlot(slot);
    setMultiStatus(`🔄 Phòng ${code} đã làm mới ván cờ!`);
  });

  socket.on('room_deleted', ({ code }) => {
    const slot = slots.find(s => s.roomCode === code);
    if (!slot) return;
    slot.state = null;
    slot.isSpectating = false;
    slot.myPlayerNumber = null;
    slot._sel = null;
    slot._validMoves = [];
    slot.el.innerHTML = '';
    slot.el.classList.add('empty');
    slot.boardEl = null;
    slot.spectatorEl = null;
    slot.moveLogEl = null;
  });

  socket.on('room_update', ({ code, state }) => {
    const slot = slots.find(s => s.roomCode === code);
    if (!slot) return;
    slot.state = state;
    renderSlot(slot);
  });

  socket.on('spectator_count', ({ code, count, max }) => {
    const slot = slots.find(s => s.roomCode === code);
    if (!slot) return;
    if (slot.state) slot.state.spectatorCount = count;
    updateSpectatorBadge(slot, count, max);
  });

  // Gắn sự kiện các nút
  const joinBtn = document.getElementById('btn-join');
  if (joinBtn) joinBtn.onclick = () => joinRoom();

  const spectateBtn = document.getElementById('btn-spectate');
  if (spectateBtn) spectateBtn.onclick = () => spectateRoom();

  const leaveBtn = document.getElementById('btn-leave');
  if (leaveBtn) leaveBtn.onclick = () => leaveCurrentRoom();

  const resetBtn = document.getElementById('btn-reset');
  if (resetBtn) resetBtn.onclick = () => resetCurrentRoom();
}

// ── Render Slot ──────────────────────────────────────────────────────

function renderSlot(slot) {
  if (!slot.state) return;
  slot.el.classList.remove('empty');
  if (!slot.boardEl) buildSlotDOM(slot);

  const s = slot.state;
  const [n1, n2] = s.names || ['P1', 'P2'];
  const isMyRoom = (currentJoinedRoom === slot.roomCode);

  if (isMyRoom) {
    slot.el.classList.add('active-my-room');
  } else {
    slot.el.classList.remove('active-my-room');
  }

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
    T${s.turnNumber}·P${s.currentPlayer}
  `;

  const cnt = s.spectatorCount || 0;
  const max = s.maxSpectators || 10;
  updateSpectatorBadge(slot, cnt, max);

  // Hiển thị banner trạng thái người chơi
  if (slot.turnBannerEl) {
    if (slot.myPlayerNumber) {
      slot.turnBannerEl.style.display = 'block';
      if (s.gameOver) {
        slot.turnBannerEl.innerHTML = `<span style="color:#f59e0b">🏁 Ván cờ đã kết thúc</span>`;
      } else if (s.currentPlayer === slot.myPlayerNumber) {
        slot.turnBannerEl.innerHTML = `<span style="color:#22c55e;font-weight:700">🎯 LƯỢT CỦA BẠN (P${slot.myPlayerNumber}) — Chọn quân để đi</span>`;
      } else {
        slot.turnBannerEl.innerHTML = `<span style="color:#8b5cf6">⏳ Đang chờ P${s.currentPlayer} đi nước...</span>`;
      }
    } else if (slot.isSpectating) {
      slot.turnBannerEl.style.display = 'block';
      slot.turnBannerEl.innerHTML = `<span style="color:#60a5fa">👁 Bạn đang xem trận đấu này</span>`;
    } else {
      slot.turnBannerEl.style.display = 'none';
    }
  }

  // Cập nhật nút nhanh trên slot
  if (slot.actionsEl) {
    if (!slot.myPlayerNumber && !slot.isSpectating) {
      slot.actionsEl.style.display = 'flex';
    } else {
      slot.actionsEl.style.display = 'none';
    }
  }

  renderMiniBoard(slot, s);

  // Xử lý GameOver
  if (s.gameOver) {
    if (!slot.gameOverEl) {
      slot.gameOverEl = document.createElement('div');
      slot.gameOverEl.className = 'mg-gameover';
      slot.el.appendChild(slot.gameOverEl);
    }
    const winnerName = (s.names && s.names[s.winner - 1]) || `P${s.winner}`;
    slot.gameOverEl.innerHTML = `
      <div class="winner">🏆 ${escapeHtml(winnerName)} thắng!</div>
      <div class="reason">${escapeHtml(s.winReason || '')}</div>
      ${slot.myPlayerNumber ? `<button class="game-btn primary-btn" style="margin-top:6px;padding:4px 12px;font-size:0.75rem" onclick="resetCurrentRoom()">🔄 Chơi lại hiệp mới</button>` : ''}
    `;
  } else if (slot.gameOverEl) {
    slot.gameOverEl.remove();
    slot.gameOverEl = null;
  }
}

function updateSpectatorBadge(slot, count, max) {
  if (!slot.spectatorEl) return;
  const full = count >= max;
  slot.spectatorEl.textContent = `👁 ${count}/${max}`;
  slot.spectatorEl.style.color = full ? '#f44336' : count > 0 ? '#7c6fff' : '#666';
  slot.spectatorEl.title = `${count}/${max} người xem`;
}

function buildSlotDOM(slot) {
  slot.el.innerHTML = `
    <div class="mg-info-bar">
      <div style="font-weight:700;color:var(--accent-gold);">${slot.roomCode}</div>
      <div class="mg-players" style="display:flex;gap:4px;flex:1;justify-content:center;min-width:0"></div>
      <div style="display:flex;align-items:center;gap:5px;flex-shrink:0">
        <span class="mg-spectator-badge" style="font-size:0.65rem;cursor:default"></span>
        <div class="mg-turn"></div>
      </div>
    </div>
    <div class="mg-slot-actions" style="display:flex;gap:4px;justify-content:center;padding:2px 0;">
      <button class="mg-quick-btn join-btn" style="padding:2px 8px;font-size:0.65rem;border-radius:4px;background:var(--accent-purple);color:#fff;border:none;cursor:pointer;">🎮 Vào chơi</button>
      <button class="mg-quick-btn spec-btn" style="padding:2px 8px;font-size:0.65rem;border-radius:4px;background:rgba(255,255,255,0.08);color:#ddd;border:none;cursor:pointer;">👁 Xem</button>
    </div>
    <div class="mg-turn-banner" style="display:none;font-size:0.68rem;text-align:center;padding:2px;background:rgba(0,0,0,0.3);border-radius:4px;"></div>
    <div style="display:flex;gap:6px;flex:1;min-height:0">
      <div class="mg-board-wrap" style="flex:1">
        <div class="mg-board"></div>
      </div>
      <div class="mg-move-log-wrap">
        <div class="mg-move-log-title">📜 Nước đi</div>
        <div class="mg-move-log"></div>
      </div>
    </div>
  `;

  slot.playersEl     = slot.el.querySelector('.mg-players');
  slot.turnEl        = slot.el.querySelector('.mg-turn');
  slot.boardEl       = slot.el.querySelector('.mg-board');
  slot.spectatorEl   = slot.el.querySelector('.mg-spectator-badge');
  slot.actionsEl     = slot.el.querySelector('.mg-slot-actions');
  slot.turnBannerEl  = slot.el.querySelector('.mg-turn-banner');
  slot.moveLogEl     = slot.el.querySelector('.mg-move-log');

  // Nút nhanh
  slot.actionsEl.querySelector('.join-btn').onclick = (e) => {
    e.stopPropagation();
    joinRoom(slot.roomCode);
  };
  slot.actionsEl.querySelector('.spec-btn').onclick = (e) => {
    e.stopPropagation();
    spectateRoom(slot.roomCode);
  };

  // Click trên bàn cờ
  slot.boardEl.addEventListener('click', (e) => {
    if (!slot.myPlayerNumber) {
      // Nếu chưa vào phòng, click vào bàn cờ hỏi vào phòng
      const codeInput = document.getElementById('mp-room-code');
      if (codeInput) codeInput.value = slot.roomCode;
      setMultiStatus(`👉 Nhấn '🎮 Vào phòng' để tham gia phòng ${slot.roomCode}`);
      return;
    }
    const cell = e.target.closest('.cell');
    if (!cell) return;
    const idx = Array.from(slot.boardEl.children).indexOf(cell);
    const row = Math.floor(idx / 9);
    const col = idx % 9;
    handleBoardClick(slot, row, col);
  });
}

// ── Move Log ─────────────────────────────────────────────────────────

function appendMoveLog(slot, move) {
  if (!slot.moveLogEl) return;

  const from = toNotation(move.fromRow, move.fromCol);
  const to   = toNotation(move.toRow,   move.toCol);
  const pColor = move.player === 1 ? 'p1' : 'p2';
  const pLabel = move.player === 1 ? '🔴' : '🔵';
  const pieceName = PIECE_NAME[move.piece?.type] || '?';

  let entry = `<div class="mg-log-entry ${pColor}">
    <span class="mg-log-icon">${pLabel}</span>
    <span class="mg-log-move">${from}→${to}</span>
    <span class="mg-log-piece">${pieceName}</span>`;

  if (move.isCapture && move.captured) {
    const capturedName = PIECE_NAME[move.captured.type] || '?';
    const enemyColor   = move.player === 1 ? 'p2' : 'p1';
    entry += `<span class="mg-log-capture ${enemyColor}">⚔️${capturedName}</span>`;
  }
  entry += `</div>`;

  slot.moveLogEl.insertAdjacentHTML('afterbegin', entry);

  const entries = slot.moveLogEl.querySelectorAll('.mg-log-entry');
  if (entries.length > 30) entries[entries.length - 1].remove();
}

// ── Render Board & Valid Moves ───────────────────────────────────────

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
        if (r === s.lastMove.toRow   && c === s.lastMove.toCol)   cell.classList.add('last-to');
      }

      // Highlight quân đang chọn
      if (slot._sel && slot._sel.row === r && slot._sel.col === c) {
        cell.classList.add('selected');
      }

      // Highlight các nước đi hợp lệ
      if (slot._validMoves && slot._validMoves.length > 0) {
        const vm = slot._validMoves.find(m => m.row === r && m.col === c);
        if (vm) {
          if (vm.isAttack) {
            cell.classList.add('valid-attack');
          } else {
            cell.classList.add('valid-move');
          }
        }
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

// ── Tham Gia / Xem Phòng ─────────────────────────────────────────────

function joinRoom(presetCode = null) {
  if (!socket) socket = new GameSocket();
  if (!socket.connected) {
    socket.connect();
    return setMultiStatus('⏳ Đang kết nối máy chủ Django... vui lòng thử lại sau vài giây');
  }

  const codeInput = document.getElementById('mp-room-code');
  const nameInput = document.getElementById('mp-name');
  const code = (presetCode || codeInput?.value || 'A1').trim().toUpperCase();
  const name = (nameInput?.value || localStorage.getItem('mp_player_name') || 'Player').trim();

  if (codeInput) codeInput.value = code;
  if (nameInput) nameInput.value = name;
  localStorage.setItem('mp_player_name', name);

  setMultiStatus(`🔄 Đang vào phòng ${code}...`);

  socket.emit('join_room', { code, name }, (res) => {
    if (res?.error) return setMultiStatus('❌ ' + res.error);

    currentJoinedRoom = code;
    setMultiStatus(`✅ ĐÃ VÀO PHÒNG ${code} — Bạn là Player ${res.playerNumber} (${res.playerNumber === 1 ? '🔴 Đỏ' : '🔵 Xanh'})`);

    // Hiện nút Rời phòng & Ván mới
    const leaveBtn = document.getElementById('btn-leave');
    const resetBtn = document.getElementById('btn-reset');
    if (leaveBtn) leaveBtn.style.display = 'inline-block';
    if (resetBtn) resetBtn.style.display = 'inline-block';

    // Cập nhật lại các slot
    slots.forEach(s => {
      if (s.roomCode === code) {
        s.state = res.state;
        s.myPlayerNumber = res.playerNumber;
        s.isSpectating = false;
        s._sel = null;
        s._validMoves = [];
        renderSlot(s);
      } else {
        s.myPlayerNumber = null;
        s.isSpectating = false;
        s._sel = null;
        s._validMoves = [];
        if (s.state) renderSlot(s);
      }
    });
  });
}

function spectateRoom(presetCode = null) {
  if (!socket) socket = new GameSocket();
  if (!socket.connected) {
    socket.connect();
    return setMultiStatus('⏳ Đang kết nối máy chủ Django...');
  }

  const codeInput = document.getElementById('mp-room-code');
  const nameInput = document.getElementById('mp-name');
  const code = (presetCode || codeInput?.value || 'A1').trim().toUpperCase();
  const name = (nameInput?.value || 'Khán giả').trim();

  if (codeInput) codeInput.value = code;

  socket.emit('join_spectate', { code, name }, (res) => {
    if (res?.error) return setMultiStatus('❌ ' + res.error);

    currentJoinedRoom = code;
    setMultiStatus(`👁 Đang xem phòng ${code} — ${res.spectatorCount}/${res.maxSpectators} khán giả`);

    const leaveBtn = document.getElementById('btn-leave');
    const resetBtn = document.getElementById('btn-reset');
    if (leaveBtn) leaveBtn.style.display = 'inline-block';
    if (resetBtn) resetBtn.style.display = 'none';

    slots.forEach(s => {
      if (s.roomCode === code) {
        s.state = res.state;
        s.myPlayerNumber = null;
        s.isSpectating = true;
        s._sel = null;
        s._validMoves = [];
        renderSlot(s);
      } else {
        s.myPlayerNumber = null;
        s.isSpectating = false;
        s._sel = null;
        s._validMoves = [];
        if (s.state) renderSlot(s);
      }
    });
  });
}

function leaveCurrentRoom() {
  if (!socket || !currentJoinedRoom) return;
  socket.emit('leave_room', {}, () => {
    setMultiStatus(`🚪 Đã rời phòng ${currentJoinedRoom} — Chuyển về chế độ theo dõi`);
    currentJoinedRoom = null;

    const leaveBtn = document.getElementById('btn-leave');
    const resetBtn = document.getElementById('btn-reset');
    if (leaveBtn) leaveBtn.style.display = 'none';
    if (resetBtn) resetBtn.style.display = 'none';

    slots.forEach(s => {
      s.myPlayerNumber = null;
      s.isSpectating = false;
      s._sel = null;
      s._validMoves = [];
      if (s.state) renderSlot(s);
    });

    socket.emit('spectate', { codes: ROOM_CODES });
  });
}

function resetCurrentRoom() {
  if (!socket || !currentJoinedRoom) return;
  socket.emit('reset_room', {});
  setMultiStatus(`🔄 Đang khởi tạo ván mới...`);
}

// ── Xử lý Click Bàn Cờ & Di Chuyển Quân ──────────────────────────────

function handleBoardClick(slot, row, col) {
  const s = slot.state;
  if (!s || s.gameOver) return;

  if (slot.isSpectating) {
    setMultiStatus('👁 Bạn đang ở chế độ xem, không thể đi nước');
    return;
  }
  if (s.currentPlayer !== slot.myPlayerNumber) {
    setMultiStatus(`⏳ Chưa đến lượt bạn! Lượt của Player ${s.currentPlayer}`);
    return;
  }

  const p = s.board[row][col];

  // Nếu chưa chọn quân cờ nào
  if (!slot._sel) {
    if (p && p.player === slot.myPlayerNumber) {
      slot._sel = { row, col };
      slot._validMoves = getValidMoves(s.board, row, col, slot.myPlayerNumber);
      renderMiniBoard(slot, s);
      setMultiStatus(`👉 Đã chọn quân ${PIECE_NAME[p.type]} tại ${toNotation(row, col)} — Bấm ô hợp lệ để đi`);
    } else {
      setMultiStatus('⚠️ Hãy bấm vào một quân cờ của bạn (màu ' + (slot.myPlayerNumber === 1 ? 'Đỏ 🔴' : 'Xanh 🔵') + ')');
    }
    return;
  }

  // Nếu click lại chính quân đang chọn -> Bỏ chọn
  if (slot._sel.row === row && slot._sel.col === col) {
    slot._sel = null;
    slot._validMoves = [];
    renderMiniBoard(slot, s);
    setMultiStatus('Đã bỏ chọn quân cờ');
    return;
  }

  // Nếu click vào một quân khác của phe mình -> Đổi chọn sang quân đó
  if (p && p.player === slot.myPlayerNumber) {
    slot._sel = { row, col };
    slot._validMoves = getValidMoves(s.board, row, col, slot.myPlayerNumber);
    renderMiniBoard(slot, s);
    setMultiStatus(`👉 Đã chuyển chọn quân ${PIECE_NAME[p.type]} tại ${toNotation(row, col)}`);
    return;
  }

  // Kiểm tra xem ô đích có nằm trong danh sách nước đi hợp lệ không
  const isMoveValid = slot._validMoves && slot._validMoves.some(m => m.row === row && m.col === col);
  if (!isMoveValid) {
    setMultiStatus('❌ Nước đi không hợp lệ theo luật Oẳn Tù Tì!');
    return;
  }

  // Thực hiện nước đi
  const from = slot._sel;
  slot._sel = null;
  slot._validMoves = [];
  renderMiniBoard(slot, s);

  socket.emit('make_move', {
    fromRow: from.row,
    fromCol: from.col,
    toRow: row,
    toCol: col,
  }, (res) => {
    if (res?.error) {
      setMultiStatus('❌ ' + res.error);
      renderMiniBoard(slot, slot.state);
    }
  });
}

// ── Helpers ──────────────────────────────────────────────────────────

function setMultiStatus(msg) {
  const el = document.getElementById('mp-status');
  if (el) el.textContent = msg;
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

// Tự động kết nối ngay khi tải trang
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    initMultiMode();
  });
} else {
  initMultiMode();
}
