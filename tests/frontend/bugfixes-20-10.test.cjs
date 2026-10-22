// Bugs found by clicking every control on the live site on 20.10.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {boot}=require('./helpers.cjs');
const FX=require('./fixtures/feature_examples.json');
const clone=x=>JSON.parse(JSON.stringify(x)), json=x=>({ok:true,json:async()=>x});
const settle=async()=>{for(let i=0;i<8;i++)await new Promise(r=>setImmediate(r));};
const change=(b,s,value)=>{const e=b.w.document.querySelector(s);e.value=value;e.dispatchEvent(new b.w.Event('change',{bubbles:true}));};
const withFeatures={healthData:FX.health_with_features,comfort:FX.comfort,build:FX.build_ok,export:FX.export_ok};
const request={location:{lat:51.128,lon:71.43},query:'coffee',context:{lang:'ru',time_budget_min:90}};
const startWalk=b=>b.w.SeruenFeatures.startWalk(b.w.SeruenFeatures.planView(clone(FX.build_ok),request),null);

// the in-app button stays when 2GIS refused (its box explains); only a 2GIS switched off on the server hides it
for (const [twogis, shown] of [[{enabled:true,search_enabled:true,last_status:'twogis_access_denied'}, true], [{enabled:true,last_status:'ok'}, true], [{enabled:false,last_status:'not_checked'}, false]]) {
  test(`2GIS rating button is ${shown ? 'shown' : 'hidden'} when /health says enabled=${twogis.enabled}, last ${twogis.last_status}`,async t=>{
    const b=await boot(t,{healthData:{mode_available:['no_ai'],twogis}});await settle();
    b.click('#goBtn');await settle();
    b.requests[0].resolve(json(clone(FX.recommend_normal)));await settle();
    assert.ok(b.w.document.querySelectorAll('.rec').length>0);
    assert.equal(b.w.document.querySelectorAll('.rec [data-act="gis"]').length>0,shown);
  });
}

test('a refused 2GIS answer is explained inside its box and every card keeps the in-app button',async t=>{
  const refused=()=>({ok:false,status:503,json:async()=>({error:{code:'twogis_access_denied'}})});
  const b=await boot(t,{healthData:{mode_available:['no_ai'],twogis:{enabled:true,search_enabled:true,last_status:'not_checked'}},twogis:refused});await settle();
  b.click('#goBtn');await settle();b.requests[0].resolve(json(clone(FX.recommend_normal)));await settle();
  const buttons=[...b.w.document.querySelectorAll('.rec [data-act="gis"]')];
  assert.ok(buttons.length>=2);
  buttons[0].click();await settle();
  const box=buttons[0].closest('.rec').querySelector('.gis-box').textContent;
  assert.match(box,/недоступны/);assert.doesNotMatch(box,/Сообщите команде/);
  assert.equal(b.w.document.querySelectorAll('.rec [data-act="gis"]').length,buttons.length);
  assert.equal(b.w.localStorage.getItem('seruen_gis_refused'),null);
  assert.equal(b.w.document.querySelectorAll('[data-gis-reviews]').length,0);
  b.w.SeruenApp.rerender();
  assert.equal(b.w.document.querySelectorAll('.rec [data-act="gis"]').length,buttons.length);
});

test('one left-out place reads «без 1 места», five read «без 5 мест»',async t=>{
  const b=await boot(t,withFeatures);await settle();
  b.click('#goBtn');await settle();b.requests[0].resolve(json(clone(FX.recommend_normal)));await settle();
  const F=b.w.SeruenFeatures;
  F.cons.exclude_ids=['a'];b.w.SeruenApp.rerender();
  assert.match(b.w.document.querySelector('.cons-active').textContent,/без 1 места/);
  F.cons.exclude_ids=['a','b','c','d','e'];b.w.SeruenApp.rerender();
  assert.match(b.w.document.querySelector('.cons-active').textContent,/без 5 мест/);
});

test('«Осталось меньше времени» asks the minutes with buttons in the panel, never a browser pop-up',async t=>{
  const b=await boot(t,withFeatures);await settle();
  b.w.prompt=()=>{throw new Error('window.prompt must not be used');};
  startWalk(b);await settle();
  b.click('#walk [data-ch="less_time"]');await settle();
  const choices=[...b.w.document.querySelectorAll('#walk [data-less]')].map(x=>x.dataset.less);
  assert.ok(choices.includes('cancel')&&choices.length>=2,choices.join(','));
  b.click('#walk [data-less="cancel"]');await settle();
  assert.equal(b.w.document.querySelector('#walk [data-less]'),null);assert.equal(b.replans.length,0);
  b.click('#walk [data-ch="less_time"]');await settle();
  const pick=choices.find(x=>x!=='cancel');
  b.click(`#walk [data-less="${pick}"]`);await settle();
  assert.equal(b.replans.length,1);assert.equal(b.replans[0].body.reason,'less_time');
  assert.match(JSON.stringify(b.replans[0].body),new RegExp(`:${pick}[,}]`));
});

test('«Сохранить прогулку» during a walk confirms in the walk panel',async t=>{
  const b=await boot(t,withFeatures);await settle();
  startWalk(b);await settle();
  b.click('#walkSave');await settle();
  const x=b.w.SeruenApp.T().x;
  // the test browser has no device storage, so «storage blocked» is the honest answer there; it must land in the walk panel
  assert.ok([x.saved,x.partialExport,x.storeBlocked].includes(b.w.document.querySelector('#walkMsg').textContent),b.w.document.querySelector('#walkMsg').textContent);
});

test('meeting mode hides «С кем» and asks the server for two people, not a group or a child',async t=>{
  let sent=null;
  const item={...clone(FX.build_ok.stops[0]),category:'coffee',walk_min:[5,9],difference_min:4,max_walk_min:9,
    paths:[[[71.430,51.128],[71.431,51.130]],[[71.404,51.133],[71.431,51.130]]],sources:['synthetic']};
  const b=await boot(t,{healthData:{...FX.health_with_features,features:{...FX.health_with_features.features,meet_halfway:1}},
    experiences:(url,body)=>{sent=body;return json({status:'ok',source:'local',items:[item]});}});await settle();
  const withWhom=b.w.document.querySelector('#companions').closest('label');
  assert.equal(withWhom.hidden,false);
  change(b,'#companions','group');
  b.click('[name="searchIntent"][value="meet"]');await settle();
  assert.equal(withWhom.hidden,true);
  change(b,'#meetPreset','khan');b.click('#goBtn');await settle();
  assert.equal(sent.request.context.companions,'alone');
  assert.equal(sent.max_walk_min,45);
  b.click('[name="searchIntent"][value="walk"]');await settle();
  assert.equal(withWhom.hidden,false);
});

test('a meeting with nothing in the limit offers one tap to search a bit further',async t=>{
  const sent=[];
  const b=await boot(t,{healthData:{...FX.health_with_features,features:{...FX.health_with_features.features,meet_halfway:1}},
    experiences:(url,body)=>{sent.push(body);return json({status:'no_matches',source:'local',items:[]});}});await settle();
  b.click('[name="searchIntent"][value="meet"]');await settle();change(b,'#meetPreset','khan');
  b.click('#goBtn');await settle();
  assert.equal(sent[0].max_walk_min,45);
  const more=b.w.document.querySelector('#meetWider');assert.match(more.textContent,/60/);
  more.click();await settle();
  assert.equal(sent.length,2);assert.equal(sent[1].max_walk_min,60);
  assert.equal(b.w.document.querySelector('#meetWider'),null);
});

test('when Gemini cannot read the team photos now, their earlier Gemini labels still show under the photos, with the date',async t=>{
  const pics=[1,2,3].map(i=>({url:`https://seruen-astana.netlify.app/img/places/c/team-coffeeboom-expo-${i}.jpg`,source:'team'}));
  const b=await boot(t,{photos:()=>json({photos:pics,status:'ai_unavailable',analysis:null})});await settle();
  b.click('#goBtn');await settle();b.requests[0].resolve(json(clone(FX.recommend_normal)));await settle();await settle();
  const box=b.w.document.querySelector('.rec .photos');
  assert.ok(box.querySelectorAll('.ph-strip img').length===3);
  assert.match(box.querySelector('.tags').textContent,/около 40 мест/);
  assert.match(box.textContent,/анализ этих фото Gemini от 20 окт/);
  // photos and their labels come right after the name, walk and address: before the purchase note, 2GIS facts and the description
  const card=box.closest('.rec');const kids=[...card.children];
  assert.ok(kids.indexOf(box)>kids.indexOf(card.querySelector('.rec-title')));
  assert.ok(kids.indexOf(box)<kids.indexOf(card.querySelector('.pills')));
  assert.ok(kids.indexOf(box)<kids.indexOf(card.querySelector('.rec-desc')));
});
