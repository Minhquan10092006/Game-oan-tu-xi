/* Replay controls for trusted sample matches; output is inserted as text. */
(() => {
  const $ = id => document.getElementById(id);
  const labels = {rock:'B', paper:'Ba', scissors:'K'};
  let match = null, frame = 0, timer = null;

  function message(text, error = false) {
    $('status').textContent = text;
    $('status').classList.toggle('is-error', error);
  }
  function stop() { clearInterval(timer); timer = null; $('play').textContent = '▶ Phát'; }
  function controls(enabled) {
    for (const id of ['play','step','restart','timeline']) $(id).disabled = !enabled;
  }
  function snapshot() {
    const event = match.events[frame];
    return event.state_after || event.final_state || match.events[0].state_after;
  }
  function draw() {
    if (!match) return;
    const state = snapshot(), board = state.board;
    const cells = new Map(state.pieces.map(piece => [piece.at.join(','), piece]));
    const fragment = document.createDocumentFragment();
    $('board').classList.remove('is-empty');
    $('board').style.gridTemplateColumns = `repeat(${board.cols}, minmax(0,1fr))`;
    for (let row = 1; row <= board.rows; row++) {
      for (let col = 1; col <= board.cols; col++) {
        const cell = document.createElement('div'), piece = cells.get(`${row},${col}`);
        cell.className = 'arena-cell';
        if ((board.blocked_cells || []).some(at => at[0] === row && at[1] === col)) cell.classList.add('blocked');
        for (const player of ['P1','P2']) {
          if (board.goals[player][0] === row && board.goals[player][1] === col) cell.classList.add(`goal-${player.toLowerCase()}`);
        }
        const event = match.events[frame];
        if (event.type === 'move' && event.to[0] === row && event.to[1] === col) cell.classList.add('last');
        if (piece) {
          const token = document.createElement('span');
          token.className = `arena-piece ${piece.owner === 'P1' ? 'p1' : 'p2'}`;
          token.textContent = labels[piece.type] || '?';
          cell.title = `${piece.owner}: ${piece.type} — hàng ${row}, cột ${col}`;
          cell.append(token);
        }
        fragment.append(cell);
      }
    }
    $('board').replaceChildren(fragment);
    $('board').setAttribute('aria-label', `Bàn cờ sau ${state.ply} nước. ${state.status === 'finished' ? 'Trận đã kết thúc.' : `Lượt ${state.current_player}.`} Chi tiết trong lịch sử nước đi.`);
    $('turn').textContent = state.status === 'finished' ? 'Trận đã kết thúc' : `Lượt: ${state.current_player}`;
    $('result').textContent = state.status === 'finished'
      ? `${state.result === 'error' ? 'Chưa có kết quả' : state.result === 'draw' ? 'Hòa' : state.winner + ' thắng'} — ${state.reason.message}` : '';
    $('progress').textContent = `Bước ${frame}/${match.events.length - 1} · ${state.ply} nước đã đi`;
    $('timeline').value = frame;
    const log = document.createDocumentFragment();
    for (const event of match.events.slice(0, frame + 1).filter(item => item.type === 'move')) {
      const row = document.createElement('div');
      row.className = 'replay-event';
      row.textContent = `${event.ply}. ${event.player} · ${labels[event.piece_type]} (${event.from.join(',')}) → (${event.to.join(',')})${event.captured_piece ? ' · bắt ' + labels[event.captured_piece.type] : ''}`;
      log.append(row);
    }
    if (!log.childNodes.length) { const p = document.createElement('p'); p.textContent = 'Vị trí khởi đầu của hai đội.'; log.append(p); }
    $('history').replaceChildren(log);
  }
  function advance() {
    if (!match || frame >= match.events.length - 1) { stop(); return; }
    frame++; draw();
    if (frame >= match.events.length - 1) stop();
  }
  async function readResponse(response) {
    const data = await response.json().catch(() => null);
    if (!response.ok) throw Error(data?.error || `Yêu cầu chưa thành công (${response.status}). Hãy tải lại trang và thử lại.`);
    if (!data) throw Error('Dữ liệu trận chưa sẵn sàng. Vui lòng thử lại.');
    return data;
  }
  $('upload-form').addEventListener('submit', async event => {
    event.preventDefault(); stop(); controls(false); $('start').disabled = true;
    message('Hai bot đang thi đấu. Đang chuẩn bị bản phát lại…');
    try {
      const data = await readResponse(await fetch(event.target.action, {method:'POST', body:new FormData(event.target)}));
      const replay = await readResponse(await fetch(`/api/matches/demo/${encodeURIComponent(data.match_id)}/`));
      if (!Array.isArray(replay.events) || !replay.events.length) throw Error('Trận chưa có diễn biến để phát lại.');
      match = replay; frame = 0; $('timeline').max = match.events.length - 1;
      draw(); message('Trận đã được lưu. Nhấn Phát hoặc kéo thanh tiến trình để xem.');
    } catch (error) { message(error.message, true); }
    finally { $('start').disabled = false; controls(Boolean(match)); }
  });
  $('play').addEventListener('click', () => {
    if (!match) return;
    if (timer) { stop(); return; }
    if (frame >= match.events.length - 1) frame = 0;
    draw(); $('play').textContent = 'Ⅱ Tạm dừng'; timer = setInterval(advance, Number($('speed').value));
  });
  $('step').addEventListener('click', () => { stop(); advance(); });
  $('restart').addEventListener('click', () => { stop(); frame = 0; draw(); });
  $('timeline').addEventListener('input', () => { stop(); frame = Number($('timeline').value); draw(); });
  $('speed').addEventListener('change', () => { if (timer) { stop(); $('play').click(); } });
  document.addEventListener('visibilitychange', () => { if (document.hidden) stop(); });
  window.addEventListener('pagehide', stop);
})();
