let config;const simulation={data:0,bool:false,values:Object.create(null)};
const $=s=>document.querySelector(s);
const typeNames={picture:'图片',label:'文字',numeric_output:'数值显示',numeric_input:'数值输入',bit_switch:'位状态',lamp:'指示灯'};
const typeCodes={picture:'0x5009',label:'0x5008（无动画）',numeric_output:'0x5008 + CAniOutput',numeric_input:'0x5025',bit_switch:'0x5028',lamp:'0x502A'};
function show(message,kind=''){ $('#status').textContent=message;$('#status').className=kind; }
function update(){
  for(const n of config.model.components){
    const el=document.getElementById(n.id);
    if(n.kind==='numeric_output')el.textContent=Number(simulation.values[n.binding.name]??0).toFixed(n.digits);
    if(n.kind==='numeric_input'&&el!==document.activeElement)el.value=Number(simulation.values[n.binding.name]??0).toFixed(n.digits);
    if(n.kind==='bit_switch'||n.kind==='lamp'){
      el.querySelectorAll('.skin').forEach(e=>e.hidden=e.dataset.state!==(simulation.values[n.binding.name]?'s1':'s0'));
      if(n.kind==='bit_switch'){el.querySelector('.caption').textContent=n.captions[simulation.values[n.binding.name]?'s1':'s0'];el.querySelector('.caption').style.color=n.state_colors[simulation.values[n.binding.name]?'s1':'s0'];el.setAttribute('aria-pressed',String(!!simulation.values[n.binding.name]));}
    }
    window.ExtraControls?.update(n,el,Number(n.binding?simulation.values[n.binding.name]??0:0));
  }
  $('#sim-state').textContent='本地模拟：'+Object.entries(simulation.values).map(([name,value])=>name+' = '+(typeof value==='boolean'?(value?1:0):value)).join('，');
}
function draw(model){
 document.getElementById('preview').style.width=model.width+'px';
 document.getElementById('preview').style.height=model.height+'px';
 document.getElementById('preview').setAttribute('aria-label',model.width+'乘'+model.height+'原生控件测试画布');
 document.getElementById('canvas-size').textContent=model.width+' × '+model.height;
 document.getElementById('canvas-status').textContent=model.canvas_profile?.note||'请按当前实际画布核对';
 PreviewRuntime.releaseAll();PreviewRuntime.seed(model,simulation.values);
 document.getElementById('preview-behavior-note').hidden=!model.components.some(n=>n.preview&&Object.keys(n.preview).length);
 $('#preview').replaceChildren();$('#layers').replaceChildren();
 for(const n of model.components){
  const el=document.createElement(n.kind==='numeric_input'?'input':['bit_switch','navigation'].includes(n.kind)?'button':'div');
  const [l,t,r,b]=n.rect;el.id=n.id;el.dataset.kind=n.kind;el.className='node';
  Object.assign(el.style,{left:l+'px',top:t+'px',width:r-l+'px',height:b-t+'px',zIndex:n.z});
  el.style.setProperty('--node-z',n.z);
  if(n.font)Object.assign(el.style,{fontFamily:n.font.family,fontSize:n.font.size_px+'px',fontWeight:n.font.weight,color:n.font.color});
  if(n.kind==='picture')PreviewRuntime.mountSVG(el,n.svg,n.id+'_picture');
  if(n.kind==='label'||n.kind==='numeric_output'){el.classList.add('native-label');if(n.kind==='label')el.textContent=n.text;}
  if(n.background){el.style.backgroundImage=`url("data:image/svg+xml,${encodeURIComponent(n.background.svg)}")`;el.style.backgroundSize='100% 100%';el.style.backgroundRepeat='no-repeat';}
  if(n.kind==='numeric_input'){
    el.classList.add('native-input');el.type='text';el.inputMode='decimal';el.setAttribute('aria-label',`${n.id} ${n.min} 到 ${n.max} ${n.digits}位小数`);
    if(n.background){el.style.backgroundImage=`url("data:image/svg+xml,${encodeURIComponent(n.background.svg)}")`;el.style.backgroundSize='100% 100%';el.style.backgroundRepeat='no-repeat';}
    const commit=()=>{
      let rounded;
      try{rounded=PreviewRuntime.number(el.value,n.min,n.max,n.digits);if(!PreviewRuntime.allows(n,simulation.values))throw new Error('演示条件未满足，未写入。');}
      catch(error){show(error.message,'error');el.value=Number(simulation.values[n.binding.name]??0).toFixed(n.digits);return false;}
      simulation.data=rounded;simulation.values[n.binding.name]=rounded;PreviewRuntime.effects(n,'on_commit',simulation.values);el.value=rounded.toFixed(n.digits);update();show(`本地 ${n.binding.name} 已设为 ${rounded}，同变量控件已同步。`);return true;
    };
    el.addEventListener('change',commit);el.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();el.blur();}if(e.key==='Escape'){el.value=Number(simulation.values[n.binding.name]??0).toFixed(n.digits);el.blur();}});
  }
  if(n.kind==='bit_switch'||n.kind==='lamp'){
    el.classList.add('state-control');
    for(const state of ['s0','s1']){const skin=document.createElement('div');skin.className='skin';skin.dataset.state=state;PreviewRuntime.mountSVG(skin,n.states[state],n.id+'_'+state);el.append(skin);}
    if(n.kind==='bit_switch'){
      const caption=document.createElement('span');caption.className='caption';el.append(caption);
      const action=n.action==='preserve'?(n.donor_action||'toggle'):(n.action||'toggle');
      const enabled=()=>{if($('#edit-mode').checked)return false;if(!PreviewRuntime.allows(n,simulation.values)){show('演示条件未满足，未发出请求。','error');return false;}return true;};
      const set=(value,phase)=>{simulation.values[n.binding.name]=value;PreviewRuntime.effects(n,phase,simulation.values);update();};
      if(action==='toggle')el.onclick=()=>{if(enabled())set(!simulation.values[n.binding.name],'on_toggle');};
      if(action==='momentary')PreviewRuntime.momentary(el,{enabled,set:value=>set(value,value?'on_press':'on_release')});
    }
  }
  window.ExtraControls?.render(n,el);$('#preview').append(el);
  const row=document.createElement('div');row.className='layer';row.dataset.kind=n.kind;
  const type=document.createElement('b');type.textContent=typeNames[n.kind];row.append(type,document.createTextNode(n.id));
  row.onclick=()=>{if(window.Editor)window.Editor.select(n.id);else el.classList.add('selected');show(`${n.id} · ${typeNames[n.kind]} ${typeCodes[n.kind]} · ${n.rect.join(', ')}${n.binding?' · 绑定 '+n.binding.name:''}${n.kind==='numeric_input'?` · 范围 ${n.min}～${n.max}，${n.digits} 位小数`:''}`);};
  $('#layers').append(row);
 }
 const count=kind=>model.components.filter(n=>n.kind===kind).length;
 $('#counts').textContent=`${model.components.length} 个对象 · `+Object.keys(typeNames).filter(k=>count(k)).map(k=>typeNames[k]+' '+count(k)).join(' / ');
 update();
 window.Editor?.afterDraw();
}
async function raster(svg,w,h){
 const cacheKey=await AssetCache.key(svg,w,h),cached=await AssetCache.get(cacheKey);if(cached)return cached;
 const img=new Image(),url=URL.createObjectURL(new Blob([PreviewRuntime.rasterSource(svg,w,h)],{type:'image/svg+xml'}));
 try{await new Promise((resolve,reject)=>{img.onload=resolve;img.onerror=()=>reject(new Error('图层渲染失败'));img.src=url;});const c=document.createElement('canvas');c.width=w;c.height=h;c.getContext('2d').drawImage(img,0,0,w,h);const png=c.toDataURL('image/png').split(',')[1];await AssetCache.put(cacheKey,png);return png;}finally{URL.revokeObjectURL(url);}
}
async function prepare(publish=true,selectedOnly=false){
 if(!config.native_ready){show(config.native_status||'原生复制尚未就绪','error');throw new Error(config.native_status||'原生复制尚未就绪');}
 if(window.Editor?.isDirty()){show('请先应用当前属性修改，再复制。','error');throw new Error('请先应用当前属性修改，再复制。');}
 const selection=selectedOnly?[window.Editor?.selectedId()]:undefined;
 if(selectedOnly&&!selection[0])throw new Error('请先选择一个控件。');
 const model=structuredClone(config.model),patches=window.Editor?.getPatches()||[];
 const nodes=selectedOnly?model.components.filter(n=>n.id===selection[0]):model.components;
 $('#copy').disabled=true;
 if(window.Editor)window.Editor.setBusy(true);
 try{
  const status=await fetch('/api/status').then(r=>r.json());const assets={};show(publish?'正在生成原生数值、位控件和独立图片…':'正在检查各类原生对象和状态子项…');
  for(const n of nodes){const [l,t,r,b]=n.rect;
   if(n.kind==='picture')assets[n.id+':s0']=await raster(n.svg,r-l,b-t);
   if(n.background)assets[n.id+':s0']=await raster(n.background.svg,r-l,b-t);
   if(n.states)for(const s of ['s0','s1'])assets[n.id+':'+s]=await raster(n.states[s],r-l,b-t);
  }
  const response=await fetch(publish?'/api/copy':'/api/check',{method:'POST',headers:{'Content-Type':'application/json','X-Local-Token':config.token},body:JSON.stringify({revision:config.model.revision,page_id:config.pageId,sequence:status.sequence,binding_mode:$('#native-binding-mode').value,assets,patches,selection})});
  const result=await response.json();if(!response.ok||!result.ok)throw new Error(result.error||'生成失败');
  show(publish?`已复制 ${result.report.count} 个原生对象，剪贴板回读一致。${selectedOnly?'在 MCGS 粘贴会新增控件，请替换旧控件并核对位置。':'请到原测试工程的新空白窗口按 Ctrl+V。'}`:`${result.report.count} 个对象结构检查通过，当前修改已用于原生生成。未写入剪贴板。`,'success');window.lastResult=result;return result;
 }catch(e){show(e.message,'error');throw e;}finally{$('#copy').disabled=false;window.Editor?.setBusy(false);}
}
$('#copy').onclick=()=>prepare(true).catch(()=>{});
$('#reset').onclick=()=>{PreviewRuntime.releaseAll();PreviewRuntime.seed(config.model,simulation.values,true);simulation.data=0;simulation.bool=false;update();show('网页模拟已恢复初值。');};
$('#outlines').onchange=e=>$('#preview').classList.toggle('outlines',e.target.checked);
$('#filter').onchange=e=>document.querySelectorAll('.layer').forEach(row=>row.hidden=e.target.value!=='all'&&row.dataset.kind!==e.target.value);
window.Demo={prepare,getState:()=>({...simulation}),getModel:()=>structuredClone(config.model)};
window.addEventListener('DOMContentLoaded',()=>fetch('/api/config').then(r=>{if(!r.ok)throw new Error('本地助手连接失败');return r.json();}).then(async data=>{config=data;$('#native-binding-mode').value=data.binding_mode||'unbound';document.querySelector('#template-library-link').hidden=!data.templates_ready;PreviewRuntime.seed(data.model,simulation.values);config.baseline=structuredClone(data.model);document.title=data.model.title||'HMI 局部编辑';draw(data.model);await window.Editor?.ready();window.WindowPages?.ready();$('#copy').disabled=!config.native_ready;show('已连接。打开“局部编辑”点选控件。'+(config.native_ready?'可复制单个或整页。':config.native_status));}).catch(e=>show(e.message,'error')));
