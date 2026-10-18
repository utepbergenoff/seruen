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
async function search(b) {
  b.click('#goBtn');await settle();b.requests.at(-1).resolve(json(clone(FX.recommend_normal)));await settle();
}
async function winterPreview(b) {
  b.click('#winterMode');await search(b);b.click('[data-plan-preview="results"]');await settle();
}
const change=(b,s,value)=>{const e=b.w.document.querySelector(s);e.value=value;e.dispatchEvent(new b.w.Event('change'));};

test('new sections are gated on health; old servers get no new requests',async t=>{
  const b=await boot(t);
  assert.equal(b.w.document.querySelector('#experiences').hidden,true);
  for(const lang of ['ru','en','kk']){
    b.click(`[data-lang="${lang}"]`);assert.equal(b.w.document.querySelector('#winterMode'),null);assert.equal(b.w.document.querySelector('#searchModeField').hidden,true);
  }
});

test('map stories open the matching article, escape text and preserve the active walk',async t=>{
  const records=JSON.parse(fs.readFileSync('data/city_stories.json','utf8'));
  const rows=records.map(p=>({...p,...p.translations.ru,distance_m:100}));rows[0].translations.ru.story='<img src=x onerror=alert(1)>';
  const b=await boot(t,{...base,stories:rows});active(b);
  const before=JSON.stringify(b.w.SeruenFeatures.walk),loc=JSON.stringify(b.w.SeruenApp.state.loc);
  b.click('#showCityStories');
  const pins=b.pins.filter(p=>p.options?.icon?.html.includes('story-pin'));
  assert.equal(pins.length,20);
  const urls=new Set();
  for (const pin of pins) {
    pin.fire('click');
    const link=[...b.w.document.querySelectorAll('#experienceResult a')].find(a=>a.textContent.includes('Узнать больше'));
    assert.ok(link);assert.equal(link.target,'_blank');assert.ok(link.rel.includes('noreferrer'));urls.add(link.href);
    assert.equal(b.w.document.querySelector('#experienceResult img'),null);
  }
  assert.equal(urls.size,20);b.click('#experienceClose');
  assert.equal(JSON.stringify(b.w.SeruenFeatures.walk),before);
  assert.equal(JSON.stringify(b.w.SeruenApp.state.loc),loc);
});

test('meeting map selection does not move first point; sends only rounded anonymous second point',async t=>{
  let body;
  const b=await boot(t,{...base,experiences:(url,p)=>{body=p;return json({items:[]});}});
  const first=JSON.stringify(b.w.SeruenApp.state.loc);
  b.click('[name="searchIntent"][value="meet"]');b.click('#meetPick');
  assert.equal(b.w.SeruenExt.onMapClick({latlng:{lat:51.13212345,lng:71.40398765}}),true);
  assert.equal(JSON.stringify(b.w.SeruenApp.state.loc),first);
  b.click('#goBtn');await settle();
  assert.deepEqual(body.second_location,{lat:51.132,lon:71.404,precision_m:100,source:'map'});
  assert.equal(body.request.context.lang,'ru');assert.ok(!body.request.end);
  assert.doesNotMatch(JSON.stringify(b.w.localStorage),/51\.132|71\.404/);
  assert.match(b.w.document.querySelector('#experienceMessage').textContent,/для обоих нет/);
});

test('late meeting answer after changing participant cannot replace new inputs',async t=>{
  let resolve;
  const b=await boot(t,{...base,experiences:()=>new Promise(r=>resolve=r)});
  b.click('[name="searchIntent"][value="meet"]');change(b,'#meetPreset','khan');b.click('#goBtn');await settle();
  change(b,'#meetPreset','expo');resolve(json({items:[{name:'OLD RESULT'}]}));await settle();
  assert.doesNotMatch(b.w.document.querySelector('#experienceResult').textContent,/OLD RESULT/);
});

test('preview steps do not move location, complete stops, or replace current walk',async t=>{
  const b=await boot(t,base);active(b);
  const before=JSON.stringify(b.w.SeruenFeatures.walk),loc=JSON.stringify(b.w.SeruenApp.state.loc);
  b.click('[data-plan-preview="active"]');await settle();
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
  await winterPreview(b);
  assert.equal(payload.max_outdoor_min,10);assert.ok(!payload.plan.request.context.weather);
  assert.equal(JSON.stringify(b.w.SeruenFeatures.walk),old);
  assert.ok(b.w.document.querySelector('#previewStart'));
  b.click('#previewStart');assert.equal(b.w.document.querySelector('#experienceBody').hidden,true);
  assert.equal(b.w.SeruenFeatures.walk.plan.server.status,'ok');
});

test('impossible winter never replaces the current goal',async t=>{
  const b=await boot(t,{...base,experiences:()=>json({...clone(FX.build_ok),fits:false,status:'impossible'})});active(b);
  const old=JSON.stringify(b.w.SeruenFeatures.walk);
  await winterPreview(b);
  assert.equal(b.w.document.querySelector('#previewStart'),null);
  assert.match(b.w.document.querySelector('#experienceMessage').textContent,/Прежний маршрут сохранён/);
  assert.equal(JSON.stringify(b.w.SeruenFeatures.walk),old);
});

test('new sections have labels in all languages and satellite does not upscale beyond zoom14',async t=>{
  const b=await boot(t,base);
  for(const lang of ['en','kk','ru']){
    b.click(`[data-lang="${lang}"]`);assert.equal(b.w.document.querySelectorAll('[data-experience]').length,0);assert.equal(b.w.document.querySelectorAll('[name="searchIntent"]').length,2);
    b.click('[name="searchIntent"][value="meet"]');assert.equal(b.w.document.querySelector('#goBtn').textContent,b.w.SeruenExperienceText[lang].find);b.click('[name="searchIntent"][value="walk"]');
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
  await winterPreview(b);
  const now=b.w.Date.now();b.w.Date.now=()=>now+61000;
  b.click('#previewStart');assert.equal(JSON.stringify(b.w.SeruenFeatures.walk),old);
  assert.match(b.w.document.querySelector('#experienceMessage').textContent,/заново/);
});

test('one search form switches to meeting and back without losing recommendations or the active walk',async t=>{
  const b=await boot(t,{...base,experiences:()=>json({items:[]})});await search(b);active(b);
  const results=b.w.document.querySelector('#results').innerHTML,walk=JSON.stringify(b.w.SeruenFeatures.walk);
  b.click('[name="searchIntent"][value="meet"]');change(b,'#meetPreset','khan');b.click('#goBtn');await settle();
  assert.equal(b.requests.length,1); // Meeting uses /meet/search, never a second recommendation request.
  assert.equal(b.w.document.querySelector('#results').hidden,true);
  b.click('#experienceClose');
  assert.equal(b.w.document.querySelector('#results').hidden,false);
  assert.equal(b.w.document.querySelector('#results').innerHTML,results);
  assert.equal(JSON.stringify(b.w.SeruenFeatures.walk),walk);
  assert.equal(b.w.document.querySelector('#goBtn').textContent,b.w.I18N.ru.go);
});

test('winter is part of the normal search and its preview; disabling it removes new-request preferences',async t=>{
  const calls=[];
  const b=await boot(t,{...base,experiences:(url,p)=>{calls.push({url,p});return json(clone(FX.build_ok));}});
  b.click('#winterMode');change(b,'#winterLimit','5');await search(b);
  const prefs=b.requests[0].body.preferences;
  assert.equal(prefs.indoor_only,true);assert.equal(prefs.winter_mode,true);assert.equal(prefs.max_walk_min,5);
  b.click('[data-plan-preview="results"]');await settle();
  assert.match(calls[0].url,/\/plans\/winter$/);assert.equal(calls[0].p.max_outdoor_min,5);
  assert.equal(b.w.SeruenFeatures.walk,null);
  b.click('#winterMode');await search(b);
  assert.equal(b.requests[1].body.preferences?.winter_mode,undefined);
});

test('preview beside the selected place targets that place, not the first recommendation',async t=>{
  const b=await boot(t,base);await search(b);
  const selected=FX.recommend_normal.recommendations[1];
  b.w.SeruenApp.markers[selected.poi_id].fire('click');
  b.click('[data-plan-preview="selected"]');await settle();
  assert.deepEqual(b.builds[0].stop_ids,[selected.poi_id]);assert.equal(b.builds[0].max_stops,1);
  assert.equal(b.w.SeruenFeatures.walk,null);
});

test('a meeting response arriving after switching back cannot erase the previous places',async t=>{
  let resolve;
  const b=await boot(t,{...base,experiences:()=>new Promise(r=>resolve=r)});await search(b);
  b.click('[name="searchIntent"][value="meet"]');change(b,'#meetPreset','khan');b.click('#goBtn');await settle();
  b.click('[name="searchIntent"][value="walk"]');
  const before=b.w.document.querySelector('#results').innerHTML;
  resolve(json({items:[{name:'STALE MEETING'}]}));await settle();
  assert.equal(b.w.document.querySelector('#experiences').hidden,true);
  assert.equal(b.w.document.querySelector('#results').innerHTML,before);
  assert.equal(b.w.document.querySelector('#goBtn').disabled,false);
});

test('meeting inputs changed mid-request invalidate the answer',async t=>{
  let resolve;
  const b=await boot(t,{...base,experiences:()=>new Promise(r=>resolve=r)});
  b.click('[name="searchIntent"][value="meet"]');change(b,'#meetPreset','khan');b.click('#goBtn');await settle();
  b.w.document.querySelector('#query').value='парк';
  resolve(json({items:[{name:'STALE COFFEE'}]}));await settle();
  assert.doesNotMatch(b.w.document.querySelector('#experienceResult').textContent,/STALE COFFEE/);
  assert.equal(b.w.document.querySelector('#goBtn').disabled,false);
});

test('opening history inside a place card does not select another place or move the map',async t=>{
  const rows=JSON.parse(fs.readFileSync('data/city_stories.json','utf8'));
  const b=await boot(t,{...base,stories:rows});
  b.click('#goBtn');await settle();
  const d=clone(FX.recommend_normal);d.recommendations[0].poi_id=rows[0].poi_id;
  b.requests[0].resolve(json(d));await settle();
  b.w.document.querySelector('.place-story summary').click();
  assert.equal(b.w.document.querySelector('.place-story').open,true);
  assert.equal(b.w.SeruenApp.state.selectedPlaceId,null);
  assert.equal(b.w.document.querySelector('#resultsOverview').hidden,false);
});

test('switching to meeting cancels a pending finish picker without changing the saved finish',async t=>{
  const b=await boot(t,base);
  b.w.SeruenFeatures.setFinish({lat:51.14,lon:71.41,source:'map'});
  b.click('#pickFinish');b.click('[name="searchIntent"][value="meet"]');
  assert.equal(b.w.SeruenExt.onMapClick({latlng:{lat:51.13,lng:71.43}}),false);
  b.click('[name="searchIntent"][value="walk"]');
  assert.equal(b.w.SeruenExt.onMapClick({latlng:{lat:51.13,lng:71.43}}),false);
  assert.equal(b.w.SeruenExt.requestExtras({}).end.lat,51.14);
});

test('choosing your own point cancels the meeting point picker',async t=>{
  const b=await boot(t,base);
  b.click('[name="searchIntent"][value="meet"]');b.click('#meetPick');
  // A failed location attempt reveals the explicit own-point fallback.
  b.click('#geoBtn');b.gps.fail({code:1});b.click('#meetPick');b.click('#geoMap');
  assert.equal(b.w.SeruenExt.onMapClick({latlng:{lat:51.13,lng:71.43}}),false);
  assert.equal(b.w.document.querySelector('#meetCancel').hidden,true);
});
