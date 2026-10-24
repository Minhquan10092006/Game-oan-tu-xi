(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const labels = {queued:'Chờ máy chấm',running:'Đang thi đấu',completed:'Hoàn thành',failed:'Chưa chấm được',cancelled:'Đã hủy'};
  const outcomes = {win:'Bạn thắng',loss:'Bạn thua',draw:'Hòa'};
  let choices, creating=false, active=false, pendingKey=null, pendingPayload='', timer, refreshing=false;
  let frames=[], replayTimer;
  const message = text => { $('practice-message').textContent=text; };
  const el = (tag,text) => { const n=document.createElement(tag); if(text!==undefined)n.textContent=text; return n; };
  const csrf = () => decodeURIComponent(document.cookie.split('; ').find(value=>value.startsWith('csrftoken='))?.slice(10) || '');
  async function api(path,data) {
    const response=await fetch('/api/practice/'+path,{credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(20000),
      ...(data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf()},body:JSON.stringify(data)})});
    const body=await response.json().catch(()=>({}));
    if(!response.ok)throw Error(typeof body.error==='string'?body.error:body.message || 'Không kết nối được. Bấm Làm mới hoặc thử lại.');
    return body;
  }
  function button(text, action) {
    const n=el('button',text);n.type='button';n.className='retro-button';
    n.onclick=async()=>{n.disabled=true;try{await action();}catch(error){message(error.message);}finally{n.disabled=false;}};return n;
  }
  function controls(){ $('practice-start').disabled=creating || active || !choices?.mine.length || choices.used>=choices.limit; }
  function describe(){const sample=choices?.samples.find(bot=>bot.key===$('practice-opponent').value);$('practice-description').textContent=sample?.description || 'Bot do người dùng nộp, đã được duyệt. Bạn chỉ xem được nước đi, không xem mã nguồn đối thủ.';}
  async function loadOptions(){
    const own=$('practice-own').value, opponent=$('practice-opponent').value;
    choices=await api('options/?q='+encodeURIComponent($('practice-search').value.trim()));
    $('practice-own').replaceChildren(...choices.mine.map(bot=>new Option(`${bot.ai_name} · v${bot.version}`,bot.id)));
    if(choices.mine.some(bot=>String(bot.id)===own))$('practice-own').value=own;
    $('practice-empty').hidden=!!choices.mine.length;
    const samples=el('optgroup');samples.label='Bot mẫu';
    choices.samples.forEach(bot=>samples.append(new Option(bot.label,bot.key)));
    const approved=el('optgroup');approved.label='Bot đã được duyệt';
    choices.opponents.forEach(bot=>approved.append(new Option(bot.label,bot.key)));
    $('practice-opponent').replaceChildren(samples,approved);
    if([...choices.samples,...choices.opponents].some(bot=>bot.key===opponent))$('practice-opponent').value=opponent;
    $('practice-quota').textContent=`Đã dùng ${choices.used}/${choices.limit} trận hôm nay. Hủy trận chờ vẫn tính lượt.`;
    $('practice-workers').textContent=choices.local_judge?'Trận sẽ được chấm tự động trên máy chủ khi sandbox sẵn sàng.':choices.online_workers?`${choices.online_workers} máy chấm đang kết nối.`:'Máy chấm chưa kết nối. Bạn có thể xếp trận và chờ hệ thống hoạt động lại.';
    describe();controls();
  }
  async function loadHistory(){
    const rows=await api('matches/');active=rows.some(row=>['queued','running'].includes(row.state));controls();
    $('practice-history').replaceChildren();
    if(!rows.length){const row=el('tr');const cell=el('td','Chưa có trận luyện tập. Chọn hai bot ở trên để bắt đầu.');cell.colSpan=5;row.append(cell);$('practice-history').append(row);}
    for(const match of rows){
      const row=el('tr');
      for(const value of [`#${match.id} · ${new Date(match.created_at).toLocaleString('vi-VN')}`,`${match.own_label} (${match.player_side})`,match.opponent_label,[outcomes[match.outcome] || labels[match.state],match.message].filter(Boolean).join(' · ')])row.append(el('td',value));
      const actions=el('td');
      if(match.state==='queued')actions.append(button('Hủy trận chờ',async()=>{if(confirm('Hủy trận chờ? Lượt luyện tập vẫn được tính.')){await api(`matches/${match.id}/cancel/`,{});await refresh();}}));
      if(match.state==='completed')actions.append(button('Xem replay',()=>showReplay(match.id)),button('Tải replay',async()=>{
        const replay=await api(`matches/${match.id}/replay/`);const url=URL.createObjectURL(new Blob([JSON.stringify(replay,null,2)],{type:'application/json'}));const link=el('a');link.href=url;link.download=`practice-${match.id}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
      }));row.append(actions);$('practice-history').append(row);
    }
  }
  function schedule(){clearTimeout(timer);if(!document.hidden && navigator.onLine)timer=setTimeout(()=>refresh(false),active?10000+Math.random()*3000:60000);}
  async function refresh(options=true){if(refreshing)return false;refreshing=true;try{if(options)await loadOptions();await loadHistory();return true;}catch(error){message(error.message);return false;}finally{refreshing=false;schedule();}}
  $('practice-form').onsubmit=async event=>{
    event.preventDefault();if(creating || active)return;
    const payload={submission_id:Number($('practice-own').value),opponent:$('practice-opponent').value,side:$('practice-side').value};
    const encoded=JSON.stringify(payload);
    if(encoded!==pendingPayload || !pendingKey){pendingKey=crypto.randomUUID();pendingPayload=encoded;}
    creating=true;controls();
    try{const match=await api('matches/',{...payload,request_id:pendingKey});pendingKey=null;message(`Đã xếp trận #${match.id}. Theo dõi kết quả bên dưới; trận chính thức được ưu tiên.`);await refresh();}
    catch(error){message(error.message);await loadHistory().catch(()=>{});}
    finally{creating=false;controls();}
  };
  $('practice-find').onclick=()=>refresh();$('practice-refresh').onclick=()=>refresh();$('practice-opponent').onchange=describe;
  function draw(){
    const index=Number($('ops-replay-timeline').value), snapshot=frames[index];if(!snapshot)return;
    const board=snapshot.board;if(!board || board.rows>20 || board.cols>20)return;
    $('ops-replay-board').style.gridTemplateColumns=`repeat(${board.cols},1fr)`;$('ops-replay-board').replaceChildren();
    for(let r=1;r<=board.rows;r++)for(let c=1;c<=board.cols;c++){
      const piece=(snapshot.pieces || []).find(p=>p.at[0]===r && p.at[1]===c);const cell=el('div',piece?({rock:'B',paper:'Ba',scissors:'K'}[piece.type] || '?'):'');
      cell.className='ops-cell'+(piece?(piece.owner==='P1'?' p1':' p2'):'');
      if((board.blocked_cells || []).some(p=>p[0]===r && p[1]===c))cell.classList.add('blocked');cell.title=`${r},${c}`;$('ops-replay-board').append(cell);
    }
    $('ops-replay-info').textContent=`Bước ${index}/${frames.length-1} · lượt ${snapshot.current_player}`;
  }
  async function showReplay(id){const replay=await api(`matches/${id}/replay/`);frames=(replay.events || []).map(event=>event.state_after || event.final_state).filter(Boolean);if(!frames.length)throw Error('Trận chưa có replay.');$('ops-replay-title').textContent=`Trận luyện tập #${id}`;$('ops-replay-timeline').max=frames.length-1;$('ops-replay-timeline').value=0;draw();$('ops-replay').showModal();}
  $('ops-replay-timeline').oninput=draw;$('ops-replay-close').onclick=()=>$('ops-replay').close();$('ops-replay').onclose=()=>{clearInterval(replayTimer);replayTimer=null;};
  $('ops-replay-play').onclick=()=>{if(replayTimer){clearInterval(replayTimer);replayTimer=null;return;}replayTimer=setInterval(()=>{const control=$('ops-replay-timeline');if(Number(control.value)>=frames.length-1){clearInterval(replayTimer);replayTimer=null;return;}control.value=Number(control.value)+1;draw();},500);};
  document.addEventListener('visibilitychange',schedule);window.addEventListener('online',schedule);window.addEventListener('offline',()=>clearTimeout(timer));
  refresh().then(ok=>{if(ok && choices)message('Chọn bot của bạn, đối thủ và bên đi để tạo trận luyện tập.');});
})();
