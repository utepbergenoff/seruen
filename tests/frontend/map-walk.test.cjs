const {test} = require('node:test');
const assert = require('node:assert/strict');
const {boot} = require('./helpers.cjs');
const FX = require('./fixtures/feature_examples.json');
const json=data=>({ok:true,json:async()=>data});
const tick=()=>new Promise(r=>setImmediate(r));
const settle=async()=>{for(let i=0;i<6;i++)await tick();};
const opts={healthData:FX.health_with_features,build:FX.build_ok};
const clone=x=>JSON.parse(JSON.stringify(x));
const request={location:{lat:51.128,lon:71.43},query:'coffee',context:{lang:'ru',time_budget_min:90}};
const walkLine=b=>[...b.layers].find(l=>l.options?.weight===5);
async function search(b) {
  b.click('#goBtn');await tick();
  const d=clone(FX.recommend_normal);
  d.source='2gis';d.next_cursor='page-two';
  d.nearby_places=[{...d.recommendations[0],poi_id:'2gis_extra',name:'Outside <top 3>',eligible:true,address:'Test street'}];
  d.nearby_places[0].visit_condition={kind:'unknown',provider_url:'https://2gis.kz/astana/firm/123',provider_attributes:['Пицца','Бургеры','Wi-Fi','Чек 3500 ₸','Можно с ноутбуком','Детское меню']};
  b.requests[0].resolve(json(d));await settle();return d;
}
function start(b) {b.w.SeruenFeatures.startWalk(b.w.SeruenFeatures.planView(clone(FX.build_ok),request),null);}

test('markers open their own panel; Back restores top 3, catalog and pagination without another search',async t=>{
  const b=await boot(t,opts);const d=await search(b);const a=b.w.SeruenApp;
  const before=JSON.stringify(a.state.last), card=b.w.document.querySelectorAll('.rec')[1];
  card.querySelector('.more').open=true;
  a.markers[d.recommendations[1].poi_id].fire('click');
  assert.equal(b.w.document.querySelector('#selectedPlaceCard .rec'),card);
  assert.equal(b.w.document.querySelector('#resultsOverview').hidden,true);
  assert.equal(a.state.selectedPlaceId,d.recommendations[1].poi_id);
  a.markers['2gis_extra'].fire('click');
  assert.match(b.w.document.querySelector('#selectedPlaceCard').textContent,/Outside <top 3>/);
  assert.equal(b.w.document.querySelector('#selectedPlaceCard top'),null);
  const conditions=b.w.document.querySelector('#selectedPlaceCard .provider-conditions');
  assert.match(conditions.textContent,/Wi-Fi/);assert.equal(conditions.querySelector('details').open,false);
  assert.match(conditions.querySelector('details').textContent,/Пицца.*Бургеры/);
  b.click('#backToPlaces');
  assert.equal(a.state.selectedPlaceId,null);
  assert.equal(b.w.document.querySelector('#resultsOverview').hidden,false);
  assert.deepEqual([...b.w.document.querySelectorAll('#resultsOverview .rec')].map(e=>e.dataset.id),d.recommendations.map(r=>r.poi_id));
  assert.equal(b.w.document.querySelectorAll('.rec')[1],card);assert.equal(card.querySelector('.more').open,true);
  assert.ok(b.w.document.querySelector('#nextPlacesBtn'));assert.ok(b.w.document.querySelector('.nearby-place'));
  assert.equal(JSON.stringify(a.state.last),before);assert.equal(b.requests.length,1);
});

test('selection survives language and health rerenders; a fresh search clears it',async t=>{
  const b=await boot(t,opts);const d=await search(b);
  b.w.SeruenApp.markers['2gis_extra'].fire('click');
  for(const lang of ['en','kk','ru']) {
    b.click(`[data-lang="${lang}"]`);await settle();
    assert.equal(b.w.SeruenApp.state.selectedPlaceId,'2gis_extra');
    assert.equal(b.w.document.querySelector('#placeSelection').hidden,false);
    assert.ok(b.w.document.querySelector('#backToPlaces').textContent.trim());
  }
  b.click('#goBtn');await tick();b.requests[1].resolve(json(d));await settle();
  assert.equal(b.w.SeruenApp.state.selectedPlaceId,null);
  assert.equal(b.w.document.querySelector('#resultsOverview').hidden,false);
});

for(const selected of ['recommendation','catalog']) {
  test(`start walk targets exactly the selected ${selected}, never top 1`,async t=>{
    const wait={};wait.promise=new Promise(r=>wait.resolve=r);
    const b=await boot(t,{...opts,buildResponse:wait});const d=await search(b);
    const p=selected==='catalog'?d.nearby_places[0]:d.recommendations[1];
    // Card selection and marker selection follow the same contract.
    if(selected==='catalog')b.w.SeruenApp.markers[p.poi_id].fire('click');
    else b.w.document.querySelectorAll('.rec')[1].click();
    b.click('#startSelectedWalk');await tick();
    assert.deepEqual(b.builds[0].stop_ids,[p.poi_id]);assert.equal(b.builds[0].max_stops,1);
    const response=clone(FX.build_ok);response.stops=[{...response.stops[0],poi_id:p.poi_id,name:p.name}];
    response.state.remaining_ids=[p.poi_id];
    wait.resolve(json(response));await settle();
    assert.deepEqual([...b.w.SeruenFeatures.walk.plan.stops].map(s=>s.poi_id),[p.poi_id]);
  });
}

test('late plan for a different selection cannot start a walk',async t=>{
  const wait={};wait.promise=new Promise(r=>wait.resolve=r);
  const b=await boot(t,{...opts,buildResponse:wait});const d=await search(b);
  b.w.SeruenApp.markers[d.recommendations[0].poi_id].fire('click');b.click('#startSelectedWalk');await tick();
  b.w.SeruenApp.markers['2gis_extra'].fire('click');wait.resolve(json(FX.build_ok));await settle();
  assert.equal(b.w.SeruenFeatures.walk,null);
  assert.equal(b.w.SeruenApp.state.selectedPlaceId,'2gis_extra');
});

test('a wrong or unavailable selected destination never silently becomes top 1',async t=>{
  const b=await boot(t,opts);await search(b);start(b);const before=JSON.stringify(b.w.SeruenFeatures.walk.plan);
  b.w.SeruenApp.markers['2gis_extra'].fire('click');b.click('#startSelectedWalk');await settle();
  assert.equal(JSON.stringify(b.w.SeruenFeatures.walk.plan),before);
  assert.ok(b.w.document.querySelector('#selectedWalkMsg').textContent);
});

test('409 no replacement preserves geometry, stops, finish and all controls',async t=>{
  const b=await boot(t,opts);start(b);const before=JSON.stringify(b.w.SeruenFeatures.walk.plan);
  const line=JSON.stringify(walkLine(b).coords);
  b.click('[data-ch="cold"]');await tick();
  b.replans[0].resolve({ok:false,status:409,json:async()=>({error:{code:'no_replacement_found'}})});await settle();
  assert.equal(JSON.stringify(b.w.SeruenFeatures.walk.plan),before);
  assert.equal(JSON.stringify(walkLine(b).coords),line);
  assert.match(b.w.document.querySelector('#walkMsg').textContent,/не учитывает новое пожелание/);
  assert.ok(b.w.document.querySelector('[data-ch="tired"]'));
});

test('cancel and collapse retain the route and ignore late replans; resume restores controls',async t=>{
  const b=await boot(t,opts);start(b);const before=JSON.stringify(b.w.SeruenFeatures.walk.plan);
  b.click('[data-ch="cold"]');await tick();b.click('#walkCancel');
  b.replans[0].resolve(json(FX.replan_ok));await settle();
  assert.equal(JSON.stringify(b.w.SeruenFeatures.walk.plan),before);assert.ok(walkLine(b));
  b.click('[data-ch="tired"]');await tick();b.click('#walkClose');
  b.replans[1].resolve(json(FX.replan_ok));await settle();
  assert.equal(JSON.stringify(b.w.SeruenFeatures.walk.plan),before);assert.ok(walkLine(b));
  assert.ok(b.w.document.querySelector('#walkResume'));b.click('#walkResume');
  assert.ok(b.w.document.querySelector('[data-ch="cold"]'));
  b.click('#walkEnd');assert.equal(b.w.SeruenFeatures.walk,null);assert.equal(walkLine(b),undefined);
});

test('undo restores previous route, preserves progress and deadline, and invalidates pending replan',async t=>{
  const b=await boot(t,opts);start(b);const original=clone(b.w.SeruenFeatures.walk.plan);
  b.click('[data-ch="cold"]');await tick();const proposed=clone(FX.replan_ok);proposed.stops=[proposed.stops[0],...clone(FX.build_ok.stops)];
  b.replans[0].resolve(json(proposed));await settle();
  assert.equal(JSON.stringify(b.w.SeruenFeatures.walk.plan),JSON.stringify(original));
  b.click('#applyWalkProposal');
  b.click('#walk [data-ws="done"]');
  const done=b.w.SeruenFeatures.walk.plan.stops.find(s=>s.status==='done').poi_id;
  b.click('[data-ch="tired"]');await tick();b.click('#walkUndo');
  b.replans[1].resolve(json(clone(FX.replan_ok)));await settle();
  const restored=b.w.SeruenFeatures.walk.plan;
  assert.deepEqual(clone(restored.server.geometry),original.server.geometry);
  assert.deepEqual(clone(restored.end),original.end);assert.equal(restored.deadline_ms,original.deadline_ms);
  assert.equal(restored.stops.find(s=>s.poi_id===done).status,'done');
  assert.ok(restored.server.state.completed_ids.includes(done));assert.ok(!restored.build_request.stop_ids.includes(done));
  assert.match(b.w.document.querySelector('#walkMsg').textContent,/предыдущий план/);
  start(b);assert.equal(b.w.document.querySelector('#walkUndo'),null);
});

test('map modes keep place selection, all markers and the active walk; provider failure falls back safely',async t=>{
  const b=await boot(t,opts);await search(b);start(b);
  b.w.SeruenApp.markers['2gis_extra'].fire('click');
  const before=JSON.stringify(b.w.SeruenFeatures.walk.plan),markers={...b.w.SeruenApp.markers};
  const select=b.w.document.querySelector('#mapMode');
  for(const mode of ['satellite','hybrid','streets','hybrid']){
    select.value=mode;select.dispatchEvent(new b.w.Event('change'));
    assert.equal(b.w.document.querySelector('#map').dataset.mode,mode);
    assert.equal(b.w.SeruenApp.state.selectedPlaceId,'2gis_extra');assert.ok(walkLine(b));
    for(const [id,marker] of Object.entries(markers))assert.equal(b.w.SeruenApp.markers[id],marker);
    assert.equal(JSON.stringify(b.w.SeruenFeatures.walk.plan),before);
  }
  assert.equal(JSON.parse(b.w.localStorage.getItem('seruen_map_mode')),'hybrid');
  const satellite=b.tiles.at(-2);satellite.fire('tileerror');satellite.fire('tileerror');satellite.fire('tileerror');
  assert.equal(select.value,'streets');assert.equal(b.w.document.querySelector('#mapNotice').hidden,false);
  assert.equal(JSON.stringify(b.w.SeruenFeatures.walk.plan),before);
});

test('theme follows system until explicit choice, persists, and never rebuilds the map or search',async t=>{
  const b=await boot(t,{...opts,darkSystem:true});await search(b);start(b);
  assert.equal(b.w.document.documentElement.dataset.theme,'dark');
  b.media.matches=false;b.media.change();assert.equal(b.w.document.documentElement.dataset.theme,'light');
  const before=JSON.stringify(b.w.SeruenFeatures.walk.plan),tileCount=b.tiles.length;
  b.click('#themeBtn');assert.equal(b.w.document.documentElement.dataset.theme,'dark');
  b.media.matches=false;b.media.change();assert.equal(b.w.document.documentElement.dataset.theme,'dark');
  assert.equal(JSON.parse(b.w.localStorage.getItem('seruen_theme')),'dark');
  b.click('#themeBtn');assert.equal(b.w.document.documentElement.dataset.theme,'light');
  assert.equal(JSON.stringify(b.w.SeruenFeatures.walk.plan),before);assert.equal(b.requests.length,1);assert.equal(b.tiles.length,tileCount);
  const reload=await boot(t,{storage:{seruen_theme:'dark',seruen_map_mode:'satellite'}});
  assert.equal(reload.w.document.documentElement.dataset.theme,'dark');assert.equal(reload.w.document.querySelector('#mapMode').value,'satellite');
});

test('cold offers a break without deleting the destination; discard keeps the exact original route',async t=>{
  const b=await boot(t,opts);start(b);const before=JSON.stringify(b.w.SeruenFeatures.walk.plan);
  b.click('[data-ch="cold"]');await tick();
  assert.equal(b.replans[0].body.keep_stops,true);
  const proposed=clone(FX.replan_ok);proposed.stops=[proposed.stops[0],...clone(FX.build_ok.stops)];
  b.replans[0].resolve(json(proposed));await settle();
  assert.equal(JSON.stringify(b.w.SeruenFeatures.walk.plan),before);
  assert.ok(b.w.document.querySelector('#walkProposal'));assert.ok(walkLine(b));
  b.click('#discardWalkProposal');assert.equal(JSON.stringify(b.w.SeruenFeatures.walk.plan),before);
  assert.equal(b.w.document.querySelector('#walkProposal'),null);
});

test('old-server cold replacement cannot remove an uncompleted destination',async t=>{
  const b=await boot(t,opts);start(b);const before=JSON.stringify(b.w.SeruenFeatures.walk.plan);
  b.click('[data-ch="cold"]');await tick();b.replans[0].resolve(json(FX.replan_ok));await settle();
  assert.equal(JSON.stringify(b.w.SeruenFeatures.walk.plan),before);
  assert.equal(b.w.document.querySelector('#applyWalkProposal'),null);
});
