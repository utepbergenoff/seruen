const {test}=require('node:test');
const assert=require('node:assert/strict');
const {boot}=require('./helpers.cjs');
const FX=require('./fixtures/feature_examples.json');
const clone=x=>x===undefined?x:JSON.parse(JSON.stringify(x)), json=x=>({ok:true,json:async()=>x});
const settle=async()=>{for(let i=0;i<8;i++)await new Promise(r=>setImmediate(r));};
const change=(b,s,value)=>{const e=b.w.document.querySelector(s);e.value=value;e.dispatchEvent(new b.w.Event('change',{bubbles:true}));};
const visible=b=>[...b.layers].flatMap(l=>l.members?[...l.members]:[l]);
const participant=(b,name)=>visible(b).find(p=>p.options?.title===name);
const item={...clone(FX.build_ok.stops[0]),category:'coffee',walk_min:[5,9],difference_min:4,max_walk_min:9,
  paths:[[[71.430,51.128],[71.431,51.130]],[[71.404,51.133],[71.431,51.130]]],sources:['synthetic']};
const plan={...clone(FX.build_ok),stops:[item],legs:[FX.build_ok.legs[0]],
  geometry:[[71.430,51.128],[item.coords.lon,item.coords.lat]],
  state:{...clone(FX.build_ok.state),finish_mode:'destination',finish:item.coords,finish_poi_id:item.poi_id,remaining_ids:[item.poi_id]}};
const base={healthData:{...FX.health_with_features,features:{...FX.health_with_features.features,meet_halfway:1,finish_preferences:1}},
  build:plan,experiences:()=>json({status:'ok',source:'local',items:[item]})};
function chooseSecond(b){b.click('[name="searchIntent"][value="meet"]');change(b,'#meetPreset','khan');}

test('point B stays visible while meeting search loads and after a provider error or empty answer',async t=>{
  let resolve;
  const b=await boot(t,{...base,experiences:()=>new Promise(r=>resolve=r)});
  chooseSecond(b);const coords=clone(participant(b,'B').coords);
  b.click('#goBtn');await settle();assert.deepEqual(clone(participant(b,'B')?.coords),coords);
  resolve({ok:false,status:503,json:async()=>({error:{code:'twogis_access_denied'}})});await settle();
  assert.deepEqual(clone(participant(b,'B')?.coords),coords);
  b.click('#goBtn');await settle();resolve(json({status:'no_matches',source:'local',items:[]}));await settle();
  assert.deepEqual(clone(participant(b,'B')?.coords),coords);
  assert.ok(participant(b,'A'));
});

test('meeting points survive preview, back, start, language and re-render without saving B',async t=>{
  const b=await boot(t,base);chooseSecond(b);
  const coords=clone(participant(b,'B').coords);
  b.click('#goBtn');await settle();b.click('[data-meet-route]');await settle();
  assert.deepEqual(clone(participant(b,'B')?.coords),coords);
  assert.deepEqual(b.builds[0].stop_ids,[item.poi_id]);
  assert.equal(b.builds[0].finish_poi_id,item.poi_id);
  b.click('#experienceClose');assert.ok(b.w.document.querySelector('[data-meet-id]'));
  assert.deepEqual(clone(participant(b,'B')?.coords),coords);
  b.click('[data-meet-route]');await settle();b.click('#previewStart');
  assert.ok(b.w.SeruenFeatures.walk);
  assert.deepEqual(clone(participant(b,'B')?.coords),coords);
  assert.equal(visible(b).filter(x=>x.options?.weight).length,1);
  for(const lang of ['en','kk','ru']){b.click(`[data-lang="${lang}"]`);await settle();assert.ok(participant(b,'B'));}
  b.click('#walkClose');b.click('#walkResume');assert.ok(participant(b,'B'));
  assert.doesNotMatch(JSON.stringify(b.w.localStorage),new RegExp(String(coords[0]).replace('.','\\.')));
  b.click('#walkEnd');assert.equal(participant(b,'B'),undefined);
});

test('clearing B does not submit the previous participant; changing language preserves a chosen point',async t=>{
  let calls=0;
  const b=await boot(t,{...base,experiences:()=>{calls++;return json({items:[]});}});
  chooseSecond(b);b.click('[data-lang="en"]');assert.ok(participant(b,'B'));
  change(b,'#meetPreset','');assert.equal(participant(b,'B'),undefined);
  b.click('#goBtn');await settle();assert.equal(calls,0);
  assert.match(b.w.document.querySelector('#experienceMessage').textContent,/second point/);
});

test('manual B replaces the preset label, sits exactly on the click, shows no coordinates and is sent rounded',async t=>{
  let body;
  const b=await boot(t,{...base,experiences:(url,p)=>{body=p;return json({items:[]});}});chooseSecond(b);b.click('#meetPick');
  b.w.SeruenExt.onMapClick({latlng:{lat:51.140123, lng:71.424456}});
  const select=b.w.document.querySelector('#meetPreset');
  assert.equal(select.value,'');
  assert.equal(select.selectedOptions[0].textContent,'Точка на карте');
  assert.deepEqual(clone(participant(b,'B').coords),[51.140123,71.424456]);
  assert.doesNotMatch(b.w.document.querySelector('#meetingFields').textContent,/\d+\.\d{2,}/);
  b.click('[data-lang="kk"]');assert.equal(b.w.document.querySelector('#meetPreset').selectedOptions[0].textContent,'Картадағы нүкте');
  b.click('#goBtn');await settle();
  assert.deepEqual(body.second_location,{lat:51.14,lon:71.424,precision_m:100,source:'map'});
});

test('walk limit pills drive the hidden select and the request',async t=>{
  let body;
  const b=await boot(t,{...base,experiences:(url,p)=>{body=p;return json({items:[]});}});chooseSecond(b);
  b.click('[data-meet-limit="45"]');
  assert.equal(b.w.document.querySelector('#meetLimit').value,'45');
  assert.deepEqual([...b.w.document.querySelectorAll('[data-meet-limit]')].map(x=>x.getAttribute('aria-pressed')),['false','false','true','false']);
  b.click('#goBtn');await settle();assert.equal(body.max_walk_min,45);
  change(b,'#meetLimit','15');assert.equal(b.w.document.querySelector('[data-meet-limit="15"]').classList.contains('on'),true);
  b.click('#meetInfo');assert.equal(b.w.document.querySelector('#meetPrivacy').hidden,false);
  assert.equal(b.w.document.querySelector('#meetPrivacy').textContent,b.w.SeruenExperienceText.ru.privacy);
  b.click('#meetStart');assert.equal(b.w.document.querySelector('#meetPrivacy').hidden,true);
});

test('meeting ends at the venue without overwriting a saved finish for ordinary walks',async t=>{
  const b=await boot(t,base);
  b.w.SeruenFeatures.setFinish({lat:51.15,lon:71.41,source:'map'});
  chooseSecond(b);assert.equal(b.w.document.querySelector('#finishField').hidden,true);
  assert.ok(!visible(b).some(p=>p.options?.icon?.html.includes('finish-pin')));
  b.click('#goBtn');await settle();b.click('[data-meet-route]');await settle();
  assert.equal(b.builds[0].finish_mode,'destination');
  assert.equal(b.builds[0].destination.lat,item.coords.lat);
  assert.equal(b.builds[0].destination.lon,item.coords.lon);
  b.click('#previewStart');
  assert.equal(b.w.SeruenFeatures.walk.plan.server.state.finish_poi_id,item.poi_id);
  assert.match(b.w.document.querySelector('.meeting-walk-context').textContent,/не его текущее положение/);
  assert.match(b.w.document.querySelector('.meeting-walk-context').textContent,/Старт друга: Хан Шатыр/);
  assert.doesNotMatch(b.w.document.querySelector('.meeting-walk-context').textContent,/\d+\.\d{2,}/);
  assert.equal(b.w.SeruenExt.requestExtras().end.lat,51.15);
  assert.ok(!visible(b).some(p=>p.options?.icon?.html.includes('finish-pin')));
  b.click('#walkEnd');
  assert.ok(visible(b).some(p=>p.options?.icon?.html.includes('finish-pin')));
});

test('failed preview keeps both points and offers return to meeting results',async t=>{
  const b=await boot(t,{...base,build:{...plan,fits:false,status:'impossible'}});chooseSecond(b);
  b.click('#goBtn');await settle();b.click('[data-meet-route]');await settle();
  assert.ok(participant(b,'A'));assert.ok(participant(b,'B'));
  assert.equal(b.w.document.querySelector('#previewStart'),null);
  b.click('#experienceClose');assert.ok(b.w.document.querySelector('[data-meet-route]'));
  b.click('[data-meet-map]');assert.equal(b.w.document.querySelector('#meetBack').hidden,false);
  b.click('#meetBack');assert.ok(participant(b,'B'));
});

test('stale meeting results cannot start a route and local fallback is labeled in all languages',async t=>{
  const b=await boot(t,{...base,experiences:()=>json({status:'ok',source:'local',items:[item],warning_codes:['local_catalog_fallback']})});
  for(const lang of ['ru','en','kk']){
    b.click(`[data-lang="${lang}"]`);chooseSecond(b);b.click('#goBtn');await settle();
    assert.ok(b.w.document.querySelector('#experienceMessage').textContent.includes(b.w.SeruenExperienceText[lang].localFallback));
    b.w.document.querySelector('#query').value+=' coffee';
    b.click('[data-meet-route]');await settle();
    assert.equal(b.builds.length,0);assert.ok(participant(b,'B'));
  }
});
