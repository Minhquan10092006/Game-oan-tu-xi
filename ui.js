/* ============================================
   OẲN TÙ TÌ 2.0 — UI CONTROLLER
   Board rendering, interaction, animations
   ============================================ */

// ---- Global State ----
let game = new GameState();
let selectedCell = null;    // { row, col }
let validMoves = [];        // Current valid moves for selected piece
let lastMove = null;        // For highlighting

// ---- DOM Refs ----
const boardEl = document.getElementById('board');
const turnTextEl = document.getElementById('turn-text');
const turnNumberEl = document.getElementById('turn-number');
const turnOrbEl = document.getElementById('turn-orb');
const statusEl = document.getElementById('status-message');
const moveLogEl = document.getElementById('move-log');
const p1InfoEl = document.getElementById('player1-info');
const p2InfoEl = document.getElementById('player2-info');
const p1PiecesEl = document.getElementById('p1-pieces');
const p2PiecesEl = document.getElementById('p2-pieces');
const victoryOverlay = document.getElementById('victory-overlay');
const victoryTitle = document.getElementById('victory-title');
const victoryMessage = document.getElementById('victory-message');

// ---- Initialize ----
document.addEventListener('DOMContentLoaded', () => {
    initBackgroundCanvas();
    buildCoordLabels();
    renderBoard();
    updateInfoBar();
    setStatus('Chọn một quân cờ để bắt đầu');
});

// ============================================
// BACKGROUND ANIMATED CANVAS
// ============================================
function initBackgroundCanvas() {
    const canvas = document.getElementById('bg-canvas');
    const ctx = canvas.getContext('2d');
    let particles = [];
    let w, h;

    function resize() {
        w = canvas.width = window.innerWidth;
        h = canvas.height = window.innerHeight;
    }
    resize();
    window.addEventListener('resize', resize);

    // Create floating particles
    const PARTICLE_COUNT = 50;
    for (let i = 0; i < PARTICLE_COUNT; i++) {
        particles.push({
            x: Math.random() * w,
            y: Math.random() * h,
            r: Math.random() * 2 + 0.5,
            dx: (Math.random() - 0.5) * 0.3,
            dy: (Math.random() - 0.5) * 0.3,
            opacity: Math.random() * 0.3 + 0.1,
            hue: Math.random() * 60 + 230, // Blue-purple range
        });
    }

    function animate() {
        ctx.clearRect(0, 0, w, h);

        // Draw grid pattern (subtle)
        ctx.strokeStyle = 'rgba(148, 163, 184, 0.02)';
        ctx.lineWidth = 1;
        const gridSize = 60;
        for (let x = 0; x < w; x += gridSize) {
            ctx.beginPath();
            ctx.moveTo(x, 0);
            ctx.lineTo(x, h);
            ctx.stroke();
        }
        for (let y = 0; y < h; y += gridSize) {
            ctx.beginPath();
            ctx.moveTo(0, y);
            ctx.lineTo(w, y);
            ctx.stroke();
        }

        // Draw particles
        for (const p of particles) {
            p.x += p.dx;
            p.y += p.dy;

            if (p.x < 0) p.x = w;
            if (p.x > w) p.x = 0;
            if (p.y < 0) p.y = h;
            if (p.y > h) p.y = 0;

            ctx.beginPath();
            ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
            ctx.fillStyle = `hsla(${p.hue}, 60%, 65%, ${p.opacity})`;
            ctx.fill();
        }

        requestAnimationFrame(animate);
    }
    animate();
}

// ============================================
// COORDINATE LABELS
// ============================================
function buildCoordLabels() {
    const topLabels = document.getElementById('top-labels');
    const bottomLabels = document.getElementById('bottom-labels');
    const leftLabels = document.getElementById('left-labels');
    const rightLabels = document.getElementById('right-labels');

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

// ============================================
// BOARD RENDERING
// ============================================
function renderBoard() {
    boardEl.innerHTML = '';

    for (let r = 0; r < 9; r++) {
        for (let c = 0; c < 9; c++) {
            const cell = document.createElement('div');
            cell.className = 'cell';
            cell.id = `cell-${r}-${c}`;
            cell.dataset.row = r;
            cell.dataset.col = c;

            // Checkerboard pattern
            cell.classList.add((r + c) % 2 === 0 ? 'light' : 'dark');

            // Goal cells
            if (r === GOALS[1].row && c === GOALS[1].col) {
                cell.classList.add('goal-p1');
                cell.dataset.tooltip = 'Đích P1 (1,9)';
            }
            if (r === GOALS[2].row && c === GOALS[2].col) {
                cell.classList.add('goal-p2');
                cell.dataset.tooltip = 'Đích P2 (9,1)';
            }

            // Last move highlights
            if (lastMove) {
                if (r === lastMove.fromRow && c === lastMove.fromCol) {
                    cell.classList.add('last-from');
                }
                if (r === lastMove.toRow && c === lastMove.toCol) {
                    cell.classList.add('last-to');
                }
            }

            // Selected
            if (selectedCell && r === selectedCell.row && c === selectedCell.col) {
                cell.classList.add('selected');
            }

            // Valid move / attack markers
            const moveInfo = validMoves.find(m => m.toRow === r && m.toCol === c);
            if (moveInfo) {
                if (moveInfo.isBlocked) {
                    cell.classList.add('blocked');
                } else if (moveInfo.isCapture) {
                    cell.classList.add('valid-attack');
                } else {
                    cell.classList.add('valid-move');
                }
            }

            // Place piece
            const piece = game.getPiece(r, c);
            if (piece) {
                const pieceEl = document.createElement('span');
                pieceEl.className = `piece p${piece.player}`;
                pieceEl.textContent = piece.emoji;
                pieceEl.dataset.tooltip = `${piece.player === 1 ? 'P1' : 'P2'} ${pieceNameVi(piece.type)}`;
                cell.appendChild(pieceEl);
            }

            // Click handler
            cell.addEventListener('click', () => onCellClick(r, c));

            boardEl.appendChild(cell);
        }
    }
}

// ============================================
// CLICK HANDLING
// ============================================
function onCellClick(row, col) {
    if (game.gameOver) return;

    const piece = game.getPiece(row, col);

    // If clicking a valid move/attack destination
    if (selectedCell) {
        const move = validMoves.find(m => m.toRow === row && m.toCol === col && !m.isBlocked);
        if (move) {
            executePlayerMove(selectedCell.row, selectedCell.col, row, col, move);
            return;
        }
    }

    // If clicking own piece — select it
    if (piece && piece.player === game.currentPlayer) {
        selectPiece(row, col);
        return;
    }

    // Clicking empty or opponent's piece with no selection — deselect
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

function executePlayerMove(fromRow, fromCol, toRow, toCol, moveInfo) {
    const moveRecord = game.executeMove(fromRow, fromCol, toRow, toCol);
    if (!moveRecord) return;

    lastMove = moveRecord;
    selectedCell = null;
    validMoves = [];

    // Animate
    renderBoard();
    animateMove(toRow, toCol, moveRecord.isCapture);
    addMoveLog(moveRecord);
    updateInfoBar();

    // Check game over
    if (game.gameOver) {
        setTimeout(() => showVictory(), 600);
    } else {
        setStatus(`Lượt Player ${game.currentPlayer} — Chọn quân cờ`);
    }
}

// ============================================
// ANIMATIONS
// ============================================
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

// ============================================
// UI UPDATES
// ============================================
function updateInfoBar() {
    // Turn indicator
    turnTextEl.textContent = `Lượt Player ${game.currentPlayer}`;
    turnNumberEl.textContent = `Turn ${game.turnNumber}`;
    turnOrbEl.className = `turn-orb ${game.currentPlayer === 2 ? 'p2' : ''}`;

    // Active player highlight
    p1InfoEl.classList.toggle('active-player', game.currentPlayer === 1);
    p2InfoEl.classList.toggle('active-player', game.currentPlayer === 2);

    // Piece counts
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
    statusEl.textContent = msg;
}

function addMoveLog(moveRecord) {
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

// ============================================
// VICTORY
// ============================================
function showVictory() {
    victoryOverlay.classList.remove('hidden');
    victoryTitle.textContent = `🎉 Player ${game.winner} Chiến Thắng!`;
    victoryMessage.textContent = game.winReason;
    createVictoryParticles();
}

function hideVictory() {
    victoryOverlay.classList.add('hidden');
}

function createVictoryParticles() {
    const container = document.getElementById('victory-particles');
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
            width: ${size}px;
            height: ${size}px;
            background: ${color};
            border-radius: ${Math.random() > 0.5 ? '50%' : '2px'};
            left: ${x}%;
            top: -10px;
            opacity: 0.8;
            animation: confettiFall ${duration}s ease-in ${delay}s infinite;
        `;
        container.appendChild(particle);
    }

    // Add confetti animation if not exists
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

// ============================================
// GAME CONTROLS
// ============================================
function newGame() {
    game = new GameState();
    selectedCell = null;
    validMoves = [];
    lastMove = null;
    moveLogEl.innerHTML = '';
    hideVictory();
    renderBoard();
    updateInfoBar();
    setStatus('Ván mới! Player 1 đi trước — Chọn quân cờ');
}

function undoMove() {
    if (game.moveHistory.length === 0) {
        setStatus('Không có nước đi nào để hoàn tác');
        return;
    }

    const wasGameOver = game.gameOver;
    const undone = game.undoLastMove();
    if (!undone) return;

    if (wasGameOver) {
        hideVictory();
    }

    selectedCell = null;
    validMoves = [];

    // Update last move reference
    lastMove = game.moveHistory.length > 0 ? game.moveHistory[game.moveHistory.length - 1] : null;

    // Remove last log entry
    const lastLog = moveLogEl.lastElementChild;
    if (lastLog) lastLog.remove();

    renderBoard();
    updateInfoBar();
    setStatus(`Đã hoàn tác — Lượt Player ${game.currentPlayer}`);
}

// ============================================
// KEYBOARD SUPPORT
// ============================================
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        deselectPiece();
    }
    if (e.key === 'z' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        undoMove();
    }
    if (e.key === 'n' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        newGame();
    }
});
