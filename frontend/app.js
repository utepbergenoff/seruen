/* Серуен website: plain JavaScript + Leaflet, no build step (plan B of the team plan).
   Privacy: coordinates are rounded to 3 decimals (~100 m) here, before anything is sent,
   and only travel in POST bodies. Visited places and coins live in this browser only.
   The page works with any backend that follows docs/frontend_contract.md: optional fields
   (per-card budget, labels, candidates) are computed here when the backend does not send them. */
(() => {
  "use strict";
  const CFG = window.SERUEN_CONFIG || {};
  const FEAT = Object.assign({mapLinks: true, weather: true, route: true, languages: true, pirate: true, points: true}, CFG.FEATURES || {});
  const API = (CFG.API_URL || "").replace(/\/$/, "");
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const round3 = (x) => Math.round(x * 1000) / 1000;
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode: ignore */ } },
  };
  const params = new URLSearchParams(location.search);
  const ASTANA = {lat: 51.128, lon: 71.43};
  const STAY = {coffee: 30, food: 40, park: 25, kids: 30, culture: 45, sight: 15, viewpoint: 20, shopping: 30, sport: 45, night: 45, work: 60};

  const state = {
    lang: params.get("lang") || store.get("seruen_lang", "ru"),
    pirate: FEAT.pirate && (params.get("pirate") === "1" || store.get("seruen_pirate", false)),
    loc: {...ASTANA, source: "preset"}, preset: null,
    presets: [], scenarios: [], last: null, lastReq: null, lastWeather: null,
    showCands: false, extraCands: null, chipCtx: {}, apiMode: null,
  };
  if (!FEAT.languages && !params.get("lang")) state.lang = "ru";
  const T = () => window.I18N[state.lang] || window.I18N.ru;
  const fmt = (s, o) => String(s).replace(/\{(\w+)\}/g, (_, k) => (o[k] ?? ""));

  // ---------- map ----------
  const map = L.map("map", {zoomControl: true}).setView([state.loc.lat, state.loc.lon], 15);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(map);
  const me = L.marker([state.loc.lat, state.loc.lon], {draggable: true, zIndexOffset: 1000, keyboard: true,
    icon: L.divIcon({className: "", iconSize: [22, 22], iconAnchor: [11, 11], html: '<div class="me"></div>'})}).addTo(map);
  me.bindTooltip(T().youAreHere, {permanent: true, direction: "top", offset: [0, -12], className: "me-label"});
  me.on("dragend", () => { const p = me.getLatLng(); setLoc(p.lat, p.lng, "map", null, false); });
  map.on("click", (e) => setLoc(e.latlng.lat, e.latlng.lng, "map", null, false));
  // the map box gets its final size after CSS/layout: tell Leaflet, or tiles leave grey gaps
  const fixSize = () => map.invalidateSize();
  window.addEventListener("load", fixSize);
  if (window.ResizeObserver) new ResizeObserver(fixSize).observe($("#map"));
  setTimeout(fixSize, 300);
  const layer = L.layerGroup().addTo(map);
  let routeLine = null;
  const markers = {};

  function setLoc(lat, lon, source, presetId, pan = true) {
    state.loc = {lat, lon, source};
    state.preset = presetId;
    me.setLatLng([lat, lon]);
    if (pan) map.setView([lat, lon], Math.max(map.getZoom(), 15));
    $$("#presets button").forEach((b) => b.classList.toggle("on", b.dataset.id === presetId));
    $("#geoMsg").hidden = true;
  }

  // ---------- language ----------
  function applyLang() {
    const t = T();
    document.documentElement.lang = state.lang;
    $$("[data-i18n]").forEach((el) => { const v = t[el.dataset.i18n]; if (typeof v === "string") el.textContent = v; });
    $$("[data-i18n-placeholder]").forEach((el) => { el.placeholder = t[el.dataset.i18nPlaceholder]; });
    $$(".lang button").forEach((b) => b.classList.toggle("on", b.dataset.lang === state.lang));
    me.setTooltipContent(t.youAreHere);
    renderPresets(); renderChips(); renderScenarioMenu(); renderPoints(); renderModeBadge();
    if (state.last) render(state.last);
  }
  $$(".lang button").forEach((b) => b.addEventListener("click", () => {
    state.lang = b.dataset.lang; store.set("seruen_lang", state.lang); applyLang();
  }));

  // ---------- presets, chips, scenarios ----------
  const plabel = (p) => (p.label && (p.label[state.lang] || p.label.ru)) || p.id;
  function renderPresets() {
    $("#presets").innerHTML = state.presets.map((p) =>
      `<button type="button" data-id="${esc(p.id)}" class="${p.id === state.preset ? "on" : ""}">${esc(plabel(p))}</button>`).join("");
    $$("#presets button").forEach((b) => b.addEventListener("click", () => {
      const p = state.presets.find((x) => x.id === b.dataset.id);
      setLoc(p.lat, p.lon, "preset", p.id);
    }));
  }
  function renderChips() {
    $("#chips").innerHTML = T().chips.map((c, i) => `<button type="button" data-i="${i}">${esc(c[0])}</button>`).join("");
    $$("#chips button").forEach((b) => b.addEventListener("click", () => {
      const c = T().chips[+b.dataset.i];
      $("#query").value = c[1];
      state.chipCtx = {...(c[2] || {})};
      if (c[2] && c[2].companions) $("#companions").value = c[2].companions;
      ask();
    }));
  }
  function renderScenarioMenu() {
    $("#scenariosMenu").innerHTML = state.scenarios.map((s) => {
      const p = state.presets.find((x) => x.id === s.preset);
      const title = typeof s.title === "string" ? s.title : (s.title && (s.title[state.lang] || s.title.ru)) || s.id;
      return `<button type="button" role="menuitem" data-id="${esc(s.id)}"><b>${esc(s.id)}</b> · ${esc(title)}
        <small>${esc(p ? plabel(p) : "")}${p ? " — " : ""}«${esc(s.query)}»</small></button>`;
    }).join("");
    $$("#scenariosMenu button").forEach((b) => b.addEventListener("click", () => { toggleMenu(false); runScenario(b.dataset.id); }));
  }
  function toggleMenu(open) { $("#scenariosMenu").hidden = !open; $("#scenariosBtn").setAttribute("aria-expanded", String(open)); }
  $("#scenariosBtn").addEventListener("click", (e) => { e.stopPropagation(); toggleMenu($("#scenariosMenu").hidden); });
  document.addEventListener("click", (e) => { if (!e.target.closest(".dropdown")) toggleMenu(false); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") toggleMenu(false); });

  function runScenario(id) {
    const s = state.scenarios.find((x) => x.id === id);
    if (!s) return;
    const p = state.presets.find((x) => x.id === s.preset);
    if (p) setLoc(p.lat, p.lon, "preset", p.id);
    else if (s.location) setLoc(s.location.lat, s.location.lon, "preset", null);
    $("#query").value = s.query;
    const ctx = s.context || {};
    if (ctx.time_budget_min) { $("#budget").value = ctx.time_budget_min; $("#budgetOut").textContent = ctx.time_budget_min; $("#budgetAuto").checked = false; }
    if (ctx.now) { $("#whenSel").value = "other"; $("#whenAt").hidden = false; $("#whenAt").value = ctx.now.slice(0, 16); }
    else if (!params.get("at")) { $("#whenSel").value = "now"; $("#whenAt").hidden = true; }
    else { $("#whenSel").value = "other"; $("#whenAt").hidden = false; $("#whenAt").value = params.get("at").slice(0, 16); }
    $("#companions").value = ctx.companions || "alone";
    if (!ctx.time_budget_min) $("#budgetAuto").checked = true;
    state.chipCtx = {};
    ask();
  }

  // ---------- context ----------
  $("#budget").addEventListener("input", () => { $("#budgetOut").textContent = $("#budget").value; $("#budgetAuto").checked = false; });
  $("#whenSel").addEventListener("change", () => {
    const other = $("#whenSel").value === "other";
    $("#whenAt").hidden = !other;
    // default: today 23:00 Astana time (UTC+5), handy for showing the night scenario in the daytime
    if (other && !$("#whenAt").value) $("#whenAt").value = new Date(Date.now() + 5 * 3600e3).toISOString().slice(0, 11) + "23:00";
  });

  // weather (extra): Open-Meteo, no key. We ask for the city centre, never for the user's point.
  let weatherCache = {t: 0, v: null};
  async function liveWeather() {
    if (Date.now() - weatherCache.t < 15 * 60e3) return weatherCache.v;
    let v = null;
    try {
      const ctrl = new AbortController(); const timer = setTimeout(() => ctrl.abort(), 3000);
      const r = await fetch(`https://api.open-meteo.com/v1/forecast?latitude=${ASTANA.lat}&longitude=${ASTANA.lon}&current=temperature_2m,wind_speed_10m,precipitation&wind_speed_unit=ms&timezone=Asia%2FAlmaty`, {signal: ctrl.signal});
      clearTimeout(timer);
      const c = (await r.json()).current;
      v = {temp_c: c.temperature_2m, wind_ms: c.wind_speed_10m, precip_mm: c.precipitation || 0, source: "open-meteo"};
    } catch { v = null; }
    weatherCache = {t: Date.now(), v};
    return v;
  }
  async function weatherForRequest() {
    if (!FEAT.weather) return null;
    const w = $("#weather").value;
    if (w === "off") return null;
    if (w === "cold") return {temp_c: -22, wind_ms: 8, precip_mm: 0, simulated: true};
    if (w === "mild") return {temp_c: 14, wind_ms: 3, precip_mm: 0, simulated: true};
    return liveWeather();
  }
  const weatherBad = (w) => !!w && (w.temp_c <= -15 || w.wind_ms >= 10 || w.precip_mm >= 2);
  function weatherText(w) {
    const t = T();
    let s = `${w.temp_c > 0 ? "+" : ""}${Math.round(w.temp_c)} °C, ${t.wind} ${Math.round(w.wind_ms)} ${t.ms}`;
    if (weatherBad(w)) s += ` → ${t.indoorFirst}`;
    return s + (w.simulated ? ` · ${t.simulated}` : " · Open-Meteo");
  }

  async function context() {
    const ctx = {lang: "auto", mode: "walk", companions: $("#companions").value, accessibility: $("#access").checked};
    if (!$("#budgetAuto").checked) ctx.time_budget_min = +$("#budget").value;
    if ($("#whenSel").value === "other" && $("#whenAt").value) { ctx.now = $("#whenAt").value + ":00+05:00"; ctx.simulate = true; }
    const w = await weatherForRequest();
    state.lastWeather = w;  // the full object (with "simulated") stays here for the panel
    if (w) ctx.weather = {temp_c: w.temp_c, wind_ms: w.wind_ms, precip_mm: w.precip_mm};  // exactly the contract fields
    return Object.assign(ctx, state.chipCtx);
  }

  // ---------- geolocation ----------
  $("#geoBtn").addEventListener("click", () => {
    const msg = $("#geoMsg"); msg.hidden = true;
    const fail = (text) => { msg.textContent = text; msg.hidden = false; };
    if (!navigator.geolocation || !window.isSecureContext) return fail(T().geoDenied);
    $("#geoBtn").disabled = true;
    navigator.geolocation.getCurrentPosition((pos) => {
      $("#geoBtn").disabled = false;
      const lat = round3(pos.coords.latitude), lon = round3(pos.coords.longitude);  // rounded right away
      if (lat < 51.0 || lat > 51.25 || lon < 71.25 || lon > 71.65) { setLoc(ASTANA.lat, ASTANA.lon, "map", null); return fail(T().geoOutside); }
      setLoc(lat, lon, "gps", null);
    }, () => { $("#geoBtn").disabled = false; fail(T().geoDenied); }, {enableHighAccuracy: false, timeout: 10000, maximumAge: 60000});
  });

  // ---------- request ----------
  $("#askForm").addEventListener("submit", (e) => { e.preventDefault(); ask(); });
  $("#query").addEventListener("input", () => { state.chipCtx = {}; });

  async function postJSON(path, body, timeoutMs = 20000) {
    const ctrl = new AbortController(); const timer = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      const r = await fetch(API + path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body), signal: ctrl.signal});
      if (!r.ok) throw new Error("HTTP " + r.status);
      return await r.json();
    } finally { clearTimeout(timer); }
  }

  async function ask() {
    $("#status").innerHTML = `<div class="loading" role="status"><div class="spinner"></div>${esc(T().loading)}</div>`;
    $("#goBtn").disabled = true;
    try {
      const body = {location: {lat: round3(state.loc.lat), lon: round3(state.loc.lon), precision_m: 100, source: state.loc.source},
        query: $("#query").value.trim(), context: await context()};
      state.lastReq = body; state.extraCands = null; state.showCands = false;
      const data = await postJSON("/recommend", body);
      state.last = data;
      $("#status").innerHTML = "";
      render(data);
      if (window.matchMedia("(max-width: 860px)").matches) $("#results").scrollIntoView({behavior: "smooth", block: "start"});
    } catch (err) {
      $("#status").innerHTML = `<p class="msg err">${esc(T().serverDown)} <button type="button" class="btn small" id="retryBtn">${esc(T().retry)}</button></p>`;
      $("#retryBtn").addEventListener("click", ask);
    } finally { $("#goBtn").disabled = false; }
  }

  // ---------- helpers for contract fields ----------
  const catLabel = (c) => (T().cats && T().cats[c]) || c;
  const codeLabel = (k) => {
    const s = String(k);
    if (s.startsWith("category:")) return catLabel(s.slice(9));
    const key = s.replace(/^tag:/, "");
    return (T().codeL && T().codeL[key]) || key.replace(/_/g, " ");
  };
  const srcName = (s) => T().srcNames[s] || s;
  function cardBudget(r, d) {
    const total = (d.considered && (d.considered.effective_budget_min || d.considered.time_budget_min)) ||
      (d.budget_breakdown && d.budget_breakdown.budget_min) || 60;
    const own = r.budget || r.budget_breakdown;
    if (own) {
      const B = own.budget_min || total;
      return {...own, budget_min: B, fits: own.total_min <= B, spare_min: own.spare_min ?? B - own.total_min};
    }
    const t = 2 * r.walk_min + r.time_to_spend_min;
    return {walk_there_min: r.walk_min, stay_min: r.time_to_spend_min, walk_back_min: r.walk_min, total_min: t,
      budget_min: total, fits: t <= total, spare_min: total - t};
  }
  function links(r) {
    const {lat, lon} = r.coords;
    // destination only: the user's own location is never put into a link
    return {
      gis: `https://2gis.kz/astana/directions/tab/pedestrian/points/%7C${lon}%2C${lat}?m=${lon}%2C${lat}%2F17`,
      gisPlace: `https://2gis.kz/astana/search/${encodeURIComponent(r.name)}?m=${lon}%2C${lat}%2F17`,
      google: `https://www.google.com/maps/dir/?api=1&destination=${lat},${lon}&travelmode=walking`,
    };
  }
  function statusPill(st) {
    const t = T();
    let txt = t.status[st.state] || st.label || st.state;
    if (st.state === "open" || st.state === "likely_open") {
      if (st.closes_at) txt += ` ${t.closes} ${st.closes_at}`;
      if (st.source && st.source !== "none") txt += ` · ${srcName(st.source)}`;
      if (st.checked_at) txt += `, ${t.checked} ${st.checked_at}`;
    } else if (st.state === "unknown") txt += ` — ${t.hoursUnknownHint}`;
    return `<span class="status-pill st-${esc(st.state)}" title="${esc(st.hours || "")}${st.confidence ? " · " + esc(t.confidence) + ": " + esc(t.conf[st.confidence] || st.confidence) : ""}">${esc(txt)}</span>`;
  }
  const srcBadge = (src) => src === "ai" ? `<span class="badge ai">${esc(T().aiIdea)}</span>` : `<span class="badge tpl">${esc(T().template)}</span>`;
  function budgetBar(b) {
    const t = T(), tot = Math.max(b.budget_min || b.total_min, b.total_min);
    const pc = (x) => (100 * x / tot).toFixed(1) + "%";
    const line = fmt(t.budgetLine, {a: b.walk_there_min, b: b.stay_min, c: b.walk_back_min, t: b.total_min, B: b.budget_min});
    return `<div class="bar" aria-hidden="true"><span class="w" style="width:${pc(b.walk_there_min)}"></span><span class="s" style="width:${pc(b.stay_min)}"></span><span class="w" style="width:${pc(b.walk_back_min)}"></span></div>
      <div class="bar-cap">${esc(line)} ${b.total_min <= b.budget_min ? "✓" : "⚠"}${b.spare_min > 0 ? ` · ${esc(t.spare)} ${b.spare_min} ${esc(t.minutes)}` : ""}</div>`;
  }
  const visited = () => store.get("seruen_visited", {});
  function renderPoints() {
    if (!FEAT.points) { $("#points").textContent = ""; return; }
    const n = Object.keys(visited()).length * 10;
    $("#points").textContent = n ? `${T().points}: ${n} ${T().pointsUnit}` : "";
    $("#points").title = T().pointsHint;
  }
  function renderModeBadge(mode) {
    const m = mode || state.apiMode;
    $("#modeBadge").hidden = !m;
    if (m) { $("#modeBadge").className = `badge mode-${m}`; $("#modeBadge").textContent = T().modes[m] || m; }
  }

  // ---------- rendering ----------
  function render(d) {
    const t = T();
    layer.clearLayers(); if (routeLine) { map.removeLayer(routeLine); routeLine = null; }
    Object.keys(markers).forEach((k) => delete markers[k]);
    const recs = d.recommendations || [];
    renderModeBadge(d.mode);
    let html = `<div class="result-head"><span class="badge mode-${esc(d.mode)}">${esc(t.mode)}: ${esc(t.modes[d.mode] || d.mode)}${d.cached_from ? " (" + esc(t.modes[d.cached_from] || d.cached_from) + ")" : ""}</span>
      <span class="meta">${d.timing_ms != null ? esc(Math.round(d.timing_ms)) + " ms" : ""}</span></div>`;
    const notes = (d.notes || []).map((n) => `<div class="note info">${esc(n)}</div>`).join("") +
      (d.safety || []).map((n) => `<div class="note safety">${esc(n)}</div>`).join("");
    if (notes) html += `<div class="notes">${notes}</div>`;
    if (!recs.length) html += `<div class="card empty"><div class="big">🧭</div><h3>${esc(t.emptyTitle)}</h3><p class="meta">${esc(t.emptyHint)}</p></div>`;

    recs.forEach((r, i) => {
      const done = !!visited()[r.poi_id];
      const L2 = links(r);
      const b = cardBudget(r, d);
      const kind = r.kind_label || r.category_label || catLabel(r.category);
      const generated = /^generated/.test(r.description_source || "");
      // real descriptions (Wikipedia / OSM) are shown; generated ones are folded behind their honest label
      const desc = !r.description ? (generated ? `<div class="desc">${esc(t.descSrc.generated_from_tags)}</div>` : "")
        : generated ? `<details class="desc"><summary>${esc(t.descSrc.generated_from_tags)}</summary>${esc(r.description)}</details>`
        : `<div class="desc">${esc(r.description)} <span class="src">(${esc(t.descSrc[r.description_source] || r.description_source || "")})</span></div>`;
      const rating = r.rating ? ` · ★ ${esc(r.rating)}${r.rating_count ? " (" + esc(r.rating_count) + ")" : ""}` : "";
      const acc = r.accessibility && r.accessibility !== "unknown" ? (r.accessibility === "no" ? "" : "♿ ") + t.accessL[r.accessibility] : t.accessL.unknown;
      const tags = (r.tag_labels || []).map((x) => `<span class="tag">${esc(x)}</span>`).join("");
      html += `<article class="card rec" data-id="${esc(r.poi_id)}" tabindex="0" aria-label="${esc(r.name)}">
        <div class="rec-title"><span class="num">${i + 1}</span><div>
          <h3><a class="plain" href="${esc(L2.gisPlace)}" target="_blank" rel="noopener" title="${esc(t.openIn2gis)}">${esc(r.name)}</a> <span class="badge db">${esc(t.fromDb)}</span></h3>
          <div class="meta">${esc(kind)} · ${esc(r.distance_m)} ${esc(t.distance)} · 🚶 ${esc(r.walk_min)} ${esc(t.walk)}${rating}</div>
        </div></div>
        <div>${r.open_status ? statusPill(r.open_status) : ""}</div>
        <div class="field"><b>${esc(t.why)}:</b> ${esc(r.why)} ${srcBadge(r.why_source)}</div>
        <div class="field"><b>${esc(t.todo)}:</b> ${esc(r.what_to_do)} ${srcBadge(r.what_to_do_source)}</div>
        <div class="field">⏱ <b>${esc(t.stay)}:</b> ~${esc(r.time_to_spend_min)} ${esc(t.minutes)}</div>
        ${budgetBar(b)}
        ${desc}
        <div class="tags">${tags}<span class="tag">${esc(acc)}</span></div>
        <div class="src">${esc(t.sources)}: ${(r.sources || [r.facts_source || "poi_db"]).map(srcName).map(esc).join(", ")}${r.last_checked ? " · " + esc(r.last_checked) : ""}</div>
        <div class="actions">
          ${FEAT.mapLinks ? `<a class="btn" href="${esc(L2.gis)}" target="_blank" rel="noopener">🗺 ${esc(t.route2gis)}</a>
          <a class="btn" href="${esc(L2.google)}" target="_blank" rel="noopener">🧭 ${esc(t.routeGoogle)}</a>` : ""}
          <button type="button" class="btn" data-act="map">📍 ${esc(t.onMap)}</button>
          ${FEAT.points ? `<button type="button" class="btn" data-act="visit" ${done ? "disabled" : ""}>${done ? "✓ " + esc(t.visitedDone) : "🪙 " + esc(t.visited) + " +10"}</button>` : ""}
        </div>
      </article>`;
      const icon = state.pirate
        ? L.divIcon({className: "", iconSize: [34, 40], iconAnchor: [17, 34], html: `<div class="chest">💰<b>${i + 1}</b></div>`})
        : L.divIcon({className: "", iconSize: [30, 30], iconAnchor: [15, 30], html: `<div class="pin"><b>${i + 1}</b></div>`});
      markers[r.poi_id] = L.marker([r.coords.lat, r.coords.lon], {icon, title: r.name}).addTo(layer)
        .bindPopup(`<b>${i + 1}. ${esc(r.name)}</b><br>${esc(r.distance_m)} ${esc(t.distance)} · ${esc(r.walk_min)} ${esc(t.walk)}`);
    });
    if (FEAT.route && recs.length >= 2) html += `<button type="button" id="routeBtn" class="btn">🧭 ${esc(t.buildRoute)}</button><div id="routeBox"></div>`;
    html += considered(d);
    html += `<p class="foot">⚠️ ${esc(d.disclaimer || t.disclaimerShort)}</p>`;
    $("#results").innerHTML = html;

    if (recs.length) map.fitBounds(L.latLngBounds([[state.loc.lat, state.loc.lon], ...recs.map((r) => [r.coords.lat, r.coords.lon])]), {padding: [40, 40], maxZoom: 16});
    $$(".rec").forEach((el) => {
      const id = el.dataset.id;
      const focus = () => {
        const m = markers[id]; if (m) { map.setView(m.getLatLng(), Math.max(map.getZoom(), 16)); m.openPopup(); }
        $$(".rec").forEach((x) => x.classList.toggle("active", x === el));
        if (window.matchMedia("(max-width: 860px)").matches) $("#map").scrollIntoView({behavior: "smooth"});
      };
      el.addEventListener("click", (e) => { if (!e.target.closest("a,button")) focus(); });
      el.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target === el) focus(); });
      el.querySelector('[data-act="map"]').addEventListener("click", focus);
      const v = el.querySelector('[data-act="visit"]');
      if (v) v.addEventListener("click", () => {
        const all = visited(); all[id] = Date.now(); store.set("seruen_visited", all); renderPoints();
        v.disabled = true; v.textContent = "✓ " + T().visitedDone;
      });
    });
    const rb = $("#routeBtn"); if (rb) rb.addEventListener("click", buildRoute);
    const cb = $("#candBtn"); if (cb) cb.addEventListener("click", toggleCands);
    if (state.pirate && recs.length) { $("#captain").textContent = t.captain[Math.floor(Math.random() * t.captain.length)]; $("#captain").hidden = false; }
    else $("#captain").hidden = true;
  }

  async function toggleCands() {
    state.showCands = !state.showCands;
    const d = state.last;
    // backend may put candidates into /recommend; otherwise ask /candidates (POST: coordinates stay out of URLs)
    if (state.showCands && !(d.candidates && d.candidates.length) && !state.extraCands) {
      try { state.extraCands = await postJSON("/candidates", state.lastReq); } catch { state.extraCands = {candidates: [], excluded: []}; }
    }
    render(d);
    const p = $("#consideredBox"); if (p && state.showCands) p.scrollIntoView({behavior: "smooth", block: "nearest"});
  }

  function considered(d) {
    const t = T(), c = d.considered || {};
    const rows = [];
    const add = (k, v) => { if (v !== undefined && v !== null && v !== "") rows.push(`<dt>${esc(k)}</dt><dd>${v}</dd>`); };
    const lr = state.lastReq ? state.lastReq.location : null;
    const loc = c.location || lr;
    if (loc) add(t.loc, `${esc(loc.lat)}, ${esc(loc.lon)} (±${esc(c.location_rounded_to_m || 100)} ${esc(t.distance)})`);
    if (c.radius_m) add(t.radius, `${esc(c.radius_m)} ${esc(t.distance)}${c.radius_expanded ? " — " + esc(t.expanded) : ""}`);
    const bb = d.budget_breakdown;
    if (c.time_budget_min || bb) {
      const eff = c.effective_budget_min || c.time_budget_min;
      let v = eff ? `${esc(eff)} ${esc(t.minutes)}` : "";
      if (c.effective_budget_min && c.time_budget_min && c.effective_budget_min !== c.time_budget_min) v += ` (${esc(c.time_budget_min)} − ${esc(c.time_budget_min - c.effective_budget_min)})`;
      if (bb) v += ` · ${esc(fmt(t.budgetLine, {a: bb.walk_there_min, b: bb.stay_min, c: bb.walk_back_min, t: bb.total_min, B: bb.budget_min || eff || ""}))}`;
      add(t.budgetL, v);
    }
    if (c.time) add(t.time, `${esc(c.time)}${c.time_simulated || c.time_shift ? " · " + esc(t.simulated) : ""}`);
    if (c.goal || (c.categories && c.categories.length)) add(t.goal, `${esc(c.goal || "")}${c.categories && c.categories.length ? " → " + esc(c.categories.join(", ")) : ""}${c.tags && c.tags.length ? " · " + esc(c.tags.join(", ")) : ""}`);
    if (c.filters && c.filters.length) add(t.filters, esc(c.filters.map(codeLabel).join("; ")));
    if (c.walk_speed_m_per_min) add(t.speed, `${esc(c.walk_speed_m_per_min)} ${esc(t.mPerMin)} × ${esc(c.street_factor || 1.3)}`);
    const w = c.weather && c.weather.temp_c !== undefined ? {...c.weather, wind_ms: c.weather.wind_ms ?? (c.weather.wind_kmh ? c.weather.wind_kmh / 3.6 : 0)} : state.lastWeather;
    if (FEAT.weather && w) add(t.weatherL, esc(weatherText(w)));
    add(t.found, esc(c.candidates_found ?? (d.candidates || []).length));
    add(t.mode, esc(t.modes[d.mode] || d.mode));
    if (c.data_snapshot) add(t.snapshot, `${esc(c.data_snapshot)}${c.places_in_database ? " · " + esc(c.places_in_database) + " " + esc(t.places) : ""}`);
    let cands = "";
    if (state.showCands) {
      const src = (d.candidates && d.candidates.length) ? d : (state.extraCands || {});
      const cl = src.candidates || [], ex = src.excluded || [];
      cands = `<h3 class="sub">${esc(t.cands)} (${cl.length})</h3><p class="meta">${esc(t.candsHint)}</p><div class="tbl"><table class="cands"><tr><th>#</th><th></th><th>${esc(t.distance)}</th><th>${esc(t.score)}</th></tr>` +
        cl.map((x, i) => `<tr><td>${i + 1}</td><td>${esc(x.name)}<br><span class="meta">${esc(x.category_label || catLabel(x.category))}${(x.reasons || []).length ? " · " + esc(x.reasons.map(codeLabel).join(", ")) : ""}</span></td><td>${esc(x.distance_m)}</td><td>${x.score != null ? esc(Number(x.score).toFixed(2)) : ""}</td></tr>`).join("") +
        `</table></div>` + (ex.length ? `<h3 class="sub">${esc(t.excluded)}</h3><div class="tbl"><table class="cands">` +
        ex.map((x) => `<tr><td>${esc(x.name)}<br><span class="meta">${esc(x.category_label || catLabel(x.category))} · ${esc(x.distance_m)} ${esc(t.distance)}</span></td><td>${esc(x.excluded_label || codeLabel(x.excluded_because))}</td></tr>`).join("") + "</table></div>" : "");
    }
    const any = (d.candidates || []).length || (d.excluded || []).length || c.candidates_found;
    return `<section class="card considered" id="consideredBox"><h3>🔎 ${esc(t.considered)}</h3><dl class="kv">${rows.join("")}</dl>
      ${any ? `<button type="button" id="candBtn" class="btn small" aria-expanded="${state.showCands}">${esc(state.showCands ? t.hideCands : t.showCands)}</button>` : ""}${cands}</section>`;
  }

  // ---------- mini-route (extra): computed in the browser, the backend is not touched ----------
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
  async function osrmLine(points) {
    try {
      const coords = points.map((p) => `${p.lon},${p.lat}`).join(";");
      const ctrl = new AbortController(); const timer = setTimeout(() => ctrl.abort(), 4000);
      const r = await fetch(`${CFG.OSRM_URL || "https://router.project-osrm.org"}/route/v1/foot/${coords}?overview=full&geometries=geojson`, {signal: ctrl.signal});
      clearTimeout(timer);
      const j = await r.json();
      if (j.code !== "Ok") throw new Error(j.code);
      return {line: j.routes[0].geometry.coordinates.map(([lon, lat]) => [lat, lon]), osrm: true};
    } catch { return {line: points.map((p) => [p.lat, p.lon]), osrm: false}; }
  }
  async function buildRoute() {
    const d = state.last, t = T();
    const c = d.considered || {};
    const budget = c.effective_budget_min || c.time_budget_min || (d.budget_breakdown && d.budget_breakdown.budget_min) || 60;
    const speed = c.walk_speed_m_per_min || ((c.companions || state.lastReq.context.companions) === "child" ? 60 : 75);
    const start = {lat: state.lastReq.location.lat, lon: state.lastReq.location.lon};
    const places = d.recommendations.map((r) => ({poi_id: r.poi_id, name: r.name, category: r.category, lat: r.coords.lat, lon: r.coords.lon}));
    const plan = planRoute(start, places, budget, speed);
    $("#routeBox").innerHTML = `<div class="loading"><div class="spinner"></div>${esc(t.loading)}</div>`;
    const geo = await osrmLine([start, ...plan.order, start]);
    if (routeLine) map.removeLayer(routeLine);
    routeLine = L.polyline(geo.line, {color: state.pirate ? "#7c2d12" : "#0f766e", weight: 4, dashArray: geo.osrm ? null : "8 8", opacity: .85}).addTo(map);
    map.fitBounds(routeLine.getBounds(), {padding: [40, 40]});
    const pts = plan.order.map((p) => `${p.lon}%2C${p.lat}`).join("%7C");
    const gis = `https://2gis.kz/astana/directions/tab/pedestrian/points/%7C${pts}?m=${plan.order[0].lon}%2C${plan.order[0].lat}%2F15`;
    const last = plan.order[plan.order.length - 1];
    const way = plan.order.slice(0, -1).map((p) => `${p.lat},${p.lon}`).join("%7C");
    const google = `https://www.google.com/maps/dir/?api=1&destination=${last.lat},${last.lon}&travelmode=walking${way ? "&waypoints=" + way : ""}`;
    const steps = plan.order.map((p, i) => `<li>${esc(p.name)} — 🚶 ${plan.legs[i]} + ⏱ ${plan.stays[i]} ${esc(t.minutes)}</li>`).join("");
    $("#routeBox").innerHTML = `<div class="card route"><h3>${esc(t.routeTitle)}: ${plan.total} / ${plan.budget} ${esc(t.minutes)} ${plan.fits ? "✓" : "⚠"}</h3>
      <ol class="meta">${steps}<li>↩ ${plan.back} ${esc(t.minutes)}</li></ol>
      <p class="meta">${esc(geo.osrm ? t.routeOsrm : t.routeStraight)}</p>
      <div class="actions"><a class="btn small" target="_blank" rel="noopener" href="${esc(gis)}">🗺 ${esc(t.route2gis)}</a>
      <a class="btn small" target="_blank" rel="noopener" href="${esc(google)}">🧭 ${esc(t.routeGoogle)}</a></div></div>`;
  }

  // ---------- pirate theme (extra) ----------
  function applyPirate() {
    document.documentElement.classList.toggle("pirate", state.pirate);
    $("#pirateBtn").setAttribute("aria-pressed", String(state.pirate));
    if (state.pirate && !document.getElementById("pirateFont")) {
      const l = document.createElement("link"); l.id = "pirateFont"; l.rel = "stylesheet";
      l.href = "https://fonts.googleapis.com/css2?family=Pirata+One&display=swap"; document.head.appendChild(l);
    }
    if (state.last) render(state.last);
  }
  $("#pirateBtn").addEventListener("click", () => { state.pirate = !state.pirate; store.set("seruen_pirate", state.pirate); applyPirate(); });

  // ---------- start ----------
  async function getJSON(url) { const r = await fetch(url); if (!r.ok) throw new Error(r.status); return r.json(); }
  async function init() {
    if (!FEAT.languages) $(".lang").hidden = true;
    if (!FEAT.pirate) $("#pirateBtn").hidden = true;
    if (!FEAT.weather) $("#weatherField").hidden = true;
    try { state.presets = await getJSON("presets.json"); } catch { state.presets = []; }
    try { state.scenarios = await getJSON(API + "/scenarios"); } catch { state.scenarios = []; }
    if (!state.scenarios.length) { try { state.scenarios = await getJSON("scenarios.json"); } catch { /* menu stays empty */ } }
    // accept both {"query": "text"} and {"query": {"q": "text"}} from the backend
    state.scenarios = state.scenarios.map((x) => {
      const req = x.request || {};
      const loc = req.location || x.location || null;
      const query = req.query ?? (typeof x.query === "object" && x.query ? (x.query.q || "") : (x.query || ""));
      let preset = x.preset || null;
      if (!preset && loc) {  // use our preset button if the scenario's point is next to it (< 500 m)
        const near = state.presets.map((p) => ({id: p.id, d: hav(p, loc)})).sort((a, b) => a.d - b.d)[0];
        if (near && near.d < 500) preset = near.id;
      }
      return {...x, preset, location: loc, query, context: req.context || x.context || {}};
    });
    try {
      const h = await getJSON(API + "/health");
      const avail = h.mode_available || [];
      state.apiMode = h.ai === "gemini" || avail.includes("ai") ? "ai" : h.ai === "no_ai" || avail.includes("no_ai") ? "no_ai" : (h.mode || null);
      const snap = h.data_snapshot || h.data_snapshot_date, places = h.places || h.poi_count;
      if (snap) $("#snapshot").textContent = `· ${T().snapshot}: ${snap}${places ? " (" + places + ")" : ""}`;
    } catch { $("#status").innerHTML = `<p class="msg err">${esc(T().serverDown)}</p>`; }
    const p0 = state.presets.find((x) => x.id === (params.get("preset") || "baiterek"));
    if (p0) setLoc(p0.lat, p0.lon, "preset", p0.id);
    applyLang(); applyPirate();
    if (FEAT.weather) liveWeather();  // warm up, so the first answer is not slowed down
    if (params.get("at")) {  // simulated time for demos and screenshots, e.g. ?at=2026-10-18T15:00
      $("#whenSel").value = "other"; $("#whenAt").hidden = false; $("#whenAt").value = params.get("at").slice(0, 16);
    }
    if (params.get("scenario")) runScenario(params.get("scenario").toUpperCase());
    else if (params.get("chip") !== null) $$("#chips button")[+params.get("chip")]?.click();
    if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost")) {
      navigator.serviceWorker.register("sw.js").catch(() => {});
    }
  }
  init();
})();
