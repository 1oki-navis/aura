const C="liftlog-v27";
const FILES=["./","index.html","manifest.json","sw.js","README.md","icon-180.png","icon-512.png","fonts/doto.woff2","fonts/bebas.woff2","fonts/mono.woff2","fonts/mono-b.woff2"];
self.addEventListener("install",e=>{self.skipWaiting();e.waitUntil(caches.open(C).then(c=>c.addAll(FILES)))});
self.addEventListener("activate",e=>e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==C).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
const timeout=(ms)=>new Promise((_,rej)=>setTimeout(()=>rej(new Error("timeout")),ms));
self.addEventListener("fetch",e=>{
  const req=e.request;if(req.method!=="GET")return;
  const url=new URL(req.url);
  if(url.pathname.includes("/fonts/")||url.pathname.endsWith(".png")||url.pathname.endsWith("manifest.json")){
    e.respondWith(caches.match(req).then(c=>c||fetch(req).then(r=>{if(r.ok)caches.open(C).then(x=>x.put(req,r.clone()));return r})));
    return;
  }
  e.respondWith(Promise.race([fetch(req),timeout(2500)]).then(r=>{if(r&&r.ok)caches.open(C).then(c=>c.put(req,r.clone()));return r}).catch(()=>caches.match(req).then(r=>r||caches.match("index.html"))));
});
