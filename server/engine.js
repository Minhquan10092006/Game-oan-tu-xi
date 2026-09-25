/* ============================================
   OẲN TÙ TÌ 2.0 — GAME ENGINE
   Core game logic, state management, and rules
   ============================================ */

/**
 * Piece types with their display emoji and combat relationships.
 */
const PieceType = Object.freeze({
    ROCK: 'rock',
    PAPER: 'paper',
    SCISSORS: 'scissors',
});

/**
 * Combat lookup: key beats value.
 * Rock > Scissors, Scissors > Paper, Paper > Rock
 */
const BEATS = Object.freeze({
    [PieceType.ROCK]: PieceType.SCISSORS,
    [PieceType.SCISSORS]: PieceType.PAPER,
    [PieceType.PAPER]: PieceType.ROCK,
});

/**
 * Emoji representation for each piece type, per player.
 * P1 uses warm-toned variants, P2 uses cool-toned variants (visually distinguished by glow).
 */
const PIECE_EMOJI = Object.freeze({
    [PieceType.ROCK]: '🪨',
    [PieceType.PAPER]: '📄',
    [PieceType.SCISSORS]: '✂️',
});

/**
 * 8 possible directions of king-like movement (dx, dy).
 */
const DIRECTIONS = Object.freeze([
    [-1, -1], [-1, 0], [-1, 1],
    [0, -1],           [0, 1],
    [1, -1],  [1, 0],  [1, 1],
]);

/**
 * Goal cells for each player.
 * Player 1 must reach (8, 8) — displayed as (9, 9) (opponent base)
 * Player 2 must reach (0, 0) — displayed as (1, 1) (opponent base)
 * Using 0-indexed internally.
 */
const GOALS = Object.freeze({
    1: { row: 8, col: 8 },  // Player 1 goal: (9, 9) in 1-indexed
    2: { row: 0, col: 0 },  // Player 2 goal: (1, 1) in 1-indexed
});

/**
 * Represents a piece on the board.
 */
class Piece {
    constructor(player, type) {
        this.player = player;  // 1 or 2
        this.type = type;      // PieceType enum value
        this.id = `p${player}-${type}-${Piece._counter++}`;
    }

    get emoji() {
        return PIECE_EMOJI[this.type];
    }

    /**
     * Check if this piece beats another piece.
     */
    beats(other) {
        if (this.player === other.player) return false;
        return BEATS[this.type] === other.type;
    }

    /**
     * Check if this piece is the same type as another.
     */
    sameType(other) {
        return this.type === other.type;
    }

    clone() {
        const p = new Piece(this.player, this.type);
        p.id = this.id;
        return p;
    }
}
Piece._counter = 0;

/**
 * Represents the full game state.
 */
class GameState {
    constructor() {
        this.board = this._createEmptyBoard();
        this.currentPlayer = 1;
        this.turnNumber = 1;
        this.moveHistory = [];
        this.gameOver = false;
        this.winner = null;
        this.winReason = '';
        this._setupInitialPieces();
    }

    _createEmptyBoard() {
        const board = [];
        for (let r = 0; r < 9; r++) {
            board.push(new Array(9).fill(null));
        }
        return board;
    }

    /**
     * Symmetrical initial setup.
     * Player 1 pieces are placed in the top-left quadrant area.
     * Player 2 pieces are mirrored across the main diagonal (swap row/col).
     * 
     * Layout (0-indexed):
     * P1 has pieces near (0,0), P2 has pieces near (8,8).
     * Symmetry: if P1 has piece at (r, c), P2 has same type at (8-r, 8-c).
     * This gives rotational symmetry (180° rotation).
     * 
     * Each player gets: 3 Rocks, 3 Papers, 3 Scissors = 9 pieces each.
     */
    _setupInitialPieces() {
        Piece._counter = 0;

        // Player 1 piece positions (0-indexed row, col)
        const p1Layout = [
            // Row 0: R P S
            { row: 0, col: 0, type: PieceType.SCISSORS },
            { row: 0, col: 1, type: PieceType.ROCK },
            { row: 0, col: 2, type: PieceType.PAPER },
            // Row 1: P S R
            { row: 1, col: 0, type: PieceType.PAPER },
            { row: 1, col: 1, type: PieceType.SCISSORS },
            { row: 1, col: 2, type: PieceType.ROCK },
            // Row 2: S R P
            { row: 2, col: 0, type: PieceType.ROCK },
            { row: 2, col: 1, type: PieceType.PAPER },
            { row: 2, col: 2, type: PieceType.SCISSORS },
        ];

        // Place Player 1 pieces
        for (const { row, col, type } of p1Layout) {
            this.board[row][col] = new Piece(1, type);
        }

        // Player 2 pieces: 180° rotation symmetry → (8 - row, 8 - col), same type
        for (const { row, col, type } of p1Layout) {
            this.board[8 - row][8 - col] = new Piece(2, type);
        }
    }

    /**
     * Get the piece at a given position.
     */
    getPiece(row, col) {
        if (row < 0 || row > 8 || col < 0 || col > 8) return undefined;
        return this.board[row][col];
    }

    /**
     * Get all pieces for a given player.
     */
    getPlayerPieces(player) {
        const pieces = [];
        for (let r = 0; r < 9; r++) {
            for (let c = 0; c < 9; c++) {
                const p = this.board[r][c];
                if (p && p.player === player) {
                    pieces.push({ piece: p, row: r, col: c });
                }
            }
        }
        return pieces;
    }

    /**
     * Count pieces by type for a given player.
     */
    countPieces(player) {
        const counts = { rock: 0, paper: 0, scissors: 0, total: 0 };
        for (let r = 0; r < 9; r++) {
            for (let c = 0; c < 9; c++) {
                const p = this.board[r][c];
                if (p && p.player === player) {
                    counts[p.type]++;
                    counts.total++;
                }
            }
        }
        return counts;
    }

    /**
     * Check if a move is valid.
     * Returns: { valid: bool, reason: string, isCapture: bool }
     */
    validateMove(fromRow, fromCol, toRow, toCol) {
        // Check bounds
        if (toRow < 0 || toRow > 8 || toCol < 0 || toCol > 8) {
            return { valid: false, reason: 'Ngoài bàn cờ' };
        }

        // Check source has current player's piece
        const piece = this.board[fromRow][fromCol];
        if (!piece) {
            return { valid: false, reason: 'Không có quân cờ tại vị trí này' };
        }
        if (piece.player !== this.currentPlayer) {
            return { valid: false, reason: 'Không phải quân của bạn' };
        }

        // Check movement is exactly 1 cell in any direction (king-like)
        const dr = Math.abs(toRow - fromRow);
        const dc = Math.abs(toCol - fromCol);
        if (dr > 1 || dc > 1 || (dr === 0 && dc === 0)) {
            return { valid: false, reason: 'Chỉ được đi 1 ô theo 8 hướng' };
        }

        // Check destination
        const target = this.board[toRow][toCol];
        if (target) {
            // Own piece blocks
            if (target.player === piece.player) {
                return { valid: false, reason: 'Ô đã có quân cùng phe' };
            }

            // Same type collision — blocked
            if (piece.sameType(target)) {
                return { valid: false, reason: 'Cùng loại — bị chặn, không thể di chuyển vào', blocked: true };
            }

            // Check if we can capture
            if (piece.beats(target)) {
                return { valid: true, isCapture: true, capturedType: target.type };
            } else {
                // Opponent's piece that beats us — we cannot move there
                return { valid: false, reason: 'Quân đối thủ khắc chế quân của bạn — không thể di chuyển vào' };
            }
        }

        return { valid: true, isCapture: false };
    }

    /**
     * Get all valid moves for a piece at (row, col).
     * Returns array of { toRow, toCol, isCapture, capturedType, blocked }
     */
    getValidMoves(row, col) {
        const moves = [];
        const piece = this.board[row][col];
        if (!piece || piece.player !== this.currentPlayer) return moves;

        for (const [dr, dc] of DIRECTIONS) {
            const toRow = row + dr;
            const toCol = col + dc;
            const result = this.validateMove(row, col, toRow, toCol);
            if (result.valid) {
                moves.push({
                    toRow,
                    toCol,
                    isCapture: result.isCapture,
                    capturedType: result.capturedType || null,
                });
            } else if (result.blocked) {
                // Mark blocked cells for UI display
                moves.push({
                    toRow,
                    toCol,
                    isBlocked: true,
                });
            }
        }

        return moves;
    }

    /**
     * Execute a move. Returns a move record or null if invalid.
     */
    executeMove(fromRow, fromCol, toRow, toCol) {
        if (this.gameOver) return null;

        const validation = this.validateMove(fromRow, fromCol, toRow, toCol);
        if (!validation.valid) return null;

        const piece = this.board[fromRow][fromCol];
        const captured = validation.isCapture ? this.board[toRow][toCol] : null;

        // Build move record (for undo & logging)
        const moveRecord = {
            player: this.currentPlayer,
            turnNumber: this.turnNumber,
            piece: piece.clone(),
            fromRow,
            fromCol,
            toRow,
            toCol,
            captured: captured ? captured.clone() : null,
            isCapture: validation.isCapture,
        };

        // Execute
        this.board[toRow][toCol] = piece;
        this.board[fromRow][fromCol] = null;

        // Store move
        this.moveHistory.push(moveRecord);

        // Check win conditions
        this._checkWinConditions(moveRecord);

        // Switch turn if game is not over
        if (!this.gameOver) {
            this.currentPlayer = this.currentPlayer === 1 ? 2 : 1;
            if (this.currentPlayer === 1) {
                this.turnNumber++;
            }
            // Check stalemate for next player
            this._checkStalemate();
        }

        return moveRecord;
    }

    /**
     * Check all win conditions after a move.
     */
    _checkWinConditions(moveRecord) {
        const { player, toRow, toCol } = moveRecord;
        const goal = GOALS[player];

        // Primary: Reached goal cell
        if (toRow === goal.row && toCol === goal.col) {
            this.gameOver = true;
            this.winner = player;
            this.winReason = `Player ${player} đã đến đích!`;
            return;
        }

        // Secondary: Opponent has no pieces left
        const opponent = player === 1 ? 2 : 1;
        const opponentPieces = this.getPlayerPieces(opponent);
        if (opponentPieces.length === 0) {
            this.gameOver = true;
            this.winner = player;
            this.winReason = `Player ${player} đã loại hết quân đối thủ!`;
            return;
        }
    }

    /**
     * Check if current player is in stalemate (no valid moves).
     */
    _checkStalemate() {
        const pieces = this.getPlayerPieces(this.currentPlayer);
        for (const { row, col } of pieces) {
            const moves = this.getValidMoves(row, col);
            if (moves.some(m => !m.isBlocked)) {
                return; // Has at least one valid move
            }
        }

        // Stalemate — current player loses
        this.gameOver = true;
        this.winner = this.currentPlayer === 1 ? 2 : 1;
        this.winReason = `Player ${this.currentPlayer} hết nước đi — thua cuộc!`;
    }

    /**
     * Undo the last move.
     */
    undoLastMove() {
        if (this.moveHistory.length === 0) return null;
        if (this.gameOver) {
            this.gameOver = false;
            this.winner = null;
            this.winReason = '';
        }

        const move = this.moveHistory.pop();

        // Restore board
        this.board[move.fromRow][move.fromCol] = this.board[move.toRow][move.toCol];
        this.board[move.toRow][move.toCol] = move.captured ? move.captured.clone() : null;

        // Restore turn
        this.currentPlayer = move.player;
        this.turnNumber = move.turnNumber;

        return move;
    }

    /**
     * Deep clone the game state (for AI or future use).
     */
    clone() {
        const gs = new GameState();
        gs.board = this.board.map(row => row.map(cell => cell ? cell.clone() : null));
        gs.currentPlayer = this.currentPlayer;
        gs.turnNumber = this.turnNumber;
        gs.moveHistory = this.moveHistory.map(m => ({ ...m }));
        gs.gameOver = this.gameOver;
        gs.winner = this.winner;
        gs.winReason = this.winReason;
        return gs;
    }
}

/**
 * Convert 0-indexed to 1-indexed display coordinates.
 */
function toDisplay(row, col) {
    return `(${col + 1}, ${row + 1})`;
}

/**
 * Get piece type name in Vietnamese.
 */
function pieceNameVi(type) {
    switch (type) {
        case PieceType.ROCK: return 'Búa';
        case PieceType.PAPER: return 'Bao';
        case PieceType.SCISSORS: return 'Kéo';
    }
}
// ---- Export cho Node.js (CommonJS) ----
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    PieceType,
    BEATS,
    PIECE_EMOJI,
    DIRECTIONS,
    GOALS,
    Piece,
    GameState,
    toDisplay,
    pieceNameVi,
  };
}