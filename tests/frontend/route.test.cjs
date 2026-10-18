const {test}=require('node:test');
const assert=require('node:assert/strict');
const {planRoute}=require('../../frontend/route.js');
const start={lat:51.128,lon:71.43};
for(const budget of [15,30,60,90,120]) for(const speed of [60,75]) {
  test(`round trip stays inside ${budget} minutes at ${speed} m/min`,()=>{
    const places=[{lat:51.1285,lon:71.43,category:'park'},{lat:51.13,lon:71.431,category:'coffee'},{lat:51.131,lon:71.432,category:'culture'}];
    const p=planRoute(start,places,budget,speed);
    assert.equal(p.fits,true);assert.ok(p.total<=budget);assert.ok(p.back>0);
    assert.equal(p.total,p.legs.reduce((a,b)=>a+b,0)+p.back+p.stays.reduce((a,b)=>a+b,0));
  });
}

test('an impossible round trip is explicitly marked unfit',()=>{
  const p=planRoute(start,[{lat:51.2,lon:71.6,category:'park'}],15,60);
  assert.equal(p.fits,false);assert.ok(p.total>p.budget);
});
