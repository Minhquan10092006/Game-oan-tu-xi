(() => {
  const status=document.getElementById('submission-admin-status');
  const csrf=()=>decodeURIComponent(document.cookie.split('; ').find(v=>v.startsWith('csrftoken='))?.slice(10)||'');
  document.getElementById('admin-source-close').onclick=()=>document.getElementById('admin-source-dialog').close();
  document.addEventListener('click',async event=>{
    const code=event.target.closest('[data-view-code]'),review=event.target.closest('[data-review]');
    if(!code&&!review)return;const button=code||review;button.disabled=true;
    try{
      if(code){const r=await fetch('/admin/submission/'+code.dataset.viewCode+'/code/',{credentials:'same-origin'});const data=await r.json();if(!r.ok)throw Error(data.error||'Không đọc được mã nguồn.');document.getElementById('admin-source-title').textContent=data.ai_name+' · phiên bản '+data.version;document.getElementById('admin-source-content').textContent=data.source_code;document.getElementById('admin-source-dialog').showModal();}
      else{const action=review.dataset.review;let reason='';if(action==='reject'){reason=prompt('Lý do từ chối bài:');if(!reason?.trim())return;}const r=await fetch('/api/submissions/admin/'+review.dataset.id+'/'+action+'/',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRFToken':csrf()},body:JSON.stringify({reason})});const data=await r.json();if(!r.ok)throw Error(data.error||'Không cập nhật được bài.');location.reload();}
    }catch(error){status.textContent=error.message;}finally{button.disabled=false;}
  });
})();
