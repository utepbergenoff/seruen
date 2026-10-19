// Run from test_feature_contract_sync.py against an isolated FastAPI with synthetic records.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {boot} = require('./helpers.cjs');
const until = async fn => { for (let i=0;i<150;i++) {if(fn()) return;await new Promise(r=>setTimeout(r,20));} assert.ok(fn(),'UI did not settle'); };
test('all eight features use real server shapes and preserve offline/privacy boundaries', async t => {
  const calls=[];
  const b=await boot(t,{live:process.env.SERUEN_TEST_URL,calls}), w=b.w, $=s=>w.document.querySelector(s);
  try { await until(()=>$('#finishField') && $('#atmosField [data-mood="light_cafe"]')); }
  catch(e) { throw new Error(JSON.stringify({calls,features:w.SeruenApp.state.features,atmos:$('#atmosField')?.innerHTML}),{cause:e}); }
  w.SeruenApp.state.loc={lat:51.128,lon:71.430,source:'map'};
  $('#query').value='Хочу кофе'; $('#budgetAuto').checked=false; $('#budget').value='90';
  w.SeruenFeatures.setFinish({lat:51.130,lon:71.430,source:'landmark'});
  b.click('#goBtn'); await until(()=>$('.rec') && !$('#goBtn').disabled);
  assert.equal(w.SeruenApp.state.lastReq.end.source,'preset');
  assert.ok(w.SeruenApp.state.last.recommendations.every(r=>r.budget_breakdown.walk_to_end_min != null));
  const first=w.SeruenApp.state.last.recommendations[0].poi_id;
  b.click('.rec [data-keep="visited"]'); await until(()=>w.SeruenFeatures.mine.places.get(first)?.visited_at);
  b.click('.rec [data-nope="other"]'); await until(()=>w.SeruenApp.state.last.recommendations[0].poi_id!==first);
  assert.ok(calls.filter(c=>c.path==='/recommend').at(-1).body.preferences.exclude_poi_ids.includes(first));

  b.click('[data-comfort="toilet"]'); await until(()=>calls.some(c=>c.path==='/comfort/search'));
  const ns=$('#noSpend'); ns.value='strict'; ns.dispatchEvent(new w.Event('change'));
  b.click('#atmosField [data-mood="light_cafe"]'); b.click('#goBtn');
  await until(()=>!$('#goBtn').disabled && w.SeruenApp.state.lastReq.preferences?.expense_mode==='free_only');
  assert.deepEqual(w.SeruenApp.state.last.recommendations.map(r=>r.poi_id),['team_coffee']);
  assert.match($('.rec').textContent,/Бесплатно/);
  assert.ok(w.SeruenApp.state.last.recommendations[0].atmosphere_match.matched_features.length);

  b.click('#startWalkBtn');b.click('#routeFinishConfirm'); await until(()=>w.SeruenFeatures.walk?.plan?.server);
  assert.ok(w.SeruenFeatures.walk.plan.server.fits);
  b.click('#walk [data-ch="tired"]'); await until(()=>calls.some(c=>c.path==='/plans/recalculate'));
  await until(()=>!$('#walk .loading'));
  const replan=calls.find(c=>c.path==='/plans/recalculate');
  assert.ok(replan.body.remaining_time_min>0 && replan.body.previous.schema_version===1);
  assert.equal(replan.body.previous.finish_mode,'destination');
  assert.equal(replan.body.keep_stops,true);
  // A free verified bench can be suggested without changing the goal or its atmosphere preference.
  assert.equal(replan.status,200);assert.ok(w.SeruenFeatures.walk.proposal);
  assert.equal(w.SeruenFeatures.walk.plan.stops.length,1);
  assert.ok(w.SeruenFeatures.walk.plan.server.stops.some(s=>s.poi_id==='team_coffee'));
  assert.ok($('#walk [data-ch="cold"]'));

  b.click('#walkSave'); await until(()=>w.SeruenFeatures.mine.walks.length===1);
  const stored=(await w.SeruenStore.allWalks())[0];
  assert.equal(stored.version,2); assert.equal(stored.offline.status,'saved');
  assert.equal('server' in stored,false); assert.equal('photos' in stored.stops[0],false);
  b.click('#walkClose'); b.click('#mineBtn'); b.click('#mine [data-tab="walks"]'); b.click('#mine [data-walk-open]');
  assert.ok(w.SeruenFeatures.walk.plan.offline); assert.equal($('#walk [data-ch]'),null);
  b.click('#walkRefresh'); await until(()=>w.SeruenFeatures.walk?.plan?.server);
  assert.ok(calls.some(c=>c.path==='/plans/refresh'));

  await w.SeruenStore.putPlace({poi_id:'2gis_7000001',name:'provider secret fact',address:'provider address',
    coords:{lat:51.128,lon:71.43},favorite:true,note:'My own note',offline_allowed:false});
  const bookmark=await w.SeruenStore.getPlace('2gis_7000001');
  assert.equal(bookmark.name,undefined);assert.equal(bookmark.coords,undefined);assert.equal(bookmark.note,'My own note');
  assert.ok(calls.every(c=>c.status===200 || (c.path==='/plans/recalculate' && c.status===409)),JSON.stringify(calls.filter(c=>c.status!==200)));
  for(const path of ['/health','/recommend','/comfort/search','/atmosphere/examples','/plans/build','/plans/recalculate','/plans/export','/plans/refresh']) {
    assert.ok(calls.some(c=>c.path===path),path);
  }
});
