/* Draw the actual winner_to graph as two wings around a central final. */
(() => {
  const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  function render(rounds,thirdPlace,entry,onReplay,canOperate=false,completed=false){
    const wrap=node('div',undefined,'real-tree-scroll');wrap.tabIndex=0;wrap.setAttribute('aria-label','Sơ đồ loại trực tiếp, cuộn ngang để xem hai nhánh và chung kết');
    const tree=node('div',undefined,'real-tree');wrap.append(tree);
    const all=rounds.flatMap(r=>r.fixtures),byId=new Map(all.map(f=>[f.id,f]));
    const finalRound=rounds.find(r=>r.stage==='final')||rounds.at(-1);
    if(!finalRound?.fixtures.length)return {element:wrap,destroy:()=>{}};
    const final=finalRound.fixtures[0],elements=new Map();
    const parents=id=>all.filter(f=>f.winner_to_id===id).sort((a,b)=>String(a.winner_to_slot).localeCompare(String(b.winner_to_slot)));
    const reaches=(fixture,id)=>{const visited=new Set();let current=fixture;while(current&&!visited.has(current.id)){if(current.id===id)return true;visited.add(current.id);current=byId.get(current.winner_to_id);}return false;};
    function card(f){
      const item=node('article',undefined,'tree-match');item.dataset.fixtureId=f.id;
      if(entry&&[f.entry1_id,f.entry2_id].includes(entry.id))item.classList.add('my-match');
      item.append(node('small',`Trận ${f.match_number}`,'tree-match-number'));
      for(const [name,id] of [[f.entry1,f.entry1_id],[f.entry2,f.entry2_id]]){
        const row=node('div',name||'Chờ xác định','tree-team');row.title=name||'Chờ xác định';
        if(id&&id===f.winner_id)row.classList.add('winner');
        if(entry&&id===entry.id)row.classList.add('own-team');item.append(row);
      }
      const label=f.result==='bye'?'Miễn vòng':f.job_state==='running'?'Đang chấm':f.job_state==='review'?'Chờ trọng tài':f.winner?`Thắng: ${f.winner}`:f.result==='draw'?'Hòa':'Chờ kết quả';
      item.append(node('small',label,'tree-match-status'));
      if(f.job_id&&['completed','review'].includes(f.job_state)&&(canOperate||completed||(entry&&[f.entry1_id,f.entry2_id].includes(entry.id)))){
        const button=node('button','Xem replay','tree-replay');button.type='button';button.onclick=()=>onReplay(f);item.append(button);
      }
      elements.set(f.id,item);return item;
    }
    const roots=parents(final.id),halves=[];
    function half(root,side){
      const wing=node('div',undefined,`tree-wing tree-${side}`),columns=[];
      for(const round of rounds.filter(r=>r!==finalRound)){
        const fixtures=round.fixtures.filter(f=>reaches(f,root.id));if(!fixtures.length)continue;
        const column=node('section',undefined,'tree-round');column.append(node('h4',round.name));
        for(const f of fixtures)column.append(card(f));wing.append(column);columns.push({column,fixtures});
      }
      halves.push({columns,root});return wing;
    }
    const left=roots[0]?half(roots[0],'left'):null,right=roots[1]?half(roots[1],'right'):null;
    const center=node('section',undefined,'tree-center');center.append(node('h4','CHUNG KẾT'),card(final));
    if(thirdPlace.length){const bronze=node('div',undefined,'tree-bronze');bronze.append(node('h4','Tranh hạng ba'));thirdPlace.forEach(f=>bronze.append(card(f)));center.append(bronze);}
    if(left)tree.append(left);tree.append(center);if(right)tree.append(right);
    const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.classList.add('tree-connectors');svg.setAttribute('aria-hidden','true');tree.prepend(svg);
    let destroyed=false,frame;
    function layout(){
      if(destroyed||!wrap.isConnected)return;
      const rows=Math.max(1,...halves.map(h=>h.columns[0]?.fixtures.length||1));
      const spacing=tree.querySelector('.tree-replay')?124:100,height=Math.max(360,rows*spacing+64);
      for(const {columns} of halves){
        const positions=new Map();
        columns.forEach(({column,fixtures},index)=>{
          column.style.height=height+'px';
          fixtures.forEach((f,i)=>{
            const incoming=parents(f.id).map(p=>positions.get(p.id)).filter(v=>v!==undefined);
            const y=index&&incoming.length?incoming.reduce((a,b)=>a+b,0)/incoming.length:72+(i+.5)*(height-72)/fixtures.length;
            positions.set(f.id,y);elements.get(f.id).style.top=y+'px';
          });
        });
      }
      center.style.minHeight=height+'px';
      svg.setAttribute('width',tree.scrollWidth);svg.setAttribute('height',tree.scrollHeight);svg.replaceChildren();
      const bounds=tree.getBoundingClientRect();
      for(const f of all){
        const a=elements.get(f.id),b=elements.get(f.winner_to_id);if(!a||!b)continue;
        const ar=a.getBoundingClientRect(),br=b.getBoundingClientRect(),forward=ar.left<br.left;
        const x1=(forward?ar.right:ar.left)-bounds.left,x2=(forward?br.left:br.right)-bounds.left;
        const y1=ar.top+ar.height/2-bounds.top,y2=br.top+br.height/2-bounds.top,mid=(x1+x2)/2;
        const path=document.createElementNS(svg.namespaceURI,'path');path.setAttribute('d',`M${x1},${y1} H${mid} V${y2} H${x2}`);svg.append(path);
      }
    }
    const schedule=()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(layout);};
    const observer=new ResizeObserver(schedule);observer.observe(wrap);schedule();
    return {element:wrap,destroy:()=>{destroyed=true;observer.disconnect();cancelAnimationFrame(frame);}};
  }
  window.TournamentBracket={render};
})();
