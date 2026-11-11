// Content + dimensions identify a raster. IndexedDB allows reuse after refresh.
(()=>{
 const memory=new Map();const stats={hits:0,rendered:0};let database;
 function db(){return database||(database=new Promise(resolve=>{try{const r=indexedDB.open('hmi-component-raster-v1',1);r.onupgradeneeded=()=>r.result.createObjectStore('png');r.onsuccess=()=>resolve(r.result);r.onerror=()=>resolve(null);}catch{resolve(null);}}));}
 async function get(key){if(memory.has(key)){stats.hits++;return memory.get(key);}const d=await db();if(!d)return null;return new Promise(resolve=>{try{const r=d.transaction('png').objectStore('png').get(key);r.onsuccess=()=>{if(r.result){stats.hits++;memory.set(key,r.result);}resolve(r.result||null);};r.onerror=()=>resolve(null);}catch{resolve(null);}});}
 async function put(key,png){stats.rendered++;memory.set(key,png);const d=await db();if(d)try{d.transaction('png','readwrite').objectStore('png').put(png,key);}catch{}}
 async function key(svg,w,h){const bytes=new TextEncoder().encode(JSON.stringify(['svg-png-v2-viewport',w,h,svg]));return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');}
 window.AssetCache={get,put,key,stats};
})();
