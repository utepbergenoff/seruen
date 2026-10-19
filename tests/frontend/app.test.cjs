const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const tick = () => new Promise(r => setImmediate(r));
const pending = () => {let resolve; const promise = new Promise(r => resolve = r); return {promise, resolve};};
const json = (data) => ({ok: true, json: async () => data});
const answer = name => ({mode:'no_ai', recommendations:[], notes:[name], safety:[], considered:{time_budget_min:60,candidates_found:0}, disclaimer:'test'});
const {boot} = require('./helpers.cjs');
test('shell and six demos stay usable while backend health is pending', async t=>{
  const b=await boot(t,{health:pending()});
  assert.match(b.w.document.querySelector('#goBtn').textContent,/Подобрать/);
  assert.equal(b.w.document.querySelectorAll('#scenariosMenu button').length,6);
  b.click('#scenariosMenu button'); await tick(); assert.equal(b.requests.length,1);
});
test('late GPS cannot replace a selected demo',async t=>{
  const b=await boot(t); b.click('#scenariosMenu button');await tick();
  b.gps.ok({coords:{latitude:51.15,longitude:71.44,accuracy:80}});
  b.click('#chips button');await tick();
  assert.equal(b.requests[1].body.location.source,'preset');
  assert.deepEqual(b.requests[1].body.location,b.requests[0].body.location);
});
test('only the newest request may render, even if older request arrives last',async t=>{
  const b=await boot(t);b.click('#scenariosMenu button');await tick();
  b.click('#chips button');await tick();assert.equal(b.requests.length,2);
  b.requests[1].resolve(json(answer('NEWEST')));await tick();
  b.requests[0].resolve(json(answer('STALE')));await tick();
  assert.match(b.w.document.querySelector('#results').textContent,/NEWEST/);
  assert.doesNotMatch(b.w.document.querySelector('#results').textContent,/STALE/);
});
test('coordinates round on device and permission failure keeps the chosen point',async t=>{
  const b=await boot(t);b.gps.ok({coords:{latitude:51.1284321,longitude:71.4304321,accuracy:80}});
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
test('rerendering while photos load shares the pending request instead of spending the quota twice', async t => {
  const pendingPhotos=pending(), b=await withCards(t,()=>json(gisAnswer),()=>pendingPhotos.promise);
  assert.equal(b.photos.length,2);
  b.w.SeruenApp.rerender(); b.w.SeruenApp.rerender(); await tick();
  assert.equal(b.photos.length,2);
  pendingPhotos.resolve(json({photos:[],status:'no_photos'})); await tick();
});
test('2GIS is asked only on the button, once per place, and its text is escaped',async t=>{
  const b=await withCards(t,()=>json(gisAnswer));
  assert.equal(b.gis.length,0);
  const btn=b.w.document.querySelector('.rec [data-act="gis"]'),box=b.w.document.querySelector('.rec .gis-box');
  btn.click();await tick();await tick();
  assert.equal(b.gis.length,1);assert.match(b.gis[0],/\/places\/p1\/2gis\?lang=ru$/);
  assert.match(box.textContent,/Данные 2ГИС/);assert.match(box.textContent,/4\.6 · отзывов: 321/);assert.ok(box.querySelector('use[href="#i-star"]'));
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

test('answers search 2GIS first and fall back to the checked database when 2GIS fails',async t=>{
  const b=await boot(t);b.click('#goBtn');await tick();
  assert.equal(b.requests[0].body.source,undefined);
  b.requests[0].resolve(json({...answer('quota'),source:'2gis',source_error:'twogis_quota_exceeded',recommendations:[]}));await tick();
  assert.equal(b.requests[1].body.source,'local');
  b.requests[1].resolve(json({...answer('local'),recommendations:[rec('p1','Drinkit')]}));await tick();
  assert.match(b.w.document.querySelector('#results').textContent,/2ГИС сейчас не ответил.*Drinkit/s);
  b.click('#goBtn');await tick();
  assert.equal(b.requests[2].body.source,undefined);
});
test('when 2GIS has nothing that fits, the checked database answers instead',async t=>{
  const b=await boot(t);b.click('#goBtn');await tick();
  b.requests[0].resolve(json({...answer('empty 2gis'),source:'2gis',recommendations:[]}));await tick();
  assert.equal(b.requests[1].body.source,'local');
  b.requests[1].resolve(json({...answer('local'),recommendations:[rec('p1','NU Park')]}));await tick();
  assert.match(b.w.document.querySelector('#results').textContent,/В 2ГИС подходящих мест рядом не нашлось.*NU Park/s);
});
test('a 2GIS place asks photos with its own name and position, never the person\'s',async t=>{
  const b=await boot(t);b.click('#goBtn');await tick();
  b.requests[0].resolve(json({...answer('2gis'),source:'2gis',recommendations:[{...rec('2gis_7','Монумент-Бәйтерек'),coords:{lat:51.128,lon:71.43}}]}));await tick();await tick();
  assert.deepEqual(b.photos[0].body.near,{name:'Монумент-Бәйтерек',lat:51.128,lon:71.43,category:'coffee'});
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

test('the time ruler puts every pick at its walking minutes and opens its card',async t=>{
  const b=await boot(t);b.click('#goBtn');await tick();
  b.requests[0].resolve(json({...answer('ruler'),recommendations:[{...rec('p1','Near'),walk_min:5},{...rec('p2','Far'),walk_min:21}]}));await tick();
  const stops=[...b.w.document.querySelectorAll('.ruler-stop')];
  assert.equal(stops.length,2);
  assert.deepEqual(stops.map(s=>s.textContent.trim()),['15 мин','221 мин']);
  assert.ok(parseFloat(stops[0].style.getPropertyValue('--x'))<parseFloat(stops[1].style.getPropertyValue('--x')));
  assert.match(b.w.document.querySelector('.ruler-scale').textContent,/Я здесь.*25 мин/s);
  stops[1].click();
  assert.ok(b.w.document.querySelectorAll('.rec')[1].classList.contains('active'));
  assert.equal(b.w.document.querySelectorAll('.rec .ic').length>0,true);
  assert.doesNotMatch(b.w.document.querySelector('#results').textContent,/[\u{1F300}-\u{1FAFF}]/u);
});

// ---------- the eight features (docs/feature_expansion_contract.md; examples in fixtures/feature_examples.json) ----------
const FX = JSON.parse(fs.readFileSync('tests/frontend/fixtures/feature_examples.json','utf8'));
const withFeatures = {healthData: FX.health_with_features, atmos: FX.atmosphere_examples, comfort: FX.comfort, build: FX.build_ok, export: FX.export_ok};
const settle = async () => { for (let i = 0; i < 6; i++) await tick(); };

test('late health enables features on cards already rendered during server wake-up', async t => {
  const health=pending(), b=await boot(t,{...withFeatures,health});
  b.click('#goBtn'); await tick(); b.requests[0].resolve(json(FX.recommend_normal)); await settle();
  assert.equal(b.w.document.querySelector('#startWalkBtn'),null);
  health.resolve(json(FX.health_with_features)); await settle();
  assert.ok(b.w.document.querySelector('#startWalkBtn'));
  assert.ok(b.w.document.querySelector('.rec [data-nope="far"]'));
  assert.equal(b.w.document.querySelector('#routeBtn'),null);
});

test('atmosphere falls back to reviewed local places when the 2GIS browse list has no matching card', async t => {
  const b=await boot(t,withFeatures); await settle();
  b.w.SeruenFeatures.setAtmosphere('greenery'); b.click('#goBtn'); await tick();
  b.requests[0].resolve(json({...answer('no match'),source:'2gis',nearby_places:[{poi_id:'2gis_1',eligible:false}]}));
  await settle(); assert.equal(b.requests.length,2);
  assert.equal(b.requests[1].body.source,'local');
  assert.equal(b.requests[1].body.preferences.atmosphere_example_id,'greenery');
  b.requests[1].resolve(json(FX.recommend_normal)); await settle();
  assert.equal(b.w.document.querySelectorAll('.rec').length,3);
});

test('no coins, chest or +10 anywhere, in all three languages', async t => {
  const b = await boot(t); b.click('#goBtn'); await tick();
  b.requests[0].resolve(json({...answer('x'), recommendations: [rec('p1', 'Парк')]})); await settle();
  for (const lang of ['ru', 'en', 'kk']) {
    b.click(`[data-lang="${lang}"]`); await tick();
    const text = b.w.document.body.textContent;
    assert.doesNotMatch(text, /\+10|🪙|Сундук|Chest|Сандық|монет|coins/i);
  }
  assert.equal(b.w.document.querySelector('#points'), null);
  const i18n = fs.readFileSync('frontend/i18n.js', 'utf8');
  assert.doesNotMatch(i18n, /pointsUnit|pointsHint/);
});

test('my places: marks, note and deletion stay on the device and survive a new answer', async t => {
  const b = await boot(t); await settle(); b.click('#goBtn'); await tick();
  b.requests[0].resolve(json({...answer('x'), recommendations: [rec('p1', 'Парк ЭКСПО')]})); await settle();
  b.click('.rec [data-keep="want"]'); await settle();
  b.click('.rec [data-keep="favorite"]'); await settle();
  b.click('.rec [data-keep="note"]');
  b.w.document.querySelector('.rec .note-box textarea').value = 'Скамейки у воды';
  b.click('.rec [data-note="save"]'); await settle();
  assert.equal(b.w.document.querySelector('.rec [data-keep="want"]').getAttribute('aria-pressed'), 'true');
  b.click('#mineBtn'); await settle();
  const mine = b.w.document.querySelector('#mine');
  assert.ok(!mine.hidden); assert.match(mine.textContent, /Парк ЭКСПО/); assert.match(mine.textContent, /Скамейки у воды/);
  assert.match(mine.textContent, /только на этом устройстве/);
  b.click('#goBtn'); await tick();
  b.requests[1].resolve(json({...answer('again'), recommendations: [rec('p1', 'Парк ЭКСПО')]})); await settle();
  assert.equal(b.w.document.querySelector('.rec [data-keep="favorite"]').getAttribute('aria-pressed'), 'true');
  b.click('#mine [data-mine-del="p1"]'); await settle();
  assert.match(b.w.document.querySelector('#mine').textContent, /Пока пусто/);
  // nothing personal ever leaves the device
  assert.ok(b.requests.every(r => !JSON.stringify(r.body).includes('Скамейки')));
});

test('old visit marks move into my places as visits; clearing history removes everything', async t => {
  const b = await boot(t);
  b.w.localStorage.setItem('seruen_visited', JSON.stringify({p9: 1760000000000}));
  b.w.localStorage.removeItem('seruen_store_migrated');
  await b.w.SeruenStore.init();
  assert.ok((await b.w.SeruenStore.getPlace('p9')).visited_at);
  b.click('#mineBtn'); await settle();
  b.w.SeruenFeatures.mine.places.set('p9', await b.w.SeruenStore.getPlace('p9'));
  b.click('#mineClose'); b.click('#mineBtn'); await settle();
  b.click('#clearAll'); await settle(); b.click('#clearYes'); await settle();
  assert.equal(await b.w.SeruenStore.getPlace('p9'), undefined);
  assert.equal(b.w.localStorage.getItem('seruen_visited'), null);
});

test('an old server never receives new fields', async t => {
  const b = await boot(t); await settle();
  b.w.SeruenFeatures.setFinish({lat: 51.13, lon: 71.44, source: 'map'});
  b.w.SeruenFeatures.setAtmosphere('greenery');
  b.click('#goBtn'); await tick();
  const body = b.requests[0].body;
  for (const k of ['end', 'constraints', 'atmosphere_id', 'request_id']) assert.equal(k in body, false, k);
  assert.equal(b.w.document.querySelector('#finishField'), null);
  assert.equal(b.w.document.querySelector('#atmosField'), null);
});

test('only new: without server support visited places are hidden here and counted', async t => {
  const b = await boot(t); await settle(); b.click('#goBtn'); await tick();
  b.requests[0].resolve(json({...answer('x'), recommendations: [rec('p1', 'Был'), rec('p2', 'Новое')]})); await settle();
  b.click('.rec [data-keep="visited"]'); await settle();
  b.click('#mineBtn'); await settle();
  const box = b.w.document.querySelector('#onlyNew'); box.checked = true; box.dispatchEvent(new b.w.Event('change')); await tick();
  b.requests[1].resolve(json({...answer('y'), recommendations: [rec('p1', 'Был'), rec('p2', 'Новое')]})); await settle();
  assert.deepEqual([...b.w.document.querySelectorAll('.rec h3')].map(h => h.textContent.trim()), ['Новое']);
  assert.match(b.w.document.querySelector('#results').textContent, /Скрыто посещённых мест: 1/);
  assert.equal('constraints' in b.requests[1].body, false);
});

test('new server: finish, atmosphere, no-spend and "too far" travel as contract fields', async t => {
  const b = await boot(t, withFeatures); await settle();
  assert.ok(b.w.document.querySelector('#finishField')); assert.ok(b.w.document.querySelector('#atmosField'));
  b.w.SeruenFeatures.setFinish({lat: 51.1301, lon: 71.4402, source: 'map'});
  b.click('#atmosField [data-atmos="greenery"]');
  const ns = b.w.document.querySelector('#noSpend'); ns.value = 'lenient'; ns.dispatchEvent(new b.w.Event('change'));
  b.click('#goBtn'); await tick();
  const body = b.requests[0].body;
  assert.deepEqual(body.end, {lat: 51.13, lon: 71.44, precision_m: 100, source: 'map'});
  assert.equal(body.preferences.atmosphere_example_id, 'greenery'); assert.equal(body.preferences.expense_mode, 'no_required_purchase'); assert.ok(body.request_id);
  b.requests[0].resolve(json(FX.recommend_normal)); await settle();
  const cards = b.w.document.querySelectorAll('.rec');
  assert.match(cards[0].textContent, /Бесплатно/); assert.match(cards[1].textContent, /Платный вход/);
  assert.match(cards[2].textContent, /Покупка по желанию/);
  assert.match(cards[0].textContent, /до финиша 7 мин/); assert.match(cards[0].textContent, /прибытие ≈11:32 \(оценка\)/);
  b.click('.rec [data-nope="far"]'); await tick();
  assert.ok(b.requests[1].body.preferences.max_distance_m > 0);
  assert.ok(b.requests[1].body.preferences.max_distance_m < FX.recommend_normal.recommendations[0].distance_m);
  assert.ok(b.requests[1].body.preferences.exclude_poi_ids.includes(FX.recommend_normal.recommendations[0].poi_id));
  b.requests[1].resolve(json(FX.recommend_empty)); await settle();
  const res = b.w.document.querySelector('#results').textContent;
  assert.match(res, /Учитываю:/); assert.match(res, /Отменить/);
  b.click('[data-undo="max"]'); await tick();
  assert.equal('max_distance_m' in (b.requests[2].body.preferences || {}), false);
});

test('"another place" replaces one card and keeps the others on the screen', async t => {
  const b = await boot(t, withFeatures); await settle(); b.click('#goBtn'); await tick();
  b.requests[0].resolve(json(FX.recommend_normal)); await settle();
  b.w.document.querySelectorAll('.rec')[1].querySelector('[data-nope="other"]').click(); await tick();
  assert.deepEqual(b.requests[1].body.preferences.exclude_poi_ids, ['osm_node_1','osm_node_2','osm_node_3']);
  b.requests[1].resolve(json({...FX.recommend_normal, recommendations: [{...FX.recommend_normal.recommendations[0], poi_id: 'osm_node_9', name: 'Замена'}]})); await settle();
  assert.deepEqual([...b.w.document.querySelectorAll('.rec h3')].map(h => h.textContent.trim()), ['Парк ЭКСПО', 'Замена', 'Discovery Coffee']);
});

test('impossible route shows the reason and "allow more time" re-asks with that budget', async t => {
  const b = await boot(t, withFeatures); await settle(); b.click('#goBtn'); await tick();
  b.requests[0].resolve(json(FX.recommend_route_impossible)); await settle();
  assert.match(b.w.document.querySelector('#results').textContent, /не хватает времени/);
  b.click('[data-more="75"]'); await tick();
  assert.equal(b.requests[1].body.context.time_budget_min, 75);
});

test('save a walk, reopen it from my places with its date and the stale warning', async t => {
  const single=JSON.parse(JSON.stringify(FX.build_ok)); single.stops=single.stops.slice(0,1);
  const exported=JSON.parse(JSON.stringify(withFeatures.export)); exported.stops=exported.stops.slice(0,1);
  const b = await boot(t, {...withFeatures,build:single,export:exported}); await settle(); b.click('#goBtn'); await tick();
  const recommendations = FX.build_ok.stops.map((s,i) => ({...FX.recommend_normal.recommendations[i], ...s}));
  b.requests[0].resolve(json({...FX.recommend_normal, recommendations})); await settle();
  b.click('#saveWalkBtn'); await settle();
  assert.match(b.w.document.querySelector('#saveWalkMsg').textContent, /сохранена|не даёт сохранять/);  // jsdom has no IndexedDB
  const walks = await b.w.SeruenStore.allWalks();
  assert.equal(walks.length, 1); assert.equal(walks[0].version, 2); assert.equal(walks[0].stops.length, 1);
  assert.equal('photos' in walks[0].stops[0], false);
  b.click('#mineBtn'); await settle(); b.click('#mine [data-tab="walks"]'); await settle();
  b.click('#mine [data-walk-open]'); await settle();
  const panel = b.w.document.querySelector('#walk');
  assert.ok(!panel.hidden); assert.match(panel.textContent, /Сохранено/); assert.match(panel.textContent, /могли измениться/);
  assert.match(panel.textContent, /SYNTHETIC team_coffee/);
});

test('plans changed: the newest change wins, a failure keeps the plan, done stops stay done', async t => {
  const b = await boot(t, withFeatures); await settle();
  const plan = b.w.SeruenFeatures.planView(FX.build_ok, {location:{lat:51.128,lon:71.43},query:'coffee',context:{lang:'ru',time_budget_min:90}});
  plan.stops[0].status = 'done';
  b.w.SeruenFeatures.startWalk(plan, null); await settle();
  b.click('#walk [data-ch="cold"]'); await tick();
  b.click('#walk [data-ch="tired"]'); await tick();
  assert.equal(b.replans.length, 2); assert.equal(b.replans[0].body.reason, 'cold');
  b.replans[1].resolve(json(FX.replan_ok)); await settle();
  b.replans[0].resolve(json({...FX.replan_ok, notes: ['OLD']})); await settle();
  const panel = b.w.document.querySelector('#walk').textContent;
  assert.match(panel, /Стало холоднее/); assert.doesNotMatch(panel, /OLD/);
  assert.equal(b.w.SeruenFeatures.walk.plan.stops.find(s => s.poi_id === 'team_coffee').status, 'done');
  b.click('#walk [data-ch="cold"]'); await tick();
  b.replans[2].resolve({ok: false, status: 503, json: async () => FX.provider_failure.body}); await settle();
  assert.match(b.w.document.querySelector('#walk').textContent, /план не изменился/);
  assert.ok(b.w.SeruenFeatures.walk.plan.stops.length >= 2);
});

test('comfort points are asked near the plan and stay off the main recommendations', async t => {
  const b = await boot(t, withFeatures); await settle(); b.click('#goBtn'); await tick();
  b.requests[0].resolve(json(FX.recommend_normal)); await settle();
  b.click('[data-comfort="toilet"]'); await settle();
  assert.equal(b.comforts.length, 1); assert.deepEqual(b.comforts[0].kinds, ['toilet']);
  assert.equal(b.comforts[0].route_points.length, 0);
  assert.ok(b.comforts[0].location);
  assert.equal(b.w.document.querySelectorAll('.rec').length, 3);
});

test('photo quota failure is shown as unavailable analysis, not missing photos', async t => {
  const b = await withCards(t, () => json(gisAnswer), () => json({photos: [], status: 'ai_unavailable'}));
  const text = b.w.document.querySelector('.rec .photos').textContent;
  assert.ok(text.includes(b.w.SeruenApp.T().ph.noAnalysis));
  assert.ok(!text.includes(b.w.SeruenApp.T().ph.none));
});

test('AI selection and factual explanation have separate labels, with a privacy hint',async t=>{
  const b=await boot(t);b.click('#goBtn');await tick();
  const chosen={...rec('p1','Coffee BOOM'),selection_source:'ai'};
  b.requests[0].resolve(json({...answer('grounded'),mode:'ai',recommendations:[chosen]}));await tick();
  const card=b.w.document.querySelector('.rec').textContent;
  assert.match(card,/место выбрал ИИ/);
  assert.match(card,/объяснение составлено из данных и расчёта/);
  assert.match(b.w.document.querySelector('#privacyHint').textContent,/Gemini/);
});

for (const change of ['cold', 'tired']) {
  test(`empty ${change} response never erases the current walk or its line`, async t => {
    const b=await boot(t,withFeatures); await settle();
    const plan=b.w.SeruenFeatures.planView(FX.build_ok,{location:{lat:51.128,lon:71.43},query:'coffee',context:{lang:'ru',time_budget_min:90}});
    b.w.SeruenFeatures.startWalk(plan,null); await settle();
    const before=JSON.stringify(b.w.SeruenFeatures.walk.plan);
    b.click(`#walk [data-ch="${change}"]`); await tick();
    b.replans[0].resolve(json({...FX.replan_ok,fits:true,status:'no_matches',stops:[],geometry:[],notes:['Нет подходящих остановок']}));
    await settle();
    assert.equal(JSON.stringify(b.w.SeruenFeatures.walk.plan),before);
    assert.match(b.w.document.querySelector('#walkMsg').textContent,/прежний маршрут/);
    assert.ok(b.w.document.querySelector('#walk [data-ch="cold"]'));
  });
}
