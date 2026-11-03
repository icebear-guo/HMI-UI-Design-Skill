/** Technical paint coverage, not an aesthetic judgement. Run inside the page. */
export function collectLayoutIssues(root) {
  const bounds=root.getBoundingClientRect(),issues=[];
  for(const e of root.querySelectorAll('[data-hmi-component]')) {
    const b=e.getBoundingClientRect(),s=getComputedStyle(e),id=e.dataset.hmiComponent;
    if(!b.width||!b.height||s.display==='none'||s.visibility==='hidden'||Number(s.opacity)===0)continue;
    if(b.left<bounds.left-.5||b.top<bounds.top-.5||b.right>bounds.right+.5||b.bottom>bounds.bottom+.5)
      issues.push({id,code:'outside_page',rect_px:[b.x-bounds.x,b.y-bounds.y,b.width,b.height]});
    if((e.dataset.hmiKind==='label'||e.dataset.hmiKind?.startsWith('numeric'))
      &&(e.scrollWidth>e.clientWidth+1||e.scrollHeight>e.clientHeight+1))
      issues.push({id,code:'text_overflow_hint',scroll_px:[e.scrollWidth,e.scrollHeight],box_px:[e.clientWidth,e.clientHeight]});
    if(['button','numeric_input','state_switch'].includes(e.dataset.hmiKind)) {
      const x=b.x+b.width/2,y=b.y+b.height/2,top=document.elementFromPoint(x,y);
      if(x>=0&&x<innerWidth&&y>=0&&y<innerHeight&&top&&top!==e&&!e.contains(top))
        issues.push({id,code:'center_hit_obscured_hint',cover_id:top.closest('[data-hmi-component]')?.dataset.hmiComponent||top.id||top.localName});
    }
  }
  return {scope:'mechanical_bounds_and_layout_hints; no_aesthetic_judgement',issues};
}

export function collectVisualCoverage(root) {
  const visible = e => {
    let n=e;
    while(n) {const s=getComputedStyle(n);if(s.display==='none'||s.visibility==='hidden'||Number(s.opacity)===0)return false;n=n.parentElement;}
    const b=e.getBoundingClientRect();return b.width>0&&b.height>0;
  };
  const alpha = value => value && value!=='transparent' && !/rgba\([^)]*,\s*0(?:\.0+)?\s*\)/.test(value);
  const paint = e => {
    const s=getComputedStyle(e), reasons=[];
    if (alpha(s.backgroundColor)||s.backgroundImage!=='none') reasons.push('background');
    if (['Top','Right','Bottom','Left'].some(x=>parseFloat(s['border'+x+'Width'])>0&&s['border'+x+'Style']!=='none'&&alpha(s['border'+x+'Color']))) reasons.push('border');
    if(s.boxShadow!=='none') reasons.push('shadow');
    if(['svg','img','canvas','video'].includes(e.localName)) reasons.push('graphic');
    if([...e.childNodes].some(n=>n.nodeType===3&&n.textContent.trim())) reasons.push('text');
    for (const pseudo of ['::before','::after']) {const p=getComputedStyle(e,pseudo);if(p.content!=='none'&&p.content!=='normal'&&p.content!=='""') reasons.push(pseudo);}
    return reasons;
  };
  const uncovered=[];
  if(root.matches('[data-hmi-component]')) uncovered.push({tag:root.localName,id:root.id||null,reasons:['page_root_cannot_own_foreground_components']});
  for (const e of [root,...root.querySelectorAll('*')]) {
    if (!visible(e)||['style','script','defs','marker','title','desc'].includes(e.localName)) continue;
    // A registered mechanical/image/button component owns its internal drawing.
    const owner=e.closest('[data-hmi-component]');
    if(owner&&owner!==root&&owner.dataset.hmiKind!=='group') continue;
    // Report an unregistered SVG as one drawing, not hundreds of paths.
    if(e.localName!=='svg'&&e.closest('svg')) continue;
    const reasons=paint(e);if(!reasons.length)continue;
    const b=e.getBoundingClientRect(),r=root.getBoundingClientRect();
    uncovered.push({tag:e.localName,id:e.id||null,class:e.getAttribute('class'),reasons,
      rect_px:[b.x-r.x,b.y-r.y,b.width,b.height],text:e.textContent.trim().slice(0,60)});
  }
  return {scope:'visible_paint_outside_registered_components',uncovered};
}

export function collectNativeHints(root) {
  return [...root.querySelectorAll('[data-hmi-component]')].filter(e=>e.getBoundingClientRect().width>0&&e.getBoundingClientRect().height>0).map(e=>{
    const s=getComputedStyle(e),kind=e.dataset.hmiKind;
    const numeric=kind==='numeric_input'||kind==='numeric_display';
    const horizontal=s.justifyContent==='center'||s.justifyItems==='center'||s.textAlign==='center'?'center':'other';
    const vertical=s.alignItems==='center'||Math.abs(parseFloat(s.lineHeight)-e.getBoundingClientRect().height)<0.1?'center':'other';
    const u=e.querySelector('.unit'),unit=e.dataset.hmiUnit||u?.textContent.trim()||'';
    const unit_owner=e.dataset.hmiUnitOwner||(u&&u.closest('[data-hmi-component]')!==e?'external':'internal');
    const alpha=value=>value!=='transparent'&&!/rgba\([^)]*,\s*0(?:\.0+)?\s*\)/.test(value);
    const border=['Top','Right','Bottom','Left'].some(x=>parseFloat(s['border'+x+'Width'])>0&&s['border'+x+'Style']!=='none'&&alpha(s['border'+x+'Color']));
    return {id:e.dataset.hmiComponent,kind,numeric_layout:numeric?{horizontal,vertical,padding_px:[s.paddingLeft,s.paddingTop,s.paddingRight,s.paddingBottom].map(parseFloat)}:null,
      appearance:numeric?{fill_enabled:alpha(s.backgroundColor),border_enabled:border,image_enabled:s.backgroundImage!=='none'}:null,unit,unit_owner,
      action:kind==='button'?(e.dataset.hmiTarget?'navigate':e.dataset.hmiAction||null):null};
  });
}
