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
  const before=JSON.stringify(b.w.SeruenFeatures.walk.plan),loc=JSON.stringify(b.w.SeruenApp.state.loc);
  b.click('#showCityStories');
  const pins=b.pins.filter(p=>p.options?.icon?.html.includes('story-pin'));
  assert.equal(pins.length,records.length);
  const urls=new Set();
  for (const pin of pins) {
    pin.fire('click');
    const link=[...b.w.document.querySelectorAll('#experienceResult a')].find(a=>a.textContent.includes('Узнать больше'));
    if(!link) {assert.ok(b.w.document.querySelector("#experienceResult a"));continue;}
    assert.equal(link.target,'_blank');assert.ok(link.rel.includes('noreferrer'));urls.add(link.href);
    assert.equal(b.w.document.querySelector('#experienceResult img'),null);
  }
  assert.equal(urls.size,records.filter(p=>p.wikipedia_url).length);b.click('#experienceClose');
  assert.equal(JSON.stringify(b.w.SeruenFeatures.walk.plan),before);
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

test('meeting places show what the place is, its photos with what Gemini sees, and a 2GIS link',async t=>{
  const item={poi_id:'2gis_70000001072135261',name:'Coffee BOOM',category:'coffee',rating:4.7,address:'проспект Мангилик Ел, 55/1',
    coords:{lat:51.0889,lon:71.4156},walk_min:[5,9],difference_min:4,max_walk_min:9,stay_min:30,
    open_status:{state:'likely_open',confidence:'medium'},visit_condition:{kind:'optional_purchase',note:'можно сидеть без заказа'},
    paths:[[[71.416,51.089],[71.4156,51.0889]],[[71.404,51.133],[71.4156,51.0889]]],sources:['2gis']};
  const photo={poi_id:item.poi_id,status:'ok',analysis_source:'gemini',
    photos:[{url:'https://example.test/img/places/c/team-coffeeboom-expo-1.jpg',source:'team'}],
    analysis:{summary:'Светлый зал, много мест у окон'}};
  const b=await boot(t,{...base,experiences:()=>json({status:'ok',items:[item],source:'2gis'}),photos:()=>json(photo)});
  b.click('[name="searchIntent"][value="meet"]');change(b,'#meetPreset','khan');b.click('#goBtn');await settle();
  const card=b.w.document.querySelector('.meet-place');
  assert.ok(card);assert.match(card.textContent,new RegExp(b.w.I18N.ru.cats.coffee||'coffee'));
  assert.match(card.textContent,/проспект Мангилик Ел, 55\/1/);assert.match(card.textContent,/4\.7/);
  assert.equal(b.photos.length,1);
  assert.deepEqual(b.photos[0].body.near,{name:'Coffee BOOM',lat:51.0889,lon:71.4156,category:'coffee'});
  assert.ok(card.querySelector('.ph-strip img'));
  assert.match(card.querySelector('.photos').textContent,/Светлый зал, много мест у окон/);
  assert.match(card.querySelector('a[href*="2gis.kz"]').href,/Coffee%20BOOM/);
});

test('a meeting photo answer arriving after leaving the meeting view changes nothing',async t=>{
  let resolve;
  const item={poi_id:'osm_node_1',name:'Парк',category:'park',coords:{lat:51.13,lon:71.41},walk_min:[5,6],difference_min:1,max_walk_min:6,
    stay_min:30,open_status:{state:'unknown'},visit_condition:{kind:'free'},paths:[[[71.41,51.13]],[[71.41,51.13]]],sources:['osm']};
  const b=await boot(t,{...base,experiences:()=>json({status:'ok',items:[item],source:'local'}),photos:()=>new Promise(r=>resolve=r)});
  b.click('[name="searchIntent"][value="meet"]');change(b,'#meetPreset','khan');b.click('#goBtn');await settle();
  b.click('#experienceClose');resolve(json({poi_id:'osm_node_1',status:'ok',photos:[{url:'https://example.test/x.jpg',source:'commons'}],analysis:{summary:'LATE'}}));await settle();
  assert.doesNotMatch(b.w.document.body.innerHTML,/LATE/);
});
