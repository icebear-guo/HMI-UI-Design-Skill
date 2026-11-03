/** Batch component capture with a measured CSS viewport. Node 22+; no npm dependencies. */
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {pathToFileURL,fileURLToPath} from 'node:url';
import {spawn} from 'node:child_process';
import {performance} from 'node:perf_hooks';
import {collectVisualCoverage,collectNativeHints,collectLayoutIssues} from './visual_inventory.mjs';
import {createContext,hash,inside} from './render_cache.mjs';

const [manifestPath, outputPath, ...flags] = process.argv.slice(2);
if (!manifestPath || !outputPath) throw new Error('Usage: node render_components.mjs manifest.json NEW_OUTPUT_DIR');
if(flags.some(x=>x!=='--no-cache'))throw Error('Supported option: --no-cache');
const manifest = JSON.parse(await fs.readFile(manifestPath, 'utf8'));
if (manifest.schema_version !== 'component-render/1.0' || !manifest.browser || !Array.isArray(manifest.components) || !manifest.components.length)
  throw new Error('manifest needs schema_version, browser executable, components');
const output = path.resolve(outputPath), root = path.dirname(path.resolve(manifestPath));
const names=new Set();
for(const {width,height,selector,html,file} of manifest.components) {
  if (!Number.isInteger(width)||!Number.isInteger(height)||width<1||height<1||!selector||!html||!/^[A-Za-z0-9_]+\.png$/.test(file)||names.has(file.toLowerCase())) throw new Error('Invalid or duplicate component capture');
  names.add(file.toLowerCase());
  if(!inside(root,path.resolve(root,html)))throw Error('Component HTML must be within manifest directory');
}
await fs.mkdir(output); // refuse to overwrite an existing output
let profile;
const pause = ms => new Promise(r => setTimeout(r, ms));
const started = performance.now(), reports = [], pending = new Map();
let processHandle, socket, seq = 0, errors = '', failure;
let context,renderer,networkViolation,currentDocument,documentFiles=new Set();
const metrics={page_loads:0,rendered_components:0,reused_components:0,cache_lookup_seconds:0,
  environment_and_source_seconds:0,browser_start_seconds:0,capture_seconds:0};
const checkpoint=report=>fs.appendFile(path.join(output,'checkpoints.jsonl'),JSON.stringify(report)+'\n');
const runtimeProfile=()=>profile?{path:profile,retained:true,policy:'preserve_private_OS_temp_profile; no_recursive_cleanup_during_generation'}:null;
function reportData(status,error) {
  const order=new Map(manifest.components.map((c,i)=>[c.file,i]));
  return {status,error,schema_version:manifest.schema_version,software_rendering:manifest.software_rendering===true,
    renderer:renderer??null,runtime_profile:runtimeProfile(),metrics,
    source_snapshot_sha256:context?.sourceDigest,cache_environment:context?.environment,
    scope:'measured or verified cached static captures; PNG content/coverage/composition require separate validation',
    seconds:(performance.now()-started)/1000,components:[...reports].sort((a,b)=>order.get(a.file)-order.get(b.file))};
}
function call(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++seq, timer = setTimeout(() => { pending.delete(id); reject(new Error('CDP timeout: ' + method)); }, 20000);
    pending.set(id, {resolve: v => {clearTimeout(timer); resolve(v);}, reject: e => {clearTimeout(timer); reject(e);}});
    socket.send(JSON.stringify({id, method, params}));
  });
}
async function evaluate(expression) {
  const result = await call('Runtime.evaluate', {expression, awaitPromise: true, returnByValue: true});
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text + ': ' + result.exceptionDetails.exception?.description);
  return result.result.value;
}
try {
  let stageTime=performance.now();
  context=await createContext(manifest,root,output,{noCache:flags.includes('--no-cache')});
  metrics.environment_and_source_seconds=(performance.now()-stageTime)/1000;
  const work=[];
  for(const component of manifest.components) {
    const t=performance.now(),cached=await context?.lookup(component);
    metrics.cache_lookup_seconds+=(performance.now()-t)/1000;
    if(cached){cached.seconds=(performance.now()-t)/1000;reports.push(cached);metrics.reused_components++;await checkpoint(cached);}
    else work.push(component);
  }
  // Static exports have no interactions/time/random/location-dependent content.
  // Legacy manifests keep their original order and reload behavior.
  if(context)work.sort((a,b)=>JSON.stringify([a.html,a.fragment||'',Math.max(1024,a.width+32),Math.max(768,a.height+32)])
    .localeCompare(JSON.stringify([b.html,b.fragment||'',Math.max(1024,b.width+32),Math.max(768,b.height+32)])));
  if(work.length) {
  stageTime=performance.now();
  profile = await fs.mkdtemp(path.join(os.tmpdir(), 'hmi-render-'));
  const args = ['--headless=new', '--remote-debugging-port=0', '--force-device-scale-factor=1', '--hide-scrollbars', '--no-first-run', '--no-default-browser-check', '--user-data-dir=' + profile, 'about:blank'];
  if (manifest.software_rendering === true) args.unshift('--disable-gpu');
  processHandle = spawn(manifest.browser, args, {windowsHide: true, stdio: ['ignore','ignore','pipe']});
  let launchError;
  processHandle.on('error', e => {launchError=e;});
  processHandle.stderr.on('data', b => {errors=(errors+b.toString()).slice(-10000);});
  let port;
  for (let i=0;i<150;i++) {
    if (launchError) throw launchError;
    try {port=Number((await fs.readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]); break;} catch {}
    if (processHandle.exitCode !== null) throw new Error('Browser exited: '+errors);
    await pause(100);
  }
  if (!port) throw new Error('Browser debugging endpoint not ready');
  const tabs = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  socket = new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
  socket.addEventListener('message', event => {
    const message=JSON.parse(event.data), waiter=pending.get(message.id);
    if (waiter) {pending.delete(message.id);message.error?waiter.reject(new Error(JSON.stringify(message.error))):waiter.resolve(message.result);}
    if(context&&message.method==='Fetch.requestPaused') {
      const {requestId,request}=message.params;
      let allowed=request.url.startsWith('data:')||request.url==='about:blank';
      if(request.url.startsWith('file:')) {
        try {const file=fileURLToPath(new URL(request.url));allowed=inside(context.snapshot,file);if(allowed)documentFiles.add(file);}catch{}
      }
      if(!allowed)networkViolation='Static source requested an external resource: '+request.url;
      call(allowed?'Fetch.continueRequest':'Fetch.failRequest',allowed?{requestId}:{requestId,errorReason:'BlockedByClient'})
        .catch(e=>{networkViolation=String(e);});
    }
  });
  await call('Page.enable');
  if(context)await call('Fetch.enable',{patterns:[{urlPattern:'*',requestStage:'Request'}]});
  await call('Emulation.setDefaultBackgroundColorOverride',{color:{r:0,g:0,b:0,a:0}});
  metrics.browser_start_seconds=(performance.now()-stageTime)/1000;
  for (const component of work) {
    const t=performance.now(), {width,height,selector,html,file}=component;
    const source=context?await context.source(component):path.resolve(root,html);
    const viewport={width:Math.max(1024,width+32),height:Math.max(768,height+32)};
    const url=pathToFileURL(source).href+(component.fragment ? '#'+encodeURIComponent(component.fragment) : '');
    const documentKey=JSON.stringify([url,viewport]);
    let reloaded=false;
    if(!context||documentKey!==currentDocument) {
    documentFiles=new Set();networkViolation=null;
    await call('Emulation.setDeviceMetricsOverride',{...viewport,deviceScaleFactor:1,mobile:false});
    await call('Page.navigate',{url});metrics.page_loads++;
    let ready=false;
    for (let i=0;i<100;i++) {
      if (await evaluate(`location.href===${JSON.stringify(url)} && document.readyState==='complete'`)) {ready=true;break;}
      await pause(25);
    }
    if (!ready) throw new Error('Component document not ready: '+html);
    if(context && await evaluate(`document.getAnimations().some(a=>a.playState==='running') || !!document.querySelector('video,audio')`))
      throw Error('Static export sources cannot contain active animations, audio or video');
    currentDocument=documentKey;
    reloaded=true;
    }
    const layout=await evaluate(`(async()=>{if(${!context||reloaded}){await document.fonts.ready;await Promise.all(Array.from(document.images,i=>i.decode()));await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));}const e=document.querySelector(${JSON.stringify(selector)});if(!e)throw Error('Missing capture element');const b=e.getBoundingClientRect();return {x:b.x+scrollX,y:b.y+scrollY,width:b.width,height:b.height,innerWidth,innerHeight,dpr:devicePixelRatio};})()`);
    if (layout.innerWidth!==viewport.width||layout.innerHeight!==viewport.height||layout.dpr!==1||Math.abs(layout.width-width)>0.01||Math.abs(layout.height-height)>0.01||layout.x<0||layout.y<0) throw new Error('Measured CSS viewport/component size mismatch: '+JSON.stringify(layout));
    if(networkViolation)throw Error(networkViolation);
    let companyLabel;
    if (component.role==='page_preview') {
      if (!component.brand_selector) throw new Error('Page preview requires an explicit company label selector');
      const expected=String(manifest.company_name||'').trim()||'工控北极熊（抖音）';
      companyLabel=await evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(component.brand_selector)});if(!e)throw Error('Company label missing from HTML');const b=e.getBoundingClientRect();let n=e;while(n){const s=getComputedStyle(n);if(s.display==='none'||s.visibility==='hidden'||Number(s.opacity)===0)throw Error('Company label hidden');n=n.parentElement;}if(!b.width||!b.height||b.x<0||b.y<0||b.right>innerWidth||b.bottom>innerHeight)throw Error('Company label outside visible page');return {text:e.innerText.trim(),bounds:[b.x,b.y,b.width,b.height]};})()`);
      if (companyLabel.text!==expected) throw new Error('Visible HTML company label must equal '+expected);
    }
    if (!renderer) renderer=await evaluate(`(()=>{const g=document.createElement('canvas').getContext('webgl');if(!g)return null;const x=g.getExtension('WEBGL_debug_renderer_info');return x?g.getParameter(x.UNMASKED_RENDERER_WEBGL):g.getParameter(g.RENDERER);})()`);
    let hmi;
    if (component.collect_hmi===true) hmi=await evaluate(`(()=>{const root=document.querySelector(${JSON.stringify(selector)}),r=root.getBoundingClientRect();const visible=e=>{let n=e;while(n){const s=getComputedStyle(n);if(s.display==='none'||s.visibility==='hidden'||Number(s.opacity)===0)return false;n=n.parentElement;}const b=e.getBoundingClientRect();return b.width>0&&b.height>0;};return {page_id:root.dataset.hmiPage,components:[...root.querySelectorAll('[data-hmi-component]')].filter(visible).map(e=>{const b=e.getBoundingClientRect();return {id:e.dataset.hmiComponent,owner:e.dataset.hmiOwner||root.dataset.hmiPage,kind:e.dataset.hmiKind,role:e.dataset.hmiRole,rect_px:[b.x-r.x,b.y-r.y,b.width,b.height],text:e.innerText,binding_name:e.dataset.hmiBinding||null};}),flow_nodes:[...root.querySelectorAll('[data-hmi-node]')].filter(visible).map(e=>e.dataset.hmiNode)};})()`);
    if (hmi) hmi.visual_coverage=await evaluate(`(${collectVisualCoverage.toString()})(document.querySelector(${JSON.stringify(selector)}))`);
    if (hmi) hmi.native_hints=await evaluate(`(${collectNativeHints.toString()})(document.querySelector(${JSON.stringify(selector)}))`);
    if (hmi) hmi.layout_issues=await evaluate(`(${collectLayoutIssues.toString()})(document.querySelector(${JSON.stringify(selector)}))`);
    let png;
    if (component.capture!==false) {
      const shot=await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:true,clip:{x:layout.x,y:layout.y,width,height,scale:1}});
      png=Buffer.from(shot.data,'base64');
      await fs.writeFile(path.join(output,file),png,{flag:'wx'});
    }
    if(networkViolation)throw Error(networkViolation);
    const dependencies=context?context.dependencyRows(documentFiles):undefined;
    const report={id:component.id,file:component.capture===false?null:file,layout,company_label:companyLabel,hmi,
      cache_hit:false,measurement:'measured_current_run',sha256:png?hash(png):undefined,dependencies,
      cache_miss:context?.miss(component)||{reason:'legacy_reload_mode'},
      seconds:(performance.now()-t)/1000};
    if(png)await context?.save(component,report,png,dependencies);
    reports.push(report);metrics.rendered_components++;metrics.capture_seconds+=(performance.now()-t)/1000;
    await checkpoint(report);
  }
  }
  await fs.writeFile(path.join(output,'render-report.json'),JSON.stringify(reportData('pass'),null,2));
} catch (e) {
  failure=e;
  await fs.writeFile(path.join(output,'render-report.json'),JSON.stringify(reportData('fail',String(e)),null,2));
} finally {
  if (socket?.readyState===WebSocket.OPEN) {try {await call('Browser.close');} catch {} socket.close();}
  for (const waiter of pending.values()) waiter.reject(new Error('Renderer closed'));
  if (processHandle && processHandle.exitCode===null && !processHandle.killed) {processHandle.kill();await pause(500);}
  // Retain this isolated OS-temp profile. Browser.close/process shutdown is not
  // a filesystem cleanup task; no recursive deletion during normal generation.
}
if (failure) {console.error(String(failure));process.exitCode=1;} else console.log(JSON.stringify({status:'pass',components:reports.length,output,seconds:(performance.now()-started)/1000}));
