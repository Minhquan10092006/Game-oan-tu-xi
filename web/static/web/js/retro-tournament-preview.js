(() => {
  const toggle = document.getElementById('preview-world-cup-toggle');
  const panel = document.getElementById('tournament-preview');
  if (!toggle || !panel) return;
  let connectorResizeObserver = null;
  let redrawConnectors = () => {};
  window.addEventListener('resize', () => redrawConnectors(), {passive: true});

  const node = (tag, className, text) => {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (text !== undefined) item.textContent = text;
    return item;
  };

  function shuffle(items) {
    for (let index = items.length - 1; index > 0; index -= 1) {
      const random = new Uint32Array(1);
      crypto.getRandomValues(random);
      const swapIndex = random[0] % (index + 1);
      [items[index], items[swapIndex]] = [items[swapIndex], items[index]];
    }
    return items;
  }

  function renderGroups(groups, bestThirdPlaces, thirdPlaceStats) {
    const section = node('section', 'group-stage');
    section.append(node('h4', '', 'Vòng bảng · 12 bảng × 4 đội · 144 trận'));
    const grid = node('div', 'group-grid');
    groups.forEach((entries, index) => {
      const code = String.fromCharCode(65 + index);
      const card = node('article', 'retro-window group-card');
      card.append(node('div', 'window-title', `BẢNG ${code} · MINH HỌA`));
      const body = node('div', 'window-body group-body');
      const table = node('table', 'standings-table');
      table.append(node('caption', 'sr-only', `Mục dự thi minh họa bảng ${code}`));
      const head = document.createElement('thead');
      const headerRow = document.createElement('tr');
      ['#', 'Đội', 'Đ', 'T', 'H', 'B', 'Điểm'].forEach(label => headerRow.append(node('th', '', label)));
      head.append(headerRow);
      const rows = document.createElement('tbody');
      entries.forEach((entry, rank) => {
        const row = document.createElement('tr');
        const qualifies = rank < 2 || (rank === 2 && bestThirdPlaces.has(index));
        if (qualifies) row.className = 'qualifier-row';
        const stats = rank === 2 ? thirdPlaceStats[index] : [
          [3, 2, 1, 0, 7], [3, 1, 2, 0, 5], null,
          [3, 0, 0, 3, 0],
        ][rank];
        [rank + 1, entry, ...stats].forEach(value => row.append(node('td', '', String(value))));
        rows.append(row);
      });
      table.append(head, rows);
      body.append(table, node('p', 'preview-fixture-note', 'Top 2 + 8 đội hạng ba tốt nhất đi tiếp'));
      card.append(body);
      grid.append(card);
    });
    section.append(grid);
    return section;
  }

  function renderBracket(groups, bestThirdPlaces) {
    const section = node('section', 'bracket-section');
    section.append(node('h4', '', 'Vòng loại trực tiếp · 32 đội · hai nhánh hội tụ tại chung kết'));
    const bracket = node('div', 'bracket-scroll bracket-compact');
    const qualified = [];
    groups.forEach((entries, group) => {
      qualified.push(`Bảng ${String.fromCharCode(65 + group)} · #1`);
      qualified.push(`Bảng ${String.fromCharCode(65 + group)} · #2`);
      if (bestThirdPlaces.has(group)) qualified.push(`Bảng ${String.fromCharCode(65 + group)} · #3`);
    });
    shuffle(qualified);

    const bracketHalves = [];
    const addHalf = (className, sideName, teams) => {
      const half = node('div', `bracket-half ${className}`);
      const rounds = [];
      const labels = ['Vòng 32', 'Vòng 16', 'Tứ kết', 'Bán kết'];
      let winners = teams;
      labels.forEach((label, roundIndex) => {
        const round = node('section', 'bracket-round');
        round.append(node('h5', '', label));
        const matches = [];
        for (let index = 0; index < winners.length; index += 2) {
          const match = node('article', 'bracket-match');
          if (roundIndex === 0) {
            match.append(node('strong', '', winners[index]), node('strong', '', winners[index + 1]));
          } else {
            match.append(node('strong', '', winners[index]), node('strong', '', winners[index + 1]));
          }
          matches.push(match);
          round.append(match);
        }
        rounds.push(round);
        winners = Array.from({length: winners.length / 2}, (_, index) => `Thắng ${label} ${index + 1}`);
      });
      rounds.forEach(round => half.append(round));
      half.setAttribute('aria-label', `${sideName} nhánh loại trực tiếp`);
      bracketHalves.push({half, rounds, sideName});
      return half;
    };

    const leftTeams = qualified.slice(0, 16);
    const rightTeams = qualified.slice(16);
    const final = node('section', 'bracket-final');
    final.append(node('h5', '', 'CHUNG KẾT'));
    const finalMatch = node('article', 'bracket-match');
    finalMatch.append(node('strong', '', 'Vô địch nhánh trái'), node('strong', '', 'Vô địch nhánh phải'));
    final.append(finalMatch);

    bracket.append(
      addHalf('bracket-left', 'Trái', leftTeams),
      final,
      addHalf('bracket-right', 'Phải', rightTeams),
    );
    const connectors = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    connectors.classList.add('bracket-connectors');
    connectors.setAttribute('aria-hidden', 'true');
    bracket.prepend(connectors);
    const drawConnectors = () => {
      const bounds = bracket.getBoundingClientRect();
      connectors.setAttribute('width', String(bracket.scrollWidth));
      connectors.setAttribute('height', String(bracket.scrollHeight));
      connectors.setAttribute('viewBox', `0 0 ${bracket.scrollWidth} ${bracket.scrollHeight}`);
      connectors.replaceChildren();

      bracketHalves.forEach(({rounds}) => {
        let centers = [];
        rounds.forEach((round, roundIndex) => {
          const matches = Array.from(round.querySelectorAll('.bracket-match'));
          const heading = round.querySelector('h5');
          const start = heading.offsetTop + heading.offsetHeight + 12;
          const maxMatchHeight = Math.max(...matches.map(match => match.offsetHeight));
          const end = round.clientHeight - maxMatchHeight / 2 - 8;
          if (roundIndex === 0) {
            const firstCenter = start + maxMatchHeight / 2;
            centers = matches.map((_, index) =>
              matches.length === 1
                ? (firstCenter + end) / 2
                : firstCenter + (end - firstCenter) * index / (matches.length - 1),
            );
          } else {
            centers = matches.map((_, index) => (centers[index * 2] + centers[index * 2 + 1]) / 2);
          }
          matches.forEach((match, index) => {
            match.style.top = `${centers[index]}px`;
          });
        });
      });

      const center = element => {
        const rect = element.getBoundingClientRect();
        return {
          x: rect.left - bounds.left + bracket.scrollLeft,
          y: rect.top - bounds.top + bracket.scrollTop,
          width: rect.width,
          height: rect.height,
        };
      };
      const connect = (source, target) => {
        const from = center(source);
        const to = center(target);
        const sourceCenter = from.x + from.width / 2;
        const targetCenter = to.x + to.width / 2;
        const forward = targetCenter > sourceCenter;
        const startX = forward ? from.x + from.width : from.x;
        const endX = forward ? to.x : to.x + to.width;
        const startY = from.y + from.height / 2;
        const endY = to.y + to.height / 2;
        const bendX = startX + (endX - startX) / 2;
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', `M ${startX} ${startY} H ${bendX} V ${endY} H ${endX}`);
        connectors.append(path);
      };

      bracketHalves.forEach(({rounds}) => {
        rounds.forEach((round, roundIndex) => {
          const nextRound = rounds[roundIndex + 1];
          if (!nextRound) return;
          const matches = round.querySelectorAll('.bracket-match');
          const nextMatches = nextRound.querySelectorAll('.bracket-match');
          matches.forEach((match, index) => connect(match, nextMatches[Math.floor(index / 2)]));
        });
      });
      const finalMatch = final.querySelector('.bracket-match');
      bracketHalves.forEach(({rounds}) => {
        const semifinal = rounds[rounds.length - 1].querySelector('.bracket-match');
        connect(semifinal, finalMatch);
      });
    };
    const scheduleConnectorDraw = () => window.requestAnimationFrame(drawConnectors);
    scheduleConnectorDraw();
    redrawConnectors = scheduleConnectorDraw;
    bracket.addEventListener('scroll', scheduleConnectorDraw, {passive: true});
    if ('ResizeObserver' in window) {
      connectorResizeObserver?.disconnect();
      connectorResizeObserver = new ResizeObserver(scheduleConnectorDraw);
      connectorResizeObserver.observe(bracket);
      bracketHalves.forEach(({half}) => connectorResizeObserver.observe(half));
    }
    section.append(bracket);
    return section;
  }

  function showPreview() {
    const entries = shuffle(Array.from({length: 48}, (_, index) => `Đội ${String(index + 1).padStart(2, '0')}`));
    const groups = Array.from({length: 12}, (_, index) => entries.slice(index * 4, index * 4 + 4));
    const outcomes = [];
    for (let wins = 0; wins <= 3; wins += 1) {
      for (let draws = 0; draws <= 3 - wins; draws += 1) {
        outcomes.push([3, wins, draws, 3 - wins - draws, wins * 3 + draws]);
      }
    }
    const thirdPlaceStats = Array.from({length: 12}, () => shuffle(outcomes.slice())[0]);
    const bestThirdPlaces = new Set(
      shuffle(Array.from({length: 12}, (_, index) => index))
        .sort((first, second) => thirdPlaceStats[second][4] - thirdPlaceStats[first][4])
        .slice(0, 8),
    );
    panel.replaceChildren();
    const heading = node('div', 'tournament-heading');
    heading.append(
      node('div', 'eyebrow', 'DEMO DRAW · NO DATABASE CHANGES'),
      node('h3', '', 'Minh họa bốc thăm 48 đội'),
      node('p', 'draw-meta', '12 bảng × 4 đội · Top 2 và 8 đội hạng ba tốt nhất vào vòng 32. Hai nhánh loại trực tiếp thu nhỏ và hội tụ ở chung kết. Dữ liệu minh họa không lưu vào hệ thống.'),
    );
    panel.append(
      heading,
      renderGroups(groups, bestThirdPlaces, thirdPlaceStats),
      renderBracket(groups, bestThirdPlaces),
    );
    panel.hidden = false;
    toggle.setAttribute('aria-expanded', 'true');
    toggle.textContent = 'Trộn lại minh họa';
  }

  toggle.addEventListener('click', () => {
    if (panel.hidden) showPreview();
    else {
      panel.hidden = true;
      toggle.setAttribute('aria-expanded', 'false');
      toggle.textContent = 'Xem demo World Cup · 48 đội';
      connectorResizeObserver?.disconnect();
      connectorResizeObserver = null;
      redrawConnectors = () => {};
    }
  });
})();
