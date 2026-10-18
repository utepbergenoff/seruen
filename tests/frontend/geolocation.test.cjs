const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {boot} = require('./helpers.cjs');
const FX = require('./fixtures/feature_examples.json');
const tick = () => new Promise(r => setImmediate(r));
const pending = () => {let resolve; const promise=new Promise(r=>resolve=r);return {promise,resolve};};
const json = data => ({ok:true,json:async()=>data});
const pos = (lat=51.15,lon=71.44) => ({coords:{latitude:lat,longitude:lon,accuracy:250}});
function clock() {
  let now=0, id=0; const jobs=new Map();
  return {
    setTimeout(fn,ms) {const key=++id;jobs.set(key,{fn,at:now+ms});return key;},
    clearTimeout(key) {jobs.delete(key);},
    advance(ms) {
      const end=now+ms;
      for (;;) {
        const next=[...jobs].filter(([,j])=>j.at<=end).sort((a,b)=>a[1].at-b[1].at)[0];
        if (!next) break;
        now=next[1].at;jobs.delete(next[0]);next[1].fn();
      }
      now=end;
    },
  };
}

test('GPS starts before static files or health finish, and search stays usable',async t=>{
  const b=await boot(t,{staticFiles:{'presets.json':pending(),'scenarios.json':pending()},health:pending()});
  assert.equal(b.gps.calls.length,1);
  assert.equal(b.w.SeruenApp.state.locating,true);
  assert.equal(b.w.document.querySelector('#goBtn').disabled,false);
  assert.equal(b.w.document.querySelector('#geoActions').hidden,false);
  assert.equal(b.gps.calls[0].options.enableHighAccuracy,false);
  assert.equal(b.gps.calls[0].options.maximumAge,60000);
  b.gps.ok(pos());
  assert.equal(b.w.SeruenApp.state.loc.source,'gps');
  assert.equal(b.w.document.querySelector('#geoActions').hidden,true);
});

test('a slow Mac fix survives the old five-second deadline without blocking search',async t=>{
  const c=clock(), b=await boot(t,{clock:c}), a=b.w.SeruenApp;
  c.advance(3000);
  assert.equal(a.state.locating,true);
  assert.equal(b.w.document.querySelector('#geoMsg').textContent,b.w.I18N.ru.geoSlow);
  assert.equal(b.w.document.querySelector('#goBtn').disabled,false);
  assert.equal(b.w.document.querySelector('#geoMap').disabled,false);
  c.advance(5000);b.gps.ok(pos());
  assert.equal(a.state.loc.source,'gps');assert.equal(a.state.loc.lat,51.15);
  assert.equal(a.state.locating,false);
  assert.equal(b.w.document.querySelector('#geoMsg').hidden,true);
  c.advance(15000);assert.equal(b.w.document.querySelector('#geoMsg').hidden,true);
});

test('unanswered GPS has a final deadline; retry ignores old callbacks',async t=>{
  const c=clock(), b=await boot(t,{clock:c}), a=b.w.SeruenApp;
  const old=b.gps.calls[0];
  c.advance(14999);assert.equal(a.state.locating,true);
  c.advance(1);assert.equal(a.state.locating,false);
  assert.match(b.w.document.querySelector('#geoMsg').textContent,/15 секунд/);
  assert.equal(b.w.document.querySelector('#geoRetry').disabled,false);
  const before=JSON.stringify(a.state.loc);
  old.ok(pos());assert.equal(JSON.stringify(a.state.loc),before);
  b.click('#geoRetry');assert.equal(b.gps.calls.length,2);
  assert.equal(b.w.document.querySelector('#geoMsg').hidden,true);
  b.click('#geoBtn');assert.equal(b.gps.calls.length,2); // Disabled; must not restart the deadline.
  old.ok(pos());old.fail({code:1});
  assert.equal(a.state.locating,true);assert.equal(JSON.stringify(a.state.loc),before);
  b.gps.ok(pos(51.16,71.45));
  assert.equal(a.state.loc.lat,51.16);assert.equal(a.state.locating,false);
  c.advance(5000);assert.equal(b.w.document.querySelector('#geoMsg').hidden,true);
});

test('map selection cancels waiting immediately and ignores a late GPS response',async t=>{
  const c=clock(),b=await boot(t,{clock:c});const old=b.gps.calls[0],a=b.w.SeruenApp,before=JSON.stringify(a.state.loc);
  b.click('#geoMap');
  assert.equal(a.state.locating,false);
  assert.equal(b.w.document.activeElement.id,'map');
  assert.match(b.w.document.querySelector('#geoMsg').textContent,/Нажмите на карту/);
  old.ok(pos());assert.equal(JSON.stringify(a.state.loc),before);
  c.advance(20000);
  assert.match(b.w.document.querySelector('#geoMsg').textContent,/Нажмите на карту/);
});

test('a search freezes its visible point while a GPS response is pending',async t=>{
  const c=clock(),b=await boot(t,{clock:c}), a=b.w.SeruenApp;
  c.advance(8000);
  b.click('#goBtn');await tick();
  const before=JSON.stringify(a.state.loc);
  b.gps.ok(pos());
  assert.equal(a.state.locating,false);
  assert.equal(JSON.stringify(a.state.loc),before);
  assert.equal(b.requests[0].body.location.lat,a.state.loc.lat);
  assert.equal(b.requests[0].body.location.lon,a.state.loc.lon);
  assert.equal(b.w.document.querySelector('#geoMsg').hidden,true);
});

test('instant fixes cancel the slow hint and show rounded accuracy in all languages',async t=>{
  const c=clock(),b=await boot(t,{clock:c});b.gps.ok(pos());
  c.advance(15000);
  assert.equal(b.w.document.querySelector('#geoMsg').hidden,true);
  for(const lang of ['en','kk','ru']) {
    b.click(`[data-lang="${lang}"]`);
    assert.equal(b.w.document.querySelector('#locLine').textContent,b.w.I18N[lang].locFound.replace('{accuracy}','300'));
  }
  b.click('#goBtn');await tick();assert.equal(b.requests[0].body.location.precision_m,300);
  assert.equal(b.w.localStorage.getItem('seruen_location'),null);
});

test('coarse location is labelled approximate and not advertised as 100 m precision',async t=>{
  const b=await boot(t);b.gps.ok({coords:{latitude:51.151234,longitude:71.441234,accuracy:650}});
  assert.equal(b.w.document.querySelector('#geoMsg').textContent,b.w.I18N.ru.geoApproximate);
  b.click('#goBtn');await tick();
  assert.deepEqual(b.requests[0].body.location,{lat:51.151,lon:71.441,precision_m:700,source:'gps'});
});

test('city-scale or unknown accuracy cannot silently replace the chosen starting point',async t=>{
  const b=await boot(t,{url:'https://example.test/?preset=baiterek'}), before=JSON.stringify(b.w.SeruenApp.state.loc);
  for(const accuracy of [12000,NaN,undefined,-1]) {
    b.click('#geoBtn');b.gps.ok({coords:{latitude:51.15,longitude:71.44,accuracy}});
    assert.equal(JSON.stringify(b.w.SeruenApp.state.loc),before);
    assert.equal(b.w.document.querySelector('#geoMsg').textContent,b.w.I18N.ru.geoImprecise);
  }
});

test('denied or outside-city retry preserves selected point and active walk',async t=>{
  const b=await boot(t,{healthData:FX.health_with_features});b.gps.ok(pos());
  const req={location:{...b.w.SeruenApp.state.loc},query:'coffee',context:{lang:'ru',time_budget_min:90}};
  b.w.SeruenFeatures.startWalk(b.w.SeruenFeatures.planView(JSON.parse(JSON.stringify(FX.build_ok)),req),null);
  const before=JSON.stringify(b.w.SeruenFeatures.walk.plan), loc=JSON.stringify(b.w.SeruenApp.state.loc);
  b.click('#geoBtn');b.gps.fail({code:1});
  assert.match(b.w.document.querySelector('#geoMsg').textContent,/запрещён/);
  b.click('#geoRetry');b.gps.ok(pos(43.23,76.95));
  assert.match(b.w.document.querySelector('#geoMsg').textContent,/за пределами/);
  assert.equal(JSON.stringify(b.w.SeruenApp.state.loc),loc);
  assert.equal(JSON.stringify(b.w.SeruenFeatures.walk.plan),before);
});

test('location errors and actions follow the chosen language',async t=>{
  const b=await boot(t);b.gps.fail({code:3});
  for(const lang of ['en','kk','ru']) {
    b.click(`[data-lang="${lang}"]`);
    assert.equal(b.w.document.querySelector('#geoMsg').textContent,b.w.I18N[lang].geoTimeout);
    assert.equal(b.w.document.querySelector('#geoMap').textContent,b.w.I18N[lang].geoPickMap);
    assert.equal(b.w.document.querySelector('#geoRetry').textContent,b.w.I18N[lang].retry);
  }
});

test('delayed presets cannot overwrite a point obtained by an explicit locate click',async t=>{
  const presets=pending(),b=await boot(t,{url:'https://example.test/?preset=baiterek',staticFiles:{'presets.json':presets}});
  assert.equal(b.gps.calls.length,0);b.click('#geoBtn');b.gps.ok(pos());
  presets.resolve(json(JSON.parse(fs.readFileSync('frontend/presets.json','utf8'))));
  await tick();await tick();
  assert.equal(b.w.SeruenApp.state.loc.source,'gps');assert.equal(b.w.SeruenApp.state.loc.lat,51.15);
});

test('preset deep links still select their landmark without starting GPS',async t=>{
  const b=await boot(t,{url:'https://example.test/?preset=baiterek'});
  assert.equal(b.gps.calls.length,0);
  assert.equal(b.w.SeruenApp.state.preset,'baiterek');
  assert.equal(b.w.SeruenApp.state.loc.source,'preset');
});
