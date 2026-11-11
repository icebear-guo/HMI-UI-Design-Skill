// Property editing uses validated patches, never replacement HTML or binary.
(()=>{
 const numeric=kind=>['numeric_input','numeric_output'].includes(kind);
 let selected=null,patches=[],history=[[]],historyIndex=0,dirty=false,busy=false,readyPromise=null;
 const pageHistory={};
 const clone=value=>structuredClone(value),find=()=>config.model.components.find(n=>n.id===selected);
 const key=()=>`mcgs-ui-editor:${config.baseline.revision}`;
 function buttons(){
  $('#undo').disabled=busy||historyIndex===0;$('#redo').disabled=busy||historyIndex===history.length-1;
  $('#copy-selected').disabled=busy||!selected||!config.native_ready;$('#property-fields').disabled=busy;$('#copy').disabled=busy||!config.native_ready;
  for(const id of ['edit-mode','export-draft','import-draft','draft-file','native-binding-mode'])$('#'+id).disabled=busy;
  window.WindowPages?.setBusy(busy);
 }
 function save(){
  try{localStorage.setItem(key(),JSON.stringify({revision:config.baseline.revision,patches}));$('#draft-state').textContent=patches.length?`${patches.length} 个控件已修改 · 草稿已保存`:'尚无修改';}
  catch{$('#draft-state').textContent='浏览器未允许保存草稿，请导出备份。';}
 }
 function groups(){
  const kind=$('#ed-kind').value;
  $('#numeric-properties').hidden=!numeric(kind);$('#input-limits').hidden=!numeric(kind);
  $('#numeric-range-note').textContent=kind==='numeric_input'?'输入上下限同时用于文字宽度和MCGS输入限制。':'显示范围用于预留文字宽度，不生成MCGS限幅逻辑。';
  $('#skin-properties').hidden=$('#ed-skin').value!=='solid';$('#label-properties').hidden=!['label','navigation'].includes(kind);$('#bit-properties').hidden=kind!=='bit_switch';
  $('#font-properties').hidden=!find()?.font;$('#font-color-property').hidden=kind==='bit_switch';
  $('#text-fit-properties').hidden=!['label','numeric_input','numeric_output'].includes(kind);
 }
 function populate(){
  const n=find();$('#property-editor').hidden=!n;if(!n)return;
  $('#selected-name').textContent=n.id;$('#selected-code').textContent=typeCodes[n.kind];
  $('#ed-kind').replaceChildren();for(const kind of numeric(n.kind)?['numeric_output','numeric_input']:[n.kind]){const option=document.createElement('option');option.value=kind;option.textContent=typeNames[kind];$('#ed-kind').append(option);}
  $('#ed-kind').value=n.kind;
  $('#ed-text-fit').value=n.text_layout?.profile||config.model.text_layout?.profile||'mcgs351-c';
  const [l,t,r,b]=n.rect;for(const [field,value] of Object.entries({x:l,y:t,width:r-l,height:b-t,digits:n.digits??0,min:n.min??0,max:n.max??100,text:n.text??'',s0:n.captions?.s0??'',s1:n.captions?.s1??'',size:n.font?.size_px??16,weight:n.font?.weight??400,color:n.font?.color??'#24334a','s0-color':n.state_colors?.s0??'#60748b','s1-color':n.state_colors?.s1??'#ffffff'}))$('#ed-'+field).value=value;
  $('#ed-binding').replaceChildren();for(const v of config.baseline.variables.filter(v=>v.kind===2)){const o=document.createElement('option');o.value=v.name;o.textContent=v.name+'（数值型）';$('#ed-binding').append(o);}$('#ed-binding').value=n.binding?.name||'';
  const patch=patches.find(p=>p.id===selected);$('#ed-skin').value=patch?.skin_mode||'keep';$('#ed-skin-color').value=patch?.skin_color||'#f0f5fc';$('#ed-radius').value=patch?.skin_radius??6;
  window.ExtraControls?.populate(n);$('#editor-error').textContent='';dirty=false;groups();buttons();
 }
 function select(id){
  if(dirty){show('请先应用当前修改，或点击“还原此控件”后再切换。','error');return;}
  selected=id;document.querySelectorAll('.node.selected').forEach(e=>e.classList.remove('selected'));document.getElementById(id)?.classList.add('selected');populate();buttons();
 }
 async function validated(next){
  const response=await fetch('/api/model',{method:'POST',headers:{'Content-Type':'application/json','X-Local-Token':config.token},body:JSON.stringify({revision:config.baseline.revision,page_id:config.pageId,patches:next})});
  const result=await response.json();if(!response.ok||!result.ok)throw new Error(result.error||'属性校验失败');return result.model;
 }
 async function commit(next,recordHistory=true){
  busy=true;buttons();
  try{
   const model=await validated(next);patches=clone(next);config.model=model;dirty=false;
   if(recordHistory){history=history.slice(0,historyIndex+1);history.push(clone(patches));historyIndex=history.length-1;}
   draw(model);save();show(model.text_layout_report?.changed?.length?'修改已应用，并按文字需要扩展尺寸；控件中心保持，复制使用相同尺寸。':'修改已应用到预览和下一次原生复制。','success');
  }finally{busy=false;buttons();}
 }
 function snapshot(){
  const number=id=>{const raw=$('#ed-'+id).value.trim();if(!raw)throw new Error('数值属性不能为空。');return Number(raw);};
  const n=find(),kind=$('#ed-kind').value;const x=number('x'),y=number('y'),w=number('width'),h=number('height');
  const patch={id:n.id,kind,rect:[x,y,x+w,y+h]};
  if(n.font)patch.font={family:n.font.family,size_px:number('size'),weight:number('weight'),color:$('#ed-color').value};
  if(['label','numeric_input','numeric_output'].includes(kind))patch.text_layout={profile:$('#ed-text-fit').value};
  if(numeric(kind))Object.assign(patch,{digits:number('digits'),min:number('min'),max:number('max'),binding_name:$('#ed-binding').value,skin_mode:$('#ed-skin').value,skin_color:$('#ed-skin-color').value,skin_radius:number('radius')});
  if(['label','navigation'].includes(kind))patch.text=$('#ed-text').value;
  if(kind==='bit_switch'){patch.captions={s0:$('#ed-s0').value,s1:$('#ed-s1').value};patch.state_colors={s0:$('#ed-s0-color').value,s1:$('#ed-s1-color').value};}
  Object.assign(patch,window.ExtraControls?.snapshot(n)||{});return patch;
 }
 $('#property-editor').addEventListener('input',()=>{dirty=true;$('#editor-error').textContent='有未应用的修改';$('#draft-state').textContent='当前属性尚未应用';});
 $('#property-editor').addEventListener('change',()=>{dirty=true;groups();});
 $('#property-editor').onsubmit=async event=>{
  event.preventDefault();
  try{const patch=snapshot(),next=patches.filter(p=>p.id!==selected);next.push(patch);await commit(next);}catch(error){$('#editor-error').textContent=error.message;show(error.message,'error');}
 };
 $('#restore-component').onclick=async()=>{try{dirty=false;await commit(patches.filter(p=>p.id!==selected));}catch(e){show(e.message,'error');}};
 $('#undo').onclick=async()=>{if(dirty){show('请先应用当前属性，再撤销。','error');return;}const target=historyIndex-1;try{await commit(history[target],false);historyIndex=target;buttons();}catch(e){show(e.message,'error');}};
 $('#redo').onclick=async()=>{if(dirty){show('请先应用当前属性，再重做。','error');return;}const target=historyIndex+1;try{await commit(history[target],false);historyIndex=target;buttons();}catch(e){show(e.message,'error');}};
 $('#copy-selected').onclick=()=>prepare(true,true).catch(e=>show(e.message,'error'));
 $('#export-draft').onclick=()=>{
  if(dirty){show('请先应用属性，再导出草稿。','error');return;}
  const blob=new Blob([JSON.stringify({revision:config.baseline.revision,patches},null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='MCGS-局部修改草稿.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 };
 $('#import-draft').onclick=()=>{if(dirty){show('请先应用当前修改，再导入草稿。','error');return;}$('#draft-file').click();};
 $('#draft-file').onchange=async()=>{
  const file=$('#draft-file').files[0];if(!file)return;
  try{if(file.size>512000)throw new Error('草稿文件超过500KB。');const draft=JSON.parse(await file.text());if(draft.revision!==config.baseline.revision||!Array.isArray(draft.patches))throw new Error('草稿版本不匹配。');await commit(draft.patches);}
  catch(error){show('草稿未导入：'+error.message,'error');}finally{$('#draft-file').value='';}
 };
 $('#edit-mode').onchange=()=>{
  PreviewRuntime.releaseAll();
  document.body.classList.toggle('editing',$('#edit-mode').checked);document.querySelectorAll('.native-input').forEach(e=>e.readOnly=$('#edit-mode').checked);
  show($('#edit-mode').checked?'局部编辑：点选控件后在右侧修改属性。':'演示操作：可以输入数值或点击开关联动。');
 };
 $('#preview').addEventListener('click',event=>{if(!$('#edit-mode').checked)return;const node=event.target.closest('#preview>.node');if(node){event.preventDefault();event.stopImmediatePropagation();select(node.id);}},true);
 window.Editor={select,selectedId:()=>selected,getPatches:()=>clone(patches),getCachedPatches:id=>pageHistory[id]?clone(pageHistory[id].patches):undefined,isDirty:()=>dirty,setBusy:value=>{busy=value;buttons();},
  switchPage:async page=>{
   if(dirty||busy)throw new Error(dirty?'请先应用当前属性，再切换页面。':'正在生成，请稍候。');
   PreviewRuntime.releaseAll();
   pageHistory[config.pageId]={patches:clone(patches),history:clone(history),historyIndex,selected};
   config.pageId=page.id;config.baseline=clone(page.model);config.model=clone(page.model);
   selected=null;patches=[];history=[[]];historyIndex=0;readyPromise=null;dirty=false;
   const cached=pageHistory[page.id];
   if(cached){selected=cached.selected;await commit(cached.patches,false);history=cached.history;historyIndex=cached.historyIndex;buttons();}
   else{draw(config.model);await window.Editor.ready();}
  },
  afterDraw:()=>{document.body.classList.toggle('editing',$('#edit-mode').checked);document.querySelectorAll('.native-input').forEach(e=>e.readOnly=$('#edit-mode').checked);if(selected){document.getElementById(selected)?.classList.add('selected');populate();}$('#filter').dispatchEvent(new Event('change'));buttons();},
  ready:()=>readyPromise||(readyPromise=(async()=>{
   let saved;try{saved=JSON.parse(localStorage.getItem(key())||'null');}catch{}
   if(saved?.revision===config.baseline.revision&&Array.isArray(saved.patches)&&saved.patches.length){try{await commit(saved.patches);}catch(error){show('保存的草稿未载入：'+error.message,'error');}}
   else save();buttons();
  })())
 };
 if(typeof config!=='undefined'&&config?.baseline)window.Editor.ready().catch(e=>show(e.message,'error'));
})();
