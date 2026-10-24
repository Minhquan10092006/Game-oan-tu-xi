(() => {
  const $ = id => document.getElementById(id);
  const csrf = () => decodeURIComponent(document.cookie.split('; ').find(x => x.startsWith('csrftoken='))?.slice(10) || '');
  const api = async (path, data) => { const r = await fetch('/api/competition/' + path, {credentials:'same-origin', ...(data === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json','X-CSRFToken':csrf()},body:JSON.stringify(data)})}); const body=await r.json().catch(()=>({})); if(!r.ok) throw Error(body.error || 'Không thể thực hiện thao tác này.'); return body; };
  let id = '';
  let replay = null, replayFrames = [], replayEvents = [], replayIndex = 0, replayTimer = null;
  const message = value => { $('message').textContent=value; };
  const dt = value => value ? new Date(value).toLocaleString('vi-VN') : 'Chưa đặt';
  async function load() {
    if(!id) return;
    const data = await api(`seasons/${id}/overview/`);
    $('season-content').hidden=false; $('season-name').textContent=data.name; $('season-description').textContent=data.description || '';
    $('deadline').textContent=dt(data.submission_deadline) + (data.submissions_open ? ' · Đang nhận bài' : ' · Đã đóng');
    $('statement').textContent=data.problem_statement || 'Ban tổ chức chưa đăng đặc tả.';
    const v=data.progress.validation, f=data.progress.fixture;
    $('progress').textContent=`Kiểm tra bot: ${v.completed}/${v.total}. Thi đấu: ${f.completed}/${f.total}. Giai đoạn: ${data.phase_label}.`;
    const status=$('job-status');
    if(status){
      const failed=(data.jobs || []).filter(job=>job.state==='failed');
      const active=(data.jobs || []).filter(job=>job.state==='queued' || job.state==='running');
      status.replaceChildren();
      if(failed.length){const error=document.createElement('p');error.className='form-error';error.textContent=`${failed.length} tác vụ lỗi. ${failed[0].result__message || failed[0].message || 'Máy chấm không chạy được.'}`;status.append(error);}
      else if(active.length){const progress=document.createElement('p');progress.textContent=`Đang xử lý ${active.length} tác vụ. Trang tự cập nhật.`;status.append(progress);}
      else if(data.phase==='completed'){status.textContent='Giải đã hoàn tất.';}
      else if(v.total){status.textContent=`Đã kiểm tra ${v.completed} trên ${v.total} bot.`;}
      else status.textContent='Chưa có tác vụ chấm.';
    }
    $('validation-progress').value=v.percent; $('fixture-progress').value=f.percent;
    $('ops-workers').textContent=(data.workers || []).map(w => `Máy ${w.slot}: ${w.online ? (w.job ? 'đang chấm' : 'sẵn sàng') : 'chưa kết nối'}`).join(' · ');
    const fixtures=await api(`seasons/${id}/fixtures/`);
    const holder=$('fixtures'); holder.replaceChildren();
    if (!fixtures.total) holder.textContent='Lịch đấu sẽ xuất hiện khi ban tổ chức chạy giải.';
    else {
      holder.append(`${fixtures.total} trận đã được tạo. Kết quả cập nhật tự động khi trận hoàn tất.`);
      const list=document.createElement('ul');
      fixtures.fixtures.forEach(f => { const item=document.createElement('li'); item.append(`${f.entry1__display_name || 'Chờ xác định'} — ${f.entry2__display_name || 'Chờ xác định'}: ${f.result} `); if(f.can_view_replay){const button=document.createElement('button'); button.type='button'; button.className='retro-button'; button.textContent='Xem diễn biến trận'; button.onclick=()=>showReplay(f.judging_job__id, f); item.append(button);} list.append(item); });
      holder.append(list);
    }
    const link=$('submit-link'); if(link) { link.hidden=!data.submissions_open; link.href='/ai/'; }
    message('');
  }
  const pieceIcons={rock:'●',paper:'■',scissors:'▲'};
  function stopReplay(){if(replayTimer){clearInterval(replayTimer);replayTimer=null;}const play=$('replay-play');if(play)play.textContent='▶ Phát';}
  function drawReplay(){
    const snapshot=replayFrames[replayIndex]; if(!snapshot)return;
    const boardData=snapshot.board, board=$('replay-board');
    board.style.gridTemplateColumns=`repeat(${boardData.cols},minmax(0,1fr))`;board.replaceChildren();
    const pieces=new Map((snapshot.pieces||[]).map(piece=>[piece.at.join(','),piece]));
    for(let row=1;row<=boardData.rows;row++)for(let col=1;col<=boardData.cols;col++){
      const cell=document.createElement('div'),key=`${row},${col}`,piece=pieces.get(key);cell.className='replay-cell';
      if((boardData.blocked_cells||[]).some(pos=>pos[0]===row&&pos[1]===col))cell.classList.add('blocked');
      if(piece){cell.classList.add(piece.owner.toLowerCase());cell.textContent=pieceIcons[piece.type]||'?';cell.title=`${piece.owner} · ${piece.type}`;}
      board.append(cell);
    }
    const event=replayEvents[replayIndex];
    $('replay-position').textContent=`Bước ${replayIndex+1}/${replayFrames.length} · Lượt ${snapshot.current_player||'—'} · ${snapshot.status||''}${event?.type==='move'?` · ${event.player}: ${event.from.join(',')} → ${event.to.join(',')}`:''}`;
    $('replay-slider').value=replayIndex;
    document.querySelectorAll('#replay-moves button').forEach(button=>button.classList.toggle('primary',Number(button.dataset.frame)===replayIndex));
    const final=replay?.result==='draw'?'Hòa':replay?.winner?`${replay.winner} thắng`:replay?.result||'';
    $('replay-summary').textContent=final?`Kết quả: ${final}`:'';
  }
  function goReplay(index){stopReplay();replayIndex=Math.max(0,Math.min(index,replayFrames.length-1));drawReplay();}
  async function showReplay(jobId, fixture){
    try{
      const result=await api(`jobs/${jobId}/replay/`);replay=result;replayEvents=result.events||[];
      replayFrames=replayEvents.map(event=>event.state_after||event.final_state).filter(Boolean);
      if(!replayFrames.length)throw Error('Trận chưa có dữ liệu diễn biến.');
      $('replay-title').textContent=`${fixture.entry1__display_name||'Đội 1'} — ${fixture.entry2__display_name||'Đội 2'}`;
      $('replay-slider').max=replayFrames.length-1;
      const moves=$('replay-moves');moves.replaceChildren();
      replayEvents.forEach((event,index)=>{if(event.type!=='move')return;const button=document.createElement('button');button.type='button';button.className='retro-button';button.dataset.frame=index;button.textContent=`${index+1}. ${event.player}: ${pieceIcons[event.piece_type]||''} ${event.from.join(',')} → ${event.to.join(',')}${event.captured_piece?` · bắt ${event.captured_piece.type}`:''}`;button.onclick=()=>goReplay(index);moves.append(button);});
      const logs=(result.bot_runs||[]).map(run=>[run.player||'Hệ thống',run.elapsed_ms!==undefined?`${run.elapsed_ms} ms`:'',run.error||'',run.stderr||''].filter(Boolean).join(' · ')).join('\n\n');
      $('replay-logs').textContent=logs||'Không có log bot.';goReplay(0);$('match-replay').showModal();
    }catch(error){message(error.message);}
  }
  $('season').onchange=async e=>{id=e.target.value; $('season-content').hidden=true; try{await load();}catch(err){message(err.message);}};
  const form=$('create-season'); if(form) form.onsubmit=async e=>{e.preventDefault();try{const data=Object.fromEntries(new FormData(form)); const created=await api('seasons/create/',data); const option=new Option(created.name,created.id,true,true);$('season').add(option);id=String(created.id);await load();message('Đã mở giải. Sinh viên có thể xem đề và nộp bài ngay.');}catch(err){message(err.message);}};
  const operate=async action=>{try{const result=await api(`seasons/${id}/operate/`,{action});await load();message(result.message || (action==='start_tournament'?'Đã gửi giải sang hàng đợi sandbox.':'Đã cập nhật giải.'));}catch(err){message(err.message);}};
  if($('close')) $('close').onclick=()=>{if(confirm('Đóng nhận bài ngay? Sinh viên sẽ không thể nộp thêm.'))operate('close_submissions');};
  if($('run')) $('run').onclick=()=>{if(confirm('Bắt đầu xử lý giải?'))operate('start_tournament');};
  if($('replay-back')) $('replay-back').onclick=()=>goReplay(replayIndex-1);
  if($('replay-next')) $('replay-next').onclick=()=>goReplay(replayIndex+1);
  if($('replay-slider')) $('replay-slider').oninput=()=>goReplay(Number($('replay-slider').value));
  if($('replay-play')) $('replay-play').onclick=()=>{if(replayTimer){stopReplay();return;}if(replayIndex>=replayFrames.length-1)goReplay(0);$('replay-play').textContent='⏸ Tạm dừng';replayTimer=setInterval(()=>{if(replayIndex>=replayFrames.length-1){stopReplay();return;}replayIndex++;drawReplay();},700);};
  if($('match-replay')) $('match-replay').addEventListener('close',stopReplay);
  if($('season').options.length>1){$('season').selectedIndex=1;$('season').dispatchEvent(new Event('change'));}
  setInterval(()=>{if(id&&!document.hidden)load().catch(err=>message(err.message));},10000);
})();
