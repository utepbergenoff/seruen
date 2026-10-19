const {test}=require('node:test');
const assert=require('node:assert/strict');
const {boot}=require('./helpers.cjs');
const FX=require('./fixtures/feature_examples.json');
const settle=async()=>{for(let i=0;i<5;i++)await new Promise(r=>setImmediate(r));};

test('removed atmosphere UI and requests stay absent even if an older server advertises it',async t=>{
  const calls=[];
  const b=await boot(t,{healthData:{...FX.health_with_features,features:{...FX.health_with_features.features,atmosphere:1,atmosphere_profiles:1}},onFetch:url=>calls.push(url)});
  for(const lang of ['ru','en','kk']){
    b.click(`[data-lang="${lang}"]`);await settle();
    assert.equal(b.w.document.querySelector('#atmosphereOptions, #atmosField, [data-mood], [data-atmos]'),null);
    assert.doesNotMatch(b.w.document.body.textContent,/по атмосфере|choose an atmosphere|атмосфераны таңдау/i);
  }
  b.w.document.querySelector('#query').value='кофе';b.click('#goBtn');await settle();
  assert.equal(b.requests.length,1);
  assert.ok(!calls.some(url=>url.includes('/atmosphere/')));
  assert.doesNotMatch(JSON.stringify(b.requests[0].body),/atmosphere/);
  const response=structuredClone(FX.recommend_normal);
  response.recommendations[0].atmosphere_match={matched_features:['bright'],source:'manual'};
  b.requests[0].resolve({ok:true,json:async()=>response});await settle();
  assert.ok(b.w.document.querySelector('.rec'));
  assert.equal(b.w.document.querySelector('.atmos-unknown'),null);
  assert.ok(b.w.document.querySelector('#startWalkBtn'));
});
