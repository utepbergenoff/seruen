const {test}=require('node:test');
const assert=require('node:assert/strict');
const {boot}=require('./helpers.cjs');
const FX=require('./fixtures/feature_examples.json');
const clone=x=>JSON.parse(JSON.stringify(x)), json=x=>({ok:true,json:async()=>x});
const settle=async()=>{for(let i=0;i<8;i++)await new Promise(r=>setImmediate(r));};
const opts={healthData:{...FX.health_with_features,features:{...FX.health_with_features.features,winter_plan:1,meet_halfway:1,city_history:1}},atmos:FX.atmosphere_examples,build:FX.build_ok};
const change=(b,s,value)=>{const e=b.w.document.querySelector(s);e.value=value;e.dispatchEvent(new b.w.Event('change'));};
async function search(b){b.click('#goBtn');await settle();b.requests.at(-1).resolve(json(clone(FX.recommend_normal)));await settle();}
function active(b){b.w.SeruenFeatures.startWalk(b.w.SeruenFeatures.planView(clone(FX.build_ok),{location:{lat:51.128,lon:71.43},query:'coffee',context:{lang:'ru',time_budget_min:90}}),null);}

for(const mode of ['place','return','destination']) test(`context is the only finish choice: ${mode}`,async t=>{
 const b=await boot(t,opts);await search(b);change(b,'#finishMode',mode);
 if(mode==='destination'){
  b.click('#pickFinish');const loc=clone(b.w.SeruenApp.state.loc);
  assert.equal(b.w.SeruenExt.onMapClick({latlng:{lat:51.1401234,lng:71.4401234}}),true);
  assert.deepEqual(clone(b.w.SeruenApp.state.loc),loc);
  const pin=b.pins.find(p=>p.options.title==='Финиш');assert.ok(pin&&b.layers.has(pin));
 }
 b.click('#startWalkBtn');await settle();
 assert.equal(b.builds.length,1);const body=b.builds[0];
 assert.equal(body.finish_mode,mode==='return'?'return':'destination');
 assert.equal(body.destination?.lat,mode==='return'?undefined:mode==='destination'?51.14:FX.recommend_normal.recommendations[0].coords.lat);
 assert.deepEqual(body.stop_ids,[FX.recommend_normal.recommendations[0].poi_id]);
 assert.equal(b.w.document.querySelector('#routeSetup'),null);
});

test('missing custom finish keeps existing route and asks to choose a visible map point',async t=>{
 const b=await boot(t,opts);await search(b);active(b);const before=JSON.stringify(b.w.SeruenFeatures.walk.plan);
 b.click('#walkClose');change(b,'#finishMode','destination');b.click('#startWalkBtn');await settle();
 assert.equal(b.builds.length,0);assert.equal(JSON.stringify(b.w.SeruenFeatures.walk.plan),before);
 assert.equal(b.w.document.querySelector('#finishMapHint').hidden,false);
});

test('a response silently omitting requested places cannot replace the current walk',async t=>{
 const b=await boot(t,opts);await search(b);active(b);
 const before=JSON.stringify(b.w.SeruenFeatures.walk.plan);
 b.click('#walkClose');b.click('#startWalkBtn');await settle();
 assert.equal(JSON.stringify(b.w.SeruenFeatures.walk.plan),before);
 assert.match(b.w.document.querySelector('#saveWalkMsg').textContent,/не проходит проверку/);
});

test('walking focuses panel; browsing and search are explicit and preserve goal',async t=>{
 const b=await boot(t,opts);await search(b);active(b);const doc=b.w.document;
 assert.ok(doc.body.classList.contains('walk-active'));assert.ok(!doc.body.classList.contains('walk-browse'));
 assert.match(doc.querySelector('#walk').textContent,/Финиш/);b.click('#walkClose');
 assert.ok(doc.body.classList.contains('walk-browse'));assert.ok(!doc.body.classList.contains('walk-search'));
 b.click('#walkSearch');assert.ok(doc.body.classList.contains('walk-search'));
 b.click('#walkResume');assert.ok(!doc.body.classList.contains('walk-browse'));b.click('#walkEnd');
 assert.ok(!doc.body.classList.contains('walk-active'));assert.ok(!doc.body.classList.contains('walk-search'));
});

test('late replan after moving location cannot insert a stop for the old position',async t=>{
 const b=await boot(t,opts);active(b);const before=JSON.stringify(b.w.SeruenFeatures.walk.plan);
 b.click('[data-ch="cold"]');await settle();b.w.SeruenApp.state.loc={lat:51.14,lon:71.44,source:'map'};
 b.replans[0].resolve(json(clone(FX.build_ok)));await settle();
 assert.equal(JSON.stringify(b.w.SeruenFeatures.walk.plan),before);assert.equal(b.w.document.querySelector('#applyWalkProposal'),null);
});

test('provider hours are visible with date, provenance and caution; HTML cannot execute',async t=>{
 const b=await boot(t,opts), A=b.w.SeruenApp;
 const el=b.w.document.createElement('div');el.innerHTML=A.statusPill({state:'likely_open',source:'2gis',hours:'Mo 09:00-18:00; Tu off',today_hours:'09:00–18:00',for_date:'2026-10-19',source_url:'https://2gis.kz/astana/firm/123',schedule_note:'<img src=x onerror=alert(1)>'});
 assert.match(el.textContent,/09:00–18:00/);assert.match(el.textContent,/Источник: 2ГИС/);assert.match(el.textContent,/Может отличаться/);
 assert.equal(el.querySelector('img'),null);assert.equal(el.querySelector('a').hostname,'2gis.kz');
 el.innerHTML=b.w.SeruenExt.cardBadges({visit_condition:{kind:'unknown',provider_url:'https://2gis.kz/astana/firm/123',provider_attributes:['Wi-Fi','<script>bad</script>']}});
 assert.match(el.textContent,/нет цены входа/);assert.match(el.textContent,/Wi-Fi/);assert.equal(el.querySelector('script'),null);
});

test('winter search preferences survive finish confirmation without duplicate preview controls',async t=>{
 const b=await boot(t,opts);b.click('#winterMode');change(b,'#winterLimit','5');await search(b);
 assert.equal(b.w.document.querySelector('[data-plan-preview]'),null);b.click('#startWalkBtn');await settle();
 assert.equal(b.builds[0].request.preferences.winter_mode,true);assert.equal(b.builds[0].request.preferences.max_walk_min,5);
});

function meetingPlaces(){return [0,1].map(i=>({poi_id:`meeting_${i}`,name:`SYNTHETIC Meeting ${i}`,category:'coffee',coords:{lat:51.129+i*.001,lon:71.43},walk_min:[3,4],difference_min:1,
 open_status:{state:'unknown'},visit_condition:{kind:'unknown'},paths:[[[71.43,51.128],[71.43,51.129+i*.001]],[[71.43,51.132],[71.43,51.129+i*.001]]]}));}
async function meeting(b){b.click('[name="searchIntent"][value="meet"]');change(b,'#meetPreset','khan');b.click('#goBtn');await settle();}
test('meeting labels identify B; cards and pins select a place and back restores both choices',async t=>{
 const items=meetingPlaces(),b=await boot(t,{...opts,experiences:()=>json({items,source:'local'})});await meeting(b);
 assert.doesNotMatch(b.w.document.querySelector('#meetPreset').textContent,/Я у/);
 assert.match(b.w.document.querySelector('#meetPoint').textContent,/точка B/i);
 b.click('[data-meet-map="1"]');let cards=[...b.w.document.querySelectorAll('[data-meet-id]')];assert.deepEqual(cards.map(c=>c.hidden),[true,false]);
 b.click('#meetBack');assert.ok(cards.every(c=>!c.hidden));
 b.pins.find(p=>p.options.title==='SYNTHETIC Meeting 0').fire('click');assert.deepEqual(cards.map(c=>c.hidden),[false,true]);
});

test('meeting route overview uses selected venue and never has a meaningless step slider',async t=>{
 const items=meetingPlaces(),p=clone(FX.build_ok);p.stops=[{...p.stops[0],poi_id:items[1].poi_id,name:items[1].name,coords:items[1].coords}];p.state.remaining_ids=[items[1].poi_id];
 const b=await boot(t,{...opts,build:p,experiences:()=>json({items,source:'local'})});await meeting(b);
 b.click('[data-meet-route="1"]');await settle();
 assert.deepEqual(b.builds[0].stop_ids,[items[1].poi_id]);assert.equal(b.builds[0].finish_mode,'destination');assert.equal(b.w.document.querySelector('#previewStep'),null);
 assert.ok(b.w.document.body.classList.contains('route-review-open'));
 assert.ok(b.w.document.querySelector('#previewStart'));b.click('#previewStart');assert.equal(b.w.SeruenFeatures.walk.plan.stops[0].poi_id,items[1].poi_id);
 assert.equal(b.w.document.body.classList.contains('route-review-open'),false);
});

test('stale meeting route overview refuses start after a minute',async t=>{
 const items=meetingPlaces(),p=clone(FX.build_ok);p.stops=[{...p.stops[0],poi_id:items[0].poi_id,coords:items[0].coords}];
 const b=await boot(t,{...opts,build:p,experiences:()=>json({items,source:'local'})});await meeting(b);b.click('[data-meet-route="0"]');await settle();
 const now=b.w.Date.now();b.w.Date.now=()=>now+61000;b.click('#previewStart');assert.equal(b.w.SeruenFeatures.walk,null);assert.match(b.w.document.querySelector('#experienceMessage').textContent,/заново/);
});
