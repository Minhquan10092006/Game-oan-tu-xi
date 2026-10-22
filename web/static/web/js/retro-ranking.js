(() => {
  const body = document.getElementById('ranking-body');
  const status = document.getElementById('ranking-status');
  const refresh = document.getElementById('ranking-refresh');
  const myRank = document.getElementById('my-rank');
  const username = document.body.dataset.username || '';

  function cell(row, value, className) {
    const td = document.createElement('td');
    if (className) td.className = className;
    td.textContent = String(value);
    row.append(td);
    return td;
  }

  function render(players) {
    const rows = document.createDocumentFragment();
    myRank.hidden = true;
    for (const player of players) {
      const row = document.createElement('tr');
      const isMe = username && player.username === username;
      if (isMe) row.classList.add('is-me');
      const rank = cell(row, '', 'rank-number');
      const number = document.createElement('span');
      number.textContent = `#${player.rank}`;
      if (player.rank <= 3) number.className = 'top-rank';
      rank.append(number);
      cell(row, player.username + (isMe ? ' (bạn)' : ''), 'player-name');
      cell(row, player.elo, 'elo-number');
      cell(row, player.wins);
      cell(row, player.losses);
      cell(row, `${player.win_rate}%`);
      cell(row, player.total_games);
      rows.append(row);
      if (isMe) {
        document.getElementById('my-rank-number').textContent = `#${player.rank}`;
        document.getElementById('my-elo').textContent = player.elo;
        document.getElementById('my-record').textContent = `${player.wins} / ${player.losses}`;
        myRank.hidden = false;
      }
    }
    body.replaceChildren(rows);
    status.textContent = players.length ? `Đang hiển thị ${players.length} người chơi.` : 'Chưa có người chơi trong bảng xếp hạng.';
  }

  async function loadRanking() {
    refresh.disabled = true;
    status.textContent = 'Đang tải bảng xếp hạng…';
    try {
      const response = await fetch('/api/ranking/');
      if (!response.ok) throw new Error('request failed');
      const players = await response.json();
      if (!Array.isArray(players)) throw new Error('invalid response');
      render(players);
    } catch (_) {
      body.replaceChildren();
      myRank.hidden = true;
      status.textContent = 'Chưa tải được bảng xếp hạng. Vui lòng thử làm mới.';
    } finally {
      refresh.disabled = false;
    }
  }

  refresh.addEventListener('click', loadRanking);
  loadRanking();
})();
