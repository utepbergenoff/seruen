/* Pure route estimates: no network, no location storage. */
(function(root) {
  "use strict";
  const STAY = {coffee: 30, food: 40, park: 25, kids: 30, culture: 45, sight: 15, viewpoint: 20, shopping: 30, sport: 45, night: 45, work: 60};
  const hav = (a, b) => {
    const R = 6371000, r = Math.PI / 180, dp = (b.lat - a.lat) * r, dl = (b.lon - a.lon) * r;
    const x = Math.sin(dp / 2) ** 2 + Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin(dl / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(x));
  };
  function planRoute(start, places, budget, speed) {
    // 3 places of different categories with the best scores (cards are already the best per category)
    const pool = [], cats = new Set();
    for (const p of places) { if (pool.length < 3 && !cats.has(p.category)) { pool.push(p); cats.add(p.category); } }
    for (const p of places) { if (pool.length < 3 && !pool.includes(p)) pool.push(p); }
    let order = [], cur = start, todo = [...pool];
    while (todo.length) { todo.sort((a, b) => hav(cur, a) - hav(cur, b)); const n = todo.shift(); order.push(n); cur = n; }
    const walk = (a, b) => Math.max(1, Math.ceil(hav(a, b) * 1.3 / speed));
    for (;;) {
      const legs = []; let c = start;
      order.forEach((p) => { legs.push(walk(c, p)); c = p; });
      const back = walk(c, start);
      const walking = legs.reduce((a, b) => a + b, 0) + back;
      let stays = order.map((p) => STAY[p.category] || 25);
      const room = budget - walking;
      if (walking + stays.reduce((a, b) => a + b, 0) > budget && room >= 10 * order.length) {
        const k = room / stays.reduce((a, b) => a + b, 0);
        stays = stays.map((s) => Math.max(10, Math.floor(s * k)));
      }
      const total = walking + stays.reduce((a, b) => a + b, 0);
      if (total <= budget || order.length <= 1) return {order, legs, back, stays, walking, total, budget, fits: total <= budget};
      order = order.slice(0, -1);
    }
  }

  const api = {hav, planRoute};
  if (typeof module !== "undefined") module.exports = api;
  else root.SeruenRoute = api;
})(typeof window !== "undefined" ? window : globalThis);
