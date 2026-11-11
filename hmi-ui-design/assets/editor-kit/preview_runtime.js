// Shared local-preview behavior. These effects do not create PLC or MCGS scripts.
(()=>{
 const active=new Set();
 function seed(model,values,reset=false){
  for(const v of model.variables||[]){
   if(reset||!Object.hasOwn(values,v.name))values[v.name]=model.preview_initial?.[v.name]??(v.kind===1?false:0);
  }
 }
 function number(raw,min,max,digits){
  const text=String(raw).trim();
  // Accept a complete decimal or correctly grouped decimal, never parseFloat's partial input.
  const plain=/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/;
  const grouped=/^[+-]?\d{1,3}(?:,\d{3})+(?:\.\d*)?$/;
  if(!text||!(plain.test(text)||grouped.test(text)))throw new Error('请输入完整有效的数值。');
  const value=Number(text.replaceAll(',',''));
  if(!Number.isFinite(value)||value<min||value>max)throw new Error(`参数范围为 ${min} ～ ${max}。`);
  const rounded=Number(value.toFixed(digits));
  if(Math.abs(rounded-value)>10**(-digits)*1e-7)throw new Error(`本项最多允许 ${digits} 位小数。`);
  return rounded;
 }
 function allows(node,values){return Object.entries(node.preview?.requires||{}).every(([key,want])=>values[key]===want);}
 function effects(node,phase,values){
  const changes=Object.create(null);
  for(const [key,value] of Object.entries(node.preview?.[phase]||{}))changes[key]=value&&typeof value==='object'?values[value.from]:value;
  Object.assign(values,changes);
 }
 function releaseAll(){for(const release of [...active])release();}
 function momentary(el,{enabled,set}){
  let held=false;const pointers=new Set(),keys=new Set();
  const sync=()=>{const next=!!(pointers.size||keys.size);if(next!==held){held=next;set(next);}};
  const release=()=>{pointers.clear();keys.clear();sync();active.delete(release);};
  const begin=()=>{if(!enabled())return false;active.add(release);return true;};
  el.addEventListener('pointerdown',e=>{if(e.button!==0||!begin())return;e.preventDefault();el.focus();pointers.add(e.pointerId);el.setPointerCapture(e.pointerId);sync();});
  for(const event of ['pointerup','pointercancel','lostpointercapture'])el.addEventListener(event,e=>{pointers.delete(e.pointerId);sync();if(!held)active.delete(release);});
  el.addEventListener('keydown',e=>{if(![' ','Enter'].includes(e.key))return;e.preventDefault();if(!begin())return;keys.add(e.key);sync();});
  el.addEventListener('keyup',e=>{if(![' ','Enter'].includes(e.key))return;e.preventDefault();keys.delete(e.key);sync();if(!held)active.delete(release);});
  el.addEventListener('blur',release);
  // A click after pointerup/keyup must never reassert a momentary request.
  el.addEventListener('click',e=>e.preventDefault());
  return release;
 }
 let sequence=0;
 function rasterSource(source,width,height){
  const doc=new DOMParser().parseFromString(source,'image/svg+xml');
  if(doc.querySelector('parsererror'))throw new Error('SVG源解析失败。');
  doc.documentElement.setAttribute('width',String(width));doc.documentElement.setAttribute('height',String(height));
  return new XMLSerializer().serializeToString(doc.documentElement);
 }
 function mountSVG(target,source,scope){
  const doc=new DOMParser().parseFromString(source,'image/svg+xml');
  if(doc.querySelector('parsererror'))throw new Error('SVG源解析失败。');
  const prefix='hmi_'+scope.replace(/[^A-Za-z0-9_-]/g,'_')+'_'+(++sequence)+'_';
  const ids=new Map();
  for(const el of doc.querySelectorAll('[id]')){const old=el.getAttribute('id');ids.set(old,prefix+old);el.setAttribute('id',prefix+old);}
  for(const el of doc.querySelectorAll('*'))for(const attr of [...el.attributes]){
   if(attr.name==='id')continue;
   let value=attr.value.replace(/url\(\s*(['"]?)#([^\s)'"\t]+)\1\s*\)/g,(_,q,id)=>`url(#${ids.get(id)||id})`);
   if(['href','xlink:href'].includes(attr.name)&&value.startsWith('#'))value='#'+(ids.get(value.slice(1))||value.slice(1));
   if(['aria-labelledby','aria-describedby'].includes(attr.name))value=value.split(/\s+/).map(id=>ids.get(id)||id).join(' ');
   if(value!==attr.value)el.setAttributeNS(attr.namespaceURI,attr.name,value);
  }
  target.replaceChildren(document.importNode(doc.documentElement,true));
 }
 window.PreviewRuntime={seed,number,allows,effects,momentary,releaseAll,mountSVG,rasterSource};
 window.addEventListener('blur',releaseAll);
 document.addEventListener('visibilitychange',()=>{if(document.hidden)releaseAll();});
})();
