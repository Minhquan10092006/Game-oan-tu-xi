(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const base = '/api/competition/';
  let season = '', state = null, page = 1, pages = 1, busy = false, generation = 0;
  let groupPage = 1, groupPages = 1;
  const names = {queued:'Đang chờ',running:'Đang chấm',completed:'Hoàn thành',failed:'Lỗi máy chấm',review:'Cần trọng tài'};
  const phases = {registration:'Đăng ký',submission:'Nộp bài',locked:'Khóa bài',running:'Thi đấu',completed:'Kết thúc'};
  const entryNames = {registered:'Đã đăng ký',locked:'Đã khóa bài',withdrawn:'Đã rút khỏi giải',disqualified:'Không đủ điều kiện'};
  const resultNames = {scheduled:'Chưa đấu',entry1_win:'Đơn vị 1 thắng',entry2_win:'Đơn vị 2 thắng',draw:'Hòa',bye:'Miễn vòng'};
  let activePanel = 'overview';
  function openPanel(name, disclosure) {
    if (!document.querySelector(`[data-ops-panel="${name}"]`)) return;
    activePanel = name;
    document.querySelectorAll('[data-ops-panel]').forEach(panel => { panel.hidden = panel.dataset.opsPanel !== name; });
    document.querySelectorAll('[data-ops-tab]').forEach(tab => {
      if (tab.dataset.opsTab === name) tab.setAttribute('aria-current', 'page');
      else tab.removeAttribute('aria-current');
    });
    if (disclosure && $(disclosure)) { $(disclosure).open = true; $(disclosure).scrollIntoView({block:'nearest'}); }
  }
  const csrf = () => decodeURIComponent(document.cookie.split('; ').find(x => x.startsWith('csrftoken='))?.slice(10) || '');
  function node(tag, text, cls) { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if(cls) n.className=cls; return n; }
  function message(text) { $('ops-message').textContent=text; $('ops-message').hidden=!text; }
  async function api(path, data) {
    const response = await fetch(base + path, {credentials:'same-origin', ...(data === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf()},body:JSON.stringify(data)})});
    if (!response.ok) { const payload = await response.json().catch(() => ({})); throw Error(payload.error || `Yêu cầu thất bại (${response.status})`); }
    return response.json();
  }
  function button(text, action) { const b=node('button',text,'retro-button'); b.type='button'; b.onclick=async()=>{ b.disabled=true; try{await action();}catch(e){message(e.message);}finally{b.disabled=false;} };return b; }
  let replayFrames=[], replayTimer=null;
  function drawReplay(){const index=Number($('ops-replay-timeline').value),snapshot=replayFrames[index];if(!snapshot)return;const b=snapshot.board;if(!b || b.rows>20 || b.cols>20)return;const board=$('ops-replay-board');board.style.gridTemplateColumns=`repeat(${b.cols},1fr)`;board.replaceChildren();for(let r=1;r<=b.rows;r++)for(let c=1;c<=b.cols;c++){const piece=snapshot.pieces.find(p=>p.at[0]===r && p.at[1]===c);const cell=node('div',piece?({rock:'B',paper:'Ba',scissors:'K'}[piece.type] || '?'):'',`ops-cell ${piece?.owner==='P1'?'p1':piece?'p2':''}`);if(piece)window.ReplayPieces.paint(cell,piece);if((b.blocked_cells || []).some(p=>p[0]===r && p[1]===c))cell.classList.add('blocked');cell.title=`${r},${c}${piece?' · '+piece.owner:''}`;board.append(cell);}$('ops-replay-info').textContent=`Bước ${index}/${replayFrames.length-1} · lượt ${snapshot.current_player} · ${snapshot.status}`;}
  async function showReplay(id){const result=await api(`jobs/${id}/replay/`);replayFrames=(result.events || result.replay?.events || []).map(e=>e.state_after || e.final_state).filter(Boolean);if(!replayFrames.length)throw Error('Chưa có dữ liệu replay.');$('ops-replay-title').textContent=`Replay tác vụ #${id}`;$('ops-replay-timeline').max=replayFrames.length-1;$('ops-replay-timeline').value=0;drawReplay();$('ops-replay').showModal();}
  async function mutate(path, data) { await api(path,data); message('Đã lưu thay đổi.'); await refresh(); }
  const seasonPath = suffix => `seasons/${season}/${suffix}/`;
  function renderNextStep(data) {
    const v=data.progress.validation,f=data.progress.fixture;
    let title,description,label,action,href;
    const panel=(name,detail)=>()=>openPanel(name,detail);
    const change=phase=>()=>{if(confirm('Chuyển giải sang '+phases[phase]+'?'))return mutate(seasonPath('operate'),{action:'phase',phase});};
    if(data.operator){
      if(data.phase==='completed'){title='Mùa giải đã hoàn tất';description='Xem lại kết quả và replay trong lịch sử đấu.';label='Xem lịch sử đấu';action=panel('results');}
      else if(!data.judge_image){title='Thiết lập mùa giải';description='Đặt thời hạn và môi trường chấm trước khi nhận bài.';label='Mở thiết lập';action=panel('manage','ops-settings-panel');}
      else if(data.phase==='registration'){title='Đang nhận đăng ký đại diện';description='Mỗi nhóm chỉ cần một sinh viên đăng ký. Khi sẵn sàng, mở nộp bài; đăng ký vẫn theo thời hạn đã đặt.';label='Mở nộp bài';action=change('submission');}
      else if(data.phase==='submission'){
        if(v.running||v.queued){title='Đang kiểm tra bài Python';description='Đã kiểm tra '+v.completed+'/'+v.total+' bài.';label='Xem tác vụ chấm';action=panel('manage','ops-jobs-panel');}
        else if(v.failed||v.passed<v.completed){title='Có bài cần xử lý';description='Xem lỗi máy chấm hoặc bài không đạt trước khi khóa.';label='Xử lý bài';action=panel('manage','ops-jobs-panel');}
        else if(v.total&&v.passed===v.total){title='Các bài đã đạt kiểm tra';description='Nếu đã hết thời gian nộp, khóa phiên bản chính thức để bốc thăm.';label='Khóa bài';action=change('locked');}
        else{title='Kiểm tra bài đã nộp';description='Các đại diện cần nộp và chọn bản chính thức. Máy sẽ kiểm tra những bài đã chọn.';label='Kiểm tra bài Python';action=()=>mutate(seasonPath('operate'),{action:'validate'});}
      }else if(data.phase==='locked'){
        if(v.passed<v.total){title='Hoàn tất kiểm tra bài';description='Tất cả bản chính thức cần đạt kiểm tra trước khi thi đấu.';label='Xem tác vụ';action=panel('manage','ops-jobs-panel');}
        else if(!data.drawn){title='Sẵn sàng bốc thăm';description='Chia bảng và tạo lịch thi đấu cho các mục dự thi.';label='Bốc thăm';action=async()=>{if(confirm('Bốc thăm và tạo lịch thi đấu?'))await mutate(seasonPath('operate'),{action:'draw'});};}
        else{title='Lịch đấu đã sẵn sàng';description='Chuyển sang thi đấu rồi đưa trận vào hàng đợi.';label='Bắt đầu thi đấu';action=change('running');}
      }else if(data.paused){title='Chấm bài đang tạm dừng';description='Tiếp tục giao việc khi máy chấm đã sẵn sàng.';label='Tiếp tục chấm';action=()=>mutate(seasonPath('operate'),{action:'pause'});}
      else if(f.failed||f.review){title='Có trận cần admin xử lý';description='Xem lỗi hoặc áp dụng quy tắc phân thắng thua cho trận hòa.';label='Xử lý tác vụ';action=panel('manage','ops-jobs-panel');}
      else if(f.total&&f.completed===f.total){title='Đã hoàn tất các trận';description='Kiểm tra lịch sử đấu và chốt kết quả chính thức.';label='Kết thúc mùa giải';action=change('completed');}
      else if(f.running||f.queued){title='Các máy đang chấm trận';description='Đã hoàn thành '+f.completed+'/'+f.total+' trận.';label='Theo dõi lịch sử đấu';action=panel('results');}
      else{title='Đưa trận vào hàng đợi';description='Bốn máy đang kết nối sẽ tự nhận các trận đủ đối thủ.';label='Bắt đầu chấm trận';action=()=>mutate(seasonPath('operate'),{action:'queue'});}
    }else{
      const entry=data.entries.find(e=>['registered','locked'].includes(e.status)),mine=entry&&data.jobs.find(j=>j.kind==='validation'&&j.entry===entry.name);
      if(!entry){title='Đăng ký bằng tài khoản đại diện';description='Một sinh viên đăng ký và nộp bot cho cả nhóm. Không cần lập đội hay email.';label='Đăng ký giải';href='/competition/';}
      else if(['registration','submission'].includes(data.phase)&&!entry.selected){title='Nộp bot Python của nhóm';description='Bạn đã đăng ký. Bấm bên dưới để nộp bot cho đúng mùa giải.';label='Nộp bot Python';href='/ai/?entry='+entry.id;}
      else if(['registration','submission'].includes(data.phase)){
        if(mine&&['queued','running'].includes(mine.state)){title='Bài của bạn đang được kiểm tra';description='Chờ máy trả kết quả; không cần gửi lặp lại.';label='Xem báo cáo';action=panel('results','ops-jobs-panel');}
        else if(mine?.valid===false){title='Bài cần sửa';description='Xem báo cáo, nộp phiên bản mới rồi chọn lại bản chính thức.';label='Xem lỗi';action=panel('results','ops-jobs-panel');}
        else if(mine?.valid===true){title='Bài đã đạt kiểm tra';description='Chờ admin khóa bài và bắt đầu giải.';label='Xem bài chính thức';action=panel('overview');}
        else{title='Kiểm tra bot trước khi thi';description='Bản chính thức đã được chọn. Gửi kiểm tra thử để phát hiện lỗi.';label='Kiểm tra bài Python';action=()=>mutate('entries/'+entry.id+'/preflight/',{});}
      }else{title=data.phase==='completed'?'Kết quả đã được chốt':'Theo dõi giải đấu';description='Xem lịch, xếp hạng và replay các trận của bạn.';label='Xem kết quả';action=panel('results');}
    }
    if($('ops-registration-link'))$('ops-registration-link').hidden=!!data.entries.length;
    $('ops-next-title').textContent=title;$('ops-next-description').textContent=description;
    let control;if(href){control=node('a',label,'retro-button primary');control.href=href;}else{control=button(label,action);control.classList.add('primary');}
    $('ops-next-action').replaceChildren(control);
  }
  function render(data) {
    state=data;
    $('ops-content').hidden=false; $('ops-progress').hidden=false;
    renderNextStep(data);
    $('ops-name').textContent=data.name;
    $('ops-summary').textContent=`${data.participants} / ${data.capacity} người · ${data.phase_label} · ${data.provisional ? 'Kết quả tạm tính' : 'Kết quả chính thức'}${data.paused ? ' · Đã tạm dừng giao việc mới' : ''}`;
    $('ops-phases').replaceChildren(...Object.entries(phases).map(([key,value],index)=>{const step=node('li',`${index+1}. ${value}`,key===data.phase?'current':'');if(key===data.phase)step.setAttribute('aria-current','step');return step;}));
    const date = value => value ? new Date(value).toLocaleString('vi-VN') : 'Chưa đặt';
    $('ops-deadlines').textContent=`Hạn đăng ký: ${date(data.registration_deadline)} · Nộp bài: ${date(data.submission_deadline)}`;
    if($('ops-profile') && !$('ops-profile').dataset.loaded){$('ops-profile').elements.student_id.value=data.profile.student_id;$('ops-profile').elements.class_name.value=data.profile.class_name;$('ops-profile').dataset.loaded='true';}
    $('ops-workers').replaceChildren(...[1,2,3,4].map(slot=>{
      const worker=data.workers.find(w=>w.slot===slot), el=node('div',undefined,`ops-worker ${worker?.online?'online':''}`);
      el.append(node('strong',worker?.name || `Máy chấm ${slot}`),node('span',!worker?'Chưa cấu hình':!worker.enabled?'Đã vô hiệu hóa':!worker.online?'Mất kết nối / chưa chạy':worker.activity==='practice'?'Đang chấm luyện tập':worker.job?`Đang chấm #${worker.job}`:'Sẵn sàng'));return el;
    }));
    for(const kind of ['validation','fixture']) {
      const p=data.progress[kind]; $(`${kind}-label`).textContent=`${p.completed} / ${p.total} · ${p.percent}%`;
      $(`${kind}-progress`).value=p.percent;
      $(`${kind}-detail`).textContent=`${p.running} đang chấm · ${p.queued} chờ · ${p.failed} lỗi máy · ${p.review} cần trọng tài`;
    }
    $('ops-entries').replaceChildren(...(data.operator?[]:data.entries).map(entry=>{
      const el=node('div',undefined,'ops-entry');el.append(node('h3',entry.name),node('p',entryNames[entry.status] || entry.status));
      const selected=entry.submissions.find(sub=>sub.id===entry.selected);
      el.append(node('p',selected?`Bản chính thức: ${selected.ai_name} · phiên bản ${selected.version}`:entry.selected?'Đã chọn bản chính thức.':'Chưa có bài chính thức.'));
      const receipt=node('details',undefined,'ops-inner-details');receipt.append(node('summary','Xem mã dự thi và biên nhận'),node('p',`Mã dự thi: ${entry.id}`),node('code',entry.hash || 'Biên nhận sẽ có sau khi nộp bài.'));el.append(receipt);
      if(entry.exclusion_reason)el.append(node('p',entry.exclusion_reason));
      if(entry.captain && ['registration','submission'].includes(data.phase) && entry.status==='registered'){
        const actions=node('div',undefined,'ops-actions');const upload=node('a',entry.selected?'Nộp phiên bản mới':'Nộp bài Python','retro-button');upload.href='/ai/?entry='+entry.id;actions.append(upload);
        if(entry.submissions.length){
          const label=node('label','Phiên bản dự thi ');const select=node('select');select.setAttribute('aria-label','Chọn phiên bản chính thức cho '+entry.name);
          for(const sub of entry.submissions){const option=node('option',`${sub.ai_name} · phiên bản ${sub.version}`);option.value=sub.id;option.selected=sub.id===entry.selected;select.append(option);}
          label.append(select);actions.append(label,button('Lưu lựa chọn',()=>mutate(`entries/${entry.id}/choose-bot/`,{submission_id:Number(select.value)})));
        }
        el.append(actions);
        const extra=node('details',undefined,'ops-inner-details');extra.append(node('summary','Thao tác khác'));
        if(entry.selected)extra.append(button('Kiểm tra thử Python',()=>mutate(`entries/${entry.id}/preflight/`,{})));
        extra.append(button('Rút khỏi giải',async()=>{if(confirm('Rút mục dự thi này khỏi giải?'))await mutate(`entries/${entry.id}/withdraw/`,{});}));el.append(extra);
      }return el;
    }));
    if(!data.entries.length) $('ops-entries').append(node('p','Bạn chưa có mục dự thi. Đăng ký tại trang Đăng ký giải.'));
    $('ops-entry-section').hidden=data.operator;
    $('ops-jobs').replaceChildren(...data.jobs.map(job=>{
      const row=node('tr'); const outcome=job.valid===true?'Đạt':job.valid===false?'Không đạt':'';
      for(const value of [`#${job.id}`,job.entry,names[job.state],job.worker || '—',[outcome,job.message].filter(Boolean).join(' · ')])row.append(node('td',String(value)));
      const actions=node('td');
      if(job.kind==='fixture')actions.append(button('Xem replay',()=>showReplay(job.id)),button('Tải replay',async()=>{const replay=await api(`jobs/${job.id}/replay/`);const url=URL.createObjectURL(new Blob([JSON.stringify(replay,null,2)],{type:'application/json'}));const a=node('a');a.href=url;a.download=`replay-${job.id}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}));
      if(data.operator && ['failed','review'].includes(job.state))actions.append(button('Chạy lại',async()=>{const reason=prompt('Lý do chạy lại:');if(reason)await mutate(`jobs/${job.id}/retry/`,{reason});}));
      if(data.operator && job.state==='review')for(const result of ['entry1_win','entry2_win'])actions.append(button(result==='entry1_win'?'Đơn vị 1 thắng':'Đơn vị 2 thắng',async()=>{const reason=prompt('Ghi quy tắc phân thắng thua và lý do quyết định:');if(reason)await mutate(`jobs/${job.id}/adjudicate/`,{result,reason});}));
      row.append(actions);return row;
    }));
    $('ops-notices').replaceChildren(...data.notices.map(n=>{const el=node('article',undefined,'ops-notice');el.append(node('h3',n.title),node('p',n.body),node('small',date(n.created_at)));return el;}));
    if(!data.notices.length)$('ops-notices').append(node('p','Chưa có thông báo mới.','ops-muted'));
    if(data.operator){
      const nextPhase={registration:'submission',submission:'locked',locked:'running',running:'completed'}[data.phase];
      const phaseSelect=$('ops-phase').elements.phase;phaseSelect.replaceChildren();
      if(nextPhase){const option=node('option',phases[nextPhase]);option.value=nextPhase;phaseSelect.append(option);}
      $('ops-phase').hidden=!nextPhase;
      const allowed={validate:['submission','locked'],draw:['locked'],queue:['running'],pause:['submission','locked','running'],reopen:['locked']};
      document.querySelectorAll('[data-op]').forEach(b=>{b.hidden=!allowed[b.dataset.op]?.includes(data.phase) || (b.dataset.op==='draw' && data.drawn);});
      for(const field of $('ops-config').elements)field.disabled=!['registration','submission'].includes(data.phase);
      $('ops-export').href=base+seasonPath('roster');$('ops-pause').textContent=data.paused?'Tiếp tục giao việc':'Tạm dừng nhận việc';
      $('ops-waiting').replaceChildren(...data.waitlist.map(item=>{const el=node('p',item.user__username+' ');el.append(button('Nhận vào giải',()=>mutate(seasonPath('operate'),{action:'promote',user_id:item.user_id})));return el;}));
      if(!data.waitlist.length)$('ops-waiting').append(node('p','Không có người trong danh sách chờ.','ops-muted'));
      $('ops-audit').replaceChildren(...data.audit.map(a=>node('p',`${date(a.created_at)} · ${a.actor__username || 'Hệ thống'} · ${a.action} · ${JSON.stringify(a.detail)}`)));
      if(!$('ops-config').dataset.loaded){
        const form=$('ops-config');form.elements.capacity.value=data.capacity;form.elements.image.value=data.judge_image;
        for(const field of ['registration_deadline','submission_deadline']){if(data[field]){const d=new Date(data[field]);d.setMinutes(d.getMinutes()-d.getTimezoneOffset());form.elements[field].value=d.toISOString().slice(0,16);}else form.elements[field].value='';}
        form.dataset.loaded='true';
      }
    }
    $('ops-updated').textContent=`Cập nhật ${new Date().toLocaleTimeString('vi-VN')} · mỗi 10 giây`;
  }
  async function fixtures() {
    const selected=season, expectedPage=page;
    const data=await api(seasonPath('fixtures')+`?page=${page}`);
    if(selected!==season || expectedPage!==page)return;
    pages=data.pages;$('ops-page').textContent=`Trang ${page} / ${pages}`;$('ops-prev').disabled=page<=1;$('ops-next').disabled=page>=pages;
    $('ops-fixture-state').textContent=`${data.total} trận · ${data.provisional?'Kết quả tạm tính':'Kết quả chính thức'}`;
    const table=node('table'),head=node('tr');for(const label of ['Mã','Vòng','Bảng','Đơn vị 1','Đơn vị 2','Kết quả','Replay'])head.append(node('th',label));table.append(head);
    for(const f of data.fixtures){const row=node('tr');for(const value of [f.id,f.tournament_round__name,f.group__code || '—',f.entry1__display_name || 'Chờ xác định',f.entry2__display_name || 'Chờ xác định',resultNames[f.result] || f.result])row.append(node('td',String(value)));const replayCell=node('td');if(f.can_view_replay)replayCell.append(button('Xem replay',()=>showReplay(f.judging_job__id)));else replayCell.textContent='—';row.append(replayCell);table.append(row);}
    $('ops-fixtures').replaceChildren(data.total?table:node('p','Lịch đấu sẽ xuất hiện sau khi ban tổ chức bốc thăm.','ops-muted'));
  }
  async function groups(){const selected=season,expected=groupPage;const data=await api(seasonPath('standings')+`?page=${groupPage}`);if(selected!==season || expected!==groupPage)return;groupPages=data.pages;$('ops-group-page').textContent=`Trang ${groupPage} / ${groupPages}`;$('ops-group-prev').disabled=groupPage<=1;$('ops-group-next').disabled=groupPage>=groupPages;$('ops-standings').replaceChildren(...data.groups.map(g=>{const el=node('div');el.append(node('h3',`Bảng ${g.code}`));for(const row of g.rows)el.append(node('p',`${row.rank}. ${row.name} · ${row.points} điểm · ${row.played} trận`));return el;}));}
  async function refresh(){if(!season || busy)return;busy=true;const selected=season,epoch=generation;try{const data=await api(seasonPath('overview'));if(selected!==season || epoch!==generation)return;if(!state)message('');render(data);await Promise.all([fixtures(),groups()]);}catch(e){message(`Không cập nhật được: ${e.message}. Bấm Làm mới để thử lại.`);}finally{busy=false;if(epoch!==generation && season)refresh();}}
  function form(id, action){const el=$(id);if(el)el.onsubmit=async event=>{event.preventDefault();const data=Object.fromEntries(new FormData(el));try{await action(data);}catch(e){message(e.message);}};}
  $('ops-season').onchange=()=>{season=$('ops-season').value;generation++;page=1;groupPage=1;state=null;openPanel(new URLSearchParams(location.search).get('panel')==='judging'?'manage':new URLSearchParams(location.search).get('panel')==='results'?'results':'overview',new URLSearchParams(location.search).get('panel')==='judging'?'ops-jobs-panel':null);$('ops-content').hidden=true;$('ops-progress').hidden=true;if($('ops-config'))delete $('ops-config').dataset.loaded;message(season?'Đang tải mùa giải…':'Chọn mùa giải để bắt đầu.');refresh();};
  document.querySelectorAll('[data-ops-tab]').forEach(tab=>tab.onclick=()=>openPanel(tab.dataset.opsTab));
  document.querySelectorAll('[data-open-create]').forEach(b=>b.onclick=()=>{const panel=$('ops-create-panel');panel.open=true;panel.querySelector('input').focus();});
  $('ops-refresh').onclick=refresh;
  $('ops-replay-timeline').oninput=drawReplay;$('ops-replay-close').onclick=()=>$('ops-replay').close();$('ops-replay').onclose=()=>{clearInterval(replayTimer);replayTimer=null;};$('ops-replay-play').onclick=()=>{if(replayTimer){clearInterval(replayTimer);replayTimer=null;return;}replayTimer=setInterval(()=>{const control=$('ops-replay-timeline');if(Number(control.value)>=replayFrames.length-1){clearInterval(replayTimer);replayTimer=null;return;}control.value=Number(control.value)+1;drawReplay();},500);};
  $('ops-prev').onclick=()=>{if(page>1){page--;fixtures().catch(e=>message(e.message));}};$('ops-next').onclick=()=>{if(page<pages){page++;fixtures().catch(e=>message(e.message));}};
  $('ops-group-prev').onclick=()=>{if(groupPage>1){groupPage--;groups().catch(e=>message(e.message));}};$('ops-group-next').onclick=()=>{if(groupPage<groupPages){groupPage++;groups().catch(e=>message(e.message));}};
  if($('ops-waitlist'))$('ops-waitlist').onclick=async()=>{try{const data=await api(seasonPath('waitlist'),{});message(`Bạn ở vị trí ${data.position} trong danh sách chờ.`);}catch(e){message(e.message);}};
  form('ops-profile',data=>mutate('profile/',data));
  form('ops-config',data=>mutate(seasonPath('operate'),{...data,capacity:Number(data.capacity),action:'configure'}));
  form('ops-create',async data=>{const created=await api('seasons/create/',data);const option=node('option',created.name);option.value=created.id;$('ops-season').append(option);$('ops-season').value=String(created.id);$('ops-create-panel').open=false;$('ops-season').onchange();});
  form('ops-phase',async data=>{if(confirm(`Chuyển giải sang ${phases[data.phase]}?`))await mutate(seasonPath('operate'),{...data,action:'phase'});});
  form('ops-notice',data=>mutate(seasonPath('operate'),{...data,action:'notice'}));
  form('ops-import',data=>mutate(seasonPath('roster'),data));
  form('ops-disqualify',async data=>{if(confirm('Loại mục dự thi này khỏi danh sách trước bốc thăm?'))await mutate(seasonPath('operate'),{...data,entry_id:Number(data.entry_id),action:'disqualify'});});
  document.querySelectorAll('[data-op]').forEach(b=>b.onclick=async()=>{if(!season)return;try{if(b.dataset.op==='draw' && !confirm('Bốc thăm sẽ khóa danh sách và tạo lịch thi đấu. Tiếp tục?'))return;const payload={action:b.dataset.op};if(payload.action==='reopen'){payload.reason=prompt('Lý do mở lại nộp bài cho toàn bộ người tham gia:');if(!payload.reason)return;}await mutate(seasonPath('operate'),payload);}catch(e){message(e.message);}});
  setInterval(()=>{if(!document.hidden)refresh();},10000);
  if($('ops-season').options.length>1){$('ops-season').selectedIndex=1;$('ops-season').onchange();}
})();
