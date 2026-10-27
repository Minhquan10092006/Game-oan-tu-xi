/* Real registered teams/results; the separate 48-team preview never writes data. */
(() => {
  const holder=document.getElementById('user-draw'), status=document.getElementById('draw-status');
  if(!holder)return;
  let generation=0,bracket=null;
  const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  document.addEventListener('tournament:loaded',async event=>{
    const run=++generation;
    try{
      const response=await fetch(`/api/competition/seasons/${encodeURIComponent(event.detail.id)}/draw/`,{credentials:'same-origin',cache:'no-store'});
      if(!response.ok)throw Error('Chưa tải được bảng đấu. Hệ thống sẽ thử lại.');
      const data=await response.json();if(run!==generation)return;
      const season=data.season,entry=data.entry;
      const oldScroll=holder.querySelector('.real-tree-scroll')?.scrollLeft||0;
      bracket?.destroy();bracket=null;
      const openedGroups=new Set([...holder.querySelectorAll('details[open]')].map(d=>d.dataset.group));
      const personal=document.getElementById('my-tournament-position');
      const ownMatchesOpen=personal?.querySelector('details')?.open;
      if(personal){personal.hidden=false;personal.replaceChildren();}
      holder.replaceChildren();
      if(!season){status.textContent='Mùa giải không còn trong danh sách đang mở.';if(personal)personal.hidden=true;return;}
      const replay=f=>document.dispatchEvent(new CustomEvent('tournament:replay',{detail:{jobId:f.job_id,fixture:{entry1__display_name:f.entry1,entry2__display_name:f.entry2}}}));
      const canReplay=f=>f.job_id&&['completed','review'].includes(f.job_state)&&(holder.dataset.operator==='true'||season.phase==='completed'||(entry&&[f.entry1_id,f.entry2_id].includes(entry.id)));
      let jump=null;
      if(personal){
        if(!entry){
          personal.append(node('h2','Bạn chưa đăng ký giải này'),node('p','Bạn vẫn xem được bảng đấu. Chọn Đăng ký giải trên menu để kiểm tra các mùa đang nhận đăng ký.'));
        }else{
          const position=entry.position;
          personal.append(node('p','VỊ TRÍ CỦA BẠN','eyebrow'),node('h2',`${entry.display_name}${position.group?' · Bảng '+position.group:''}`));
          if(!position.group)personal.append(node('p','Bạn đã đăng ký. Ban tổ chức chưa xếp bạn vào bảng; hãy chờ bốc thăm.'));
          else{
            const stats=node('div',undefined,'my-position-stats');
            for(const [label,value] of [['Hạng tạm thời',`${position.rank} / ${position.standings.length}`],['Điểm',position.points],['Đã đấu',position.played]]){const item=node('div');item.append(node('span',label),node('strong',String(value)));stats.append(item);}personal.append(stats);
            jump=node('button','Xem bảng của tôi','retro-button primary');jump.type='button';personal.append(jump);
            const details=node('details',undefined,'my-fixtures');details.open=!!ownMatchesOpen;details.append(node('summary','Các trận của bạn'));
            const list=node('ol');
            for(const f of position.fixtures){
              const result=f.job_state==='review'?'Chờ trọng tài':f.job_state==='running'?'Đang thi đấu':f.result==='scheduled'?'Chờ thi đấu':f.result==='bye'?'Miễn vòng':f.result==='draw'?'Hòa':f.winner_id===entry.id?'Bạn thắng':'Bạn thua';
              const item=node('li');item.append(node('strong',`${f.entry1} (P1) — ${f.entry2} (P2)`),node('span',`${f.round} · Lượt ${f.leg} · ${result}`));
              if(canReplay(f)){const button=node('button','Xem replay','retro-button tree-replay');button.type='button';button.onclick=()=>replay(f);item.append(button);}
              else if(f.result!=='bye')item.append(node('small','Replay sẽ có sau khi máy chấm trả kết quả.'));
              list.append(item);
            }
            details.append(list);personal.append(details);
          }
        }
      }
      status.textContent=season.paginated?'Giải có trên 128 đội. Bảng riêng của bạn được hiển thị bên dưới.':!season.drawn?'Ban tổ chức chưa bốc thăm. Bảng đấu sẽ xuất hiện sau khi công bố.':`${season.name} · Dữ liệu thật · ${season.groups.length} bảng. Thứ hạng còn tạm tính khi giải chưa kết thúc.`;
      const groups=node('div',undefined,'group-grid');
      const displayGroups=season.paginated && entry?.position.group?[{code:entry.position.group,standings:entry.position.standings}]:season.groups;
      for(const group of displayGroups){
        const card=node('article',undefined,'retro-window group-card');card.append(node('h3',`Bảng ${group.code}`));
        if(group.code===entry?.position.group){
          card.classList.add('my-group');card.tabIndex=-1;
          card.querySelector('h3').textContent+= ' · Bảng của bạn';
          if(jump)jump.onclick=()=>{card.scrollIntoView({behavior:document.body.dataset.motion==='paused'?'instant':'smooth',block:'start'});card.focus({preventScroll:true});};
        }
        const table=node('table',undefined,'standings-table');table.append(node('caption',`Xếp hạng bảng ${group.code}`,'sr-only'));
        const head=node('thead'),hr=node('tr');for(const label of ['#','Đội','Đã đấu','Thắng','Hòa','Thua','Điểm'])hr.append(node('th',label));head.append(hr);table.append(head);
        const body=node('tbody');for(const row of group.standings){const tr=node('tr');if(row.entry_id===entry?.id)tr.classList.add('my-team');for(const value of [row.rank,row.name+(row.entry_id===entry?.id?' · Bạn':''),row.played,row.wins,row.draws,row.losses,row.points])tr.append(node('td',String(value)));body.append(tr);}table.append(body);card.append(table);
        if(group.fixtures?.length){
          const details=node('details',undefined,'group-games');details.dataset.group=group.code;details.open=openedGroups.has(group.code);details.append(node('summary','Trận đấu & replay trong bảng'));
          const games=node('div',undefined,'group-games-grid');
          for(const f of group.fixtures){const tile=node('article',undefined,'group-game');const result=f.winner?`Thắng: ${f.winner}`:f.result==='draw'?'Hòa':f.job_state==='running'?'Đang chấm':'Chờ thi đấu';tile.append(node('strong',`${f.entry1} — ${f.entry2}`),node('small',`Lượt ${f.leg} · ${result}`));if(canReplay(f)){const b=node('button','Xem replay','tree-replay');b.type='button';b.onclick=()=>replay(f);tile.append(b);}games.append(tile);}details.append(games);card.append(details);
        }
        groups.append(card);
      }
      holder.append(groups);
      if(season.bracket.length || season.third_place.length){
        holder.append(node('h3','Nhánh loại trực tiếp'));
        bracket=window.TournamentBracket.render(season.bracket,season.third_place,entry,replay,holder.dataset.operator==='true',season.phase==='completed');
        holder.append(bracket.element);bracket.element.scrollLeft=oldScroll;
      }
    }catch(error){if(run===generation)status.textContent=error.message;}
  });
})();
