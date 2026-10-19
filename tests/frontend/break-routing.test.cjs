const {test}=require('node:test');
const assert=require('node:assert/strict');
const {boot}=require('./helpers.cjs');
const FX=require('./fixtures/feature_examples.json');
const clone=x=>JSON.parse(JSON.stringify(x));
const settle=async()=>{for(let i=0;i<8;i++)await new Promise(r=>setImmediate(r));};
const json=data=>({ok:true,json:async()=>data});
const request={location:{lat:51.128,lon:71.43},query:'coffee',context:{lang:'ru',time_budget_min:90}};
function routed(){const p=clone(FX.build_ok);p.routing_source='osrm_foot';return p;}
function via(){const p=routed();p.stops.unshift({...clone(p.stops[0]),poi_id:'bench',name:'Скамейка',coords:{lat:51.129,lon:71.43}});p.state.remaining_ids.unshift('bench');p.geometry=[[71.43,51.128],[71.4301,51.1285],[71.43,51.129],...p.geometry.slice(1)];return p;}
async function setup(t){const b=await boot(t,{healthData:FX.health_with_features});b.w.SeruenFeatures.startWalk(b.w.SeruenFeatures.planView(routed(),request),null);return b;}

test('accepting a break replaces geometry with a solid routed path and keeps a clickable stop marker',async t=>{
 const b=await setup(t),before=JSON.stringify(b.w.SeruenFeatures.walk.plan);
 b.click('[data-ch="cold"]');await settle();b.replans[0].resolve(json(via()));await settle();
 assert.equal(JSON.stringify(b.w.SeruenFeatures.walk.plan),before);
 b.click('#applyWalkProposal');
 const active=b.lines.filter(l=>b.layers.has(l)).at(-1);
 assert.equal(active.options.dashArray,null);
 assert.deepEqual(JSON.parse(JSON.stringify(active.coords)),via().geometry.map(([lon,lat])=>[lat,lon]));
 assert.equal(b.w.SeruenFeatures.walk.plan.stops[0].poi_id,'bench');
 const marker=b.pins.findLast(p=>p.options.title==='Скамейка' && p.target?.members.has(p));
 assert.ok(marker);b.click('#walkClose');marker.fire('click');
 assert.ok(b.w.document.querySelector('#walkStop0'));
 b.click('#walkUndo');assert.equal(JSON.stringify(b.w.SeruenFeatures.walk.plan.server.geometry),JSON.stringify(routed().geometry));
});

for(const failure of ['fallback','http'])test(`failed ${failure} keeps the street route and supports retry`,async t=>{
 const b=await setup(t),before=JSON.stringify(b.w.SeruenFeatures.walk.plan);
 b.click('[data-ch="cold"]');await settle();
 b.replans[0].resolve(failure==='fallback'?json({...via(),routing_source:'distance_estimate'}):{ok:false,status:409,json:async()=>({error:{code:'break_routing_unavailable'}})});await settle();
 assert.equal(JSON.stringify(b.w.SeruenFeatures.walk.plan),before);assert.equal(b.w.document.querySelector('#applyWalkProposal'),null);
 assert.match(b.w.document.querySelector('#walkMsg').textContent,/Прежний маршрут сохранён/);
 b.click('#retryWalkRoute');await settle();assert.equal(b.replans.length,2);
 b.replans[1].resolve(json(via()));await settle();b.click('#applyWalkProposal');
 assert.equal(b.w.SeruenFeatures.walk.plan.stops[0].poi_id,'bench');
});

test('moving after preview recomputes the chosen stop instead of applying a stale line',async t=>{
 const b=await setup(t),before=JSON.stringify(b.w.SeruenFeatures.walk.plan);
 b.click('[data-ch="cold"]');await settle();b.replans[0].resolve(json(via()));await settle();
 b.w.SeruenApp.state.loc={lat:51.129,lon:71.43,source:'map'};b.click('#applyWalkProposal');await settle();
 assert.equal(JSON.stringify(b.w.SeruenFeatures.walk.plan),before);
 assert.equal(b.replans[1].body.reason,'add_stop');assert.equal(b.replans[1].body.poi_id,'bench');
 assert.equal(b.replans[1].body.request.location.lat,51.129);
 b.replans[1].resolve(json(via()));await settle();
});
