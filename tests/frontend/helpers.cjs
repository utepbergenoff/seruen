const fs = require('node:fs');
const {JSDOM} = require('jsdom');
const tick = () => new Promise(r => setImmediate(r));
const pending = () => {let resolve; const promise = new Promise(r => resolve = r); return {promise, resolve};};
const json = data => ({ok:true,json:async()=>data});
async function boot(t, opts = {}) {
  const dom = new JSDOM(fs.readFileSync('frontend/index.html','utf8'), {url:'https://example.test/',runScripts:'outside-only'});
  t.after(() => dom.window.close());
  const w=dom.window, requests=[], gps={}, gis=[], photos=[], replans=[], comforts=[];
  if (opts.live) w.AbortController = AbortController;
  w.matchMedia=()=>({matches:false});
  w.HTMLElement.prototype.scrollIntoView=()=>{};
  w.SERUEN_CONFIG={API_URL:'https://api.example.test',FEATURES:{weather:false}};
  Object.defineProperty(w,'isSecureContext',{value:true});
  Object.defineProperty(w.navigator,'geolocation',{value:{getCurrentPosition:(ok,fail)=>Object.assign(gps,{ok,fail})}});
  const map={setView(){return this;},on(){return this;},getZoom(){return 15;},invalidateSize(){},fitBounds(){},removeLayer(){}};
  w.L={map:()=>map,tileLayer:()=>({addTo(){}}),divIcon:x=>x,
    marker:()=>({addTo(){return this;},bindTooltip(){return this;},bindPopup(){return this;},getLatLng(){return [51.13,71.43];},openPopup(){},on(){return this;},setLatLng(){},setTooltipContent(){}}),
    layerGroup:()=>({addTo(){return this;},clearLayers(){}}),latLngBounds:x=>x,
    Control:{extend:cfg=>class{addTo(){w.document.body.appendChild(cfg.onAdd());}}},
    DomUtil:{create:(tag,cl)=>{const el=w.document.createElement(tag);el.className=cl;return el;}},
    DomEvent:{disableClickPropagation(){},on:(el,event,cb)=>el.addEventListener(event,cb),stop:e=>e.stopPropagation()}};
  w.fetch=async(url,options)=>{
    if(url==='presets.json'||url==='scenarios.json') return json(JSON.parse(fs.readFileSync('frontend/'+url,'utf8')));
    if(opts.live && url.startsWith('https://api.example.test')) {
      let response;
      try { response = await fetch(url.replace('https://api.example.test', opts.live), options); }
      catch(e) { opts.calls?.push({path:new URL(url).pathname, error:String(e),cause:String(e.cause)});throw e; }
      opts.calls?.push({path: new URL(url).pathname, body: options?.body ? JSON.parse(options.body) : null, status: response.status});
      return response;
    }
    if(url.endsWith('/health')) return opts.health ? opts.health.promise : json(opts.healthData||{mode_available:['no_ai']});
    if(url.endsWith('/plans/recalculate')) {const p=pending();replans.push({body:JSON.parse(options.body),...p});return p.promise;}
    if(url.endsWith('/comfort/search')) {comforts.push(JSON.parse(options.body));return json(opts.comfort||[]);}
    if(url.endsWith('/atmosphere/examples')) return json(opts.atmos||[]);
    if(url.endsWith('/plans/build')) return json(opts.build);
    if(url.endsWith('/plans/export')) return json(opts.export);
    if(url.endsWith('/plans/refresh')) return json(opts.refresh || opts.build);
    if(url.endsWith('/recommend')) {const p=pending();requests.push({body:JSON.parse(options.body),...p});return p.promise;}
    if(/\/2gis(\?|$)/.test(url)) {gis.push(url);return opts.twogis(url);}
    if(url.endsWith('/photos')) {photos.push({url,body:JSON.parse(options.body)});return opts.photos?opts.photos(url):json({poi_id:'x',photos:[],status:'no_photos',checked_at:'2026-10-18T09:00:00Z'});}
    throw Error('Unexpected request '+url);
  };
  for(const file of ['storage.js','i18n.js','route.js','app.js','features.js']) w.eval(fs.readFileSync('frontend/'+file,'utf8'));
  await tick(); await tick();
  return {w,requests,gps,gis,photos,replans,comforts,click:s=>w.document.querySelector(s).click()};
}

module.exports = {boot};
