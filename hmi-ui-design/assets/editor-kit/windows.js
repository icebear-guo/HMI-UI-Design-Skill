// Window selection and independent page drafts use the same validated editor models.
(()=>{
 let busy=false,names={},selected=new Set();
 const clone=x=>structuredClone(x);
 const storageKey=()=>`mcgs-ui-windows:${config.catalog.revision}`;
 function save(){try{localStorage.setItem(storageKey(),JSON.stringify({names,selected:[...selected]}));}catch{show('浏览器无法保存窗口选择，请保留当前页面。','error');}}
 function render(){
  const list=$('#window-pages');list.replaceChildren();
  for(const page of config.catalog.pages){
   const row=document.createElement('div');row.className='window-page'+(page.id===config.pageId?' active':'');
   const check=document.createElement('input');check.type='checkbox';check.checked=selected.has(page.id);check.disabled=busy;check.dataset.pageId=page.id;check.setAttribute('aria-label','导出 '+names[page.id]);
   check.onchange=()=>{check.checked?selected.add(page.id):selected.delete(page.id);save();render();};
   const button=document.createElement('button');button.type='button';button.textContent=names[page.id];button.disabled=busy;button.dataset.pageId=page.id;button.setAttribute('aria-pressed',String(page.id===config.pageId));
   button.onclick=async()=>{try{await Editor.switchPage(page);render();show(`当前页面：${names[page.id]}。每页修改独立保存。`);}catch(e){show(e.message,'error');}};
   row.append(check,button);list.append(row);
  }
  $('#window-name').value=names[config.pageId]||'';$('#window-name').disabled=busy;
  $('#window-selection-count').textContent=`已选 ${selected.size} / ${config.catalog.pages.length} 个窗口`;
  for(const id of ['copy-windows','check-windows'])$('#'+id).disabled=busy||!selected.size||!config.window_ready;
  for(const id of ['select-all-windows','select-no-windows'])$('#'+id).disabled=busy;
 }
 function nameOK(name){return typeof name==='string'&&name===name.trim()&&/^[^\\/:*?"<>|\x00-\x1f]{1,30}$/.test(name);}
 function patchesFor(page){
  if(page.id===config.pageId)return Editor.getPatches();
  const cached=Editor.getCachedPatches(page.id);if(cached)return cached;
  const value=localStorage.getItem(`mcgs-ui-editor:${page.model.revision}`);
  if(!value)return [];
  const draft=JSON.parse(value);
  if(draft.revision!==page.model.revision||!Array.isArray(draft.patches))throw new Error(`${names[page.id]} 的草稿版本不匹配，请切换到该页检查。`);
  return draft.patches;
 }
 async function prepareWindows(publish=true){
  if(busy)throw new Error('正在生成，请稍候。');
  if(!config.window_ready)throw new Error(config.window_status||'当前项目未提供已验证窗口供体。');
  if(Editor.isDirty())throw new Error('请先应用当前属性修改，再复制窗口。');
  if(!selected.size)throw new Error('请至少勾选一个窗口。');
  const chosen=config.catalog.pages.filter(p=>selected.has(p.id));
  const unique=new Set();
  for(const p of chosen){const name=names[p.id];if(!nameOK(name))throw new Error('窗口名须为1～30字，不能含路径符号。');if(unique.has(name.toLowerCase()))throw new Error('所选窗口名称不能重复。');unique.add(name.toLowerCase());}
  Editor.setBusy(true);
  try{
   const status=await fetch('/api/status').then(r=>r.json()),pages=[];
   for(const [index,page] of chosen.entries()){
    show(`正在生成 ${index+1}/${chosen.length}：${names[page.id]}…`);
    const patches=patchesFor(page);
    const response=await fetch('/api/model',{method:'POST',headers:{'Content-Type':'application/json','X-Local-Token':config.token},body:JSON.stringify({page_id:page.id,revision:page.model.revision,patches})});
    const result=await response.json();if(!response.ok||!result.ok)throw new Error(result.error||'页面校验失败');
    const assets={};
    for(const n of result.model.components){const [l,t,r,b]=n.rect;
     if(n.kind==='picture')assets[n.id+':s0']=await raster(n.svg,r-l,b-t);
     if(n.background)assets[n.id+':s0']=await raster(n.background.svg,r-l,b-t);
     if(n.states)for(const state of ['s0','s1'])assets[n.id+':'+state]=await raster(n.states[state],r-l,b-t);
    }
    pages.push({id:page.id,name:names[page.id],revision:page.model.revision,patches,assets});
   }
   const response=await fetch(publish?'/api/windows/copy':'/api/windows/check',{method:'POST',headers:{'Content-Type':'application/json','X-Local-Token':config.token},body:JSON.stringify({revision:config.catalog.revision,sequence:status.sequence,binding_mode:$('#native-binding-mode').value,pages})});
   const result=await response.json();if(!response.ok||!result.ok)throw new Error(result.error||'窗口生成失败');
   show(publish?`已复制 ${result.report.window_count} 个完整窗口、${result.report.count} 个控件，剪贴板回读一致。请到 MCGS 工程工作台的“用户窗口”列表按 Ctrl+V；粘贴会新增窗口。`:`${result.report.window_count} 个窗口、${result.report.count} 个控件结构检查通过，未写入剪贴板。`,'success');
   window.lastWindowResult=result;return result;
  }catch(e){show(e.message,'error');throw e;}finally{Editor.setBusy(false);}
 }
 $('#window-name').addEventListener('input',()=>{
  names[config.pageId]=$('#window-name').value;
  const button=document.querySelector(`#window-pages button[data-page-id="${config.pageId}"]`),check=document.querySelector(`#window-pages input[data-page-id="${config.pageId}"]`);
  if(button)button.textContent=names[config.pageId];if(check)check.setAttribute('aria-label','导出 '+names[config.pageId]);save();
 });
 $('#window-name').addEventListener('change',()=>{if(!nameOK(names[config.pageId]))show('窗口名须为1～30字，不能含路径符号。','error');});
 $('#select-all-windows').onclick=()=>{selected=new Set(config.catalog.pages.map(p=>p.id));save();render();};
 $('#select-no-windows').onclick=()=>{selected.clear();save();render();};
 $('#copy-windows').onclick=()=>prepareWindows(true).catch(e=>show(e.message,'error'));
 $('#check-windows').onclick=()=>prepareWindows(false).catch(e=>show(e.message,'error'));
 window.WindowPages={prepare:prepareWindows,refresh:render,setBusy:value=>{busy=value;if(config?.catalog)render();},
  getState:()=>({active:config.pageId,names:clone(names),selected:[...selected]}),
  ready:()=>{
   let saved;try{saved=JSON.parse(localStorage.getItem(storageKey())||'null');}catch{}
   for(const p of config.catalog.pages)names[p.id]=typeof saved?.names?.[p.id]==='string'?saved.names[p.id]:p.name;
   const initial=Array.isArray(config.initial_window_selection)?config.initial_window_selection.filter(id=>config.catalog.pages.some(p=>p.id===id)):config.catalog.pages.map(p=>p.id);
   selected=new Set(saved?.selected?.filter(id=>config.catalog.pages.some(p=>p.id===id))||initial);
   render();
  }};
})();
