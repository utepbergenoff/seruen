/* Серуен website: plain JavaScript + Leaflet, no build step (plan B of the team plan).
   Privacy: coordinates are rounded to 3 decimals (~100 m) here, before anything is sent,
   and only travel in POST bodies. Personal places and saved walks live on this device only (storage.js).
   The page works with any backend that follows docs/api.md: optional fields
   (per-card budget, labels, candidates) are computed here when the backend does not send them. */
(() => {
  "use strict";
  const CFG = window.SERUEN_CONFIG || {};
  const FEAT = Object.assign({mapLinks: true, weather: true, route: true, languages: true, twogis: true, photos: true}, CFG.FEATURES || {});
  // extension points filled by features.js (my places, saved walks, the eight-feature UI); every hook is optional
  const ext = window.SeruenExt = window.SeruenExt || {};
  const API = (CFG.API_URL || "").replace(/\/$/, "");
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));
  const icon = (n) => `<svg class="ic" aria-hidden="true"><use href="#i-${n}"/></svg>`;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const round3 = (x) => Math.round(x * 1000) / 1000;
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode: ignore */ } },
  };
  const params = new URLSearchParams(location.search);
  const ASTANA = {lat: 51.128, lon: 71.43};

  const state = {
    lang: params.get("lang") || store.get("seruen_lang", "ru"),
    loc: {...ASTANA, source: "map"}, locKind: "center", locating: false, geoMessage: null, locVersion: 0, requestVersion: 0, preset: null,
    presets: [], scenarios: [], last: null, lastReq: null, lastWeather: null,
    showCands: false, extraCands: null, chipCtx: {}, apiMode: null, gis: {}, photos: {}, photoPending: {}, features: {},
    selectedPlaceId: null, mapMode: null, mapError: false,
  };
  if (!FEAT.languages && !params.get("lang")) state.lang = "ru";
  const T = () => window.I18N[state.lang] || window.I18N.ru;
  const fmt = (s, o) => String(s).replace(/\{(\w+)\}/g, (_, k) => (o[k] ?? ""));

  // ---------- map ----------
  const map = L.map("map", {zoomControl: true}).setView([state.loc.lat, state.loc.lon], 15);
  const fitTo = (bounds, opts = {}) => map.fitBounds(bounds, {padding: [48, 48], ...opts, maxZoom: state.mapMode === "streets" ? 19 : 14});
  const showAt = (latlng, zoom) => map.setView(latlng, Math.min(zoom, state.mapMode === "streets" ? 19 : 14));
  let baseTiles = [], tileVersion = 0;
  function renderMapControls() {
    $("#mapMode").value = state.mapMode;
    $("#mapNotice").hidden = !state.mapError && state.mapMode === "streets";
    $("#mapNotice").textContent = state.mapError ? T().mapLayerError : T().mapSatelliteHint;
    $("#mapDetailBtn").hidden = state.mapMode === "streets";
    const mode = window.SeruenTheme?.mode || "system";
    $("#themeBtn").textContent = "◐ " + T().themeModes[mode];
    $("#themeBtn").title = T().themeSwitch;
    $("#themeBtn").setAttribute("aria-label", T().themeSwitch + ": " + T().themeModes[mode]);
  }
  function setMapMode(mode) {
    if (!["streets", "satellite", "hybrid"].includes(mode)) mode = "streets";
    const version = ++tileVersion; let errors = 0;
    baseTiles.forEach(l => map.removeLayer(l)); baseTiles = [];
    state.mapMode = mode; state.mapError = false;
    // Sentinel-2 is 10 m imagery: never enlarge overview pixels to building-level zoom.
    map.setMaxZoom?.(mode === "streets" ? 19 : 14);
    store.set("seruen_map_mode", mode); $("#map").dataset.mode = mode;
    const add = (url, options) => {
      const tile = L.tileLayer(url, {maxZoom: mode === "streets" ? 19 : 14, ...options});
      tile.on("tileerror", () => {
        if (version !== tileVersion) return;
        if (++errors >= 3 && mode !== "streets") setMapMode("streets");
        state.mapError = true; renderMapControls();
      });
      baseTiles.push(tile); tile.addTo(map);
    };
    const osm = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
    if (mode === "streets") add("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {attribution: osm});
    else {
      // EOX's public non-commercial layer: no key, billing account or offline tile download.
      const root = "https://tiles.maps.eox.at/wmts/1.0.0/";
      add(root + "s2cloudless-2025_3857/default/g/{z}/{y}/{x}.jpg", {maxNativeZoom: 14,
        attribution: '<a href="https://cloudless.eox.at">EOxCloudless</a> by <a href="https://eox.at">EOX IT Services GmbH</a> (Contains modified Copernicus Sentinel data 2025) · <a href="https://creativecommons.org/licenses/by-nc-sa/4.0/">CC BY-NC-SA</a>'});
      if (mode === "hybrid") add(root + "overlay_bright_3857/default/g/{z}/{y}/{x}.png", {maxNativeZoom: 14,
        attribution: osm + ' · <a href="https://maps.eox.at">EOX::Maps</a> / MapServer'});
    }
    renderMapControls();
  }
  $("#mapMode").addEventListener("change", e => setMapMode(e.target.value));
  $("#mapDetailBtn").addEventListener("click", () => setMapMode("streets"));
  $("#themeBtn").addEventListener("click", () => { window.SeruenTheme?.cycle(); renderMapControls(); });
  setMapMode(store.get("seruen_map_mode", "streets"));
  const meIcon = () => L.divIcon({className: "", iconSize: [22, 22], iconAnchor: [11, 11], html: '<div class="me"></div>'});
  const me = L.marker([state.loc.lat, state.loc.lon], {draggable: true, zIndexOffset: 1000, keyboard: true, icon: meIcon()}).addTo(map);
  me.bindTooltip(T().youAreHere, {permanent: true, direction: "top", offset: [0, -14], className: "me-label"});
  me.on("dragend", () => { const p = me.getLatLng(); setLoc(p.lat, p.lng, "map", null, false); });
  map.on("click", (e) => { if (ext.onMapClick && ext.onMapClick(e)) return; setLoc(e.latlng.lat, e.latlng.lng, "map", null, false); });
  // the map box gets its final size after CSS/layout: tell Leaflet, or tiles leave grey gaps
  const fixSize = () => map.invalidateSize();
  window.addEventListener("load", fixSize);
  if (window.ResizeObserver) new ResizeObserver(fixSize).observe($("#map"));
  if (window.ResizeObserver) new ResizeObserver(entries => {
    document.documentElement.style.setProperty("--header-h", entries[0].target.getBoundingClientRect().height + "px");
  }).observe($(".top"));
  setTimeout(fixSize, 300);
  const layer = L.layerGroup().addTo(map);
  const suggestionRoutes = L.layerGroup().addTo(map);
  let routeLine = null;
  const markers = {};
  function setWalkActive(active) {
    state.walkActive = !!active;
    document.body.classList.toggle("walk-active", !!active);
    if (active) $("#scenariosMenu").hidden = true;
    if (active) {
      map.removeLayer(suggestionRoutes);
      if (routeLine) { map.removeLayer(routeLine); routeLine = null; }
    } else suggestionRoutes.addTo(map);
  }

  // source goes to the backend (gps | map | preset); locKind is only for the line under the title
  function cancelLocation() {
    state.locVersion++; state.locating = false;
    clearTimeout(state.locTimer); clearTimeout(state.locHintTimer);
    if (state.geoMessage === "geoSlow") state.geoMessage = null;
  }
  function setLoc(lat, lon, source, presetId, pan = true, kind = null) {
    cancelLocation(); state.geoMessage = null;
    state.loc = {lat: round3(lat), lon: round3(lon), source};
    state.preset = presetId;
    state.locKind = kind || source;
    me.setLatLng([lat, lon]);
    if (pan) showAt([lat, lon], Math.max(map.getZoom(), 15));
    renderLocLine();
  }
  // ---------- language ----------
  function applyLang() {
    const t = T();
    document.documentElement.lang = state.lang;
    $$("[data-i18n]").forEach((el) => { const v = t[el.dataset.i18n]; if (typeof v === "string") el.textContent = v; });
    $$("[data-i18n-placeholder]").forEach((el) => { el.placeholder = t[el.dataset.i18nPlaceholder]; });
    $$(".lang button").forEach((b) => b.classList.toggle("on", b.dataset.lang === state.lang));
    me.setTooltipContent(t.youAreHere);
    renderMapControls();
    renderChips(); renderScenarioMenu(); renderScenarioStrip(); renderModeBadge(); renderLocLine();
    if (ext.onLang) ext.onLang();
    const gb = $("#geoBtn"); if (gb) { gb.title = t.myLocation; gb.setAttribute("aria-label", t.myLocation); }
    if (state.last) render(state.last);
  }
  $$(".lang button").forEach((b) => b.addEventListener("click", () => {
    state.lang = b.dataset.lang; store.set("seruen_lang", state.lang); applyLang();
  }));

  // ---------- presets, chips, scenarios ----------
  const plabel = (p) => (p.label && (p.label[state.lang] || p.label.ru)) || p.id;
  // quick requests as photo tiles (photos: Wikimedia Commons / CC0, credits on the About page)
  const CHIP_PHOTOS = ["coffee", "walk", "kids", "unusual", "flight", "night"];
  function renderChips() {
    $("#chips").innerHTML = T().chips.map((c, i) => {
      const label = c[0].replace(/^[^\p{L}\p{N}]+/u, "");
      const ph = CHIP_PHOTOS[i];
      return `<button type="button" class="tile" data-i="${i}">${ph ? `<img src="img/cat-${ph}.jpg" alt="" decoding="async">` : ""}<span>${esc(label)}</span></button>`;
    }).join("");
    $$("#chips button").forEach((b) => b.addEventListener("click", () => {
      const c = T().chips[+b.dataset.i];
      $("#query").value = c[1]; fitQuery();
      state.chipCtx = {...(c[2] || {})};
      // "with a child" from a tile applies to that tile only: the next tile goes back to the person's own choice
      if (c[2] && c[2].companions) { $("#companions").value = c[2].companions; state.compFromTile = true; }
      else if (state.compFromTile) { $("#companions").value = state.companionsChoice || "alone"; state.compFromTile = false; }
      ask();
    }));
  }
  function renderScenarioMenu() {
    $("#scenariosMenu").innerHTML = state.scenarios.map((s) => {
      const p = state.presets.find((x) => x.id === s.preset);
      const title = typeof s.title === "string" ? s.title : (s.title && (s.title[state.lang] || s.title.ru)) || s.id;
      return `<button type="button" role="menuitem" data-id="${esc(s.id)}"><img src="img/${scenarioPhoto(s)}.jpg" alt="" loading="lazy" decoding="async">
        <span class="menu-text"><b>${esc(s.id)}</b> · ${esc(title)}
        <small>${esc(p ? plabel(p) : "")}${p ? " — " : ""}«${esc(s.query)}»</small></span></button>`;
    }).join("");
    $$("#scenariosMenu button").forEach((b) => b.addEventListener("click", () => { toggleMenu(false); runScenario(b.dataset.id); }));
  }
  // ready-made scenarios as photo cards (photos of the real locations)
  const LOC_PHOTO = {expo: "loc-expo", khan: "loc-khan", mega: "loc-mega", baiterek: "loc-baiterek", nurly: "cat-flight", airport: "loc-airport"};
  function scenarioPhoto(s) {
    const hour = s.context && s.context.now ? +String(s.context.now).slice(11, 13) : 12;
    if (hour >= 21 || hour < 5) return "cat-night";
    // the Expo "unusual" scenario gets the Nur Alem sphere (also at Expo), so the two Expo cards differ
    if (s.preset === "expo" && /необыч|unusual|ерекше/i.test(`${s.query} ${typeof s.title === "string" ? s.title : ""}`)) return "cat-unusual";
    return LOC_PHOTO[s.preset] || "hero-baiterek-night";
  }
  // the same scenarios used to repeat here as cards; they now live only in the header menu (with photos)
  function renderScenarioStrip() {
    $("#scenarioStrip").hidden = true; $("#scenarioCards").innerHTML = "";
  }
  // the search box shows the whole request: it grows line by line (up to a limit, then scrolls)
  function fitQuery() {
    const q = $("#query"); if (!q) return;
    q.style.height = "";
    if (q.value && q.scrollHeight > q.clientHeight) q.style.height = Math.min(q.scrollHeight + 3, 260) + "px";
  }
  function toggleMenu(open) { $("#scenariosMenu").hidden = !open; $("#scenariosBtn").setAttribute("aria-expanded", String(open)); }
  $("#scenariosBtn").addEventListener("click", (e) => { e.stopPropagation(); toggleMenu($("#scenariosMenu").hidden); });
  document.addEventListener("click", (e) => { if (!e.target.closest(".dropdown")) toggleMenu(false); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") toggleMenu(false); });

  function runScenario(id) {
    const s = state.scenarios.find((x) => x.id === id);
    if (!s) return;
    ext.onScenario?.();
    const p = state.presets.find((x) => x.id === s.preset);
    if (p) setLoc(p.lat, p.lon, "preset", p.id);
    else if (s.location) setLoc(s.location.lat, s.location.lon, "preset", null);
    $("#query").value = s.query; fitQuery();
    const ctx = s.context || {};
    $("#weather").value = "auto"; $("#access").checked = !!ctx.accessibility;
    if (ctx.time_budget_min) { $("#budget").value = ctx.time_budget_min; $("#budgetOut").textContent = ctx.time_budget_min; $("#budgetAuto").checked = false; }
    if (ctx.now) { $("#whenSel").value = "other"; $("#whenAt").hidden = false; $("#whenAt").value = ctx.now.slice(0, 16); }
    else if (!params.get("at")) { $("#whenSel").value = "now"; $("#whenAt").hidden = true; }
    else { $("#whenSel").value = "other"; $("#whenAt").hidden = false; $("#whenAt").value = params.get("at").slice(0, 16); }
    $("#companions").value = ctx.companions || "alone";
    state.compFromTile = $("#companions").value !== "alone";  // set by the scenario, not by the person
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
    Object.assign(ctx, state.chipCtx, {companions:$("#companions").value, accessibility:$("#access").checked});
    if (!$("#budgetAuto").checked) ctx.time_budget_min = +$("#budget").value;
    const w = await weatherForRequest();
    if (w) ctx.weather = {temp_c: w.temp_c, wind_ms: w.wind_ms, precip_mm: w.precip_mm};  // exactly the contract fields
    return ctx;
  }

  // ---------- location: detected automatically when the page opens ----------
  function renderLocLine() {
    const t = T(), p = state.presets.find((x) => x.id === state.preset);
    const text = state.locating ? t.locLocating
      : state.locKind === "gps" ? fmt(t.locFound, {accuracy: state.loc.precision_m || 100})
      : p ? fmt(t.locPreset, {name: plabel(p)})
      : state.locKind === "map" ? t.locMap
      : t.locCenter;
    $("#locLine").textContent = text;
    $("#geoMsg").textContent = state.geoMessage ? t[state.geoMessage] : "";
    $("#geoMsg").hidden = !state.geoMessage;
    $("#geoActions").hidden = !state.locating && !state.geoMessage;
    $("#geoRetry").disabled = state.locating;
    const button = $("#geoBtn");
    if (button) { button.disabled = state.locating; button.setAttribute("aria-busy", String(state.locating)); }
  }
  function locate() {
    if (state.locating) return; // Repeated clicks must not restart the wait or launch overlapping requests.
    ext.cancelMapPick?.();
    const version = ++state.locVersion;
    const fail = (key) => {
      if (version !== state.locVersion || !state.locating) return;
      cancelLocation();
      state.geoMessage = key; renderLocLine(); // Keep the current point and active walk, including on failure.
    };
    state.geoMessage = null; state.locating = true; renderLocLine();
    if (!navigator.geolocation || !window.isSecureContext) return fail("geoUnavailable");
    // A slow Wi-Fi fix or permission dialog must not throw away an otherwise valid answer.
    // Offer the map early, but let this one bounded request finish; search never waits for GPS.
    state.locHintTimer = setTimeout(() => {
      if (version !== state.locVersion || !state.locating) return;
      state.geoMessage = "geoSlow"; renderLocLine();
    }, 3000);
    state.locTimer = setTimeout(() => fail("geoTimeout"), 15000);
    try { navigator.geolocation.getCurrentPosition((pos) => {
      if (version !== state.locVersion || !state.locating) return;
      const lat = round3(pos.coords.latitude), lon = round3(pos.coords.longitude);  // rounded right away
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) return fail("geoUnavailable");
      const accuracy = pos.coords.accuracy;
      // A city-sized network estimate cannot support nearby venues or walking directions.
      if (!Number.isFinite(accuracy) || accuracy < 0 || accuracy > 1000) return fail("geoImprecise");
      if (lat < 51.0 || lat > 51.25 || lon < 71.25 || lon > 71.65) {
        fail("geoOutside"); return;
      }
      setLoc(lat, lon, "gps", null);
      state.loc.precision_m = Math.max(100, Math.ceil(accuracy / 100) * 100);
      state.geoMessage = accuracy > 300 ? "geoApproximate" : null;
      renderLocLine();
    }, (err) => {
      if (version !== state.locVersion || !state.locating) return;
      clearTimeout(state.locTimer);
      // 1 = permission denied, 2 = position unavailable (often: browser not allowed in macOS/Windows settings), 3 = timeout
      fail(err && err.code === 1 ? "geoDenied" : err && err.code === 3 ? "geoTimeout" : "geoUnavailable");
    }, {enableHighAccuracy: false, timeout: 15000, maximumAge: 60000});
    } catch { fail("geoUnavailable"); }
  }
  $("#geoRetry").addEventListener("click", locate);
  $("#geoMap").addEventListener("click", () => {
    ext.cancelMapPick?.();
    cancelLocation(); state.geoMessage = "geoChooseMap"; renderLocLine();
    $("#map").scrollIntoView({block: "center", behavior: "smooth"});
    $("#map").focus({preventScroll: true});
  });
  // "find me" button on the map (to detect again, e.g. after moving the point by hand)
  const LocateCtl = L.Control.extend({
    options: {position: "topleft"},
    onAdd() {
      const b = L.DomUtil.create("button", "locate-btn");
      b.id = "geoBtn"; b.type = "button";
      b.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/></svg>';
      L.DomEvent.disableClickPropagation(b);
      L.DomEvent.on(b, "click", (e) => { L.DomEvent.stop(e); locate(); });
      return b;
    },
  });
  new LocateCtl().addTo(map);

  // ---------- request ----------
  $("#askForm").addEventListener("submit", (e) => { e.preventDefault(); ask(); });
  $("#query").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); $("#askForm").requestSubmit(); }
  });
  $("#query").addEventListener("input", fitQuery);
  $("#query").addEventListener("input", () => {
    state.chipCtx = {};
    if (state.compFromTile) { $("#companions").value = state.companionsChoice || "alone"; state.compFromTile = false; }
  });
  $("#companions").addEventListener("change", () => { state.compFromTile = false; state.companionsChoice = $("#companions").value; });  // the person's own choice stays

  async function postJSON(path, body, timeoutMs = 20000) {
    const ctrl = new AbortController(); const timer = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      const r = await fetch(API + path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body), signal: ctrl.signal});
      if (!r.ok) {
        const error = new Error("HTTP " + r.status); error.status = r.status;
        try { error.code = (await r.json())?.error?.code; } catch { /* non-JSON error */ }
        throw error;
      }
      return await r.json();
    } finally { clearTimeout(timer); }
  }

  async function ask() {
    // Search uses the point visible when the person submits, never a late GPS response.
    if (state.locating) { cancelLocation(); renderLocLine(); }
    if (ext.onSearch?.()) return;
    const version = ++state.requestVersion;
    const simulatedWeather = ["cold", "mild"].includes($("#weather").value);
    $("#status").innerHTML = `<div class="loading walking" role="status"><span class="trail" aria-hidden="true"><i></i></span>${esc(T().loading)}</div>`;
    $("#goBtn").disabled = true;
    try {
      // the server searches the full 2GIS catalog with Gemini; if 2GIS fails, its demo quota is used up or it
      // has nothing that fits, the same request goes to our own checked database, so 2GIS never leaves it empty
      let body = {location: {lat: round3(state.loc.lat), lon: round3(state.loc.lon), precision_m: state.loc.precision_m || 100, source: state.loc.source},
        query: $("#query").value.trim(), context: await context()};
      if (version !== state.requestVersion) return;
      if (ext.requestExtras) Object.assign(body, ext.requestExtras(body));
      let data = await postJSON("/recommend", body);
      if (version !== state.requestVersion) return;
      // a 2GIS answer that lists nearby places or can load more is kept: the person sees them on the map
      if (data.source === "2gis" && !(data.recommendations || []).length
          && (data.source_error || (body.preferences?.atmosphere_example_id || (body.preferences?.atmosphere_profile && body.preferences?.atmosphere_verified_only)) || (!(data.nearby_places || []).length && !data.next_cursor))) {
        const local = await postJSON("/recommend", {...body, source: "local"});
        if (version !== state.requestVersion) return;
        if ((local.recommendations || []).length || data.source_error) {
          body = {...body, source: "local"};
          local.notes = [data.source_error ? T().catalog.fallback : T().catalog.fallbackEmpty, ...(local.notes || [])];
          data = local;
        }
      }
      state.lastWeather = body.context.weather ? {...body.context.weather, simulated: simulatedWeather} : null;
      state.lastReq = body; state.extraCands = null; state.showCands = false;
      state.last = data; state.selectedPlaceId = null;
      $("#status").innerHTML = "";
      render(data);
      if (!healthReady) void refreshHealth(); // Recover features after a cold start or deployment.
      $("#results").scrollIntoView({behavior: "smooth", block: "start"});
    } catch (err) {
      if (version !== state.requestVersion) return;
      $("#status").innerHTML = `<p class="msg err">${esc(err.userMessage || T().serverDown)} <button type="button" class="btn small" id="retryBtn">${esc(T().retry)}</button></p>`;
      $("#retryBtn").addEventListener("click", ask);
    } finally { if (version === state.requestVersion) $("#goBtn").disabled = false; }
  }

  async function askNext() {
    const previous = state.last;
    if (!previous?.next_cursor || !state.lastReq) return;
    const version = ++state.requestVersion;
    const button = $("#nextPlacesBtn");
    if (button) button.disabled = true;
    try {
      const body = {...state.lastReq, cursor: previous.next_cursor};
      const data = await postJSON("/recommend", body);
      if (version !== state.requestVersion) return;
      if (data.source_error && !data.nearby_places?.length && !data.recommendations?.length) {
        $("#status").textContent = (data.notes || []).join(" ") || T().serverDown;
        if (button?.isConnected) button.disabled = false;
        return;
      }
      if (data.source === "2gis") {
        const places = new Map((previous.nearby_places || []).map(p => [p.poi_id, p]));
        (data.nearby_places || []).forEach(p => places.set(p.poi_id, p));
        data.nearby_places = [...places.values()].sort((a,b) => a.distance_m - b.distance_m);
      }
      state.lastReq = body;
      state.last = data;
      $("#status").innerHTML = "";
      render(data);
    } catch {
      if (version !== state.requestVersion) return;
      $("#status").innerHTML = `<p class="msg err">${esc(T().serverDown)}</p>`;
      if (button?.isConnected) button.disabled = false;
    }
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
    const total = (d.considered && d.considered.time_budget_min) ||
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
      gisPlace: /^https:\/\/2gis\.kz\/astana\/(firm|geo)\/\d+$/.test(r.links?.["2gis"] || "") ? r.links["2gis"] : `https://2gis.kz/astana/search/${encodeURIComponent(r.name)}?m=${lon}%2C${lat}%2F17`,
      google: `https://www.google.com/maps/dir/?api=1&destination=${lat},${lon}&travelmode=walking`,
    };
  }
  function statusPill(st) {
    if (!st) return "";
    const t = T(), days = state.lang === "en" ? ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
      : state.lang === "kk" ? ["Дс","Сс","Ср","Бс","Жм","Сб","Жс"] : ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"];
    const readable = raw => String(raw || "").replace(/\b(Mo|Tu|We|Th|Fr|Sa|Su)\b/g, d => days[["Mo","Tu","We","Th","Fr","Sa","Su"].indexOf(d)])
      .replace(/\boff\b/g,t.hoursOff).replace(/(\d)-(\d)/g,"$1–$2");
    const date = st.for_date ? fmt(t.hoursDate, {d: st.for_date}) + ": " : "";
    const hours = st.today_hours != null ? readable(st.today_hours) : readable(st.hours);
    const source = st.source === "2gis" ? (state.lang==="en"?"2GIS":"2ГИС") : st.source && st.source !== "none" ? srcName(st.source) : "";
    const url = /^https:\/\/2gis\.kz\/astana\/(firm|geo)\/\d+$/.test(st.source_url || "") ? st.source_url : null;
    const provenance = source ? `${t.hoursSource}: ${url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(source)}</a>` : esc(source)}` : "";
    return `<div class="hours-fact"><span class="status-pill st-${esc(st.state)}">${esc(t.status[st.state] || st.state)}</span>
      <span class="hours-value">${esc(hours ? date + hours : t.hoursMissing)}</span>
      ${st.today_hours && st.hours && st.hours !== "24/7" ? `<details><summary>${esc(t.weekSchedule)}</summary>${esc(readable(st.hours))}</details>` : ""}
      <small>${provenance}${source ? " · " : ""}${esc(st.schedule_has_exceptions ? t.hoursExceptions : t.hoursCaution)}${st.schedule_note ? " " + esc(st.schedule_note) : ""}</small></div>`;
  }

  const srcBadge = (src) => src === "ai" ? `<span class="badge ai">${esc(T().aiIdea)}</span>` : `<span class="badge tpl">${esc(T().template)}</span>`;
  function budgetBar(b) {
    const t = T(), tot = Math.max(b.budget_min || b.total_min, b.total_min);
    const finalWalk = b.walk_to_end_min ?? b.walk_back_min;
    const pc = (x) => (100 * x / tot).toFixed(1) + "%";
    const template = b.walk_to_end_min != null ? t.x.budgetToEnd : t.budgetLine;
    const line = fmt(template, {a: b.walk_there_min, b: b.stay_min, c: finalWalk, r: b.reserve_min || 0, t: b.total_min, B: b.budget_min});
    return `<div class="bar" aria-hidden="true"><span class="w" style="width:${pc(b.walk_there_min)}"></span><span class="s" style="width:${pc(b.stay_min)}"></span><span class="w" style="width:${pc(finalWalk)}"></span></div>
      <div class="bar-cap">${esc(line)} ${icon(b.total_min <= b.budget_min ? "check" : "info")}${b.spare_min > 0 ? ` · ${esc(t.spare)} ${b.spare_min} ${esc(t.minutes)}` : ""}</div>`;
  }
  function renderModeBadge(mode) {
    const m = mode || state.apiMode;
    $("#modeBadge").hidden = !m;
    if (m) { $("#modeBadge").className = `badge mode-${m}`; $("#modeBadge").textContent = T().modes[m] || m; }
  }

  // ---------- rendering ----------
  let selectedCardHome = null;
  function selectPlace(id, focus = true) {
    if (focus && id) ext.focusPlace?.();
    const overview = $("#resultsOverview"), selection = $("#placeSelection"), detail = $("#selectedPlaceCard");
    if (!overview || !selection) return;
    // Move the actual recommendation, preserving photos, notes and event handlers.
    if (selectedCardHome?.isConnected && detail.firstElementChild) selectedCardHome.replaceWith(detail.firstElementChild);
    selectedCardHome = null; detail.innerHTML = "";
    const p = [...(state.last?.recommendations || []), ...(state.last?.nearby_places || [])].find(p => p.poi_id === id);
    const card = $$("#resultsOverview .rec").find(el => el.dataset.id === id);
    if (!p || (!card && !(state.last?.nearby_places || []).some(p => p.poi_id === id))) id = null;
    state.selectedPlaceId = id;
    overview.hidden = !!id; selection.hidden = !id;
    if (!id) {
      if (focus) { overview.scrollIntoView({block: "start", behavior: "smooth"}); overview.focus({preventScroll: true}); }
      return;
    }
    if (card) {
      selectedCardHome = document.createComment("selected place position");
      card.before(selectedCardHome); detail.appendChild(card);
    } else {
      const t = T(), nav = links(p);
      detail.innerHTML = `<article class="card block catalog-detail" data-id="${esc(id)}">
        <p class="src">${esc(t.catalogSelection)}</p><h3>${esc(p.name)}</h3>
        <p class="meta">${esc(catLabel(p.category))}${p.rating ? ` · ${icon("star")} ${esc(p.rating)}` : ""}</p>
        ${p.address ? `<p>${esc(p.address)}</p>` : ""}
        <p>${esc(p.distance_m)} ${esc(t.distance)}${p.walk_min != null ? ` · ${esc(p.walk_min)} ${esc(t.walk)}` : ""}</p>
        ${p.open_status ? statusPill(p.open_status) : ""}
        ${ext.cardBadges?.(p) || ""}
        ${p.eligible === false ? `<p class="msg warn">${esc(t.catalog.filtered)} ${esc(codeLabel(p.excluded_because))}</p>` : ""}
        <div class="actions"><a class="btn" href="${esc(nav.gisPlace)}" target="_blank" rel="noopener">${esc(t.openIn2gis)}</a>
        ${FEAT.mapLinks ? `<a class="btn" href="${esc(nav.gis)}" target="_blank" rel="noopener">${esc(t.route2gis)}</a>` : ""}
        ${FEAT.twogis ? `<button type="button" class="btn" id="selectedGis" aria-expanded="false" aria-controls="selectedGisBox">${esc(t.gisBtn)}</button>` : ""}</div>
        <div class="gis-box" id="selectedGisBox" hidden></div></article>`;
      $("#selectedGis")?.addEventListener("click", e => toggleGis(detail.firstElementChild, id, e.currentTarget));
    }
    $("#selectedPlaceActions").innerHTML = ext.selectedPlaceActions ? ext.selectedPlaceActions(p) : "";
    if (ext.onPlaceSelected) ext.onPlaceSelected(p, state.last);
    if (focus) { selection.scrollIntoView({block: "start", behavior: "smooth"}); $("#backToPlaces").focus({preventScroll: true}); }
  }
  function render(d) {
    if (ext.filterAnswer) d = ext.filterAnswer(d);
    const t = T();
    layer.clearLayers(); suggestionRoutes.clearLayers();
    if (routeLine) { map.removeLayer(routeLine); routeLine = null; }
    Object.keys(markers).forEach((k) => delete markers[k]);
    const recs = d.recommendations || [];
    const nearby = d.nearby_places || [];
    document.body.classList.add("has-results");
    renderModeBadge(d.mode);
    let html = `<div class="result-head"><span class="badge mode-${esc(d.mode)}">${esc(t.mode)}: ${esc(t.modes[d.mode] || d.mode)}${d.cached_from ? " (" + esc(t.modes[d.cached_from] || d.cached_from) + ")" : ""}</span>
      <span class="meta">${d.timing_ms != null ? esc(Math.round(d.timing_ms)) + " ms" : ""}</span></div>`;
    if (d.source === "2gis") html += `<p class="badge gis">${esc(t.catalog.source)}</p>`;
    const notes = (d.notes || []).map((n) => `<div class="note info">${esc(n)}</div>`).join("") +
      (d.safety || []).map((n) => `<div class="note safety">${esc(n)}</div>`).join("");
    // the answer opens with the walking-time ruler; the server's notes follow it
    html += timeRuler(recs);
    if (notes) html += `<div class="notes">${notes}</div>`;
    if (ext.resultsTop) html += ext.resultsTop(d);
    if (!recs.length) html += `<div class="card empty"><div class="big">${icon("nav")}</div><h3>${esc(t.emptyTitle)}</h3><p class="meta">${esc(t.emptyHint)}</p></div>`;

    // the AI may pick fewer than three places; the backend then adds the next best checked ones with template texts
    const mixed = recs.some((r) => r.ai_reviewed || (r.selection_source || r.why_source) === "ai");
    recs.forEach((r, i) => {
      const L2 = links(r);
      const b = cardBudget(r, d);
      const kind = r.kind_label || r.category_label || catLabel(r.category);
      const rating = r.rating ? ` · ${icon("star")} ${esc(r.rating)}${r.rating_count ? " (" + esc(r.rating_count) + ")" : ""}` : "";
      // The four required parts are visible without opening More.
      const realDesc = r.description && !/^generated/.test(r.description_source || "");
      const desc = !realDesc ? "" : `<div class="desc">${esc(r.description)} <span class="src">(${r.description_url && /^https:\/\/(?:[a-z-]+\.)?wikipedia\.org\//i.test(r.description_url) ? `<a href="${esc(r.description_url)}" target="_blank" rel="noopener">${esc(t.descSrc[r.description_source] || r.description_source)}</a>` : esc(t.descSrc[r.description_source] || r.description_source || "")})</span></div>`;
      const picked = r.why_source === "ai" ? t.pickAi : r.ai_reviewed ? t.reviewAiGrounded : r.selection_source ? (r.selection_source === "ai" ? t.pickAiGrounded : t.pickRulesGrounded)
        : r.why_source === "ai" ? t.pickAi : mixed ? t.pickCode : t.pickTpl;
      const acc = r.accessibility && r.accessibility !== "unknown" ? t.accessL[r.accessibility] : t.accessL.unknown;
      html += `<article class="card rec" data-id="${esc(r.poi_id)}" tabindex="0" aria-label="${esc(r.name)}" style="--i:${i}">
        <div class="rec-title"><span class="num">${i + 1}</span><div class="rec-name">
          <h3><a class="plain" href="${esc(L2.gisPlace)}" target="_blank" rel="noopener" title="${esc(t.openIn2gis)}">${esc(r.name)}</a></h3>
          <div class="meta">${esc(kind)}${rating}</div>
        </div></div>
        <div class="walk"><span class="walk-line" aria-hidden="true"><i></i></span>
          <span class="walk-txt">${icon("walk")} <b>${esc(r.walk_min)}</b> ${esc(t.walk)} · ${esc(r.distance_m)} ${esc(t.distance)}</span></div>
        ${r.address ? `<div class="meta">${icon("pin")} ${esc(r.address)}</div>` : ""}
        <div class="pills">${r.open_status ? statusPill(r.open_status) : ""}${ext.cardBadges ? ext.cardBadges(r) : ""}</div>
        <div class="field why"><b>${esc(t.why)}:</b> ${esc(r.why)}</div>
        <div class="field"><b>${esc(t.todo)}:</b> ${esc(r.what_to_do)}</div>
        <div class="meta">⏱ ${esc(t.stay)}: ~${esc(r.time_to_spend_min)} ${esc(t.minutes)} · ${srcBadge(r.what_to_do_source)}</div>
        ${FEAT.photos ? `<div class="photos" aria-live="polite"></div>` : ""}
        <div class="actions">
          ${FEAT.mapLinks ? `<a class="btn" href="${esc(L2.gis)}" target="_blank" rel="noopener">${icon("map")} ${esc(t.route2gis)}</a>
          <a class="btn" href="${esc(L2.google)}" target="_blank" rel="noopener">${icon("nav")} ${esc(t.routeGoogle)}</a>` : ""}
          <button type="button" class="btn" data-act="map">${icon("pin")} ${esc(t.onMap)}</button>
          ${FEAT.twogis ? `<button type="button" class="btn" data-act="gis" aria-expanded="false" aria-controls="gis-${i}">${icon("star")} ${esc(t.gisBtn)}</button>` : ""}
        </div>
        ${FEAT.twogis ? `<div class="gis-box" id="gis-${i}" aria-live="polite" hidden></div>` : ""}
        ${ext.cardExtras ? ext.cardExtras(r, i, d) : ""}
        <details class="more"><summary>${esc(t.more)}</summary>
          ${budgetBar(b)}
          ${desc}
          <div class="src">${esc(acc)}</div>
          <div class="src">${esc(t.sources)}: ${(r.sources || [r.facts_source || "poi_db"]).map(srcName).map(esc).join(", ")}${r.last_checked ? " · " + esc(r.last_checked) : ""} · ${esc(picked)}</div>
        </details>
      </article>`;
      const pinIcon = L.divIcon({className: "", iconSize: [30, 30], iconAnchor: [15, 15], html: `<div class="pin"><b>${i + 1}</b></div>`});
      // a thin dashed line from the person to each pick: every place is measured from where they stand
      const from = state.lastReq ? state.lastReq.location : state.loc;
      if (L.polyline) L.polyline([[from.lat, from.lon], [r.coords.lat, r.coords.lon]], {color: "#00AFCA", weight: 3, dashArray: "1 8", lineCap: "round", opacity: .95, interactive: false}).addTo(suggestionRoutes);
      markers[r.poi_id] = L.marker([r.coords.lat, r.coords.lon], {icon: pinIcon, title: r.name}).addTo(layer)
        .bindPopup(`<b>${i + 1}. ${esc(r.name)}</b><br>${esc(r.distance_m)} ${esc(t.distance)} · ${esc(r.walk_min)} ${esc(t.walk)}`)
        .on("click", () => selectPlace(r.poi_id));
    });
    if (FEAT.route && !state.features.plan_export && recs.length >= 2) html += `<button type="button" id="routeBtn" class="btn">${icon("route")} ${esc(t.buildRoute)}</button><div id="routeBox"></div>`;
    if (nearby.length) {
      html += `<section class="card" id="nearbyPlaces"><h3>${esc(t.catalog.all)} (${nearby.length})</h3><p class="meta">${esc(t.catalog.hint)}</p>`;
      nearby.forEach(p => {
        const url = links(p).gisPlace;
        html += `<div class="field nearby-place" data-id="${esc(p.poi_id)}"><a href="${esc(url)}" target="_blank" rel="noopener">${esc(p.name)}</a>
          <div class="meta">${esc(p.distance_m)} ${esc(t.distance)} · ${esc(catLabel(p.category))}${p.rating ? ` · ${icon("star")} ${esc(p.rating)}` : ""}${p.address ? ` · ${esc(p.address)}` : ""}</div>
          ${p.open_status ? statusPill(p.open_status) : ""}${p.eligible ? "" : `<div class="meta">${esc(t.catalog.filtered)} ${esc(codeLabel(p.excluded_because))}</div>`}
          <button type="button" class="btn small" data-nearby="${esc(p.poi_id)}">${icon("pin")} ${esc(t.onMap)}</button></div>`;
        if (!markers[p.poi_id]) {
          const dotIcon = L.divIcon({className: "", iconSize: [24,24], iconAnchor: [12,12], html: '<div class="pin dot"><b>•</b></div>'});
          markers[p.poi_id] = L.marker([p.coords.lat, p.coords.lon], {icon: dotIcon, title:p.name}).addTo(layer)
            .bindPopup(`<b>${esc(p.name)}</b><br>${esc(p.distance_m)} ${esc(t.distance)}`)
            .on("click", () => selectPlace(p.poi_id));
        }
      });
      html += '</section>';
    }
    if (d.next_cursor) html += `<button type="button" id="nextPlacesBtn" class="btn">${esc(t.catalog.next)}</button>`;
    if (ext.resultsBottom) html += ext.resultsBottom(d);
    html += considered(d);
    html += `<p class="foot">${icon("info")} ${esc(d.disclaimer || t.disclaimerShort)}</p>`;
    selectedCardHome = null;
    $("#results").innerHTML = `<div id="resultsOverview" tabindex="-1">${html}</div>
      <section id="placeSelection" hidden aria-label="${esc(t.selectedPlace)}">
      <button type="button" id="backToPlaces" class="btn">${icon("back")} ${esc(t.backToPlaces)}</button>
      <div id="selectedPlaceCard"></div><div id="selectedPlaceActions"></div></section>`;
    $("#backToPlaces").addEventListener("click", () => selectPlace(null));

    const mapped = nearby.length ? nearby : recs;
    if (mapped.length && !state.selectedPlaceId) fitTo(L.latLngBounds([[state.loc.lat, state.loc.lon], ...mapped.map((r) => [r.coords.lat, r.coords.lon])]), {maxZoom: 16});
    $$("[data-nearby]").forEach(el => el.addEventListener("click", () => {
      const marker = markers[el.dataset.nearby];
      if (marker) {showAt(marker.getLatLng(), 16); marker.openPopup();}
      selectPlace(el.dataset.nearby, false);
      if (window.matchMedia("(max-width: 860px)").matches) $("#map").scrollIntoView({behavior:"smooth"});
    }));
    $$(".rec").forEach((el) => {
      const id = el.dataset.id;
      const focus = () => {
        const m = markers[id]; if (m) { showAt(m.getLatLng(), Math.max(map.getZoom(), 16)); m.openPopup(); }
        $$(".rec").forEach((x) => x.classList.toggle("active", x === el));
        selectPlace(id, false);
        if (window.matchMedia("(max-width: 860px)").matches) $("#map").scrollIntoView({behavior: "smooth"});
      };
      el.addEventListener("click", (e) => { if (!e.target.closest("a,button,input,textarea,select,details,.gis-box")) focus(); });
      el.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target === el) focus(); });
      el.querySelector('[data-act="map"]').addEventListener("click", focus);
      const g = el.querySelector('[data-act="gis"]');
      if (g) g.addEventListener("click", () => toggleGis(el, id, g));
    });
    $$(".ruler-stop").forEach((b) => b.addEventListener("click", () => {
      const el = $$(".rec").find((x) => x.dataset.id === b.dataset.stop), m = markers[b.dataset.stop];
      $$(".rec").forEach((x) => x.classList.toggle("active", x === el));
      if (el) el.scrollIntoView({behavior: "smooth", block: "start"});
      if (m) { showAt(m.getLatLng(), Math.max(map.getZoom(), 16)); m.openPopup(); }
      selectPlace(b.dataset.stop, false);
    }));
    const np = $("#nextPlacesBtn"); if (np) np.addEventListener("click", askNext);
    const rb = $("#routeBtn"); if (rb) rb.addEventListener("click", buildRoute);
    if (FEAT.photos) recs.forEach((r) => loadPhotos(r, d));
    if (ext.afterRender) ext.afterRender(d);
    if (state.selectedPlaceId) selectPlace(state.selectedPlaceId, false);
  }

  // ---------- 2GIS rating and hours (extra): asked only when the button is pressed, never for every card ----------
  const GIS_RETRY = ["twogis_timeout", "twogis_unavailable", "twogis_local_limit", "network"];
  const gisKey = (id) => `${id}|${state.lang === "kk" ? "kk" : "ru"}`;  // English gets the Russian 2GIS answer anyway
  async function getTwoGis(id) {
    const ctrl = new AbortController(), timer = setTimeout(() => ctrl.abort(), 15000);
    try {
      const r = await fetch(`${API}/places/${encodeURIComponent(id)}/2gis?lang=${encodeURIComponent(state.lang)}`, {signal: ctrl.signal, cache: "no-store"});
      const j = await r.json().catch(() => null);
      if (!r.ok || !j || !j.provider_name) return {error: (j && j.error && j.error.code) || "twogis_unavailable"};
      return j;
    } catch { return {error: "network"}; }
    finally { clearTimeout(timer); }
  }
  function gisHours(g) {
    const t = T(), G = t.gis;
    if (g.is_24x7) return G.allDay;
    if (!(g.weekly_hours || []).length) return G.noHours;
    const byDay = Object.fromEntries(g.weekly_hours.map((d) => [d.day, d.intervals || []]));
    const groups = [];
    ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].forEach((d, i) => {
      // a missing day is "no data", not "closed": 2GIS did not say
      const v = byDay[d] && byDay[d].length ? byDay[d].map((x) => `${x.start}–${x.end}`).join(", ") : G.noData;
      const last = groups[groups.length - 1];
      if (last && last.v === v) last.to = i; else groups.push({from: i, to: i, v});
    });
    return groups.map((x) => `${t.weekday[x.from]}${x.to > x.from ? "–" + t.weekday[x.to] : ""} ${x.v}`).join("; ");
  }
  function gisHtml(g) {
    const t = T(), G = t.gis;
    if (g.error) {
      return `<p class="msg warn">${esc(G.err[g.error] || G.err.twogis_unavailable)}${GIS_RETRY.includes(g.error) ? ` <button type="button" class="btn small" data-act="gis-retry">${esc(t.retry)}</button>` : ""}</p>`;
    }
    const today = new Intl.DateTimeFormat("en-CA", {timeZone: "Asia/Almaty"}).format(new Date());
    const special = (g.special_hours || []).filter((x) => x.date >= today).slice(0, 3)
      .map((x) => `${x.date.split("-").reverse().join(".")} ${(x.intervals || []).map((v) => `${v.start}–${v.end}`).join(", ") || G.noData}`);
    const rating = g.rating != null
      ? `${icon("star")} ${esc(g.rating)}${g.rating_count != null ? ` · ${esc(G.reviews)}: ${esc(g.rating_count)}` : ""}${G.scope[g.rating_scope] ? ` <span class="meta">(${esc(G.scope[g.rating_scope])})</span>` : ""}`
      : esc(G.noRating);
    const when = new Intl.DateTimeFormat({ru: "ru-RU", kk: "kk-KZ", en: "en-GB"}[state.lang] || "ru-RU",
      {day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Almaty"}).format(new Date(g.checked_at));
    const match = g.match_method === "catalog_id" ? t.catalog.match : g.match_method === "stored_id" ? G.matchManual : fmt(G.matchAuto, {m: g.match_distance_m});
    const url = /^https:\/\/2gis\.(kz|ru)\//.test(g.provider_url || "") ? g.provider_url : "";
    return `<div class="gis-head"><span class="badge gis">${esc(G.data)}</span> <b>${esc(g.provider_name)}</b></div>
      ${g.address ? `<div class="meta">${icon("pin")} ${esc(g.address)}</div>` : ""}
      <div>${rating}</div>
      <div>${icon("clock")} <b>${esc(G.hours)}:</b> ${esc(gisHours(g))}</div>
      ${special.length ? `<div>${icon("calendar")} <b>${esc(G.special)}:</b> ${esc(special.join("; "))}</div>` : ""}
      ${g.schedule_note ? `<div class="meta">${esc(g.schedule_note)}</div>` : ""}
      <p class="meta">${esc(G.notNow)}${G.langNote ? " " + esc(G.langNote) : ""}</p>
      <p class="src">${esc(match)} · ${esc(t.checked)} ${esc(when)}${url ? ` · <a href="${esc(url)}" target="_blank" rel="noopener">${esc(G.open)} ${icon("ext")}</a>` : ""}</p>`;
  }
  function toggleGis(card, id, btn) {
    const box = card.querySelector(".gis-box"), open = box.hidden;
    box.hidden = !open; btn.setAttribute("aria-expanded", String(open));
    if (open) loadGis(card, id, btn);
  }
  async function loadGis(card, id, btn) {
    const box = card.querySelector(".gis-box"), key = gisKey(id);
    if (!state.gis[key]) {
      btn.disabled = true;
      box.innerHTML = `<div class="loading" role="status"><div class="spinner"></div>${esc(T().gis.loading)}</div>`;
      const g = await getTwoGis(id);
      btn.disabled = false;
      if (!GIS_RETRY.includes(g.error)) state.gis[key] = g;  // final answers are kept, so 2GIS is asked once per place
      if (!card.isConnected) return;
      box.innerHTML = gisHtml(g);
    } else box.innerHTML = gisHtml(state.gis[key]);
    const rb = box.querySelector('[data-act="gis-retry"]');
    if (rb) rb.addEventListener("click", () => loadGis(card, id, btn));
  }

  // ---------- photos of the place and what Gemini sees on them (asked for every card after the answer) ----------
  const photoCredit = (x) => x.source === "team" ? T().ph.team : `${x.author || "Wikimedia Commons"}${x.license ? ", " + x.license : ""}`;
  const https = (u) => /^https:\/\//.test(u || "") ? u : "";
  function photosHtml(p) {
    const P = T().ph, photos = ((p && p.photos) || []).filter((x) => https(x.url));
    if (!photos.length) return `<p class="ph-none">${icon("camera")} ${esc(!p || p.status === "ai_unavailable" ? P.noAnalysis : P.none)}</p>`;
    const a = p.analysis;
    const chips = a ? [
      P.light[a.lighting] && ["sun", P.light[a.lighting]],
      P.kids[a.kids_area] && ["kids", P.kids[a.kids_area]],
      a.seats ? ["seat", fmt(P.seats, {n: a.seats})] : P.seating[a.seating] && ["seat", P.seating[a.seating]],
      P.space[a.space] && ["space", P.space[a.space]],
      a.decor && ["leaf", a.decor],
    ].filter(Boolean).map(([n, x]) => `<span class="tag">${icon(n)} ${esc(x)}</span>`).join("") : "";
    return `<div class="ph-strip">${photos.map((x) => `<a class="ph" href="${esc(https(x.page_url) || x.url)}" target="_blank" rel="noopener" title="${esc(photoCredit(x))}"><img src="${esc(x.url)}" alt="${esc(P.alt)}" loading="lazy" referrerpolicy="no-referrer"></a>`).join("")}</div>
      ${a && a.summary ? `<div class="field ph-why">${icon("camera")} <b>${esc(P.title)}:</b> ${esc(a.summary)}</div>` : a ? "" : `<p class="src">${esc(P.noAnalysis)}</p>`}
      ${chips ? `<div class="tags">${chips}</div>` : ""}
      <p class="src">${esc(P.credit)}: ${[...new Set(photos.map(photoCredit))].map(esc).join("; ")}</p>`;
  }
  async function loadPhotos(r, d) {
    const card = $$(".rec").find((el) => el.dataset.id === r.poi_id);
    return fillPhotos(card && card.querySelector(".photos"), r, () => state.last === d);
  }
  // any place box (recommendation cards, meeting places); current() says the box still belongs to the shown answer
  async function fillPhotos(box, r, current = () => true, query = null) {
    if (!box || !FEAT.photos || !r?.poi_id || !r.coords) return;
    const ask = {lang: state.lang, query: query ?? ((state.lastReq && state.lastReq.query) || ""), companions: (state.lastReq && state.lastReq.context.companions) || "alone"};
    // a 2GIS place is matched on the server to the same place in our photo list by name and position
    if (r.poi_id.startsWith("2gis_")) ask.near = {name: r.name, lat: r.coords.lat, lon: r.coords.lon, category: r.category};
    const key = `${r.poi_id}|${ask.lang}|${ask.companions}|${ask.query}`;
    if (!state.photos[key]) {
      box.innerHTML = `<div class="loading"><div class="spinner"></div>${esc(T().ph.loading)}</div>`;
      // POST keeps the request text out of URLs; one answer per place and request, kept for this page
      try {
        if (!state.photoPending[key]) state.photoPending[key] = postJSON(`/places/${encodeURIComponent(r.poi_id)}/photos`, ask, 40000)
          .finally(() => { delete state.photoPending[key]; });
        state.photos[key] = await state.photoPending[key];
      }
      catch { state.photos[key] = null; }
    }
    if (current() && box.isConnected) box.innerHTML = photosHtml(state.photos[key]);
  }

  // the signature: every pick on one walking-time scale that starts where the person stands
  function timeRuler(recs) {
    if (!recs.length) return "";
    const t = T(), max = Math.max(...recs.map((r) => r.walk_min || 0));
    const end = Math.max(10, Math.ceil(max * 1.12 / 5) * 5);
    // stops keep their order by minutes; ones that are only a minute or two apart are spread so their labels never overlap
    const order = recs.map((r, i) => ({r, i, x: (r.walk_min || 0) / end * 100})).sort((a, b) => a.x - b.x);
    let prev = 3;
    order.forEach((o) => { o.x = Math.max(o.x, prev + 19); prev = o.x; });
    const over = order.length ? order[order.length - 1].x - 97 : 0;
    if (over > 0) order.forEach((o) => { o.x -= over; });
    const stops = order.sort((a, b) => a.i - b.i).map(({r, i, x}) =>
      `<button type="button" class="ruler-stop" data-stop="${esc(r.poi_id)}" style="--x:${x.toFixed(1)}%;--k:${i}" aria-label="${esc(`${i + 1}. ${r.name}: ${r.walk_min} ${t.walk}`)}"><b>${i + 1}</b><span>${esc(r.walk_min)} ${esc(t.minutes)}</span></button>`).join("");
    return `<div class="ruler" role="group" aria-label="${esc(fmt(t.rulerLabel || "", {list: recs.map((r, i) => `${i + 1} — ${r.walk_min} ${t.minutes}`).join(", ")}))}">
      <div class="ruler-track"><span class="ruler-me" aria-hidden="true"></span><span class="ruler-fill" aria-hidden="true"></span>${stops}</div>
      <div class="ruler-scale"><span>${esc(t.youAreHere)}</span><span>${esc(end)} ${esc(t.minutes)}</span></div></div>`;
  }

  function considered(d) {
    const t = T(), c = d.considered || {}, rows = [];
    const add = (n, k, v) => { if (v) rows.push(`<li>${icon(n)}<span><b>${esc(k)}${/:/.test(k) ? "" : ":"}</b> ${v}</span></li>`); };
    const w = c.weather && c.weather.temp_c !== undefined ? {...c.weather, simulated: !!state.lastWeather?.simulated, wind_ms: c.weather.wind_ms ?? (c.weather.wind_kmh ? c.weather.wind_kmh / 3.6 : 0)} : state.lastWeather;
    if (FEAT.weather && w) add("cloud", t.weatherL, esc(weatherText(w)));
    if (c.time) add("clock", t.time, `${esc(c.target_time ? new Intl.DateTimeFormat({ru:"ru-RU",kk:"kk-KZ",en:"en-GB"}[state.lang] || "ru-RU", {weekday:"short",hour:"2-digit",minute:"2-digit",timeZone:"Asia/Almaty"}).format(new Date(c.target_time)) : c.time)}${c.time_simulated || c.time_shift ? " · " + esc(t.simulated) : ""}`);
    if (c.radius_m) add("radius", t.radius, `${esc(c.radius_m)} ${esc(t.distance)}${c.radius_expanded ? " — " + esc(t.expanded) : ""} · ${esc(fmt(t.roundedTo, {m: c.location_rounded_to_m || 100}))}`);
    const looked = (c.filters || []).filter((f) => !String(f).startsWith("exclude:")).map(codeLabel);
    if (looked.length) add("search", t.lookedFor, esc(looked.join(", ")));
    // every place the count mentions is listed; the chosen ones are ticked
    const chosen = new Set((d.recommendations || []).map((r) => r.poi_id));
    const list = d.candidates || [];
    if (list.length) add("list", fmt(t.lookedAt, {n: list.length}), `<span class="cands-list">${list.map((x) =>
      `<span class="cand${chosen.has(x.poi_id) ? " on" : ""}">${chosen.has(x.poi_id) ? icon("check") + " " : ""}${esc(x.name)} · ${esc(x.distance_m)} ${esc(t.distance)}</span>`).join("")}</span>`);
    return `<section class="card considered" id="consideredBox"><h3>${esc(t.considered)}</h3><ul class="cons">${rows.join("")}</ul></section>`;
  }

  // ---------- mini-route (extra): computed in the browser, the backend is not touched ----------
  const {hav, planRoute} = window.SeruenRoute;
  async function osrmLine(points) {
    try {
      const coords = points.map((p) => `${p.lon},${p.lat}`).join(";");
      const ctrl = new AbortController(); const timer = setTimeout(() => ctrl.abort(), 4000);
      const r = await fetch(`${CFG.OSRM_URL || "https://routing.openstreetmap.de/routed-foot"}/route/v1/foot/${coords}?overview=full&geometries=geojson`, {signal: ctrl.signal});
      clearTimeout(timer);
      const j = await r.json();
      if (j.code !== "Ok") throw new Error(j.code);
      return {line: j.routes[0].geometry.coordinates.map(([lon, lat]) => [lat, lon]), osrm: true};
    } catch { return {line: points.map((p) => [p.lat, p.lon]), osrm: false}; }
  }
  async function buildRoute() {
    if (state.walkActive) return;
    const d = state.last, t = T();
    const c = d.considered || {};
    const budget = c.effective_budget_min || c.time_budget_min || (d.budget_breakdown && d.budget_breakdown.budget_min) || 60;
    const speed = c.walk_speed_m_per_min || ((c.companions || state.lastReq.context.companions) === "child" ? 60 : 75);
    const start = {lat: state.lastReq.location.lat, lon: state.lastReq.location.lon};
    const places = d.recommendations.map((r) => ({poi_id: r.poi_id, name: r.name, category: r.category, lat: r.coords.lat, lon: r.coords.lon}));
    const plan = planRoute(start, places, budget, speed);
    if (!plan.fits) { $("#routeBox").innerHTML = `<p class="msg warn">${esc(t.routeNoBudget)}</p>`; return; }
    $("#routeBox").innerHTML = `<div class="loading"><div class="spinner"></div>${esc(t.loading)}</div>`;
    const geo = await osrmLine([start, ...plan.order, start]);
    if (state.walkActive || state.last !== d || !$("#routeBox")) return;
    if (routeLine) map.removeLayer(routeLine);
    routeLine = L.polyline(geo.line, {color: "#00708A", weight: 5, dashArray: geo.osrm ? null : "8 8", lineCap: "round", opacity: .9}).addTo(map);
    fitTo(routeLine.getBounds());
    const pts = plan.order.map((p) => `${p.lon}%2C${p.lat}`).join("%7C");
    const gis = `https://2gis.kz/astana/directions/tab/pedestrian/points/%7C${pts}?m=${plan.order[0].lon}%2C${plan.order[0].lat}%2F15`;
    const last = plan.order[plan.order.length - 1];
    const way = plan.order.slice(0, -1).map((p) => `${p.lat},${p.lon}`).join("%7C");
    const google = `https://www.google.com/maps/dir/?api=1&destination=${last.lat},${last.lon}&travelmode=walking${way ? "&waypoints=" + way : ""}`;
    const steps = plan.order.map((p, i) => `<li>${esc(p.name)} — ${icon("walk")} ${plan.legs[i]} + ${icon("clock")} ${plan.stays[i]} ${esc(t.minutes)}</li>`).join("");
    $("#routeBox").innerHTML = `<div class="card route"><h3>${esc(t.routeTitle)}: ${plan.total} / ${plan.budget} ${esc(t.minutes)} ${icon(plan.fits ? "check" : "info")}</h3>
      <ol class="meta">${steps}<li>${icon("walk")} ${plan.back} ${esc(t.minutes)}</li></ol>
      <p class="meta">${esc(geo.osrm ? t.routeOsrm : t.routeStraight)}</p>
      <div class="actions"><a class="btn small" target="_blank" rel="noopener" href="${esc(gis)}">${icon("map")} ${esc(t.route2gis)}</a>
      <a class="btn small" target="_blank" rel="noopener" href="${esc(google)}">${icon("nav")} ${esc(t.routeGoogle)}</a></div></div>`;
  }

  // ---------- start ----------
  async function getJSON(url, timeoutMs = 12000) {
    const ctrl = new AbortController(), timer = setTimeout(() => ctrl.abort(), timeoutMs);
    try { const r = await fetch(url, {signal: ctrl.signal, cache: "no-store"}); if (!r.ok) throw new Error(r.status); return await r.json(); }
    finally { clearTimeout(timer); }
  }
  let healthReady = false, healthPending = null;
  function refreshHealth() {
    if (healthPending) return healthPending;
    healthPending = (async () => {
      try {
        const h = await getJSON(API + "/health");
        state.features = h.feature_contract_version === 2 && h.features && typeof h.features === "object" ? h.features : {};
        if (ext.onHealth) ext.onHealth(h);
        const avail = h.mode_available || [];
        state.apiMode = h.ai === "gemini" || avail.includes("ai") ? "ai" : h.ai === "no_ai" || avail.includes("no_ai") ? "no_ai" : (h.mode || null);
        const snap = h.data_snapshot || h.data_snapshot_date, places = h.places || h.poi_count;
        if (snap && !h.twogis?.search_enabled) $("#snapshot").textContent = `· ${T().snapshot}: ${snap}${places ? " (" + places + ")" : ""}`;
        healthReady = true;
        renderModeBadge(state.last ? state.last.mode : null);
      } catch { /* Retry after a successful search; do not poll a sleeping free server. */ }
      finally { healthPending = null; }
    })();
    return healthPending;
  }
  async function init() {
    applyLang(); // Labels and inputs must work even while Render wakes up.
    if (!FEAT.languages) $(".lang").hidden = true;
    if (!FEAT.weather) $("#weatherField").hidden = true;
    // GPS starts immediately, independent of static files, backend wake-up and health.
    if (!params.get("preset") && !params.get("scenario")) locate();
    const initialLocVersion = state.locVersion;
    [state.presets, state.scenarios] = await Promise.all([
      getJSON("presets.json").catch(() => []), getJSON("scenarios.json").catch(() => []),
    ]);
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
    applyLang();
    // where the person is: a preset from the link (demos), else detect automatically
    const p0 = state.presets.find((x) => x.id === params.get("preset"));
    const initialPointUnchanged = state.locVersion === initialLocVersion;
    if (initialPointUnchanged) {
      if (p0) setLoc(p0.lat, p0.lon, "preset", p0.id);
      else if (params.get("preset") && !params.get("scenario")) locate();
    }
    if (FEAT.weather) liveWeather();  // warm up, so the first answer is not slowed down
    if (params.get("at")) {  // simulated time for demos and screenshots, e.g. ?at=2026-10-18T15:00
      $("#whenSel").value = "other"; $("#whenAt").hidden = false; $("#whenAt").value = params.get("at").slice(0, 16);
    }
    if (initialPointUnchanged && params.get("scenario")) runScenario(params.get("scenario").toUpperCase());
    else if (initialPointUnchanged && params.get("chip") !== null) $$("#chips button")[+params.get("chip")]?.click();
    void refreshHealth();
    if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost")) {
      navigator.serviceWorker.register("sw.js").catch(() => {});
    }
  }
  window.SeruenApp = {state, FEAT, API, T, fmt, esc, icon, $, $$, map, layer, markers, L, showAt, fitTo, round3, setWalkActive,
    freezeLocation: () => { if (state.locating) { cancelLocation(); renderLocLine(); } },
    postJSON, getJSON, context, ask: () => ask(), render: (d) => render(d), rerender: () => { if (state.last) render(state.last); }, catLabel,
    statusPill, links, fillPhotos, presetName: p => p?.name?.[state.lang] || p?.name?.ru || p?.label?.[state.lang] || p?.id || ""};
  init();
  if (ext.onReady) ext.onReady();
})();
