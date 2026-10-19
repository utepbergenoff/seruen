const {test} = require('node:test');
const assert = require('node:assert/strict');
const {boot} = require('./helpers.cjs');
const FX = require('./fixtures/feature_examples.json');
const tick=()=>new Promise(r=>setImmediate(r));
const settle=async()=>{for(let i=0;i<6;i++)await tick();};
const json=data=>({ok:true,json:async()=>data});
const clone=x=>JSON.parse(JSON.stringify(x));
const health={...FX.health_with_features, features:{...FX.health_with_features.features,comfort_breaks:1}};
const comfort=[{poi_id:'bench',name:'Скамейка <test>',coords:{lat:51.128,lon:71.43},kind:'bench',access:'public',distance_m:100,walk_min:3,indoor:false,open_status:{state:'unknown'},checked_at:'2026-10-19',note:'Test only',source_url:'https://example.org'},
 {...clone({poi_id:'closed-warm',name:'Закрытый ТРЦ',coords:{lat:51.128,lon:71.43},kind:'warming',access:'public',distance_m:100,walk_min:3,indoor:true,open_status:{state:'closed'},checked_at:'2026-10-19',note:'',source_url:'https://example.org'})}];
const opts={healthData:health,comfort,build:FX.build_ok};
const request={location:{lat:51.128,lon:71.43},query:'coffee',context:{lang:'ru',time_budget_min:90}};
function start(b){b.w.SeruenFeatures.startWalk(b.w.SeruenFeatures.planView(clone(FX.build_ok),request),null);}







test('cold loads benches and facilities independently even when venue suggestion fails',async t=>{
 const b=await boot(t,opts);start(b);const before=JSON.stringify(b.w.SeruenFeatures.walk.plan);
 b.click('[data-ch="cold"]');await settle();
 assert.equal(b.comforts[0].radius_m,100);assert.equal(b.comforts[0].on_route_only,true);assert.equal(b.comforts[0].route_points.length,2);
 assert.ok(b.comforts[0].kinds.includes('bench'));assert.ok(b.comforts[0].kinds.includes('toilet'));
 b.replans[0].resolve({ok:false,status:409,json:async()=>({error:{code:'no_replacement_found'}})});await settle();
 assert.equal(JSON.stringify(b.w.SeruenFeatures.walk.plan),before);
 const rest=b.w.document.querySelector('#restOptions');assert.match(rest.textContent,/согреться здесь не получится/);
 assert.equal(rest.querySelector('test'),null);assert.match(rest.textContent,/Скамейка <test>/);
 assert.equal(rest.querySelector('[data-rest-add="closed-warm"]').disabled,true);
 assert.equal(rest.querySelector('[data-rest-add="bench"]').disabled,false);
 assert.ok(b.pins.some(p=>p.options.title==='Скамейка <test>'));
});

test('choosing a bench previews it before the destination, applies only with confirmation',async t=>{
 const b=await boot(t,opts);start(b);const before=JSON.stringify(b.w.SeruenFeatures.walk.plan);
 b.click('[data-ch="tired"]');await settle();b.replans[0].resolve({ok:false,status:409,json:async()=>({error:{code:'no_replacement_found'}})});await settle();
 b.click('[data-rest-add="bench"]');await tick();
 assert.equal(b.replans[1].body.reason,'add_stop');assert.equal(b.replans[1].body.keep_stops,true);
 const response=clone(FX.build_ok);const extra={...clone(response.stops[0]),poi_id:'bench',name:'Скамейка'};
 response.stops.unshift(extra);response.state.remaining_ids.unshift('bench');
 b.replans[1].resolve(json(response));await settle();
 assert.equal(JSON.stringify(b.w.SeruenFeatures.walk.plan),before);assert.ok(b.w.document.querySelector('#applyWalkProposal'));
 b.click('#applyWalkProposal');assert.equal(b.w.SeruenFeatures.walk.plan.stops[0].poi_id,'bench');
 assert.equal(b.w.document.querySelector('#restOptions'),null);
 b.click('#walkUndo');assert.equal(b.w.SeruenFeatures.walk.plan.stops[0].poi_id,FX.build_ok.stops[0].poi_id);
});

test('moving the chosen point refreshes rest options instead of adding a stale nearby bench',async t=>{
 const b=await boot(t,opts);start(b);b.click('[data-ch="cold"]');await settle();
 b.replans[0].resolve({ok:false,status:409,json:async()=>({error:{code:'no_replacement_found'}})});await settle();
 b.w.SeruenApp.state.loc={lat:51.13,lon:71.43,source:'map'};b.click('[data-rest-add="bench"]');await settle();
 assert.equal(b.replans.length,1);assert.equal(b.comforts.length,2);
 assert.equal(b.comforts[1].location.lat,51.13);
});

test('day and night hero are separate credited assets and follow manual and system theme',async t=>{
 const b=await boot(t,opts),$=s=>b.w.document.querySelector(s);
 assert.match($('.welcome-day').src,/hero-baiterek-day/);assert.match($('.welcome-night').src,/hero-baiterek-night/);
 assert.equal(b.w.document.documentElement.dataset.theme,'light');
 b.w.SeruenTheme.cycle();assert.equal(b.w.document.documentElement.dataset.theme,'dark');
 b.w.SeruenTheme.cycle();assert.equal(b.w.document.documentElement.dataset.theme,'light');
 b.w.SeruenTheme.cycle();b.media.matches=true;b.media.change();
 assert.equal(b.w.document.documentElement.dataset.theme,'dark');
});



