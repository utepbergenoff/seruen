const {test}=require('node:test');
const assert=require('node:assert/strict');
const {boot}=require('./helpers.cjs');
const FX=require('./fixtures/feature_examples.json');
const settle=async()=>{for(let i=0;i<8;i++)await new Promise(r=>setImmediate(r));};
const json=x=>({ok:true,json:async()=>x});
const coffee=()=>({...structuredClone(FX.recommend_normal.recommendations[0]),
  poi_id:'team_cafe_coffeeboom_expo',name:'Coffee BOOM (EXPO, Мангилик Ел 55/1)',
  coords:{lat:51.088679,lon:71.41551},rating:null,
  links:{'2gis':'https://2gis.kz/astana/firm/70000001072135261'}});
async function answer(b, extra={}) {
  b.click('#goBtn');await settle();
  b.requests[0].resolve(json({...structuredClone(FX.recommend_normal),recommendations:[coffee()],...extra}));
  await settle();
}

test('Coffee BOOM uses one exact branch for the marker, card, directions and external reviews in every language',async t=>{
  const b=await boot(t,{healthData:{...FX.health_with_features,twogis:{enabled:true,last_status:'twogis_access_denied'}}});
  await answer(b);
  for(const lang of ['ru','en','kk']) {
    b.click(`[data-lang="${lang}"]`);await settle();
    const c=b.w.document.querySelector('.rec');
    assert.equal(c.querySelector('h3 a').href,coffee().links['2gis']);
    assert.equal(c.querySelector('[data-gis-reviews]').href,coffee().links['2gis']+'/tab/reviews');
    assert.ok([...c.querySelectorAll('a')].some(a=>a.href.includes('destination=51.088679,71.41551')));
    const pin=b.pins.filter(p=>p.options?.title===coffee().name).at(-1);
    assert.deepEqual(Array.from(pin.coords),[51.088679,71.41551]);
    assert.equal(b.gis.length,0); // no denied calls or substitute rating
  }
});

test('restored provider is available despite the previous release six-hour browser flag',async t=>{
  const b=await boot(t,{storage:{seruen_gis_refused:Date.now()},
    healthData:{mode_available:['no_ai'],twogis:{enabled:true,last_status:'ok'}}});
  await answer(b);
  assert.ok(b.w.document.querySelector('.rec [data-act="gis"]'));
  assert.equal(b.w.localStorage.getItem('seruen_gis_refused'),null);
});

test('a refused auto search immediately offers reviews without another failed API request',async t=>{
  const b=await boot(t,{healthData:{mode_available:['no_ai'],twogis:{enabled:true,last_status:'not_checked'}}});
  await answer(b,{source:'local',source_error:'twogis_access_denied'});
  assert.equal(b.w.document.querySelector('.rec [data-act="gis"]'),null);
  assert.equal(b.w.document.querySelector('[data-gis-reviews]').href,coffee().links['2gis']+'/tab/reviews');
  assert.equal(b.gis.length,0);
  b.click('.rec [data-act="map"]');await settle();
  assert.ok(b.w.document.querySelector('#selectedPlaceCard [data-gis-reviews]'));
});
