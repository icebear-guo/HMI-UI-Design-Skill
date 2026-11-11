// Common control fields are shared by the preview and validated server patches.
(()=>{
 const labels={navigation:'画面跳转',alarm_strip:'报警条',alarm_browser:'报警浏览',gauge:'仪表',percentage_fill:'百分比填充',realtime_trend:'实时趋势'};
 Object.assign(typeNames,labels);Object.assign(typeCodes,{navigation:'0x5027',alarm_strip:'AlarmScrollBar',alarm_browser:'AlarmTableView',gauge:'0x5032',percentage_fill:'0x5031',realtime_trend:'0x502D'});
 const specs={
  bit_switch:[['action','按钮动作','select',[['preserve','保留预设动作'],['momentary','按1松0'],['toggle','取反']]]],
  navigation:[['target_name','目标窗口','targets']],
  alarm_strip:[['background_color','底色','color']],
  alarm_browser:[['alarm_mode','记录模式','select',[['realtime','实时报警'],['history','历史报警']]]],
  gauge:[['show_background','显示原背景','checkbox'],['needle_color','指针颜色','color'],['needle_width','指针宽度','number'],['needle_margin','指针边距','number']],
  percentage_fill:[['max','上限（下限固定0）','select',[[100,'100'],[200,'200'],[1000,'1000']]],['fill_color','填充色','color'],['text_color','文字色','nullable'],['background_color','未填充底色','nullable'],['hide_text','隐藏文字','checkbox']],
  realtime_trend:[['x_major','X主刻线','number'],['y_major','Y主刻线','number'],['time_minutes','时间长度（分钟）','select',[[10,'10'],[15,'15'],[20,'20']]],['y_max','Y上限（下限固定0）','select',[[100,'100'],[200,'200'],[300,'300']]],['curve_color','曲线1颜色','color']]
 };
 const area=document.createElement('div');area.id='extra-properties';$('#bit-properties').after(area);
 function populate(n){
  area.replaceChildren();area.hidden=!specs[n.kind]&&!n.binding;
  if(n.binding){const label=document.createElement('label');label.textContent='网页变量名（名称绑定模式使用）';const input=document.createElement('input');input.id='ed-design-binding';input.value=n.binding.name;input.maxLength=64;label.append(input);area.append(label);}
  if(['gauge','percentage_fill','realtime_trend'].includes(n.kind)){
   const note=document.createElement('p');note.textContent=`绑定：${n.binding.name}（网页设计/模拟信号）`+(n.kind==='gauge'?' · 量程0～120':'');area.append(note);
  }
  for(const [key,label,type,values] of specs[n.kind]||[]){
   const wrapper=document.createElement('label');wrapper.textContent=label;let input=document.createElement(type==='select'||type==='targets'?'select':'input');input.dataset.extra=key;
   if(type==='select'||type==='targets'){
    const choices=type==='targets'?(config.navigation_targets?.length?config.navigation_targets.map(t=>[t.name,t.name]):[[n.target_name,n.target_name]]):values;
    for(const [value,text] of choices){const option=document.createElement('option');option.value=value;option.textContent=text;input.append(option);}
    input.value=n[key]??'preserve';
   }else if(type==='checkbox'){input.type='checkbox';input.checked=!!n[key];}
   else{input.type=type==='nullable'?'color':type;input.value=n[key]??'#ffffff';if(type==='number')input.step=1;}
   wrapper.append(input);
   if(type==='nullable'){
    const empty=document.createElement('input');empty.type='checkbox';empty.dataset.empty=key;empty.checked=n[key]===null;
    const small=document.createElement('span');small.textContent=' 无色';small.prepend(empty);wrapper.append(small);
   }
   area.append(wrapper);
  }
  if(n.kind==='percentage_fill'){const note=document.createElement('p');note.textContent='宽度大于高度：横向；高度大于宽度：竖向液位。修改宽高即可。';area.append(note);}
 }
 function snapshot(n){const patch={};if(n.binding)patch.binding_name=$('#ed-design-binding').value;for(const [key,label,type] of specs[n.kind]||[]){const input=area.querySelector(`[data-extra="${key}"]`);let value=type==='checkbox'?input.checked:type==='number'||['max','time_minutes','y_max'].includes(key)?Number(input.value):input.value;if(type==='nullable'&&area.querySelector(`[data-empty="${key}"]`).checked)value=null;patch[key]=value;}return patch;}
 const svg=(w,h,body)=>`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}">${body}</svg>`;
 function render(n,el){
  if(!labels[n.kind])return;
  el.classList.add('extra-control',n.kind);el.dataset.extraNative='true';
  if(n.kind==='navigation'){
   for(const state of ['s0','s1']){const skin=document.createElement('div');skin.className='skin';skin.dataset.navState=state;skin.hidden=state==='s1';PreviewRuntime.mountSVG(skin,n.states[state],n.id+'_nav_'+state);el.append(skin);}
   const caption=document.createElement('span');caption.className='caption';caption.textContent=n.text;el.append(caption);
   el.onclick=async()=>{if($('#edit-mode').checked)return;try{const target=config.catalog.pages.find(p=>p.name===n.target_name);if(target){await Editor.switchPage(target);WindowPages.refresh();}else show('跳转目标：'+n.target_name+'。此目标在MCGS工程内，网页未载入该画面。');}catch(error){show(error.message,'error');}};
   el.addEventListener('pointerdown',()=>{if($('#edit-mode').checked)return;el.querySelectorAll('.skin').forEach(s=>s.hidden=s.dataset.navState!=='s1');});
   for(const event of ['pointerup','pointerleave','pointercancel'])el.addEventListener(event,()=>el.querySelectorAll('.skin').forEach(s=>s.hidden=s.dataset.navState!=='s0'));
  }else if(n.kind==='alarm_strip'){el.style.background=n.background_color;el.textContent='报警条 · 运行时显示工程报警消息';}
  else if(n.kind==='alarm_browser'){
   const table=document.createElement('table');const head=document.createElement('tr');for(const text of ['时间',n.alarm_mode==='history'?'历史报警':'实时报警','状态']){const th=document.createElement('th');th.textContent=text;head.append(th);}table.append(head);const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=3;td.textContent='原生数据源保留 · 网页未接入报警记录';tr.append(td);table.append(tr);el.append(table);
  }else if(n.kind==='percentage_fill'){
   el.style.background=n.background_color||'transparent';const fill=document.createElement('div');fill.className='percentage-color';fill.style.background=n.fill_color;el.append(fill);const caption=document.createElement('span');caption.className='percentage-value';caption.style.color=n.text_color||'transparent';caption.hidden=n.hide_text;el.append(caption);
  }
 }
 const trendSamples=new Map();
 function update(n,el,value){
  if(n.kind==='percentage_fill'){
   const fraction=Math.max(0,Math.min(1,(value-n.min)/(n.max-n.min)));const vertical=n.rect[3]-n.rect[1]>n.rect[2]-n.rect[0];const fill=el.querySelector('.percentage-color');Object.assign(fill.style,{width:vertical?'100%':fraction*100+'%',height:vertical?fraction*100+'%':'100%',bottom:0,left:0});el.querySelector('.percentage-value').textContent=Math.round(fraction*100)+'%';
  }else if(n.kind==='gauge'){
   const angle=(-135+270*Math.max(0,Math.min(1,value/120)))*Math.PI/180;let ticks='';for(let i=0;i<=12;i++){const a=(-135+i*22.5)*Math.PI/180;const x=100+Math.sin(a)*78,y=100-Math.cos(a)*78;ticks+=`<text x="${x}" y="${y}" text-anchor="middle" dominant-baseline="central" font-size="9" fill="#526177">${i*10}</text>`;}
   el.innerHTML=svg(200,200,`${n.show_background?'<circle cx="100" cy="100" r="95" fill="#fafafa" stroke="#64748b" stroke-width="3"/>':''}${ticks}<line x1="100" y1="100" x2="${100+Math.sin(angle)*(85-n.needle_margin*.4)}" y2="${100-Math.cos(angle)*(85-n.needle_margin*.4)}" stroke="${n.needle_color}" stroke-width="${n.needle_width}"/><circle cx="100" cy="100" r="6" fill="${n.needle_color}"/>`);
  }else if(n.kind==='realtime_trend'){
   const key=config.pageId+':'+n.id;let samples=trendSamples.get(key)||[];const now=Math.floor(Date.now()/1000);if(samples.at(-1)?.t!==now){samples.push({t:now,v:value});samples=samples.slice(-60);trendSamples.set(key,samples);}
   const w=n.rect[2]-n.rect[0],h=n.rect[3]-n.rect[1];let grid='';for(let i=0;i<=n.x_major;i++){const x=35+(w-45)*i/n.x_major;grid+=`<line x1="${x}" y1="20" x2="${x}" y2="${h-25}"/>`;}for(let i=0;i<=n.y_major;i++){const y=20+(h-45)*i/n.y_major;grid+=`<line x1="35" y1="${y}" x2="${w-10}" y2="${y}"/>`;}
   const points=samples.map((s,i)=>`${35+(w-45)*i/59},${h-25-Math.max(0,Math.min(1,s.v/n.y_max))*(h-45)}`).join(' ');
   el.innerHTML=svg(w,h,`<rect width="${w}" height="${h}" fill="#fff"/><g stroke="#dbe4ef" stroke-width="1">${grid}</g><polyline points="${points}" fill="none" stroke="${n.curve_color}" stroke-width="2"/><text x="8" y="14" font-size="11" fill="#65748b">${n.y_max} · ${n.time_minutes} min · 网页本地采样示意</text>`);
  }
 }
 window.ExtraControls={populate,snapshot,render,update,has:kind=>!!labels[kind]};
 $('#ed-binding').addEventListener('change',()=>{const input=$('#ed-design-binding');if(input)input.value=$('#ed-binding').value;});
 const filter=$('#filter');for(const [kind,name] of Object.entries(labels)){const o=document.createElement('option');o.value=kind;o.textContent=name;filter.append(o);}
 setInterval(()=>{if(config?.model)updateAllExtra();},1000);
 function updateAllExtra(){for(const n of config.model.components)if(['gauge','percentage_fill','realtime_trend'].includes(n.kind)){const el=document.getElementById(n.id);if(el)update(n,el,Number(simulation.values[n.binding.name]??0));}}
})();
