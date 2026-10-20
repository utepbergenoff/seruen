// «Мои места» names a place by its name, never by its catalog id (round 4).
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {boot} = require('./helpers.cjs');
const tick = () => new Promise(r => setImmediate(r));
const settle = async () => { for (let i = 0; i < 6; i++) await tick(); };
const json = (data) => ({ok: true, json: async () => data});
const place = (id, name, extra = {}) => ({poi_id: id, name, category: 'coffee', address: 'проспект Мангилик Ел, 55/1',
  coords: {lat: 51.0887, lon: 71.4155}, distance_m: 300, walk_min: 5, time_to_spend_min: 30, why: 'w', why_source: 'template',
  what_to_do: 'd', what_to_do_source: 'template', offline_allowed: false, ...extra});
const answer = (recs, nearby = []) => ({mode: 'no_ai', source: '2gis', recommendations: recs, nearby_places: nearby, notes: [], safety: [],
  considered: {time_budget_min: 60, candidates_found: recs.length}, disclaimer: 'test'});

test('my places: a saved 2GIS place keeps its name; old id-only rows get a known name or «Неизвестное место»', async t => {
  const b = await boot(t); await settle();
  const S = b.w.SeruenStore, mine = b.w.SeruenFeatures.mine;
  // rows saved by an older version: only the id and the mark
  for (const row of [{poi_id: '2gis_70000001114585277', want: true}, {poi_id: '2gis_70000001027813142', favorite: true}]) {
    mine.places.set(row.poi_id, await S.putPlace(row));
  }
  b.click('#goBtn'); await tick();
  b.requests[0].resolve(json(answer([place('2gis_70000001072135261', 'Coffee BOOM, сеть кофеен')],
    [place('2gis_70000001027813142', 'Starbucks', {address: 'Кабанбай батыр проспект, 62'})]))); await settle();
  b.click('.rec [data-keep="want"]'); await settle();

  // stored with its label (not its provider coordinates), so it is still named after a reload
  const saved = await S.getPlace('2gis_70000001072135261');
  assert.equal(saved.name, 'Coffee BOOM, сеть кофеен'); assert.equal(saved.category, 'coffee');
  assert.equal(saved.address, 'проспект Мангилик Ел, 55/1'); assert.equal(saved.coords, undefined);

  b.click('#mineBtn'); await settle();
  const box = b.w.document.querySelector('#mine'), text = box.textContent;
  assert.doesNotMatch(text, /2gis_\d+/);
  assert.match(text, /Coffee BOOM/); assert.match(text, /Сеть кофеен · проспект Мангилик Ел, 55\/1/);
  assert.match(text, /Starbucks/);  // the old row, named from the current answer
  assert.match(text, /Неизвестное место/);  // the old row nobody knows any more
  assert.equal(box.querySelectorAll('a[aria-label="Открыть в 2ГИС"]').length, 3);
  assert.ok(box.querySelector('[data-mine-del="2gis_70000001072135261"][aria-label="Удалить"]'));
  // the two settings are still checkboxes, shown as switches; the storage note sits at the bottom
  for (const id of ['onlyNew', 'mineOnMap']) {
    const input = box.querySelector('#' + id);
    assert.equal(input.type, 'checkbox'); assert.equal(input.getAttribute('role'), 'switch');
  }
  assert.ok(box.querySelector('.mine-foot .mine-device'));

  b.click('[data-lang="en"]'); await settle();
  assert.match(b.w.document.querySelector('#mine').textContent, /Unknown place/);
  b.click('[data-lang="kk"]'); await settle();
  assert.match(b.w.document.querySelector('#mine').textContent, /Белгісіз орын/);
});

test('my places: an old row saved with an empty name gets the name when it is marked again', async t => {
  const b = await boot(t); await settle();
  const S = b.w.SeruenStore, mine = b.w.SeruenFeatures.mine;
  mine.places.set('2gis_7', await S.putPlace({poi_id: '2gis_7', name: '', visited_at: 1760000000000}));
  b.click('#goBtn'); await tick();
  b.requests[0].resolve(json(answer([place('2gis_7', 'Монумент «Байтерек»', {category: 'sight'})]))); await settle();
  b.click('.rec [data-keep="favorite"]'); await settle();
  const row = await S.getPlace('2gis_7');
  assert.equal(row.name, 'Монумент «Байтерек»'); assert.equal(row.favorite, true); assert.equal(row.visited_at, 1760000000000);
});
