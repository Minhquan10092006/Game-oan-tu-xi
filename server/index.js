/* ============================================
   OẲN TÙ TÌ 2.0 — SERVER
   Express + Socket.IO + Room Manager
   ============================================ */

const express = require('express');
const http = require('http');
const path = require('path');
const { Server } = require('socket.io');
const { RoomManager } = require('./roomManager');

const app = express();
const server = http.createServer(app);
const io = new Server(server, { cors: { origin: '*' } });

app.use(express.static(path.join(__dirname, '..')));

app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, '..', 'index.html'));
});

const rooms = new RoomManager();

app.get('/api/rooms', (req, res) => {
  const list = Array.from(rooms.rooms.values()).map(r => ({
    code: r.code,
    names: r.names,
    status: r.status,
    turnNumber: r.state.turnNumber,
    currentPlayer: r.state.currentPlayer,
    gameOver: r.state.gameOver,
    winner: r.state.winner,
  }));
  res.json(list);
});

io.on('connection', (socket) => {
  console.log('🔌 Connected:', socket.id);

  socket.on('join_room', ({ code, name }, ack) => {
    if (!rooms.getRoom(code)) rooms.createRoom(code);
    const result = rooms.joinRoom(code, socket.id, name || 'Player');
    if (result.error) return ack?.({ error: result.error });

    socket.join(code);
    socket.data.roomCode = code;
    socket.data.playerNumber = result.playerNumber;

    ack?.({
      ok: true,
      playerNumber: result.playerNumber,
      state: serializeState(result.room),
      names: result.room.names,
    });

    io.to(code).emit('room_update', {
      code,
      names: result.room.names,
      status: result.room.status,
      state: serializeState(result.room),
    });
  });

  socket.on('spectate', ({ codes }) => {
    codes.forEach(code => socket.join(`spectate:${code}`));
    socket.data.spectating = codes;
    const snapshot = codes
      .map(code => rooms.getRoom(code))
      .filter(Boolean)
      .map(serializeState);
    socket.emit('spectate_snapshot', snapshot);
  });

  socket.on('make_move', ({ fromRow, fromCol, toRow, toCol }, ack) => {
    const code = socket.data.roomCode;
    const playerNumber = socket.data.playerNumber;
    const room = rooms.getRoom(code);
    if (!room) return ack?.({ error: 'Phòng không tồn tại' });
    if (room.state.gameOver) return ack?.({ error: 'Ván đã kết thúc' });
    if (room.state.currentPlayer !== playerNumber)
      return ack?.({ error: 'Chưa đến lượt bạn' });

    const moveRecord = room.state.executeMove(fromRow, fromCol, toRow, toCol);
    if (!moveRecord) return ack?.({ error: 'Nước đi không hợp lệ' });

    const payload = { code, move: moveRecord, state: serializeState(room) };
    io.to(code).emit('move_made', payload);
    io.to(`spectate:${code}`).emit('move_made', payload);

    if (room.state.gameOver) room.status = 'finished';
    ack?.({ ok: true });
  });

  socket.on('reset_room', () => {
    const code = socket.data.roomCode;
    const room = rooms.resetRoom(code);
    if (!room) return;
    const payload = { code, state: serializeState(room), names: room.names };
    io.to(code).emit('room_reset', payload);
    io.to(`spectate:${code}`).emit('room_reset', payload);
  });

  socket.on('disconnect', () => {
    const code = socket.data.roomCode;
    if (!code) return;
    const result = rooms.leaveRoom(code, socket.id);
    if (result?.deleted) {
      io.to(`spectate:${code}`).emit('room_deleted', { code });
    } else if (result) {
      io.to(code).emit('room_update', {
        code,
        names: result.names,
        status: result.status,
        state: serializeState(result),
      });
    }
  });
});

function serializeState(room) {
  const s = room.state;
  return {
    code: room.code,
    names: room.names,
    status: room.status,
    board: s.board.map(row => row.map(cell => cell ? {
      player: cell.player,
      type: cell.type,
      id: cell.id,
    } : null)),
    currentPlayer: s.currentPlayer,
    turnNumber: s.turnNumber,
    gameOver: s.gameOver,
    winner: s.winner,
    winReason: s.winReason,
    lastMove: s.moveHistory.length > 0 ? s.moveHistory[s.moveHistory.length - 1] : null,
  };
}

const PORT = process.env.PORT || 3000;
server.listen(PORT, () => {
  console.log(`🚀 Server: http://localhost:${PORT}`);
  console.log(`   Menu:       http://localhost:${PORT}/`);
  console.log(`   2 người:    http://localhost:${PORT}/#solo`);
  console.log(`   8 người:    http://localhost:${PORT}/#multi`);
});