/* Night lights: on the dark map, places that are open right now glow like lit windows.
   «Right now» is the planner's time (the ?at= demo time) or the real time in Astana. Opening hours come from
   night-lights.json, built by scripts/build_night_lights.py with the server's own hours parser. Places without
   readable hours are not in that file, so nothing glows on a guess. */
(() => {
  "use strict";
  const A = window.SeruenApp, E = window.SeruenExt;
  if (!A || !window.L || !A.map.getPane?.("lights")) return;
  const {$, esc, fmt, map, state} = A, x = () => A.T().night;
  const SLOTS = 336, pad = (n) => String(n).padStart(2, "0");
  let data = null, loading = false, layer = null, lastKey = "";

  // half-hour slot of the week, Monday 00:00 = 0, in Astana time (UTC+5)
  function moment() {
    const at = $("#whenSel")?.value === "other" && $("#whenAt")?.value;
    let d;
    if (at) {
      const [y, m, day] = at.slice(0, 10).split("-").map(Number), [h, mi] = at.slice(11, 16).split(":").map(Number);
      d = new Date(Date.UTC(y, m - 1, day, h || 0, mi || 0));
    } else d = new Date(Date.now() + 5 * 3600e3);
    if (isNaN(d)) d = new Date(Date.now() + 5 * 3600e3);
    return {slot: ((d.getUTCDay() + 6) % 7) * 48 + d.getUTCHours() * 2 + (d.getUTCMinutes() >= 30 ? 1 : 0),
      label: pad(d.getUTCHours()) + ":" + pad(d.getUTCMinutes())};
  }
  const open = (week, i) => (parseInt(week[(i % SLOTS) >> 2], 16) >> (3 - (i % 4))) & 1;
  function closesAt(week, i) {
    for (let k = 1; k < SLOTS; k++) if (!open(week, i + k)) { const s = (i + k) % 48; return pad(s >> 1) + ":" + (s & 1 ? "30" : "00"); }
    return null;  // open the whole week
  }
  const nameOf = (p) => (state.lang === "en" && p.name_en) || (state.lang === "kk" && p.name_kk) || p.name;

  function draw(force = false) {
    const dark = document.documentElement.dataset.theme === "dark", t = moment();
    const key = [dark, t.slot, state.lang, !!data].join("|");
    if (!force && key === lastKey) return;
    lastKey = key;
    if (layer) { map.removeLayer(layer); layer = null; }
    const info = $("#nightInfo");
    if (!dark) { if (info) info.hidden = true; return; }
    if (!data) { load(); return; }
    layer = L.layerGroup();
    let lit = 0;
    for (const p of data.places) {
      if (!open(p.week, t.slot)) continue;
      lit++;
      const until = closesAt(p.week, t.slot), name = nameOf(p);
      const icon = L.divIcon({className: "", iconSize: [14, 14], iconAnchor: [7, 7], html: `<span class="night-light" data-cat="${esc(p.category)}"></span>`});
      L.marker([p.lat, p.lon], {icon, pane: "lights", title: name, alt: name, keyboard: false, riseOnHover: true})
        .bindPopup(`<b>${esc(name)}</b><br>${esc(A.catLabel(p.category))} · ${esc(until ? fmt(x().until, {t: until}) : x().allDay)}`
          + `<br><small>${esc(x().hours)}: ${esc(p.hours)} · ${esc(String(p.source || "").toUpperCase())}${p.checked ? ", " + esc(p.checked) : ""}</small>`)
        .addTo(layer);
    }
    layer.addTo(map);
    if (info) { info.hidden = false; info.innerHTML = `<i aria-hidden="true"></i><span>${esc(fmt(x().info, {n: lit, t: t.label}))}</span>`; }
  }
  function load() {
    if (loading) return;
    loading = true;
    fetch("night-lights.json").then((r) => (r.ok ? r.json() : null)).then((d) => {
      if (d && Array.isArray(d.places)) { data = d; draw(true); }
    }).catch(() => { /* offline without the file: the dark map simply has no lights */ }).finally(() => { loading = false; });
  }

  new MutationObserver(() => draw()).observe(document.documentElement, {attributes: true, attributeFilter: ["data-theme"]});
  for (const id of ["#whenSel", "#whenAt"]) $(id)?.addEventListener("change", () => draw());
  setInterval(() => draw(), 60000);
  const oldLang = E.onLang;
  E.onLang = (...args) => { oldLang?.(...args); draw(true); };
  draw(true);
})();
