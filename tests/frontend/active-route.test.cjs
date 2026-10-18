const {test}=require('node:test');
const assert=require('node:assert/strict');
const {boot}=require('./helpers.cjs');
const FX=require('./fixtures/feature_examples.json');
const clone=x=>JSON.parse(JSON.stringify(x)), json=x=>({ok:true,json:async()=>x});
const settle=async()=>{for(let i=0;i<8;i++)await new Promise(r=>setImmediate(r));};
const opts={healthData:{...FX.health_with_features,features:{...FX.health_with_features.features,meet_halfway:1}},build:FX.build_ok};
const req={location:{lat:51.128,lon:71.43},query:'coffee',context:{lang:'ru',time_budget_min:90}};
const start=b=>b.w.SeruenFeatures.startWalk(b.w.SeruenFeatures.planView(clone(FX.build_ok),req),null);
const visible=b=>[...b.layers].flatMap(l=>l.members?[...l.members]:[l]);
const routes=b=>visible(b).filter(l=>l.options?.weight);
function planFor(places){
  const plan=clone(FX.build_ok);
  plan.stops=places.map(p=>({...clone(plan.stops[0]),poi_id:p.poi_id,name:p.name,coords:p.coords}));
  plan.state.remaining_ids=places.map(p=>p.poi_id);
  plan.geometry=[[71.43,51.128],...places.map(p=>[p.coords.lon,p.coords.lat]),[71.43,51.128]];
  return plan;
}
async function search(b,data=FX.recommend_normal){
  b.click('#goBtn');await settle();b.requests.at(-1).resolve(json(clone(data)));await settle();
}

test('starting the selected walk removes suggestion lines but keeps all place markers',async t=>{
  const selected=FX.recommend_normal.recommendations[1], plan=planFor([selected]);
  const b=await boot(t,{...opts,build:plan});await search(b);
  assert.equal(routes(b).length,FX.recommend_normal.recommendations.length);
  const markers=Object.values(b.w.SeruenApp.markers);
  b.w.SeruenApp.markers[selected.poi_id].fire('click');
  b.click('#startSelectedWalk');await settle();
  assert.equal(routes(b).length,1);assert.equal(routes(b)[0].options.weight,5);
  assert.deepEqual(b.builds[0].stop_ids,[selected.poi_id]);
  assert.deepEqual(clone(routes(b)[0].coords),plan.geometry.map(([lon,lat])=>[lat,lon]));
  assert.ok(markers.every(p=>visible(b).includes(p)));
  b.click('#walkClose');assert.equal(routes(b).length,1);
  b.click('#walkResume');b.click('#walkEnd');
  assert.equal(routes(b).length,FX.recommend_normal.recommendations.length);
  assert.ok(routes(b).every(l=>l.options.dashArray==='1 8'));
});

test('language, new results and failed replan cannot bring alternatives back during a walk',async t=>{
  const b=await boot(t,opts);await search(b);start(b);
  for(const lang of ['en','kk','ru']){b.click(`[data-lang="${lang}"]`);await settle();assert.equal(routes(b).length,1);}
  const latest=clone(FX.recommend_normal);latest.recommendations=latest.recommendations.slice(0,1);
  await search(b,latest);assert.equal(routes(b).length,1);
  b.click('[data-ch="cold"]');await settle();
  b.replans[0].resolve({ok:false,status:409,json:async()=>({error:{code:'no_replacement_found'}})});await settle();
  assert.equal(routes(b).length,1);assert.equal(routes(b)[0].options.weight,5);
  b.click('#walkEnd');assert.equal(routes(b).length,1);assert.equal(routes(b)[0].options.dashArray,'1 8');
});

test('starting from preview removes both preview and recommendation paths',async t=>{
  const b=await boot(t,{...opts,build:planFor(FX.recommend_normal.recommendations)});await search(b);
  b.click('[data-plan-preview="results"]');await settle();
  assert.ok(routes(b).some(l=>l.options.dashArray==='5 5'));
  b.click('#previewStart');
  assert.equal(routes(b).length,1);assert.equal(routes(b)[0].options.weight,5);
  assert.equal(b.w.document.querySelector('#experienceBody').hidden,true);
});

test('late meeting response cannot draw competing routes after a saved walk starts',async t=>{
  let resolve;
  const b=await boot(t,{...opts,experiences:()=>new Promise(r=>resolve=r)});
  b.click('[name="searchIntent"][value="meet"]');
  const select=b.w.document.querySelector('#meetPreset');select.value='khan';select.dispatchEvent(new b.w.Event('change'));
  b.click('#goBtn');await settle();assert.equal(typeof resolve,'function');
  start(b);
  resolve(json({items:[{name:'Stale meeting',paths:[FX.build_ok.geometry,FX.build_ok.geometry]}]}));await settle();
  assert.equal(routes(b).length,1);assert.equal(routes(b)[0].options.weight,5);
  assert.equal(b.w.document.querySelector('#experienceBody').hidden,true);
});
