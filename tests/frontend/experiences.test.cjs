const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {boot}=require('./helpers.cjs');
const FX=require('./fixtures/feature_examples.json');
const clone=x=>JSON.parse(JSON.stringify(x)), json=x=>({ok:true,json:async()=>x});
const settle=async()=>{for(let i=0;i<8;i++)await new Promise(r=>setImmediate(r));};
const base={healthData:{...FX.health_with_features,features:{...FX.health_with_features.features,city_history:1,meet_halfway:1,winter_plan:1}},atmos:FX.atmosphere_examples,build:FX.build_ok};
const req={location:{lat:51.128,lon:71.43},query:'coffee',context:{lang:'ru',time_budget_min:90}};
const active=b=>b.w.SeruenFeatures.startWalk(b.w.SeruenFeatures.planView(clone(FX.build_ok),req),null);
const change=(b,s,value)=>{const e=b.w.document.querySelector(s);e.value=value;e.dispatchEvent(new b.w.Event('change'));};

test('new sections are gated on health; old servers get no new requests',async t=>{
  const b=await boot(t);
  assert.equal(b.w.document.querySelector('#experiences').hidden,true);
  for(const lang of ['ru','en','kk']){
    b.click(`[data-lang="${lang}"]`);assert.equal(b.w.document.querySelector('[data-experience="winter"]'),null);
  }
});

test('history has real per-place Wikipedia buttons, escapes text and preserves the active walk',async t=>{
  const records=JSON.parse(fs.readFileSync('data/city_stories.json','utf8'));
  const rows=records.map(p=>({...p,...p.translations.ru,distance_m:100}));rows[0].story='<img src=x onerror=alert(1)>';
  const b=await boot(t,{...base,experiences:()=>json({items:rows})});active(b);
  const before=JSON.stringify(b.w.SeruenFeatures.walk);
  b.click('[data-experience="history"]');b.click('#historyLoad');await settle();
  const links=[...b.w.document.querySelectorAll('#experienceResult a')].filter(a=>a.href.includes('wikipedia.org'));
  assert.equal(links.length,records.length * 2 - 3);assert.equal(new Set(links.map(a=>a.href)).size,records.length);
  assert.ok(links.every(a=>a.target==='_blank'&&a.rel.includes('noreferrer')));
  assert.equal(b.w.document.querySelector('#experienceResult img'),null);
  b.click('[data-story="0"]');b.click('#experienceClose');
  assert.equal(JSON.stringify(b.w.SeruenFeatures.walk),before);
});

test('meeting map selection does not move first point; sends only rounded anonymous second point',async t=>{
  let body;
  const b=await boot(t,{...base,experiences:(url,p)=>{body=p;return json({items:[]});}});
  const first=JSON.stringify(b.w.SeruenApp.state.loc);
  b.click('[data-experience="meet"]');b.click('#meetPick');
  assert.equal(b.w.SeruenExt.onMapClick({latlng:{lat:51.13212345,lng:71.40398765}}),true);
  assert.equal(JSON.stringify(b.w.SeruenApp.state.loc),first);
  b.click('#meetFind');await settle();
  assert.deepEqual(body.second_location,{lat:51.132,lon:71.404,precision_m:100,source:'map'});
  assert.equal(body.request.context.lang,'ru');assert.ok(!body.request.end);
  assert.doesNotMatch(JSON.stringify(b.w.localStorage),/51\.132|71\.404/);
  assert.match(b.w.document.querySelector('#experienceMessage').textContent,/для обоих нет/);
});

test('late meeting answer after changing participant cannot replace new inputs',async t=>{
  let resolve;
  const b=await boot(t,{...base,experiences:()=>new Promise(r=>resolve=r)});
  b.click('[data-experience="meet"]');change(b,'#meetPreset','khan');b.click('#meetFind');await settle();
  change(b,'#meetPreset','expo');resolve(json({items:[{name:'OLD RESULT'}]}));await settle();
  assert.doesNotMatch(b.w.document.querySelector('#experienceResult').textContent,/OLD RESULT/);
});

test('preview steps do not move location, complete stops, or replace current walk',async t=>{
  const b=await boot(t,base);active(b);
  const before=JSON.stringify(b.w.SeruenFeatures.walk),loc=JSON.stringify(b.w.SeruenApp.state.loc);
  b.click('[data-experience="preview"]');b.click('#previewBuild');await settle();
  assert.ok(b.w.document.querySelector('#previewStep'));
  b.click('#previewNext');assert.match(b.w.document.querySelector('#previewStage').textContent,new RegExp(FX.build_ok.stops[0].name));
  b.click('#previewNext');b.click('#previewBack');
  assert.equal(JSON.stringify(b.w.SeruenFeatures.walk),before);
  assert.equal(JSON.stringify(b.w.SeruenApp.state.loc),loc);
  assert.equal(b.w.document.querySelector('#previewStart'),null);
  b.click('#experienceClose');assert.equal(JSON.stringify(b.w.SeruenFeatures.walk),before);
});

test('winter response is a preview until explicit start, and failures preserve the current walk',async t=>{
  let payload;
  const b=await boot(t,{...base,experiences:(url,p)=>{payload=p;return json(FX.build_ok);}});active(b);
  const old=JSON.stringify(b.w.SeruenFeatures.walk);
  b.click('[data-experience="winter"]');b.click('#winterBuild');await settle();
  assert.equal(payload.max_outdoor_min,10);assert.ok(!payload.plan.request.context.weather);
  assert.equal(JSON.stringify(b.w.SeruenFeatures.walk),old);
  assert.ok(b.w.document.querySelector('#previewStart'));
  b.click('#previewStart');assert.equal(b.w.document.querySelector('#experienceBody').hidden,true);
  assert.equal(b.w.SeruenFeatures.walk.plan.server.status,'ok');
});

test('impossible winter never replaces the current goal',async t=>{
  const b=await boot(t,{...base,experiences:()=>json({...clone(FX.build_ok),fits:false,status:'impossible'})});active(b);
  const old=JSON.stringify(b.w.SeruenFeatures.walk);
  b.click('[data-experience="winter"]');b.click('#winterBuild');await settle();
  assert.equal(b.w.document.querySelector('#previewStart'),null);
  assert.match(b.w.document.querySelector('#experienceMessage').textContent,/Прежний маршрут сохранён/);
  assert.equal(JSON.stringify(b.w.SeruenFeatures.walk),old);
});

test('new sections have labels in all languages and satellite does not upscale beyond zoom14',async t=>{
  const b=await boot(t,base);
  for(const lang of ['en','kk','ru']){
    b.click(`[data-lang="${lang}"]`);assert.equal(b.w.document.querySelectorAll('[data-experience]').length,4);
    b.click('[data-experience="meet"]');assert.ok(b.w.document.querySelector('#meetFind').textContent.trim());b.click('#experienceClose');
  }
  change(b,'#mapMode','satellite');assert.equal(b.w.SeruenApp.map.maxZoom,14);assert.equal(b.tiles.at(-1).options.maxZoom,14);
  assert.equal(b.w.document.querySelector('#mapDetailBtn').hidden,false);
  b.click('#mapDetailBtn');assert.equal(b.w.SeruenApp.map.maxZoom,19);assert.equal(b.w.SeruenApp.state.mapMode,'streets');
});

test('Wikipedia links follow object ID or close exact-name match, never a similarly named coffee shop',async t=>{
  const data=JSON.parse(fs.readFileSync('data/city_stories.json','utf8'));
  const b=await boot(t,{...base,stories:data});await settle();
  const story=data[0], ext=b.w.SeruenExt;
  assert.match(ext.cardExtras({poi_id:story.poi_id}),/wikipedia\.org/);
  assert.match(ext.selectedPlaceActions({poi_id:'2gis_actual',name:story.aliases[0]+', monument',coords:story.coords}),/wikipedia\.org/);
  assert.doesNotMatch(ext.selectedPlaceActions({poi_id:'2gis_coffee',name:'Baiterek Coffee',coords:story.coords}),/wikipedia\.org/);
  assert.doesNotMatch(ext.selectedPlaceActions({poi_id:'far_away',name:story.aliases[0],coords:{lat:51.2,lon:71.6}}),/wikipedia\.org/);
});

test('preview older than sixty seconds requires rechecking before start',async t=>{
  const b=await boot(t,{...base,experiences:()=>json(clone(FX.build_ok))});active(b);
  const old=JSON.stringify(b.w.SeruenFeatures.walk);
  b.click('[data-experience="winter"]');b.click('#winterBuild');await settle();
  const now=b.w.Date.now();b.w.Date.now=()=>now+61000;
  b.click('#previewStart');assert.equal(JSON.stringify(b.w.SeruenFeatures.walk),old);
  assert.match(b.w.document.querySelector('#experienceMessage').textContent,/заново/);
});
