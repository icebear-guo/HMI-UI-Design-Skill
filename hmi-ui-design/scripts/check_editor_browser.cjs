// Actual-browser checks of an existing project editor. Never publishes clipboard data.
const fs=require('fs'),path=require('path');
const args=process.argv.slice(2),option=name=>{const i=args.indexOf(name);return i<0?undefined:args[i+1];};
const out=option('--out'),url=option('--url'),nativeCheck=args.includes('--native-check');
const checks=[],errors=[];let browser;
function check(name,pass,detail){checks.push({name,pass:!!pass,detail});}
function finish(status,error){
 const report={status,checks,errors,...(error?{error}:{}),clipboard_published:false,native_application:'not_run',
  scope:'current project editor: actual text fit, page values, momentary release, optional native structure checks; not arbitrary business logic or field usability'};
 fs.writeFileSync(out,JSON.stringify(report,null,2));
 process.stdout.write(JSON.stringify({status,checks:checks.length,failed:checks.filter(c=>!c.pass).length})+'\n');
 process.exitCode=status==='pass'?0:status==='blocked'?3:1;
}
(async()=>{
 if(!out||!url||!/^http:\/\/127\.0\.0\.1:\d+\/$/.test(url))throw new Error('Use --url http://127.0.0.1:PORT/ --out NEW_REPORT.json [--native-check]');
 if(fs.existsSync(out))throw new Error('Report already exists; use a new batch');
 let playwright;
 try{playwright=require(option('--playwright-module')||'playwright');}
 catch{finish('blocked','Playwright is unavailable. Use an existing installation via NODE_PATH or --playwright-module; no package was installed.');return;}
 try{
  browser=await playwright.chromium.launch({headless:true,...(option('--channel')?{channel:option('--channel')}:{})});
  const context=await browser.newContext({viewport:{width:1500,height:1000}});
  await context.route('**/api/**',route=>route.request().url().endsWith('/copy')?route.abort():route.continue());
  const page=await context.newPage();page.on('pageerror',e=>errors.push(String(e)));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
  await page.goto(url);await page.waitForSelector('.window-page button');
  const pages=await page.evaluate(()=>config.catalog.pages.map(p=>({id:p.id,name:p.name})));
  for(const item of pages){
   await page.locator(`.window-page button[data-page-id="${item.id}"]`).click();
   await page.waitForFunction(id=>config.pageId===id,item.id);await page.evaluate(()=>document.fonts.ready);
   const types=await page.evaluate(()=>({bits:config.model.components.filter(n=>n.kind==='bit_switch'&&(n.action==='momentary'||n.donor_action==='momentary')).map(n=>({id:n.id,variable:n.binding.name})),
    invalidInitial:config.model.variables.filter(v=>!Object.hasOwn(simulation.values,v.name)).map(v=>v.name),
    ids:[...document.querySelectorAll('#preview [id]')].map(e=>e.id)}));
   check(item.id+':declared_variables_initialized',!types.invalidInitial.length,types.invalidInitial);
   check(item.id+':unique_svg_and_control_ids',new Set(types.ids).size===types.ids.length);
   const fits=await page.evaluate(()=>{
    const canvas=document.createElement('canvas'),ctx=canvas.getContext('2d'),problems=[];
    for(const n of config.model.components){
     if(!['label','numeric_output','numeric_input','bit_switch','navigation'].includes(n.kind))continue;
     const el=document.getElementById(n.id),cs=getComputedStyle(el);ctx.font=`${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
     let texts=n.kind==='label'?[n.text]:n.kind==='navigation'?[n.text]:n.kind==='bit_switch'?Object.values(n.captions):[el.value??el.textContent];
     if(['numeric_output','numeric_input'].includes(n.kind))for(const value of [n.min,n.max])if(Number.isFinite(value))texts.push(value.toFixed(n.digits));
     for(const text of texts){const metric=ctx.measureText(text),height=metric.actualBoundingBoxAscent+metric.actualBoundingBoxDescent;
      if(metric.width>el.clientWidth+1||height>el.clientHeight+1)problems.push({id:n.id,text,width:metric.width,height,box:[el.clientWidth,el.clientHeight]});}
    }return problems;
   });
   check(item.id+':current_and_declared_numeric_bounds_fit',fits.length===0,fits);
   for(const node of types.bits){
    await page.locator('#reset').click();
    const control=page.locator('#'+node.id),box=await control.boundingBox();
    await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();await page.mouse.up();
    check(item.id+':'+node.id+':mouse_release',await page.evaluate(name=>simulation.values[name]===false,node.variable));
    await control.focus();await page.keyboard.down('Space');await page.keyboard.up('Space');
    check(item.id+':'+node.id+':keyboard_release',await page.evaluate(name=>simulation.values[name]===false,node.variable));
    await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();await page.mouse.move(box.x+box.width+20,box.y-20);await page.mouse.up();
    check(item.id+':'+node.id+':outside_release',await page.evaluate(name=>simulation.values[name]===false,node.variable));
   }
   if(nativeCheck){
    const result=await page.evaluate(async()=>{if(!config.native_ready)return {blocked:true};try{return await prepare(false);}catch(error){return {error:error.message};}});
    check(item.id+':native_structure_only',!!result.ok&&result.check_only===true,{blocked:result.blocked,error:result.error,count:result.report?.count});
   }
  }
  check('browser_errors',errors.length===0,errors);
  finish(checks.every(c=>c.pass)?'pass':'fail');
 }catch(error){finish(browser?'fail':'blocked',String(error));}
 finally{if(browser)await browser.close();}
})().catch(error=>{console.error(String(error));process.exitCode=1;});
