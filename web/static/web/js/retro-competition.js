(() => {
  const list=document.getElementById('season-list'), status=document.getElementById('competition-status');
  const node=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};
  const csrf=()=>decodeURIComponent(document.cookie.split('; ').find(v=>v.startsWith('csrftoken='))?.slice(10)||'');
  async function load(){
    try{
      const response=await fetch('/api/competition/me/',{credentials:'same-origin'}),data=await response.json();
      if(!response.ok)throw Error(data.error||'Không tải được mùa giải.');
      list.replaceChildren();status.textContent=data.seasons.length?'Chọn mùa giải và đăng ký bằng tài khoản đại diện của nhóm.':'Chưa có mùa giải đang mở.';
      for(const season of data.seasons){
        const card=node('section');card.className='retro-window';const title=node('div',season.name);title.className='window-title';
        const body=node('div');body.className='window-body';const entry=data.entries.find(e=>e.season_id===season.id);
        body.append(node('p',season.participants+' / '+season.capacity+' tài khoản đại diện'));
        if(entry){
          body.append(node('h3',entry.display_name),node('p',entry.status==='disqualified'?'Mục dự thi đã bị loại.':entry.status==='locked'?'Bản dự thi đã khóa.':'Bạn đã đăng ký thành công.'));
          if(entry.position?.group)body.append(node('p',`Bạn ở bảng ${entry.position.group} · Hạng tạm thời ${entry.position.rank} · ${entry.position.points} điểm`));
          const link=node('a','Xem bảng đấu của tôi');link.href='/tournament/?season='+season.id;link.className='retro-button primary';body.append(link);
          if(entry.status==='registered'){const upload=node('a','Nộp bot Python');upload.href='/ai/?entry='+entry.id;upload.className='retro-button';body.append(upload);}
        }else if(season.registration_open){
          body.append(node('p','Đang nhận đăng ký'+(season.registration_deadline?' đến '+new Date(season.registration_deadline).toLocaleString('vi-VN'):'')+'.'));
          const form=node('form');form.className='ops-form';const label=node('label','Tên dự thi (tùy chọn)');const input=node('input');input.maxLength=120;input.placeholder='Tên nhóm hoặc tên hiển thị';label.append(input);const button=node('button','Đăng ký tham gia');button.className='retro-button primary';button.type='submit';form.append(label,button);
          form.onsubmit=async event=>{event.preventDefault();button.disabled=true;try{const r=await fetch('/api/competition/seasons/'+season.id+'/register/',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRFToken':csrf()},body:JSON.stringify({display_name:input.value})});const result=await r.json();if(!r.ok)throw Error(result.error||'Không đăng ký được.');await load();status.textContent='Đã đăng ký. Bấm Nộp bot Python để gửi bài cho mùa giải này.';}catch(error){status.textContent=error.message;}finally{button.disabled=false;}};
          body.append(form);
        }else body.append(node('p','Mùa giải đã đóng đăng ký hoặc bắt đầu thi đấu.'));
        card.append(title,body);list.append(card);
      }
    }catch(error){status.textContent=error.message;}
  }
  load();
})();
