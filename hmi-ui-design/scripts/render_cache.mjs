/** Immutable, machine-local cache for explicitly static, self-contained exports. */
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import {inflateSync} from 'node:zlib';

export const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
export const inside = (root, file) => {
  const rel=path.relative(root,file);
  return rel==='' || (rel!=='..'&&!rel.startsWith('..'+path.sep)&&!path.isAbsolute(rel));
};
const canonical = value => JSON.stringify(value, (_, x) => x && typeof x === 'object' && !Array.isArray(x)
  ? Object.fromEntries(Object.keys(x).sort().map(k => [k, x[k]])) : x);

const crcTable=Array.from({length:256},(_,n)=>{for(let k=0;k<8;k++)n=n&1?0xedb88320^(n>>>1):n>>>1;return n>>>0;});
function crc32(bytes) {let c=0xffffffff;for(const b of bytes)c=crcTable[(c^b)&255]^(c>>>8);return(c^0xffffffff)>>>0;}
export function validPng(raw,width,height) {
  try {
    if(raw.length<45||raw.subarray(0,8).toString('hex')!=='89504e470d0a1a0a')return false;
    let at=8,channels,ended=false;const data=[];
    while(at<raw.length) {
      const size=raw.readUInt32BE(at),end=at+12+size;
      if(end>raw.length)return false;
      const type=raw.toString('ascii',at+4,at+8),payload=raw.subarray(at+8,at+8+size);
      if(crc32(raw.subarray(at+4,at+8+size))!==raw.readUInt32BE(at+8+size))return false;
      if(at===8&&type!=='IHDR')return false;
      if(type==='IHDR') {
        if(at!==8||size!==13||payload.readUInt32BE(0)!==width||payload.readUInt32BE(4)!==height
          ||payload[8]!==8||![2,6].includes(payload[9])||payload[10]||payload[11]||payload[12])return false;
        channels=payload[9]===6?4:3;
      } else if(type==='IDAT')data.push(payload);
      else if(type==='IEND'){if(size!==0||end!==raw.length)return false;ended=true;break;}
      at=end;
    }
    if(!ended||!channels||!data.length)return false;
    const stride=width*channels+1,expected=stride*height;
    const pixels=inflateSync(Buffer.concat(data),{maxOutputLength:expected});
    if(pixels.length!==expected)return false;
    for(let y=0;y<height;y++)if(pixels[y*stride]>4)return false;
    return true;
  }catch{return false;}
}

async function inventory(root) {
  const files = new Map();
  async function visit(dir) {
    for (const item of await fs.readdir(dir, {withFileTypes: true})) {
      const full = path.join(dir, item.name);
      if (item.isSymbolicLink() || !inside(root, await fs.realpath(full))) throw Error('Static sources cannot contain links');
      if (item.isDirectory()) await visit(full);
      else if (item.isFile()) {
        const raw = await fs.readFile(full);
        files.set(path.relative(root, full).split(path.sep).join('/'), {sha256: hash(raw), raw});
      }
    }
  }
  await visit(root);
  return files;
}

async function fontStamp() {
  const roots = process.platform === 'win32'
    ? [path.join(process.env.WINDIR || 'C:\\Windows', 'Fonts'), path.join(process.env.LOCALAPPDATA || '', 'Microsoft/Windows/Fonts')]
    : ['/usr/share/fonts', path.join(os.homedir(), '.local/share/fonts'), '/System/Library/Fonts', '/Library/Fonts'];
  const rows = [];
  async function visit(dir) {
    let entries; try {entries = await fs.readdir(dir, {withFileTypes:true});} catch {return;}
    for (const e of entries) {
      const f = path.join(dir,e.name);
      if (e.isDirectory()) await visit(f);
      else if (e.isFile()) {const s=await fs.stat(f); rows.push([f,s.size,s.mtimeMs]);}
    }
  }
  for (const root of roots) await visit(root);
  return rows.sort((a,b)=>a[0].localeCompare(b[0]));
}

export async function createContext(manifest, manifestRoot, output, options = {}) {
  const config = manifest.optimization;
  if (!config) return null; // Legacy inputs retain reload-per-capture behavior.
  if (config.static !== true || !config.source_root) throw Error('Optimization requires static:true and a dedicated source_root');
  const root = path.resolve(manifestRoot, config.source_root);
  if (!inside(manifestRoot, root) || root === manifestRoot || inside(root,output) || inside(output,root))
    throw Error('Use a dedicated static source directory, separate from outputs');
  if (await fs.realpath(root) !== root) throw Error('Static source root cannot be linked');
  const files = await inventory(root);
  const cacheRoot = options.noCache ? null : options.cache || config.cache_dir;
  const cache = cacheRoot ? path.resolve(manifestRoot, cacheRoot) : null;
  if (cache && (inside(root,cache) || inside(cache,root) || inside(output,cache) || inside(cache,output)))
    throw Error('Cache, source and output directories must be separate');
  const browserPath = await fs.realpath(manifest.browser);
  let backendReport;
  if(config.backend_report) {
    backendReport=JSON.parse(await fs.readFile(path.resolve(manifestRoot,config.backend_report),'utf8'));
    if(!backendReport.cache_identity)throw Error('backend_report must contain a probe cache_identity');
  }
  const browserStat = await fs.stat(browserPath);
  let siblings=[];
  for (const e of await fs.readdir(path.dirname(browserPath), {withFileTypes:true})) {
    if (e.isDirectory() && /^\d+\.\d+/.test(e.name)) siblings.push(e.name);
  }
  const environment = hash(canonical({host:os.hostname(),os:os.release(),arch:os.arch(),node:process.version,
    browser:browserPath,browser_sha256:hash(await fs.readFile(browserPath)),browser_mtime:browserStat.mtimeMs,
    browser_versions:siblings.sort(),fonts:await fontStamp(),software:manifest.software_rendering===true,
    backend_key:config.backend_key || null,backend_report:backendReport?.cache_identity || null,contract:'static-export-cache/1.0'}));
  const sourceDigest = hash(canonical([...files].map(([file,v])=>[file,v.sha256]).sort()));
  const snapshot = path.join(output,'source-snapshot');
  const misses=new WeakMap();
  let madeSnapshot=false;
  function captureKey(component) {
    const copy={...component,html:path.relative(root,path.resolve(manifestRoot,component.html)).split(path.sep).join('/')};
    return hash(canonical({component:copy,environment}));
  }
  function eligible(c) {return cache && c.capture!==false && c.collect_hmi!==true && c.role!=='page_preview';}
  function dependenciesMatch(deps, html) {
    return Array.isArray(deps) && deps.length>0 && deps.some(d=>d.file===html)
      && deps.every(d=>files.get(d.file)?.sha256===d.sha256);
  }
  return {root,files,sourceDigest,environment,snapshot,cache,
    miss:component=>misses.get(component)||{reason:'cache_disabled_or_live_dom_required'},
    async source(component) {
      const original=path.resolve(manifestRoot,component.html);
      if (!inside(root,original) || !files.has(path.relative(root,original).split(path.sep).join('/')))
        throw Error('Every optimized capture must originate inside source_root');
      if (!madeSnapshot) {
        await fs.mkdir(snapshot);
        for (const [rel,item] of files) {const dest=path.join(snapshot,rel);await fs.mkdir(path.dirname(dest),{recursive:true});await fs.writeFile(dest,item.raw,{flag:'wx'});}
        madeSnapshot=true;
      }
      return path.join(snapshot,path.relative(root,original));
    },
    async lookup(component) {
      if (!eligible(component)) return null;
      const key=captureKey(component), dir=path.join(cache,key);
      misses.set(component,{reason:'capture_or_environment_not_cached'});
      let entries;try {entries=(await fs.readdir(dir)).filter(x=>x.endsWith('.json')).sort().reverse();}catch{return null;}
      const html=path.relative(root,path.resolve(manifestRoot,component.html)).split(path.sep).join('/');
      for (const entry of entries) {
        try {
          const saved=JSON.parse(await fs.readFile(path.join(dir,entry),'utf8'));
          if(saved.key!==key || saved.environment!==environment)continue;
          if(!dependenciesMatch(saved.dependencies,html)) {
            misses.set(component,{reason:'source_dependencies_changed',files:(saved.dependencies||[])
              .filter(d=>files.get(d.file)?.sha256!==d.sha256).map(d=>d.file)});continue;
          }
          if (!/^[a-f0-9-]+\.png$/.test(saved.png)) continue;
          const raw=await fs.readFile(path.join(dir,saved.png));
          if(hash(raw)!==saved.sha256 || !validPng(raw,component.width,component.height)) {
            misses.set(component,{reason:'cached_png_invalid'});continue;
          }
          await fs.writeFile(path.join(output,component.file),raw,{flag:'wx'});
          return {...saved.report,id:component.id,file:component.file,cache_hit:true,cache_key:key,
            cache_miss:undefined,
            sha256:saved.sha256,dependencies:saved.dependencies,
            measurement:'reused_prior_measurement; source_dependencies_and_png_hash_verified',seconds:0};
        } catch (error) {if(error.code==='EEXIST')throw error;misses.set(component,{reason:'cache_entry_unreadable'});}
      }
      return null;
    },
    dependencyRows(urlFiles) {
      const rows=[];
      for (const absolute of urlFiles) {
        if(!inside(snapshot,absolute)) throw Error('Resource escaped the static snapshot');
        const rel=path.relative(snapshot,absolute).split(path.sep).join('/');
        const item=files.get(rel);if(!item)throw Error('Undeclared static resource: '+rel);
        rows.push({file:rel,sha256:item.sha256});
      }
      return rows.sort((a,b)=>a.file.localeCompare(b.file));
    },
    async save(component,report,raw,dependencies) {
      if(!eligible(component))return;
      if(!validPng(raw,component.width,component.height))throw Error('Rendered PNG failed structural/decode validation');
      const key=captureKey(component),dir=path.join(cache,key),id=crypto.randomUUID();
      await fs.mkdir(dir,{recursive:true});
      await fs.writeFile(path.join(dir,id+'.png'),raw,{flag:'wx'});
      await fs.writeFile(path.join(dir,id+'.json'),JSON.stringify({key,environment,dependencies,png:id+'.png',
        sha256:hash(raw),report},null,2),{flag:'wx'});
    }
  };
}
