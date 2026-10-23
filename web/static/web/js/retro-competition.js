(() => {
  const status = document.getElementById('competition-status');
  const list = document.getElementById('season-list');
  const csrf = () => document.cookie.split(';').map(v => v.trim()).find(v => v.startsWith('csrftoken='))?.slice(10) || '';

  async function call(url, body) {
    const response = await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf()},
      body: JSON.stringify(body || {}),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw Error(data.error || data.detail || 'Không thể hoàn tất thao tác.');
    return data;
  }

  function tell(message, isError = false) {
    status.textContent = message;
    status.style.borderColor = isError ? '#800000' : '#808080';
  }

  function entryFor(entries, seasonId) {
    return entries.find(entry => entry.season_id === seasonId);
  }

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function renderFixtureList(fixtures) {
    const list = element('ol', 'fixture-list');
    for (const fixture of fixtures) {
      const item = element('li', 'fixture-item');
      item.append(
        element('span', 'fixture-number', `#${fixture.match_number}${fixture.leg > 1 ? ` · Lượt ${fixture.leg}` : ''}`),
        element('span', 'fixture-players', `${fixture.entry1 || 'Chờ xếp'}  —  ${fixture.entry2 || (fixture.result === 'bye' ? 'Miễn vòng' : 'Chờ xếp')}`),
        element('span', `fixture-result result-${fixture.result}`, fixture.result === 'scheduled' ? 'Chưa đấu' : fixture.winner || (fixture.result === 'draw' ? 'Hòa' : 'Đã có kết quả')),
      );
      list.append(item);
    }
    return list;
  }

  function renderTournament(season) {
    const view = element('section', 'tournament-view');
    view.hidden = !season.drawn;
    view.setAttribute('aria-label', 'Bảng đấu và nhánh loại trực tiếp');
    if (!season.drawn) return view;

    const heading = element('div', 'tournament-heading');
    heading.append(
      element('div', 'eyebrow', 'TOURNAMENT DRAW'),
      element('h3', '', 'Bảng đấu & nhánh vô địch'),
      element('p', 'draw-meta', `Bốc thăm ${new Date(season.drawn_at).toLocaleString('vi-VN')} · mã công khai ${season.draw_seed}`),
    );
    view.append(heading);

    const groupSection = element('section', 'group-stage');
    groupSection.append(element('h4', '', 'Vòng bảng · tối đa 4 mục mỗi bảng · 2 đội đầu bảng đi tiếp'));
    const groupGrid = element('div', 'group-grid');
    for (const group of season.groups) {
      const card = element('article', 'retro-window group-card');
      card.append(element('div', 'window-title', `BẢNG ${group.code}`));
      const body = element('div', 'window-body group-body');
      const tableWrap = element('div', 'standings-scroll');
      const table = element('table', 'standings-table');
      const caption = element('caption', 'sr-only', `Bảng xếp hạng bảng ${group.code}`);
      const head = document.createElement('thead');
      const headerRow = document.createElement('tr');
      for (const label of ['#', 'Đơn vị dự thi', 'Đ', 'T', 'H', 'B', 'Điểm']) {
        headerRow.append(element('th', '', label));
      }
      head.append(headerRow);
      const rows = document.createElement('tbody');
      for (const row of group.standings) {
        const tr = document.createElement('tr');
        if (row.rank <= 2) tr.className = 'qualifier-row';
        for (const value of [row.rank, row.name, row.played, row.wins, row.draws, row.losses, row.points]) {
          tr.append(element('td', '', String(value)));
        }
        rows.append(tr);
      }
      table.append(caption, head, rows);
      tableWrap.append(table);
      body.append(tableWrap);
      const schedule = element('details', 'group-fixtures');
      schedule.append(element('summary', '', `Lịch bảng · ${group.fixtures.length} ván`));
      schedule.append(renderFixtureList(group.fixtures));
      body.append(schedule);
      card.append(body);
      groupGrid.append(card);
    }
    groupSection.append(groupGrid);
    view.append(groupSection);

    const bracketSection = element('section', 'bracket-section');
    bracketSection.append(element('h4', '', 'Vòng loại trực tiếp · nhánh tới chung kết'));
    const bracket = element('div', 'bracket-scroll');
    for (const round of season.bracket) {
      const column = element('section', 'bracket-round');
      column.append(element('h5', '', round.name));
      for (const fixture of round.fixtures) {
        const match = element('article', 'bracket-match');
        match.append(
          element('span', 'bracket-match-number', `Trận ${fixture.match_number}`),
          element('strong', fixture.winner === fixture.entry1 && fixture.winner ? 'bracket-winner' : '', fixture.entry1 || 'Chờ kết quả'),
          element('strong', fixture.winner === fixture.entry2 && fixture.winner ? 'bracket-winner' : '', fixture.entry2 || (fixture.result === 'bye' ? 'BYE' : 'Chờ kết quả')),
        );
        if (fixture.result === 'bye') match.append(element('small', 'bye-note', 'Miễn vòng đầu'));
        column.append(match);
      }
      bracket.append(column);
    }
    bracketSection.append(bracket);
    if (season.third_place.length) {
      const third = element('section', 'third-place');
      third.append(element('h5', '', 'Tranh hạng ba'));
      third.append(renderFixtureList(season.third_place));
      bracketSection.append(third);
    }
    view.append(bracketSection);
    return view;
  }

  function render(data) {
    list.replaceChildren();
    if (!data.seasons.length) {
      tell('Chưa có mùa giải đang mở. BTC sẽ thông báo khi mở đăng ký.');
      return;
    }
    tell('Chọn hình thức tham gia phù hợp với mùa giải.');
    for (const season of data.seasons) {
      const node = document.getElementById('season-template').content.cloneNode(true);
      const card = node.querySelector('.season-card');
      const entry = entryFor(data.entries, season.id);
      const emailInput = node.querySelector('.contact-email');
      const emailWrap = node.querySelector('.contact-email-wrap');
      const saveEmail = node.querySelector('.save-contact-email');
      emailInput.value = data.contact_email || '';
      emailInput.required = !data.contact_email;
      emailWrap.hidden = Boolean(data.contact_email);
      node.querySelector('.season-title').textContent = `▸ season_${season.id}.cfg`;
      node.querySelector('.season-mode').textContent = season.entry_mode === 'both' ? 'CÁ NHÂN + ĐỘI' : season.entry_mode.toUpperCase();
      node.querySelector('.season-name').textContent = season.name;
      node.querySelector('.season-state').textContent = season.registration_open ? 'Đang nhận đăng ký.' : 'Đăng ký đã đóng hoặc mùa giải chưa mở.';
      for (const round of season.rounds) {
        const tag = element('span', round.status, round.name);
        node.querySelector('.round-track').append(tag);
      }
      const individual = node.querySelector('.individual-action');
      const create = node.querySelector('.create-team-form');
      const join = node.querySelector('.join-team-form');
      if (!season.registration_open || entry) {
        individual.disabled = true;
        create.querySelector('button').disabled = true;
        join.querySelector('button').disabled = true;
      }
      if (season.entry_mode === 'team') individual.hidden = true;
      if (season.entry_mode === 'individual') { create.hidden = true; join.hidden = true; }
      if (entry) {
        const mine = node.querySelector('.my-entry');
        mine.hidden = false;
        mine.textContent = `Đã đăng ký: ${entry.display_name} (${entry.kind === 'team' ? 'đội' : 'cá nhân'}). `;
        if (entry.kind === 'individual' || entry.is_captain) {
          const link = element('a', '', 'Nộp bot cho mục này →');
          link.href = `/ai/?entry=${encodeURIComponent(entry.id)}`;
          mine.append(link);
        }
      }

      saveEmail.addEventListener('click', async () => {
        try {
          await call('/api/competition/email/', {contact_email: emailInput.value});
          await load();
          tell('Đã lưu email nhận thông báo.');
        } catch (error) { tell(error.message, true); }
      });
      individual.addEventListener('click', async () => {
        try {
          await call(`/api/competition/seasons/${season.id}/individual/`, {contact_email: emailInput.value});
          await load();
        } catch (error) { tell(error.message, true); }
      });
      create.addEventListener('submit', async event => {
        event.preventDefault();
        try {
          const out = await call(`/api/competition/seasons/${season.id}/teams/`, {
            name: new FormData(create).get('name'),
            contact_email: emailInput.value,
          });
          await load();
          tell(`Đã lập đội. Lưu mã đội ngay: ${out.join_code}`);
        } catch (error) { tell(error.message, true); }
      });
      join.addEventListener('submit', async event => {
        event.preventDefault();
        try {
          await call('/api/competition/teams/join/', {
            join_code: new FormData(join).get('join_code'),
            contact_email: emailInput.value,
          });
          await load();
        } catch (error) { tell(error.message, true); }
      });
      card.querySelector('.tournament-view').replaceWith(renderTournament(season));
      list.append(card);
    }
  }

  async function load() {
    try {
      const response = await fetch('/api/competition/me/', {credentials: 'same-origin'});
      const data = await response.json();
      if (!response.ok) throw Error(data.detail || `HTTP ${response.status}`);
      render(data);
    } catch (error) {
      tell(`Chưa tải được thông tin mùa giải: ${error.message}`, true);
    }
  }

  load();
})();
