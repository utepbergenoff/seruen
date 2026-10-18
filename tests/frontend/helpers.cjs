const fs = require('node:fs');
const {JSDOM} = require('jsdom');
const tick = () => new Promise(r => setImmediate(r));
const pending = () => {let resolve; const promise = new Promise(r => resolve = r); return {promise, resolve};};
const json = data => ({ok:true,json:async()=>data});
async function boot(t, opts = {}) {
  const dom = new JSDOM(fs.readFileSync('frontend/index.html','utf8'), {url:opts.url||'https://example.test/',runScripts:'outside-only'});
  t.after(() => dom.window.close());
  const w=dom.window, requests=[], gps={calls:[]}, gis=[], photos=[], replans=[], comforts=[], builds=[], tiles=[], lines=[], pins=[];
  if (opts.clock) {w.setTimeout=opts.clock.setTimeout;w.clearTimeout=opts.clock.clearTimeout;}
  if (opts.live) w.AbortController = AbortController;
  const media={matches:!!opts.darkSystem,addEventListener:(_, cb)=>{media.change=cb;}};
  w.matchMedia=q=>q.includes('prefers-color-scheme') ? media : {matches:false};
  for(const [k,v] of Object.entries(opts.storage||{})) w.localStorage.setItem(k,JSON.stringify(v));
  w.HTMLElement.prototype.scrollIntoView=()=>{};
  w.SERUEN_CONFIG={API_URL:'https://api.example.test',FEATURES:{weather:false}};
  Object.defineProperty(w,'isSecureContext',{value:true});
  Object.defineProperty(w.navigator,'geolocation',{value:{getCurrentPosition:(ok,fail,options)=>{
    gps.calls.push({ok,fail,options});Object.assign(gps,{ok,fail});
  }}});
  const layers=new Set();
  const map={setView(){return this;},setMaxZoom(z){this.maxZoom=z;return this;},on(){return this;},getZoom(){return 15;},invalidateSize(){},fitBounds(){},removeLayer(l){layers.delete(l);}};
  const events=()=>{const handlers={};return {on(e,cb){handlers[e]=cb;return this;},fire(e,payload={}){handlers[e]?.(payload);return this;}};};
  w.L={map:()=>map,tileLayer:(url,options)=>{const l={url,options,...events(),addTo(){layers.add(this);return this;}};tiles.push(l);return l;},divIcon:x=>x,
    marker:(coords,options)=>{const p={coords,options,...events(),addTo(target){this.target=target;if(target===map)layers.add(this);else target.addLayer?.(this);return this;},bindTooltip(){return this;},bindPopup(){return this;},getLatLng(){return coords;},openPopup(){},setLatLng(){},setTooltipContent(){}};pins.push(p);return p;},
    polyline:(coords,options)=>{const l={coords,options,addTo(target){this.target=target;if(target===map)layers.add(this);else target.addLayer?.(this);return this;}};lines.push(l);return l;},
    layerGroup:()=>({members:new Set(),addLayer(l){this.members.add(l);return this;},addTo(){layers.add(this);return this;},clearLayers(){this.members.clear();return this;}}),latLngBounds:x=>x,
    Control:{extend:cfg=>class{addTo(){w.document.body.appendChild(cfg.onAdd());}}},
    DomUtil:{create:(tag,cl)=>{const el=w.document.createElement(tag);el.className=cl;return el;}},
    DomEvent:{disableClickPropagation(){},on:(el,event,cb)=>el.addEventListener(event,cb),stop:e=>e.stopPropagation()}};
  w.fetch=async(url,options)=>{
    if(url==='presets.json'||url==='scenarios.json') return opts.staticFiles?.[url]?.promise || json(JSON.parse(fs.readFileSync('frontend/'+url,'utf8')));
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
    if(url.endsWith('/atmosphere/profiles')) return opts.atmosProfileResponse?.promise || json(opts.atmosProfiles || {profiles:[]});
    if(url.endsWith('/atmosphere/examples')) return json(opts.atmos||[]);
    if(url.includes('/city/stories?')) return json({items: opts.stories || []});
    if(url.endsWith('/plans/build')) {builds.push(JSON.parse(options.body));return opts.buildResponse ? opts.buildResponse.promise : json(opts.build);}
    if(url.endsWith('/plans/export')) return json(opts.export);
    if(url.endsWith('/plans/refresh')) return json(opts.refresh || opts.build);
    if(url.endsWith('/recommend')) {const p=pending();requests.push({body:JSON.parse(options.body),...p});return p.promise;}
    if(/\/2gis(\?|$)/.test(url)) {gis.push(url);return opts.twogis(url);}
    if(url.endsWith('/photos')) {photos.push({url,body:JSON.parse(options.body)});return opts.photos?opts.photos(url):json({poi_id:'x',photos:[],status:'no_photos',checked_at:'2026-10-18T09:00:00Z'});}
    if(opts.experiences && ['/city/history','/meet/search','/plans/winter'].some(p=>url.endsWith(p))) return opts.experiences(url,JSON.parse(options.body));
    throw Error('Unexpected request '+url);
  };
  for(const file of ['theme.js','storage.js','i18n.js','route.js','app.js','features.js','experiences-i18n.js','experiences.js']) w.eval(fs.readFileSync('frontend/'+file,'utf8'));
  await tick(); await tick();
  return {w,requests,gps,gis,photos,replans,comforts,builds,tiles,lines,pins,layers,media,click:s=>w.document.querySelector(s).click()};
}

module.exports = {boot};
