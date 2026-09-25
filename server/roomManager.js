const { GameState } = require('./engine');

class RoomManager {
  constructor() {
    this.rooms = new Map();
  }

  createRoom(code) {
    if (this.rooms.has(code)) return this.rooms.get(code);
    const room = {
      code,
      state: new GameState(),
      players: [null, null],
      names: ['Đang chờ...', 'Đang chờ...'],
      status: 'waiting',
      createdAt: Date.now(),
    };
    this.rooms.set(code, room);
    return room;
  }

  joinRoom(code, socketId, playerName) {
    const room = this.rooms.get(code);
    if (!room) return { error: 'Phòng không tồn tại' };

    const existing = room.players.indexOf(socketId);
    if (existing !== -1) return { room, playerNumber: existing + 1 };

    const slot = room.players.indexOf(null);
    if (slot === -1) return { error: 'Phòng đã đầy' };

    room.players[slot] = socketId;
    room.names[slot] = playerName;
    if (room.players.every(p => p !== null)) room.status = 'playing';
    return { room, playerNumber: slot + 1 };
  }

  leaveRoom(code, socketId) {
    const room = this.rooms.get(code);
    if (!room) return null;
    const idx = room.players.indexOf(socketId);
    if (idx !== -1) {
      room.players[idx] = null;
      room.names[idx] = 'Đã rời';
      room.status = 'waiting';
    }
    if (room.players.every(p => p === null)) {
      this.rooms.delete(code);
      return { deleted: true, code };
    }
    return room;
  }

  getRoom(code) {
    return this.rooms.get(code);
  }

  resetRoom(code) {
    const room = this.rooms.get(code);
    if (!room) return null;
    room.state = new GameState();
    room.status = room.players.every(p => p !== null) ? 'playing' : 'waiting';
    return room;
  }
}

module.exports = { RoomManager };