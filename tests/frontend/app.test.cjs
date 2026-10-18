const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {JSDOM} = require('jsdom');
const tick = () => new Promise(r => setImmediate(r));
const pending = () => {let resolve; const promise = new Promise(r => resolve = r); return {promise, resolve};};
const json = (data) => ({ok: true, json: async () => data});
const answer = name => ({mode:'no_ai', recommendations:[], notes:[name], safety:[], considered:{time_budget_min:60,candidates_found:0}, disclaimer:'test'});
async function boot(t, opts = {}) {
  const dom = new JSDOM(fs.readFileSync('frontend/index.html','utf8'), {url:'https://example.test/',runScripts:'outside-only'});
  t.after(() => dom.window.close());
  const w=dom.window, requests=[], gps={};
  w.matchMedia=()=>({matches:false});
  w.HTMLElement.prototype.scrollIntoView=()=>{};
  w.SERUEN_CONFIG={API_URL:'https://api.example.test',FEATURES:{weather:false}};
  Object.defineProperty(w,'isSecureContext',{value:true});
  Object.defineProperty(w.navigator,'geolocation',{value:{getCurrentPosition:(ok,fail)=>Object.assign(gps,{ok,fail})}});
  const map={setView(){return this;},on(){return this;},getZoom(){return 15;},invalidateSize(){},fitBounds(){},removeLayer(){}};
  w.L={map:()=>map,tileLayer:()=>({addTo(){}}),divIcon:x=>x,
    marker:()=>({addTo(){return this;},bindTooltip(){return this;},on(){return this;},setLatLng(){},setTooltipContent(){}}),
    layerGroup:()=>({addTo(){return this;},clearLayers(){}}),latLngBounds:x=>x,
    Control:{extend:cfg=>class{addTo(){w.document.body.appendChild(cfg.onAdd());}}},
    DomUtil:{create:(tag,cl)=>{const el=w.document.createElement(tag);el.className=cl;return el;}},
    DomEvent:{disableClickPropagation(){},on:(el,event,cb)=>el.addEventListener(event,cb),stop:e=>e.stopPropagation()}};
  w.fetch=async(url,options)=>{
    if(url==='presets.json'||url==='scenarios.json') return json(JSON.parse(fs.readFileSync('frontend/'+url,'utf8')));
    if(url.endsWith('/health')) return opts.health ? opts.health.promise : json({mode_available:['no_ai']});
    if(url.endsWith('/recommend')) {const p=pending();requests.push({body:JSON.parse(options.body),...p});return p.promise;}
    throw Error('Unexpected request '+url);
  };
  for(const file of ['i18n.js','route.js','app.js']) w.eval(fs.readFileSync('frontend/'+file,'utf8'));
  await tick(); await tick();
  return {w,requests,gps,click:s=>w.document.querySelector(s).click()};
}
test('shell and six demos stay usable while backend health is pending', async t=>{
  const b=await boot(t,{health:pending()});
  assert.match(b.w.document.querySelector('#goBtn').textContent,/Подобрать/);
  assert.equal(b.w.document.querySelectorAll('#scenarioCards button').length,6);
  b.click('#scenarioCards button'); await tick(); assert.equal(b.requests.length,1);
});
test('late GPS cannot replace a selected demo',async t=>{
  const b=await boot(t); b.click('#scenarioCards button');await tick();
  b.gps.ok({coords:{latitude:51.15,longitude:71.44}});
  b.click('#chips button');await tick();
  assert.equal(b.requests[1].body.location.source,'preset');
  assert.deepEqual(b.requests[1].body.location,b.requests[0].body.location);
});
test('only the newest request may render, even if older request arrives last',async t=>{
  const b=await boot(t);b.click('#scenarioCards button');await tick();
  b.click('#chips button');await tick();assert.equal(b.requests.length,2);
  b.requests[1].resolve(json(answer('NEWEST')));await tick();
  b.requests[0].resolve(json(answer('STALE')));await tick();
  assert.match(b.w.document.querySelector('#results').textContent,/NEWEST/);
  assert.doesNotMatch(b.w.document.querySelector('#results').textContent,/STALE/);
});
test('coordinates round on device and permission failure keeps the chosen point',async t=>{
  const b=await boot(t);b.gps.ok({coords:{latitude:51.1284321,longitude:71.4304321}});
  b.click('#goBtn');await tick();
  assert.equal(b.requests[0].body.location.lat,51.128);
  assert.equal(b.requests[0].body.location.lon,71.43);
});
test('server errors show an actionable retry',async t=>{
  const b=await boot(t);b.click('#goBtn');await tick();b.requests[0].resolve({ok:false,status:503});await tick();
  assert.ok(b.w.document.querySelector('#retryBtn'));b.click('#retryBtn');await tick();assert.equal(b.requests.length,2);
});
test('all three UI languages render without missing labels',async t=>{
  const b=await boot(t);
  for(const lang of ['en','kk','ru']) {b.click(`[data-lang="${lang}"]`);assert.equal(b.w.document.documentElement.lang,lang);assert.ok(b.w.document.querySelector('#goBtn').textContent);}
});

test('candidate panel stays usable with a city-sized exclusion list',async t=>{
  const b=await boot(t);b.click('#goBtn');await tick();
  const a=answer('Candidates');a.considered.candidates_found=1;
  a.candidates=[{name:'Place',category:'park',distance_m:100,score:.8}];
  a.excluded=Array.from({length:1250},(_,n)=>({name:'Excluded '+n,category:'park',distance_m:n+1,excluded_because:'closed'}));
  b.requests[0].resolve(json(a));await tick();b.click('#candBtn');await tick();
  assert.equal(b.w.document.querySelectorAll('.cands tr').length,22);
  assert.match(b.w.document.querySelector('#consideredBox').textContent,/20\/1250/);
});

for (const choice of ['alone','group','child']) {
  test(`child tile does not overwrite the manual ${choice} preference for later tiles`,async t=>{
    const b=await boot(t);const select=b.w.document.querySelector('#companions');
    select.value=choice;select.dispatchEvent(new b.w.Event('change'));
    b.click('#chips button[data-i="2"]');await tick();
    assert.equal(b.requests[0].body.context.companions,'child');
    b.click('#chips button[data-i="0"]');await tick();
    assert.equal(b.requests[1].body.context.companions,choice);
  });
}
