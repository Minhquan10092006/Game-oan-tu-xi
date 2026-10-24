/* Durable browser outbox. Server receipts make retries safe across tabs. */
(() => {
  'use strict';
  const panel = document.getElementById('offline-submissions');
  const status = document.getElementById('offline-status');
  const fields = ['ai-name', 'competition-entry', 'submission-method', 'git-url', 'git-commit', 'code-editor'];
  let db, owner, busy = false, enqueuing = false, timer, maxSize = 65536, ready = false;
  const username = panel.dataset.username;
  const announce = message => { status.textContent = message; };
  const request = (store, mode, action) => new Promise((resolve, reject) => {
    const tx = db.transaction(store, mode);
    const result = action(tx.objectStore(store));
    tx.oncomplete = () => resolve(result.result);
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error || new Error('Không lưu được dữ liệu.'));
  });
  const get = key => request('drafts', 'readonly', store => store.get(key));
  const put = item => request('drafts', 'readwrite', store => store.put(item));
  const all = () => request('outbox', 'readonly', store => store.getAll());
  const saveJob = item => request('outbox', 'readwrite', store => store.put(item));
  const removeJob = id => request('outbox', 'readwrite', store => store.delete(id));
  const values = () => Object.fromEntries(fields.map(id => [id, document.getElementById(id).value]));
  function restore(data) {
    if (!data) return;
    const select = document.getElementById('competition-entry');
    if (data['competition-entry'] && !Array.from(select.options).some(o => o.value === data['competition-entry'])) {
      select.add(new Option(data.entryLabel || 'Mùa đã lưu — server sẽ kiểm tra lại hạn nộp', data['competition-entry']));
    }
    fields.forEach(id => { if (data[id] !== undefined) document.getElementById(id).value = data[id]; });
    document.getElementById('git-evidence').hidden = data['submission-method'] !== 'git';
  }
  async function saveDraft() {
    if (!ready || !owner) throw new Error('Hãy mở trang online và đăng nhập một lần trước khi lưu offline.');
    const data = values();
    data.entryLabel = document.getElementById('competition-entry').selectedOptions[0]?.textContent;
    await put({key: `draft:${owner.id}`, data});
    announce(`Đã lưu bản nháp trên máy cho ${owner.username}. Chưa gửi server.`);
  }
  async function render() {
    const list = document.getElementById('local-queue-list');
    list.replaceChildren();
    const jobs = (await all()).filter(job => job.owner === owner?.id).sort((a, b) => a.created - b.created);
    for (const job of jobs) {
      const li = document.createElement('li');
      li.textContent = `${job.payload.ai_name} · ${new Date(job.created).toLocaleString('vi-VN')} · ${job.message || 'Chờ gửi'} `;
      const exportButton = document.createElement('button');
      exportButton.type = 'button'; exportButton.textContent = 'Tải .py';
      exportButton.onclick = () => download(job.payload.source_code);
      li.append(exportButton);
      if (job.state !== 'accepted') {
        const retry = document.createElement('button');
        retry.type = 'button'; retry.textContent = 'Thử lại';
        retry.onclick = () => guarded(async () => {
          job.state = 'queued'; job.next = 0; await saveJob(job); await sync();
        });
        const remove = document.createElement('button');
        remove.type = 'button'; remove.textContent = 'Xóa khỏi máy';
        remove.onclick = () => guarded(async () => {
          if (confirm('Xóa bản chờ này trên máy? Bài đã tới server (nếu có) không bị xóa.')) {
            await removeJob(job.id); await render();
          }
        });
        li.append(retry, remove);
      }
      list.append(li);
    }
  }
  function download(source) {
    const url = URL.createObjectURL(new Blob([source], {type: 'text/x-python;charset=utf-8'}));
    const link = document.createElement('a'); link.href = url; link.download = 'bot.py'; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  async function session() {
    const response = await fetch('/api/submissions/session/', {cache: 'no-store', credentials: 'same-origin',
      signal: AbortSignal.timeout(15000)});
    if (!response.ok) throw new Error('Cần đăng nhập lại đúng tài khoản. Bài vẫn giữ trên máy.');
    const data = await response.json();
    if (String(data.user_id) !== owner.id) throw new Error(`Hãy đăng nhập tài khoản ${owner.username} để gửi bài chờ. Không gửi bằng tài khoản khác.`);
    maxSize = data.max_code_size;
    return data;
  }
  async function sync() {
    if (!ready || !owner || busy || !navigator.onLine) return;
    busy = true;
    try {
      const jobs = (await all()).filter(job => job.owner === owner.id && job.state === 'queued' && (!job.next || job.next <= Date.now()));
      if (!jobs.length) return;
      for (const job of jobs.sort((a, b) => a.created - b.created)) {
        const auth = await session();
        try {
          const response = await fetch('/api/submissions/', {
            method: 'POST', credentials: 'same-origin', signal: AbortSignal.timeout(30000),
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': auth.csrf_token},
            body: JSON.stringify({...job.payload, client_submission_id: job.id, client_account_id: owner.id}),
          });
          const data = await response.json().catch(() => null);
          if (response.ok && data?.id) {
            // Retain source and receipt locally until the owner explicitly clears them.
            job.state = 'accepted'; job.message = `Server đã nhận · biên nhận #${data.id} · v${data.version}`;
          } else if (response.status === 429 || response.status >= 500) {
            const retryAfter = response.headers.get('Retry-After');
            const delay = retryAfter && (/^\d+$/.test(retryAfter) ? Number(retryAfter) * 1000 : Date.parse(retryAfter) - Date.now());
            job.next = Date.now() + Math.max(1000, delay || backoff(job));
            job.message = 'Server bận; sẽ tự thử lại. Bài vẫn ở máy.';
          } else {
            job.state = 'blocked';
            job.message = (response.status === 401 || response.status === 403)
              ? 'Cần đăng nhập/kiểm tra quyền rồi bấm Thử lại.'
              : `Server từ chối: ${JSON.stringify(data || {error: response.status})}. Giữ bài trên máy; sửa và nộp bản mới nếu cần.`;
          }
        } catch (_) {
          job.next = Date.now() + backoff(job);
          job.message = 'Chưa nhận được xác nhận; sẽ gửi lại cùng mã để tránh trùng bài.';
          await saveJob(job); break;
        }
        await saveJob(job);
      }
      announce('Đã kiểm tra hàng đợi. Xem biên nhận hoặc lỗi của từng bài bên dưới.');
      if (typeof loadHistory === 'function') loadHistory();
    } catch (error) { announce(error.message); }
    finally { busy = false; await render(); }
  }
  function backoff(job) {
    job.attempts = (job.attempts || 0) + 1;
    return Math.min(300000, 3000 * 2 ** Math.min(job.attempts, 7)) + Math.random() * 1000;
  }
  async function guarded(action) {
    try { await action(); } catch (error) { announce(`Không hoàn tất: ${error.message}. Hãy tải file .py dự phòng.`); }
  }
  // Replace the direct-send handler: persist immutable payload before touching network.
  window.submitCode = async () => {
    if (enqueuing) return;
    enqueuing = true;
    document.getElementById('submit-btn').disabled = true;
    try { await guarded(async () => {
    if (!ready || !owner) throw new Error('Chưa mở được bộ nhớ local.');
    const data = values(); const entry = data['competition-entry'];
    if (!data['ai-name'].trim() || !data['code-editor'].trim() || !entry) throw new Error('Điền tên bot, source và chọn mùa giải hoặc luyện tập.');
    if (new TextEncoder().encode(data['code-editor']).length > maxSize) throw new Error(`Source vượt ${maxSize} byte.`);
    await saveDraft();
    const payload = {ai_name: data['ai-name'].trim(), source_code: data['code-editor'],
      competition_entry: entry === 'practice' ? null : Number(entry), practice: entry === 'practice',
      submission_method: data['submission-method'],
      git_url: data['submission-method'] === 'git' ? data['git-url'].trim() : '',
      git_commit: data['submission-method'] === 'git' ? data['git-commit'].trim() : ''};
    const existing = (await all()).find(job => job.owner === owner.id && job.state !== 'accepted' && JSON.stringify(job.payload) === JSON.stringify(payload));
    if (!existing) await saveJob({id: window.submissionId(), owner: owner.id, payload, created: Date.now(), state: 'queued'});
    announce('Đã lưu bài vào hàng đợi trên máy. Chưa có biên nhận thì chưa xác nhận đã nộp.');
    await render(); await sync();
    }); } finally {
      enqueuing = false;
      document.getElementById('submit-btn').disabled = false;
    }
  };
  document.getElementById('save-local-draft').onclick = () => guarded(saveDraft);
  document.getElementById('export-local-code').onclick = () => download(document.getElementById('code-editor').value);
  document.getElementById('sync-local-queue').onclick = () => guarded(async () => {
    for (const job of await all()) if (job.owner === owner?.id && job.state === 'queued') { job.next = 0; await saveJob(job); }
    await sync();
  });
  document.getElementById('clear-local-data').onclick = () => guarded(async () => {
    if (busy) throw new Error('Đang gửi bài, hãy chờ hoàn tất trước khi xóa.');
    if (!owner || !confirm('Xóa bản nháp, source và mọi biên nhận/bài chờ của tài khoản này trên máy? Hãy tải file dự phòng trước.')) return;
    await request('drafts', 'readwrite', store => store.delete(`draft:${owner.id}`));
    for (const job of await all()) if (job.owner === owner.id) await removeJob(job.id);
    document.getElementById('code-editor').value = '';
    await render(); announce('Đã xóa dữ liệu bài local của tài khoản này.');
  });
  fields.forEach(id => {
    for (const event of ['input', 'change']) document.getElementById(id).addEventListener(event, () => {
      clearTimeout(timer); timer = setTimeout(() => guarded(saveDraft), 400);
    });
  });
  window.addEventListener('online', () => guarded(sync));
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden' && ready && owner) { clearTimeout(timer); guarded(saveDraft); }
  });
  window.addEventListener('offline', () => announce('Đang offline. Tiếp tục sửa và lưu; bài chờ sẽ gửi khi mở trang có mạng lại.'));
  document.querySelectorAll('form[action="/logout/"]').forEach(form => form.addEventListener('submit', event => {
    if (!confirm('Dữ liệu bài vẫn nằm trên trình duyệt sau đăng xuất. Bạn đã tải dự phòng và xóa dữ liệu nếu dùng máy chung?')) event.preventDefault();
  }));
  async function init() {
    const opening = indexedDB.open('ott-submission-local-v1', 1);
    opening.onupgradeneeded = () => {
      opening.result.createObjectStore('drafts', {keyPath: 'key'});
      opening.result.createObjectStore('outbox', {keyPath: 'id'});
    };
    db = await new Promise((resolve, reject) => { opening.onsuccess = () => resolve(opening.result); opening.onerror = () => reject(opening.error); });
    if (panel.dataset.userId) {
      owner = {id: panel.dataset.userId, username};
      await put({key: 'last-owner', data: owner});
    } else owner = (await get('last-owner'))?.data;
    ready = true;
    if (!owner) { announce('Mở trang Nộp AI online và đăng nhập một lần trước khi dùng offline.'); return; }
    restore((await get(`draft:${owner.id}`))?.data);
    announce(`Bản local của ${owner.username}. Tự lưu bản nháp; hạn nộp vẫn do server kiểm tra.`);
    if ('serviceWorker' in navigator && window.isSecureContext) {
      navigator.serviceWorker.register('/submission-sw.js').then(() => navigator.serviceWorker.ready)
        .then(() => announce(`Đã sẵn sàng mở trang Nộp AI offline cho ${owner.username}. Giữ bản .py dự phòng.`))
        .catch(() => announce('Bản nháp vẫn lưu local; chưa cài được trang offline. Cần HTTPS hoặc localhost và mở online trước.'));
    } else {
      document.getElementById('offline-capability').textContent = 'Đang dùng HTTP qua LAN: lưu nháp và bài chờ được, nhưng phải giữ trang này mở nếu mất LAN. Tải .py dự phòng. Muốn mở lại trang khi mất LAN cần HTTPS đã được trình duyệt tin cậy.';
    }
    await render(); await sync();
    setInterval(() => guarded(sync), 15000);
  }
  guarded(init);
})();
