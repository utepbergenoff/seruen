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
  const w=dom.window, requests=[], gps={}, gis=[], photos=[];
  w.matchMedia=()=>({matches:false});
  w.HTMLElement.prototype.scrollIntoView=()=>{};
  w.SERUEN_CONFIG={API_URL:'https://api.example.test',FEATURES:{weather:false}};
  Object.defineProperty(w,'isSecureContext',{value:true});
  Object.defineProperty(w.navigator,'geolocation',{value:{getCurrentPosition:(ok,fail)=>Object.assign(gps,{ok,fail})}});
  const map={setView(){return this;},on(){return this;},getZoom(){return 15;},invalidateSize(){},fitBounds(){},removeLayer(){}};
  w.L={map:()=>map,tileLayer:()=>({addTo(){}}),divIcon:x=>x,
    marker:()=>({addTo(){return this;},bindTooltip(){return this;},bindPopup(){return this;},on(){return this;},setLatLng(){},setTooltipContent(){}}),
    layerGroup:()=>({addTo(){return this;},clearLayers(){}}),latLngBounds:x=>x,
    Control:{extend:cfg=>class{addTo(){w.document.body.appendChild(cfg.onAdd());}}},
    DomUtil:{create:(tag,cl)=>{const el=w.document.createElement(tag);el.className=cl;return el;}},
    DomEvent:{disableClickPropagation(){},on:(el,event,cb)=>el.addEventListener(event,cb),stop:e=>e.stopPropagation()}};
  w.fetch=async(url,options)=>{
    if(url==='presets.json'||url==='scenarios.json') return json(JSON.parse(fs.readFileSync('frontend/'+url,'utf8')));
    if(url.endsWith('/health')) return opts.health ? opts.health.promise : json({mode_available:['no_ai']});
    if(url.endsWith('/recommend')) {const p=pending();requests.push({body:JSON.parse(options.body),...p});return p.promise;}
    if(url.includes('/2gis')) {gis.push(url);return opts.twogis(url);}
    if(url.endsWith('/photos')) {photos.push({url,body:JSON.parse(options.body)});return opts.photos?opts.photos(url):json({poi_id:'x',photos:[],status:'no_photos',checked_at:'2026-10-18T09:00:00Z'});}
    throw Error('Unexpected request '+url);
  };
  for(const file of ['i18n.js','route.js','app.js']) w.eval(fs.readFileSync('frontend/'+file,'utf8'));
  await tick(); await tick();
  return {w,requests,gps,gis,photos,click:s=>w.document.querySelector(s).click()};
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
test('2GIS next page preserves the original request and cannot overwrite a newer search',async t=>{
  const b=await boot(t); b.click('#goBtn'); await tick();
  const first={...answer('FIRST'),source:'2gis',next_cursor:'opaque-next'};
  b.requests[0].resolve(json(first));await tick();
  assert.match(b.w.document.querySelector('#results').textContent,/Места из 2ГИС/);
  assert.ok(b.w.document.querySelector('#nextPlacesBtn'));
  b.click('#nextPlacesBtn');await tick();
  assert.deepEqual(b.requests[1].body,{...b.requests[0].body,cursor:'opaque-next'});
  assert.ok(b.w.document.querySelector('#nextPlacesBtn').disabled);
  b.click('#goBtn');await tick();
  b.requests[2].resolve(json(answer('LATEST')));await tick();
  b.requests[1].resolve(json({...answer('OLD PAGE'),source:'2gis'}));await tick();
  assert.match(b.w.document.querySelector('#results').textContent,/LATEST/);
  assert.doesNotMatch(b.w.document.querySelector('#results').textContent,/OLD PAGE/);
  assert.equal(b.w.document.querySelector('#nextPlacesBtn'),null);
});

test('2GIS paging error preserves results and enables retry',async t=>{
  const b=await boot(t);b.click('#goBtn');await tick();
  b.requests[0].resolve(json({...answer('KEEP ME'),source:'2gis',next_cursor:'next'}));await tick();
  b.click('#nextPlacesBtn');await tick();
  b.requests[1].resolve({ok:false,status:503});await tick();
  assert.match(b.w.document.querySelector('#results').textContent,/KEEP ME/);
  assert.equal(b.w.document.querySelector('#nextPlacesBtn').disabled,false);
});
test('all three UI languages render without missing labels',async t=>{
  const b=await boot(t);
  for(const lang of ['en','kk','ru']) {b.click(`[data-lang="${lang}"]`);assert.equal(b.w.document.documentElement.lang,lang);assert.ok(b.w.document.querySelector('#goBtn').textContent);}
});

test('what-I-considered lists every place it counts, even with a city-sized exclusion list',async t=>{
  const b=await boot(t);b.click('#goBtn');await tick();
  const a=answer('Candidates');a.considered.candidates_found=6;
  a.candidates=Array.from({length:6},(_,n)=>({poi_id:'c'+n,name:'Place '+n,category:'park',distance_m:100+n,score:.8}));
  a.excluded=Array.from({length:1250},(_,n)=>({name:'Excluded '+n,category:'park',distance_m:n+1,excluded_because:'closed'}));
  b.requests[0].resolve(json(a));await tick();
  const box=b.w.document.querySelector('#consideredBox');
  assert.equal(box.querySelectorAll('.cand').length,6);
  assert.match(box.textContent,/Рассмотрено мест: 6/);
  assert.doesNotMatch(box.textContent,/Excluded/);
  assert.equal(b.w.document.querySelector('#candBtn'),null);
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

const rec = (id, name) => ({poi_id:id,name,category:'coffee',coords:{lat:51.13,lon:71.43},distance_m:300,walk_min:5,time_to_spend_min:30,
  why:'w',why_source:'template',what_to_do:'d',what_to_do_source:'template',open_status:{state:'unknown',confidence:'low',hours:null,source:'none',checked_at:null}});
const gisAnswer = {poi_id:'p1',twogis_place_id:'70000001',source:'2gis',provider_name:'Coffee BOOM',address:'<img src=x onerror=alert(1)>',language:'ru',
  checked_at:'2026-10-18T09:00:00Z',match_method:'exact_name_nearby',match_distance_m:12,rating:4.6,rating_count:321,rating_scope:'organization',
  weekly_hours:['Mon','Tue','Wed','Thu','Fri'].map(day=>({day,intervals:[{start:'08:00',end:'22:00'}]})),special_hours:[],is_24x7:false,
  schedule_note:null,open_now:null,provider_url:'https://2gis.kz/astana/firm/70000001',attribution:'Данные 2ГИС',photos_supported:false};
async function withCards(t, twogis, photos) {
  const b=await boot(t,{twogis,photos});b.click('#goBtn');await tick();
  b.requests[0].resolve(json({...answer('cards'),recommendations:[rec('p1','Coffee BOOM'),rec('p2','Drinkit')]}));await tick();
  return b;
}
test('2GIS is asked only on the button, once per place, and its text is escaped',async t=>{
  const b=await withCards(t,()=>json(gisAnswer));
  assert.equal(b.gis.length,0);
  const btn=b.w.document.querySelector('.rec [data-act="gis"]'),box=b.w.document.querySelector('.rec .gis-box');
  btn.click();await tick();await tick();
  assert.equal(b.gis.length,1);assert.match(b.gis[0],/\/places\/p1\/2gis\?lang=ru$/);
  assert.match(box.textContent,/Данные 2ГИС/);assert.match(box.textContent,/★ 4\.6 · отзывов: 321/);
  assert.match(box.textContent,/пн–пт 08:00–22:00; сб–вс нет данных/);
  assert.match(box.textContent,/не подтверждает, что место открыто прямо сейчас/);
  assert.equal(box.querySelector('img'),null);
  assert.equal(box.querySelector('a').href,'https://2gis.kz/astana/firm/70000001');
  btn.click();assert.ok(box.hidden);
  btn.click();await tick();assert.ok(!box.hidden);assert.equal(b.gis.length,1);
});
test('2GIS failures: no match is final, a timeout offers retry, the card stays',async t=>{
  let code='twogis_not_matched';
  const b=await withCards(t,()=>({ok:false,status:404,json:async()=>({error:{code}})}));
  const [c1,c2]=b.w.document.querySelectorAll('.rec');
  c1.querySelector('[data-act="gis"]').click();await tick();await tick();
  assert.match(c1.querySelector('.gis-box').textContent,/нет надёжного совпадения/);
  assert.equal(c1.querySelector('[data-act="gis-retry"]'),null);
  code='twogis_timeout';
  c2.querySelector('[data-act="gis"]').click();await tick();await tick();
  assert.match(c2.querySelector('.gis-box').textContent,/не ответил вовремя/);
  c2.querySelector('[data-act="gis-retry"]').click();await tick();await tick();
  assert.equal(b.gis.length,3);
  assert.match(c1.querySelector('h3').textContent,/Coffee BOOM/);
});

test('card face has no AI or template labels; the More fold keeps what-to-do, time there and sources',async t=>{
  const b=await boot(t);b.click('#goBtn');await tick();
  const ai={...rec('p1','Fame City'),why_source:'ai',what_to_do_source:'ai'};
  b.requests[0].resolve(json({...answer('mixed'),mode:'ai',recommendations:[ai,rec('p2','Сквер'),rec('p3','Парк')]}));await tick();
  const cards=[...b.w.document.querySelectorAll('.rec')];
  for(const c of cards){
    assert.equal(c.querySelectorAll('.badge.ai,.badge.tpl,.badge.db').length,0);
    assert.match(c.querySelector('.why').textContent,/Почему: w/);
    assert.doesNotMatch([...c.children].filter(x=>!x.matches('details')).map(x=>x.textContent).join(' '),/Что делать|На месте/);
    assert.match(c.querySelector('details.more').textContent,/Что делать: d.*На месте: ~30/s);
  }
  assert.match(cards[0].querySelector('.more').textContent,/текст написал ИИ/);
  assert.match(cards[1].querySelector('.more').textContent,/место добавлено кодом/);
});

test('photos: strip, photo reason and facts per card; no photos says so; text stays out of URLs',async t=>{
  const pic={url:'https://upload.wikimedia.org/a.jpg',page_url:'https://commons.wikimedia.org/wiki/File:A.jpg',author:'Ann <b>X</b>',license:'CC BY-SA 4.0',source:'commons'};
  const b=await withCards(t,null,url=>url.includes('/p1/')
    ? json({poi_id:'p1',photos:[pic,{...pic,url:'http://insecure.example/x.jpg'}],status:'ok',analysis_source:'gemini',checked_at:'2026-10-18T09:00:00Z',
        analysis:{lighting:'natural',kids_area:'no',seats:24,seating:'some',space:'medium',decor:'дерево и растения',summary:'Большие окна и около 24 мест.'}})
    : json({poi_id:'p2',photos:[],status:'no_photos',checked_at:'2026-10-18T09:00:00Z'}));
  await tick();await tick();
  assert.equal(b.photos.length,2);
  assert.match(b.photos[0].url,/\/places\/p1\/photos$/);assert.equal(b.photos[0].body.lang,'ru');
  const [c1,c2]=b.w.document.querySelectorAll('.rec');
  assert.equal(c1.querySelectorAll('.ph img').length,1);
  assert.match(c1.querySelector('.photos').textContent,/По фото: Большие окна и около 24 мест\./);
  assert.match(c1.querySelector('.photos').textContent,/много дневного света.*детской зоны не видно.*около 24 мест.*средний размер.*дерево и растения/s);
  assert.match(c1.querySelector('.photos').textContent,/Ann <b>X<\/b>, CC BY-SA 4\.0/);
  assert.match(c2.querySelector('.photos').textContent,/Фото этого места пока нет/);
});

test('answers come from the checked database with AI; the 2GIS catalog only from its own button',async t=>{
  const b=await boot(t);b.click('#goBtn');await tick();
  assert.equal(b.requests[0].body.source,'local');
  b.requests[0].resolve(json({...answer('local'),recommendations:[rec('p1','Drinkit')]}));await tick();
  b.click('#catalogBtn');await tick();
  assert.equal(b.requests[1].body.source,'2gis');assert.equal(b.requests[1].body.cursor,undefined);
  b.requests[1].resolve(json({...answer('catalog'),source:'2gis',recommendations:[rec('2gis_1','Coffee BOOM')]}));await tick();
  assert.match(b.w.document.querySelector('#results').textContent,/Coffee BOOM/);
  assert.equal(b.w.document.querySelector('#catalogBtn'),null);
});
const nearbyPlace = (id,name,eligible=true) => ({poi_id:id,name,category:'coffee',coords:{lat:51.128,lon:71.43},distance_m:100,walk_min:2,address:'Test address',rating:4.8,eligible,excluded_because:eligible?null:'closed',links:{'2gis':'https://2gis.kz/astana/firm/123'}});
test('nearby list contains unselected and closed places; next page appends without duplicates', async t=>{
  const b=await boot(t);b.click('#goBtn');await tick();
  b.requests[0].resolve(json({...answer('FIRST'),source:'2gis',next_cursor:'page2',nearby_places:[nearbyPlace('a','Espresso Day'),nearbyPlace('b','Coffee Boom',false)]}));await tick();
  assert.equal(b.w.document.querySelectorAll('.nearby-place').length,2);
  assert.match(b.w.document.querySelector('#nearbyPlaces').textContent,/Coffee Boom/);
  assert.match(b.w.document.querySelector('#nearbyPlaces').textContent,/закрыто в это время/);
  b.click('#nextPlacesBtn');await tick();
  b.requests[1].resolve(json({...answer('SECOND'),source:'2gis',nearby_places:[nearbyPlace('b','Coffee Boom',false),nearbyPlace('c','New cafe')]}));await tick();
  assert.equal(b.w.document.querySelectorAll('.nearby-place').length,3);
  assert.match(b.w.document.querySelector('#nearbyPlaces').textContent,/Espresso Day/);
  assert.equal(b.w.document.querySelector('#nextPlacesBtn'),null);
  b.click('#goBtn');await tick();
  b.requests[2].resolve(json({...answer('NEW SEARCH'),source:'2gis',nearby_places:[nearbyPlace('d','Different place')]}));await tick();
  assert.equal(b.w.document.querySelectorAll('.nearby-place').length,1);
});
test('provider quota error preserves the accumulated catalog for retry',async t=>{
  const b=await boot(t);b.click('#goBtn');await tick();
  b.requests[0].resolve(json({...answer('KEEP'),source:'2gis',next_cursor:'page2',nearby_places:[nearbyPlace('a','Espresso Day')]}));await tick();
  b.click('#nextPlacesBtn');await tick();
  b.requests[1].resolve(json({...answer('LIMIT'),source:'2gis',source_error:'twogis_local_limit'}));await tick();
  assert.match(b.w.document.querySelector('#nearbyPlaces').textContent,/Espresso Day/);
  assert.equal(b.w.document.querySelector('#nextPlacesBtn').disabled,false);
});
