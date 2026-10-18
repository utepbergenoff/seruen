/* Серуен: the eight features on top of app.js (docs/feature_expansion_contract.md).
   On this device only: my places (want to go, visited, favourite, note) and saved walks (F6, F8).
   Server-backed, shown only when /health announces them: plans changed (F1), finish point (F2),
   "not for me" reasons (F3), comfort points (F4), no-spend filter (F5), search by atmosphere (F7).
   An old server never receives a field it does not know. */
(() => {
  "use strict";
  const A = window.SeruenApp, S = window.SeruenStore, ext = window.SeruenExt;
  if (!A || !S || !ext) return;
  const {state, T, esc, icon, fmt, $, $$, L, map} = A;
  const X = () => T().x || window.I18N.ru.x;
  const has = (f) => !!(state.features && state.features[f]);
  const pref = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode */ } },
  };
  const r3 = (x) => Math.round(x * 1000) / 1000;
  const sessionPlaces = new Map();  // Provider labels live only in this tab's memory.
  const placeView = p => ({...sessionPlaces.get(p.poi_id), ...p});

  const mine = {places: new Map(), walks: [], tab: "places", filter: "all", onlyNew: pref.get("seruen_only_new", false),
    onMap: false, confirmClear: false, error: null};
  // F3/F5: what the person asked to avoid, shown above the answer with "Undo"
  let cons = {exclude_ids: [], max_distance_m: null, exclude_categories: [], no_spend: null};
  let finish = null, picking = false, atmosphere = null, atmosExamples = [], comfortKinds = new Set(), comfortMsg = "";
  let walk = null, walkVersion = 0, walkMsg = "", walkBusy = false, reqSeq = 0;
  const personal = L.layerGroup().addTo(map), comfortLayer = L.layerGroup().addTo(map), pauseLayer = L.layerGroup().addTo(map);
  let finishMarker = null, walkLine = null, comfortVersion = 0;

  // ---------- storage ----------
  async function loadMine() {
    try {
      mine.places = new Map((await S.allPlaces()).map((p) => [p.poi_id, p]));
      mine.walks = (await S.allWalks()).filter(w => w.version === 2 && w.offline?.status === "saved")
        .sort((a, b) => String(b.saved_at).localeCompare(String(a.saved_at)));
    } catch { /* keeps what is in memory */ }
    mine.error = S.problem === "blocked" ? X().storeBlocked : mine.error;
  }
  async function keep(r, patch) {
    sessionPlaces.set(r.poi_id, r);
    const cur = mine.places.get(r.poi_id) || {};
    const row = {poi_id: r.poi_id, name: r.name || cur.name || "", category: r.category || cur.category || "",
      address: r.address || cur.address || "", coords: r.coords || cur.coords || null, ...cur, ...patch,
      offline_allowed: r.offline_allowed === true && !r.poi_id.startsWith("2gis_")};
    try {
      const saved = await S.putPlace(row);
      if (saved) mine.places.set(row.poi_id, saved); else mine.places.delete(row.poi_id);
      mine.error = S.problem === "blocked" ? X().storeBlocked : null;
    } catch (e) { mine.error = e && e.name === "QuotaExceededError" ? X().storeQuota : X().storeBlocked; }
    renderMine(); drawPersonal();
  }
  const visitedIds = () => [...mine.places.values()].filter((p) => p.visited_at).map((p) => p.poi_id);

  // ---------- requests: new fields only when the server announced them ----------
  function activeConstraints() {
    const out = {};
    const ex = [...new Set([...cons.exclude_ids, ...(mine.onlyNew ? visitedIds() : [])])];
    if (ex.length > 200) throw Object.assign(new Error("too_many_exclusions"), {userMessage: X().tooMany});
    if (ex.length) out.exclude_ids = ex;
    if (cons.max_distance_m) out.max_distance_m = cons.max_distance_m;
    if (cons.exclude_categories.length) out.exclude_categories = cons.exclude_categories;
    if (cons.no_spend) out.no_spend = cons.no_spend;
    return out;
  }
  ext.requestExtras = (body = {}) => {
    const out = {};
    const c = has("constraints") ? activeConstraints() : {};
    const preferences = {};
    if (c.exclude_ids) preferences.exclude_poi_ids = c.exclude_ids;
    if (c.max_distance_m) preferences.max_distance_m = c.max_distance_m;
    if (c.no_spend) preferences.expense_mode = c.no_spend === "strict" ? "free_only" : "no_required_purchase";
    if (c.exclude_categories) out.context = {...body.context,
      exclude_categories: [...new Set([...(body.context?.exclude_categories || []), ...c.exclude_categories])]};
    if (has("end_point") && finish) out.end = {lat: r3(finish.lat), lon: r3(finish.lon), precision_m: 100,
      source: finish.source === "landmark" ? "preset" : finish.source || "map"};
    if (has("atmosphere") && atmosphere) preferences.atmosphere_example_id = atmosphere;
    if (Object.keys(preferences).length) out.preferences = preferences;
    if (Object.keys(out).length) out.request_id = `r${++reqSeq}`;
    return out;
  };
  // without server support "only new" hides visited places here and says how many
  ext.filterAnswer = (d) => {
    if (!mine.onlyNew || has("constraints") || !d || !d.recommendations) return d;
    const seen = new Set(visitedIds()), keepRecs = d.recommendations.filter((r) => !seen.has(r.poi_id));
    return keepRecs.length === d.recommendations.length ? d : {...d, recommendations: keepRecs, _hiddenVisited: d.recommendations.length - keepRecs.length};
  };

  // ---------- card ----------
  const COST = {free: "costFree", optional_purchase: "costOptional", paid: "costPaid", unknown: "costUnknown"};
  ext.cardBadges = (r) => {
    const cost = r.visit_condition;
    if (!cost) return "";
    const st = COST[cost.kind] ? cost.kind : "unknown", x = X();
    const title = [cost.note, cost.source_url && `${T().sources}: ${cost.source_url}`, cost.checked_at].filter(Boolean).join(" · ");
    return `<span class="cost cost-${esc(st)}" title="${esc(title)}">${icon("wallet")} ${esc(x[COST[st]])}${cost.note ? ` · ${esc(cost.note)}` : ""}</span>`;
  };
  ext.cardExtras = (r) => {
    const x = X(), p = mine.places.get(r.poi_id) || {}, b = r.budget_breakdown || {};
    const chip = (k, ic, on, label) => `<button type="button" class="chip-btn${on ? " on" : ""}" data-keep="${k}" aria-pressed="${on}">${icon(ic)} ${esc(label)}</button>`;
    let html = "";
    if (b.walk_to_end_min != null || r.arrival_estimate) {
      const at = r.arrival_estimate ? new Intl.DateTimeFormat("ru-RU", {hour: "2-digit", minute: "2-digit", timeZone: "Asia/Almaty"}).format(new Date(r.arrival_estimate)) : "";
      html += `<div class="meta finish-line">${icon("finish")} ${b.walk_to_end_min != null ? esc(fmt(x.toEnd, {m: b.walk_to_end_min})) : ""}${at ? ` · ${esc(fmt(x.arrival, {t: at}))}` : ""}</div>`;
    }
    if (r.atmosphere_match && (r.atmosphere_match.matched_features || []).length) {
      const f = r.atmosphere_match.matched_features.map((k) => x.feat[k] || k).join(", ");
      html += `<div class="meta">${icon("image")} ${esc(fmt(x.matched, {f}))} · ${esc(r.atmosphere_match.source === "gemini" ? x.srcAi : x.srcManual)}</div>`;
    }
    html += `<div class="keep" role="group" aria-label="${esc(x.keepTitle)}">
      ${chip("want", "flag", !!p.want, x.want)}${chip("visited", "visit", !!p.visited_at, x.visited)}
      ${chip("favorite", "heart", !!p.favorite, x.favorite)}${chip("note", "note", !!p.note, x.note)}</div>
      <div class="note-box" hidden><textarea maxlength="500" rows="2" placeholder="${esc(x.notePh)}">${esc(p.note || "")}</textarea>
      <div class="row"><button type="button" class="btn small" data-note="save">${esc(x.noteSave)}</button>${p.note ? `<button type="button" class="btn small" data-note="del">${esc(x.noteDelete)}</button>` : ""}</div>
      <p class="src">${esc(x.deviceOnly)}</p></div>`;
    if (has("constraints")) {
      html += `<details class="nope"><summary>${esc(x.nope)}</summary><div class="row">
        <button type="button" class="btn small" data-nope="far">${esc(x.nFar)}</button>
        <button type="button" class="btn small" data-nope="been">${esc(x.nBeen)}</button>
        <button type="button" class="btn small" data-nope="format">${esc(x.nFormat)}</button>
        <button type="button" class="btn small" data-nope="free">${esc(x.nFree)}</button>
        <button type="button" class="btn small" data-nope="other">${esc(x.nOther)}</button></div>
        <div class="nope-format" hidden><label>${esc(x.pickCategory)} <select>${Object.entries(T().cats || {}).map(([k, v]) =>
          `<option value="${esc(k)}"${k === r.category ? " selected" : ""}>${esc(v)}</option>`).join("")}</select></label>
          <button type="button" class="btn small" data-nope="format-ok">OK</button></div></details>`;
    }
    return html;
  };

  // ---------- above and below the answer ----------
  const consLabel = () => {
    const x = X(), out = [];
    if (cons.max_distance_m) out.push(["max", fmt(x.cMaxDist, {m: cons.max_distance_m})]);
    if (cons.exclude_ids.length) out.push(["ids", fmt(x.cExclude, {n: cons.exclude_ids.length})]);
    if (cons.exclude_categories.length) out.push(["cats", fmt(x.cCat, {c: cons.exclude_categories.map(A.catLabel).join(", ")})]);
    if (cons.no_spend) out.push(["spend", x.cFree]);
    return out;
  };
  ext.resultsTop = (d) => {
    const x = X();
    let html = "";
    if (d._hiddenVisited) html += `<p class="msg info">${esc(fmt(x.hiddenVisited, {n: d._hiddenVisited}))}</p>`;
    const active = has("constraints") ? consLabel() : [];
    if (active.length) html += `<div class="cons-active"><span>${esc(x.active)}</span>${active.map(([k, l]) =>
      `<span class="cchip">${esc(l)} <button type="button" data-undo="${k}" aria-label="${esc(x.undo)}">${icon("x")}</button></span>`).join("")}</div>`;
    if (d.route_impossible) {
      const ri = d.route_impossible, reason = ri.reason === "distance" ? x.reasonDistance : x.reasonBudget;
      html += `<div class="card block impossible"><b>${icon("info")} ${esc(fmt(x.impossible, {r: reason}))}</b>${ri.need_min ? ` <span class="meta">${esc(fmt(x.needMin, {m: ri.need_min}))}</span>` : ""}
        <div class="row">${(ri.suggestions || []).map((s) => s.kind === "more_time" && s.min
          ? `<button type="button" class="btn small" data-more="${esc(s.min)}">${esc(fmt(x.sugMore, {m: s.min}))}</button>`
          : s.kind === "fewer_stops" ? `<span class="meta">${esc(x.sugFewer)}</span>` : "").join("")}</div></div>`;
    }
    const relax = {increase_distance_limit: ["max_distance_m", x.nFar], allow_unknown_expenses: ["no_spend", x.cFree],
      restore_excluded_places: ["exclude_ids", x.nBeen], remove_atmosphere_filter: ["atmosphere", x.atmos]};
    if (has("constraints") && (d.relaxation_options || []).length) {
      html += `<div class="row relax">${d.relaxation_options.filter(k => relax[k]).map(k =>
        `<button type="button" class="btn small" data-relax="${esc(relax[k][0])}">${esc(x.undo)}: ${esc(relax[k][1])}</button>`).join("")}</div>`;
    }
    return html;
  };
  ext.resultsBottom = (d) => {
    const x = X();
    if (!(d.recommendations || []).length) return "";
    let html = has("plan_export") ? `<div class="row walk-actions"><button type="button" class="btn" id="saveWalkBtn">${icon("save")} ${esc(x.saveWalk)}</button>
      <button type="button" class="btn" id="startWalkBtn">${icon("play")} ${esc(x.startWalk)}</button></div><p class="src" id="saveWalkMsg" aria-live="polite"></p>` : "";
    if (has("comfort")) {
      const kinds = [["warm", "fire", x.kWarm], ["toilet", "toilet", x.kToilet], ["sit", "bench", x.kSit], ["water", "water", x.kWater], ["entrance", "door", x.kEntrance]];
      html += `<div class="card block comfort"><h3>${esc(x.comfort)}</h3><div class="row">${kinds.map(([k, ic, l]) =>
        `<button type="button" class="chip-btn${comfortKinds.has(k) ? " on" : ""}" data-comfort="${k}" aria-pressed="${comfortKinds.has(k)}">${icon(ic)} ${esc(l)}</button>`).join("")}</div>
        ${comfortMsg ? `<p class="meta">${esc(comfortMsg)}</p>` : ""}</div>`;
    }
    return html;
  };
  ext.selectedPlaceActions = p => has("plan_export")
    ? `<button type="button" class="btn primary" id="startSelectedWalk">${icon("play")} ${esc(X().startWalk)}</button>
       <p class="meta">${esc(T().selectedDestination)}: ${esc(p.name)}</p><p class="src" id="selectedWalkMsg" aria-live="polite"></p>` : "";
  ext.onPlaceSelected = (p, d) => {
    $("#startSelectedWalk")?.addEventListener("click", () => buildAnswer(d, false, p.poi_id));
  };

  // ---------- after the answer is on the page ----------
  ext.afterRender = (d) => {
    (d.recommendations || []).forEach(r => sessionPlaces.set(r.poi_id, r));
    const x = X();
    $$(".rec").forEach((el) => {
      const r = (d.recommendations || []).find((q) => q.poi_id === el.dataset.id);
      if (!r) return;
      el.querySelectorAll("[data-keep]").forEach((b) => b.addEventListener("click", () => {
        const k = b.dataset.keep, p = mine.places.get(r.poi_id) || {};
        if (k === "note") { const box = el.querySelector(".note-box"); box.hidden = !box.hidden; if (!box.hidden) box.querySelector("textarea").focus(); return; }
        const patch = k === "want" ? {want: !p.want} : k === "favorite" ? {favorite: !p.favorite} : {visited_at: p.visited_at ? null : Date.now()};
        keep(r, patch).then(() => A.rerender());
      }));
      el.querySelectorAll("[data-note]").forEach((b) => b.addEventListener("click", () => {
        const note = b.dataset.note === "save" ? el.querySelector(".note-box textarea").value.trim().slice(0, 500) : "";
        keep(r, {note}).then(() => A.rerender());
      }));
      el.querySelectorAll("[data-nope]").forEach((b) => b.addEventListener("click", () => nope(b.dataset.nope, r, el, d)));
    });
    $$("[data-undo]").forEach((b) => b.addEventListener("click", () => {
      const k = b.dataset.undo;
      if (k === "max") cons.max_distance_m = null; else if (k === "ids") cons.exclude_ids = [];
      else if (k === "cats") cons.exclude_categories = []; else if (k === "spend") { cons.no_spend = null; syncSpend(); }
      A.ask();
    }));
    $$("[data-relax]").forEach((b) => b.addEventListener("click", () => {
      const k = b.dataset.relax;
      if (k === "max_distance_m") cons.max_distance_m = null; else if (k === "no_spend") { cons.no_spend = null; syncSpend(); }
      else if (k === "exclude_categories") cons.exclude_categories = []; else if (k === "exclude_ids") cons.exclude_ids = [];
      else if (k === "atmosphere") { atmosphere = null; renderAtmosphere(); }
      A.ask();
    }));
    $$("[data-more]").forEach((b) => b.addEventListener("click", () => {
      $("#budgetAuto").checked = false; $("#budget").value = b.dataset.more; $("#budgetOut").textContent = b.dataset.more; A.ask();
    }));
    const sb = $("#saveWalkBtn"); if (sb) sb.addEventListener("click", () => buildAnswer(d, true));
    const st = $("#startWalkBtn"); if (st) st.addEventListener("click", () => buildAnswer(d, false));
    $$("[data-comfort]").forEach((b) => b.addEventListener("click", () => {
      const k = b.dataset.comfort;
      if (comfortKinds.has(k)) comfortKinds.delete(k); else comfortKinds.add(k);
      loadComfort(d);
    }));
    drawFinish(); drawPersonal();
  };

  // ---------- F3: why it does not fit ----------
  async function nope(kind, r, el, d) {
    const x = X();
    if (kind === "format") { el.querySelector(".nope-format").hidden = false; return; }
    if (kind === "format-ok") { const c = el.querySelector(".nope-format select").value; if (!cons.exclude_categories.includes(c)) cons.exclude_categories.push(c); return A.ask(); }
    if (kind === "far") {
      cons.max_distance_m = Math.max(50, Math.floor(Math.min(cons.max_distance_m || Infinity, r.distance_m) * 0.6 / 50) * 50);
      if (!cons.exclude_ids.includes(r.poi_id)) cons.exclude_ids.push(r.poi_id);
      return A.ask();
    }
    if (kind === "been") { await keep(r, {visited_at: Date.now()}); if (!cons.exclude_ids.includes(r.poi_id)) cons.exclude_ids.push(r.poi_id); return A.ask(); }
    if (kind === "free") { cons.no_spend = "strict"; syncSpend(); return A.ask(); }
    if (kind === "other") {
      // one card is replaced; the rest of the answer stays on the screen
      const b = el.querySelector('[data-nope="other"]'); b.disabled = true; b.textContent = x.replacing;
      const last = state.last;
      try {
        const body = {...state.lastReq, ...ext.requestExtras(state.lastReq)};
        body.preferences = {...body.preferences, exclude_poi_ids: [...new Set([
          ...(body.preferences?.exclude_poi_ids || []), ...last.recommendations.map(q => q.poi_id)])]};
        if (body.preferences.exclude_poi_ids.length > 200) throw new Error("too_many_exclusions");
        const res = await A.postJSON("/recommend", body);
        if (state.last !== last) return;
        const next = (res.recommendations || []).find((q) => !last.recommendations.some((o) => o.poi_id === q.poi_id));
        if (next) { state.last = {...last, recommendations: last.recommendations.map((o) => (o.poi_id === r.poi_id ? next : o))}; A.render(state.last); }
        else { b.disabled = false; b.textContent = x.nOther; }
      } catch { b.disabled = false; b.textContent = x.nOther; }
    }
  }

  // ---------- F5: no-spend filter in "Context" ----------
  function syncSpend() { const s = $("#noSpend"); if (s) s.value = cons.no_spend || ""; }
  function mountSpend() {
    if ($("#noSpendField") || !has("constraints")) return;
    const x = X(), lab = document.createElement("label");
    lab.id = "noSpendField";
    lab.innerHTML = `<span>${esc(x.noSpend)}</span><select id="noSpend"><option value="">${esc(x.noSpendOff)}</option>
      <option value="lenient">${esc(x.noSpendLenient)}</option><option value="strict">${esc(x.noSpendStrict)}</option></select>`;
    $(".ctx-grid").appendChild(lab);
    $("#noSpend").addEventListener("change", (e) => { cons.no_spend = e.target.value || null; });
    syncSpend();
  }

  // ---------- F2: finish point ----------
  function mountFinish() {
    if ($("#finishField") || !has("end_point")) return;
    const x = X(), box = document.createElement("div");
    box.id = "finishField"; box.className = "finish-field";
    $(".ctx-grid").appendChild(box);
    renderFinish();
  }
  function renderFinish() {
    const box = $("#finishField"); if (!box) return;
    const x = X(), p = finish && finish.presetLabel ? finish.presetLabel : finish ? `${r3(finish.lat)}, ${r3(finish.lon)}` : "";
    box.innerHTML = `<span class="lbl">${esc(x.finish)}</span>
      <label class="check"><input type="radio" name="finishMode" value="back" ${finish ? "" : "checked"}> ${esc(x.finishBack)}</label>
      <label class="check"><input type="radio" name="finishMode" value="other" ${finish || picking ? "checked" : ""}> ${esc(x.finishOther)}</label>
      <div class="row finish-pick" ${finish || picking ? "" : "hidden"}>
        <button type="button" class="btn small" id="pickFinish">${icon("finish")} ${esc(picking ? x.pickHint : x.pickOnMap)}</button>
        <select id="finishPreset"><option value="">${esc(x.finishLandmark)}</option>${state.presets.map((q) =>
          `<option value="${esc(q.id)}">${esc((q.label && (q.label[state.lang] || q.label.ru)) || q.name || q.id)}</option>`).join("")}</select>
        ${finish ? `<span class="meta">${esc(fmt(x.finishSet, {p}))}</span> <button type="button" class="btn small" id="resetFinish">${esc(x.reset)}</button>` : ""}</div>`;
    box.querySelectorAll('[name="finishMode"]').forEach((r) => r.addEventListener("change", () => {
      if (r.value === "back") { finish = null; picking = false; drawFinish(); }
      else picking = !finish;
      renderFinish();
    }));
    const pf = $("#pickFinish"); if (pf) pf.addEventListener("click", () => { picking = true; renderFinish(); });
    const fp = $("#finishPreset"); if (fp) fp.addEventListener("change", () => {
      const q = state.presets.find((z) => z.id === fp.value);
      if (q) { finish = {lat: q.lat, lon: q.lon, source: "landmark", presetLabel: fp.selectedOptions[0].textContent}; picking = false; drawFinish(); renderFinish(); }
    });
    const rf = $("#resetFinish"); if (rf) rf.addEventListener("click", () => { finish = null; picking = false; drawFinish(); renderFinish(); });
  }
  ext.onMapClick = (e) => {
    if (!picking) return false;
    finish = {lat: e.latlng.lat, lon: e.latlng.lng, source: "map"}; picking = false;
    drawFinish(); renderFinish();
    return true;
  };
  function drawFinish() {
    if (finishMarker) { map.removeLayer(finishMarker); finishMarker = null; }
    if (!finish) return;
    const fi = L.divIcon({className: "", iconSize: [30, 30], iconAnchor: [15, 15], html: `<div class="pin finish-pin">${icon("finish")}</div>`});
    finishMarker = L.marker([finish.lat, finish.lon], {icon: fi, title: X().finish}).addTo(map);
  }

  // ---------- F7: search by atmosphere ----------
  async function mountAtmosphere() {
    if ($("#atmosField") || !has("atmosphere")) return;
    try {
      const res = await A.getJSON(A.API + "/atmosphere/examples");
      atmosExamples = (res.examples || []).map(a => ({id: a.example_id, title: a.titles,
        fallbackTitle: a.title, image_url: a.photos?.[0]?.url, credit: a.photos?.[0]?.attribution}));
    } catch { atmosExamples = []; }
    if (!Array.isArray(atmosExamples) || $("#atmosField")) return;
    const box = document.createElement("div");
    box.id = "atmosField"; box.className = "atmos";
    $(".ask").insertAdjacentElement("afterend", box);
    renderAtmosphere();
  }
  function renderAtmosphere() {
    const box = $("#atmosField"); if (!box) return;
    const x = X(), safe = (u) => (/^(https:\/\/|img\/)/.test(u || "") ? u : "");
    if (!atmosExamples.length) { box.innerHTML = `<p class="meta">${esc(x.unavailableAtmosphere)}</p>`; return; }
    box.innerHTML = `<p class="lbl">${icon("image")} ${esc(x.atmos)} <span class="meta">${esc(x.atmosHint)}</span></p><div class="atmos-row">
      <button type="button" class="atmos-tile none${atmosphere ? "" : " on"}" data-atmos="" aria-pressed="${!atmosphere}">${esc(x.atmosAny)}</button>
      ${atmosExamples.map((a) => `<button type="button" class="atmos-tile${atmosphere === a.id ? " on" : ""}" data-atmos="${esc(a.id)}" aria-pressed="${atmosphere === a.id}" title="${esc(a.credit || "")}">
        ${safe(a.image_url) ? `<img src="${esc(safe(a.image_url))}" alt="" loading="lazy">` : ""}<span>${esc((a.title && (a.title[state.lang] || a.title.ru)) || a.fallbackTitle || a.id)}</span></button>`).join("")}</div>`;
    box.querySelectorAll("[data-atmos]").forEach((b) => b.addEventListener("click", () => { atmosphere = b.dataset.atmos || null; renderAtmosphere(); }));
  }

  // ---------- F4: comfort points ----------
  async function loadComfort(d) {
    const version = ++comfortVersion, answerVersion = state.requestVersion;
    comfortLayer.clearLayers(); comfortMsg = "";
    if (!comfortKinds.size || !has("comfort")) { A.rerender(); return; }
    // Only an actual server route is a route. Independent cards are not consecutive stops.
    const geometry = walk?.plan?.server?.geometry || [];
    const route = geometry.length ? geometry.filter((_, i) => i % Math.ceil(geometry.length / 19) === 0)
      .concat([geometry[geometry.length - 1]]).map(([lon, lat]) => ({lat: r3(lat), lon: r3(lon)})) : [];
    try {
      const pts = await A.postJSON("/comfort/search", {location: currentLocation(), route_points: route,
        kinds: [...comfortKinds].map(k => ({warm: "warming", sit: "bench"}[k] || k)), radius_m: 300});
      if (version !== comfortVersion || answerVersion !== state.requestVersion) return;
      if (!pts.length) comfortMsg = X().comfortNone;
      pts.forEach((p) => {
        const ic = {warming: "fire", toilet: "toilet", bench: "bench", water: "water", entrance: "door"}[p.kind] || "info";
        const di = L.divIcon({className: "", iconSize: [26, 26], iconAnchor: [13, 13], html: `<div class="cpin">${icon(ic)}</div>`});
        const acc = {public: X().accFree, customers_only: X().accCustomers, paid: X().costPaid}[p.access] || X().accUnknown;
        L.marker([p.coords.lat, p.coords.lon], {icon: di, title: p.name}).addTo(comfortLayer).bindPopup(
          `<b>${esc(p.name)}</b><br>${esc(acc)}${p.note ? ` · ${esc(p.note)}` : ""}${p.floor ? `<br>${esc(p.floor)}` : ""}
           <br><span class="src">${esc(T().sources)}: ${esc(p.source_url || "")}${p.checked_at ? ` · ${esc(p.checked_at)}` : ""}</span>
           ${walk?.plan?.server && has("replan") ? `<br><button type="button" class="btn small" data-addstop="${esc(p.poi_id)}">${esc(X().addStop)}</button>` : ""}`);
      });
    } catch { if (version !== comfortVersion || answerVersion !== state.requestVersion) return; comfortMsg = T().serverDown; }
    A.rerender();
  }
  map.on("popupopen", (e) => {
    const el = e.popup && e.popup.getElement && e.popup.getElement();
    const b = el && el.querySelector("[data-addstop]");
    if (b) b.addEventListener("click", () => replan("add_stop", b.dataset.addstop));
  });

  // ---------- F6: saved walks, F1: the walk in progress ----------
  const currentLocation = () => ({lat: r3(state.loc.lat), lon: r3(state.loc.lon), precision_m: 100,
    source: ["gps", "map", "preset"].includes(state.loc.source) ? state.loc.source : "map"});
  function planView(result, request, done = [], deadline = null) {
    request = JSON.parse(JSON.stringify(request));
    request.preferences = result.applied_preferences;
    request.context = {...request.context, exclude_categories: result.state.exclude_categories,
      companions: result.state.companions, accessibility: result.state.accessibility};
    delete request.feedback;
    const build = {request, finish_mode: result.state.finish_mode, destination: result.state.finish,
      origin: result.state.origin, stop_ids: result.stops.map(s => s.poi_id),
      completed_ids: result.state.completed_ids, skipped_ids: result.state.skipped_ids,
      reserve_min: result.budget.reserve_min, max_stops: 5};
    return {version: 2, saved_at: null, lang: state.lang, query: request.query,
      start: result.state.origin, end: result.state.finish, budget_min: result.budget.available_min,
      total_min: result.budget.total_min, server: result, request, build_request: build,
      deadline_ms: deadline ?? Date.now() + result.budget.available_min * 60000,
      stops: [...done, ...result.stops.filter(s => !done.some(d => d.poi_id === s.poi_id)).map((s, i) => ({
        poi_id: s.poi_id, name: s.name, coords: s.coords, stay_min: s.stay_min,
        walk_min: result.legs[i]?.walk_min || 0, hours_text: s.open_status.hours || "", status: "next"}))]};
  }
  function usablePlan(result) {
    return result.fits && ["ok", "partial"].includes(result.status) && result.stops.length;
  }
  let buildVersion = 0;
  async function buildAnswer(d, saving, selectedId = state.selectedPlaceId) {
    const msg = selectedId ? $("#selectedWalkMsg") : $("#saveWalkMsg"), version = state.requestVersion;
    const build = ++buildVersion;
    const buttons = [$("#saveWalkBtn"), $("#startWalkBtn"), $("#startSelectedWalk")].filter(Boolean);
    buttons.forEach(b => b.disabled = true);
    if (msg) msg.textContent = X().replanning;
    try {
      const request = JSON.parse(JSON.stringify(state.lastReq));
      delete request.cursor; delete request.request_id;
      const payload = {request, stop_ids: selectedId ? [selectedId] : d.recommendations.map(r => r.poi_id), max_stops: selectedId ? 1 : 3,
        finish_mode: request.end ? "destination" : "return", destination: request.end || null};
      const result = await A.postJSON("/plans/build", payload, 40000);
      if (version !== state.requestVersion || build !== buildVersion || selectedId !== state.selectedPlaceId) return;
      if (!usablePlan(result) || (selectedId && (result.stops.length !== 1 || result.stops[0].poi_id !== selectedId))) {
        if (msg) msg.textContent = X().planUnavailable; return;
      }
      const plan = planView(result, request);
      if (saving) await saveWalk(plan); else startWalk(plan, null);
      if (!saving && msg) msg.textContent = result.notes.join(" ");
    } catch { if (msg && version === state.requestVersion) msg.textContent = X().replanFail; }
    finally { buttons.forEach(b => b.disabled = false); }
  }
  async function saveWalk(plan) {
    const msg = $("#saveWalkMsg") || $("#walkMsg");
    try {
      if (!plan.build_request || navigator.onLine === false) {
        if (msg) msg.textContent = X().exportNeedsOnline;
        return;
      }
      const saved = await A.postJSON("/plans/export", {schema_version: 1, plan: plan.build_request}, 40000);
      if (saved.status !== "saved" || !saved.stops.length) {
        if (msg) msg.textContent = X().notExportable;
        return;
      }
      // Keep only the reviewed export, never the in-memory provider response or plan state.
      const row = await S.saveWalk({version: 2, saved_at: saved.saved_at, offline: saved,
        lang: plan.lang, query: plan.query, id: plan.id,
        request_context: {companions: plan.request.context?.companions || "alone",
          accessibility: !!plan.request.context?.accessibility, time_budget_min: plan.budget_min,
          lang: plan.lang, exclude_categories: plan.request.context?.exclude_categories || []},
        preferences: plan.server?.applied_preferences || plan.request.preferences || {},
        total_min: saved.budget?.total_min ?? null,
        stops: saved.stops.map(s => ({...s, walk_min: null, hours_text: "", status: "next"}))});
      mine.walks = [row, ...mine.walks.filter((w) => w.id !== row.id)];
      if (walk && !walk.savedId) walk.savedId = row.id;
      if (msg) msg.textContent = S.problem === "blocked" ? X().storeBlocked : saved.contains_full_route ? X().saved : X().partialExport;
    } catch (e) { if (msg) msg.textContent = e && e.name === "QuotaExceededError" ? X().storeQuota : X().storeBlocked; }
    renderMine();
  }
  function startWalk(plan, savedId) {
    if (!plan.server && !plan.offline) return;
    walk = {plan: JSON.parse(JSON.stringify(plan)), savedId, history: [], collapsed: false, proposal: null};
    walkMsg = ""; walkBusy = false; walkVersion++;
    renderWalk();
    $("#walk").scrollIntoView({behavior: "smooth", block: "start"});
  }
  function renderWalk() {
    const box = $("#walk"); if (!box) return;
    pauseLayer.clearLayers();
    if (walkLine) { map.removeLayer(walkLine); walkLine = null; }
    box.hidden = !walk;
    if (!walk) { box.innerHTML = ""; return; }
    const x = X(), p = walk.plan, saved = walk.savedId && p.saved_at;
    if (p.server?.geometry?.length && L.polyline) {
      walkLine = L.polyline(p.server.geometry.map(([lon, lat]) => [lat, lon]), {
        color: "#00708A", weight: 5, dashArray: p.server.routing_source === "osrm_foot" ? null : "8 8",
      }).addTo(map);
    }
    const proposed = walk.proposal?.plan.stops.filter(s => !p.stops.some(old => old.poi_id === s.poi_id)) || [];
    proposed.forEach(s => {
      const pin = L.divIcon({className: "", iconSize: [30,30], iconAnchor: [15,15], html: `<div class="cpin">${icon("coffee")}</div>`});
      L.marker([s.coords.lat, s.coords.lon], {icon: pin, title: s.name}).addTo(pauseLayer)
        .bindPopup(`<b>${esc(s.name)}</b><br>${esc(x.breakPreview)}`)
        .on("click", () => { walk.collapsed = false; renderWalk(); $("#walkProposal")?.scrollIntoView({block: "start", behavior: "smooth"}); });
    });
    if (walk.collapsed) {
      box.innerHTML = `<div class="walk-head"><h2>${icon("walk")} ${esc(x.activeWalk)}</h2>
        <button type="button" class="btn" id="walkResume">${esc(x.resumeWalk)}</button></div>`;
      $("#walkResume").addEventListener("click", () => { walk.collapsed = false; renderWalk(); });
      return;
    }
    const next = p.stops.filter((s) => s.status === "next");
    const statusL = {done: x.statusDone, skipped: x.statusSkipped, next: x.statusNext};
    const can = has("replan") && navigator.onLine !== false && !!p.server;
    box.innerHTML = `<div class="walk-head"><h2>${icon("walk")} ${esc(x.activeWalk)}</h2>
        <button type="button" class="btn small" id="walkClose">${icon("x")} ${esc(x.close)}</button></div>
      ${p.query ? `<p class="meta">«${esc(p.query)}»</p>` : ""}
      ${saved ? `<p class="src">${esc(fmt(x.savedAt, {d: new Date(p.saved_at).toLocaleString(state.lang === "en" ? "en-GB" : "ru-RU")}))}</p><p class="msg warn">${esc(x.stale)}</p>` : ""}
      ${navigator.onLine === false ? `<p class="msg info">${esc(x.offline)}</p>` : saved ? `<div class="row"><span class="meta">${esc(x.backOnline)}</span><button type="button" class="btn small" id="walkRefresh">${icon("refresh")} ${esc(x.refresh)}</button></div>` : ""}
      ${p.offline && !p.offline.contains_full_route ? `<p class="msg warn">${esc(x.partialExport)}</p>` : ""}
      ${p.total_min ? `<p class="walk-left">${esc(fmt(x.remaining, {m: p.total_min}))}</p>` : ""}
      ${p.server ? `<p class="src">${esc(p.server.notes.join(" "))}</p>` : ""}
      ${p.server?.legs?.length ? `<p class="meta">${esc(fmt(x.toEnd, {m: p.server.legs[p.server.legs.length-1].walk_min}))} · ${esc(fmt(x.arrival, {
        t: new Intl.DateTimeFormat(state.lang === "en" ? "en-GB" : "ru-RU", {hour:"2-digit",minute:"2-digit",timeZone:"Asia/Almaty"}).format(new Date(p.server.estimated_arrival_at)),
      }))}</p>` : ""}
      <ol class="walk-stops">${p.stops.map((s, i) => `<li class="ws ws-${esc(s.status)}"><div><b>${esc(s.name)}</b> <span class="meta">· ${esc(statusL[s.status] || s.status)}</span></div>
        <div class="meta">${s.address ? esc(s.address) + " · " : ""}${s.walk_min != null ? `${icon("walk")} ${esc(s.walk_min)} ${esc(T().minutes)} · ` : ""}${s.stay_min ? `${esc(s.stay_min)} ${esc(T().minutes)}` : ""}${s.hours_text ? ` · ${esc(s.hours_text)}` : ""}</div>
        ${(mine.places.get(s.poi_id) || {}).note ? `<div class="meta">${icon("note")} ${esc(mine.places.get(s.poi_id).note)}</div>` : ""}
        ${s.status === "next" ? `<div class="row"><button type="button" class="btn small" data-ws="done" data-i="${i}">${icon("check")} ${esc(x.done)}</button>
          <button type="button" class="btn small" data-ws="skip" data-i="${i}">${esc(x.skip)}</button></div>` : ""}</li>`).join("")}</ol>
      ${can && next.length ? `<div class="row changes"><button type="button" class="btn small" data-ch="less_time">${esc(x.chLess)}</button>
        <button type="button" class="btn small" data-ch="cold">${esc(x.chCold)}</button><button type="button" class="btn small" data-ch="tired">${esc(x.chTired)}</button>
        <button type="button" class="btn small" data-ch="closed">${esc(x.chClosed)}</button></div>` : ""}
      ${walkBusy ? `<div class="loading"><div class="spinner"></div>${esc(x.replanning)}</div>
        <button type="button" class="btn small" id="walkCancel">${esc(x.cancelReplan)}</button>` : ""}
      <p class="src" id="walkMsg" aria-live="polite">${esc(walkMsg)}</p>
      ${walk.proposal ? `<section class="card block break-preview" id="walkProposal"><h3>${esc(x.breakPreview)}</h3>
        <p>${esc(x.breakKeepsRoute)}</p>
        ${proposed.map(s => `<p><b>${esc(s.name)}</b> · ${esc(s.walk_min)} ${esc(T().walk)}</p>
          ${ext.cardBadges(walk.proposal.plan.server.stops.find(p => p.poi_id === s.poi_id) || {})}`).join("")}
        <p>${esc(fmt(x.remaining, {m: walk.proposal.plan.total_min}))}</p>
        <p class="meta">${esc(walk.proposal.plan.server.notes.join(" "))}</p>
        <div class="row"><button type="button" class="btn primary" id="applyWalkProposal">${esc(x.applyBreak)}</button>
        <button type="button" class="btn" id="discardWalkProposal">${esc(x.keepCurrentRoute)}</button></div></section>` : ""}
      ${walk.history.length ? `<button type="button" class="btn small" id="walkUndo">${esc(x.undoReplan)}</button>` : ""}
      <div class="row">${p.build_request ? `<button type="button" class="btn" id="walkSave">${icon("save")} ${esc(x.saveWalk)}</button>` : ""}
        <button type="button" class="btn" id="walkEnd">${esc(x.endWalk)}</button></div>`;
    $("#walkClose").addEventListener("click", () => {
      walkVersion++; walkBusy = false; walk.collapsed = true; renderWalk();
    });
    $("#walkEnd").addEventListener("click", () => { walkVersion++; walkBusy = false; walk = null; renderWalk(); });
    const ws = $("#walkSave"); if (ws) ws.addEventListener("click", () => saveWalk(walk.plan));
    const cancel = $("#walkCancel"); if (cancel) cancel.addEventListener("click", () => {
      walkVersion++; walkBusy = false; walkMsg = X().replanCancelled; renderWalk();
    });
    const undo = $("#walkUndo"); if (undo) undo.addEventListener("click", undoReplan);
    $("#discardWalkProposal")?.addEventListener("click", () => { walkVersion++; walk.proposal = null; walkBusy = false; walkMsg = X().replanCancelled; renderWalk(); });
    $("#applyWalkProposal")?.addEventListener("click", () => {
      const proposal = walk.proposal;
      if (!proposal || Date.now() - proposal.created > 60000 || proposal.plan.deadline_ms - Date.now() < 300000) {
        walk.proposal = null; walkMsg = X().breakExpired; renderWalk(); return;
      }
      walkVersion++; walkBusy = false;
      walk.history.push(JSON.parse(JSON.stringify(walk.plan))); if (walk.history.length > 5) walk.history.shift();
      walk.plan = proposal.plan; walk.proposal = null; walkMsg = X().breakAdded; renderWalk();
    });
    const wr = $("#walkRefresh"); if (wr) wr.addEventListener("click", () => {
      refreshWalk();
    });
    box.querySelectorAll("[data-ws]").forEach((b) => b.addEventListener("click", () => {
      const s = walk.plan.stops[+b.dataset.i];
      if (b.dataset.ws === "done") { walkVersion++; walkBusy = false; walk.proposal = null; s.status = "done"; }
      else if (can) return replan("skip", s.poi_id);
      else s.status = "skipped";
      renderWalk();
    }));
    box.querySelectorAll("[data-ch]").forEach((b) => b.addEventListener("click", () => {
      const ch = b.dataset.ch;
      if (ch === "less_time") {
        const m = window.prompt(x.lessHow, String(Math.max(10, Math.round((walk.plan.total_min || 60) / 2))));
        if (m === null) return;
        return replan("less_time", null, Math.max(5, Math.min(480, parseInt(m, 10) || 30)));
      }
      if (ch === "closed") { const s = walk.plan.stops.find((q) => q.status === "next"); return replan("closed", s && s.poi_id); }
      replan(ch);
    }));
  }
  function undoReplan() {
    if (!walk?.history.length) return;
    walkVersion++; walkBusy = false; walk.proposal = null;
    const current = walk.plan, restored = walk.history.pop();
    // Reverting a suggestion must not undo physical progress or grant extra time.
    const done = current.stops.filter(s => s.status === "done");
    const completed = [...new Set([...restored.server.state.completed_ids,
      ...current.server.state.completed_ids, ...done.map(s => s.poi_id)])];
    restored.stops.forEach(s => { if (completed.includes(s.poi_id)) s.status = "done"; });
    restored.stops.push(...done.filter(s => !restored.stops.some(p => p.poi_id === s.poi_id)));
    restored.server.state.completed_ids = completed;
    restored.server.state.remaining_ids = restored.server.state.remaining_ids.filter(id => !completed.includes(id));
    restored.build_request.completed_ids = completed;
    restored.build_request.stop_ids = restored.build_request.stop_ids.filter(id => !completed.includes(id));
    restored.deadline_ms = Math.min(restored.deadline_ms, current.deadline_ms);
    walk.plan = restored; walkMsg = X().replanRestored; renderWalk();
  }
  // the newest change wins: a late answer to an older change never replaces the plan
  async function replan(change, target, remaining) {
    if (!walk?.plan?.server || !has("replan")) return;
    if (["cold", "tired"].includes(change) && !has("nearby_break")) {
      walkMsg = X().breakNeedsUpdate; renderWalk(); return;
    }
    const version = ++walkVersion, before = JSON.parse(JSON.stringify(walk.plan));
    walkBusy = true; walkMsg = ""; walk.proposal = null; renderWalk();
    const left = remaining ?? Math.floor((before.deadline_ms - Date.now()) / 60000);
    if (left < 5) { walkBusy = false; walkMsg = X().planUnavailable; renderWalk(); return; }
    const request = {...before.request, location: currentLocation(),
      context: {...before.request.context, lang: state.lang, simulate: false, now: null}};
    delete request.preferences; delete request.feedback;
    const completed = before.stops.filter(s => s.status === "done" && before.server.state.remaining_ids.includes(s.poi_id)).map(s => s.poi_id);
    const body = {request, previous: before.server.state, reason: change,
      remaining_time_min: left, completed_ids: completed, reserve_min: before.server.budget.reserve_min};
    const nearbyBreak = ["cold", "tired"].includes(change);
    if (nearbyBreak) body.keep_stops = true;
    if (target) body.poi_id = target;
    try {
      const res = await A.postJSON("/plans/recalculate", body, 40000);
      if (version !== walkVersion || !walk) return;
      if (!usablePlan(res)) {
        const error = new Error("plan_unavailable");
        if (res.status === "no_matches" || !res.stops?.length) error.code = "no_replacement_found";
        throw error;
      }
      // Never accept an old/incompatible server's replacement as an additive break.
      if (nearbyBreak && (before.stops.some(s => s.status === "next" && !res.stops.some(p => p.poi_id === s.poi_id))
          || JSON.stringify(res.state.finish) !== JSON.stringify(before.server.state.finish))) throw new Error("lost_destination");
      request.preferences = res.applied_preferences;
      request.context.exclude_categories = res.state.exclude_categories;
      request.context.time_budget_min = left;
      const replacement = planView(res, request, before.stops.filter(s => s.status === "done"),
        remaining != null ? Date.now() + remaining * 60000 : before.deadline_ms);
      if (nearbyBreak) {
        if (!replacement.stops.some(s => !before.stops.some(p => p.poi_id === s.poi_id))) throw new Error("no_new_stop");
        walk.proposal = {plan: replacement, created: Date.now()}; walkMsg = X().breakKeepsRoute; return;
      }
      walk.history.push(before); if (walk.history.length > 5) walk.history.shift();
      walk.plan = replacement;
      walkMsg = res.notes.join(" ");
    } catch (error) {
      if (version !== walkVersion || !walk) return;
      walk.plan = before;
      walkMsg = error.code === "no_replacement_found" ? X().replanEmpty : X().replanFail;
    } finally { if (version === walkVersion) { walkBusy = false; renderWalk(); } }
  }

  async function refreshWalk() {
    if (!walk?.plan?.offline) return;
    const old = walk.plan, version = ++walkVersion;
    walkBusy = true; renderWalk();
    try {
      const request = {location: currentLocation(), query: old.query || "", source: "local",
        context: {...old.request_context, lang: state.lang, simulate: false}, preferences: old.preferences || {}};
      const result = await A.postJSON("/plans/refresh", {saved: old.offline, request}, 40000);
      if (version !== walkVersion || !walk) return;
      if (!usablePlan(result)) throw new Error("plan_unavailable");
      walk.plan = planView(result, request);
      walk.savedId = null;
      walkMsg = result.notes.join(" ");
    } catch { if (version === walkVersion && walk) walkMsg = X().replanFail; }
    finally { if (version === walkVersion) { walkBusy = false; renderWalk(); } }
  }

  // ---------- F8: my places ----------
  function renderMine() {
    const box = $("#mine"); if (!box || box.hidden) return;
    const x = X(), all = [...mine.places.values()].map(placeView).sort((a, b) => (b.updated_at || 0) - (a.updated_at || 0));
    const pick = {all: () => true, want: (p) => p.want, visited: (p) => p.visited_at, favorite: (p) => p.favorite}[mine.filter] || (() => true);
    const list = all.filter(pick);
    const tab = (k, l, n) => `<button type="button" role="tab" class="tab${mine.tab === k ? " on" : ""}" data-tab="${k}" aria-selected="${mine.tab === k}">${esc(l)} (${n})</button>`;
    const fchip = (k, l) => `<button type="button" class="chip-btn${mine.filter === k ? " on" : ""}" data-filter="${k}" aria-pressed="${mine.filter === k}">${esc(l)}</button>`;
    box.innerHTML = `<div class="walk-head"><h2 id="mineTitle">${icon("heart")} ${esc(x.keepTitle)}</h2>
        <button type="button" class="btn small" id="mineClose">${icon("x")} ${esc(x.close)}</button></div>
      <p class="src">${esc(x.deviceOnly)}</p>${mine.error ? `<p class="msg warn">${esc(mine.error)}</p>` : ""}
      <div class="tabs" role="tablist">${tab("places", x.tabPlaces, all.length)}${tab("walks", x.tabWalks, mine.walks.length)}</div>
      ${mine.tab === "places" ? `<div class="row">${fchip("all", x.fAll)}${fchip("want", x.fWant)}${fchip("visited", x.fVisited)}${fchip("favorite", x.fFav)}</div>
        <label class="check"><input type="checkbox" id="onlyNew" ${mine.onlyNew ? "checked" : ""}> ${esc(x.onlyNew)}</label>
        <label class="check"><input type="checkbox" id="mineOnMap" ${mine.onMap ? "checked" : ""}> ${esc(x.showOnMap)}</label>
        ${list.length ? `<ul class="mine-list">${list.map((p) => `<li><div><b>${esc(p.name || `${x.providerBookmark} (${p.poi_id})`)}</b>
            <span class="marks">${p.want ? icon("flag") : ""}${p.visited_at ? icon("visit") : ""}${p.favorite ? icon("heart") : ""}</span></div>
            ${p.note ? `<div class="meta">${icon("note")} ${esc(p.note)}</div>` : ""}
            ${/^2gis_\d+$/.test(p.poi_id) ? `<a class="btn small" target="_blank" rel="noopener" href="https://2gis.kz/astana/firm/${esc(p.poi_id.slice(5))}">2ГИС</a>` : ""}
            <div class="row">${p.coords ? `<button type="button" class="btn small" data-mine-map="${esc(p.poi_id)}">${icon("pin")} ${esc(T().onMap)}</button>` : ""}
            <button type="button" class="btn small" data-mine-del="${esc(p.poi_id)}">${icon("trash")} ${esc(x.remove)}</button></div></li>`).join("")}</ul>`
          : `<p class="meta">${esc(x.emptyPlaces)}</p>`}`
      : mine.walks.length ? `<ul class="mine-list">${mine.walks.map((w) => `<li><div><b>${esc(w.query || x.activeWalk)}</b></div>
            <div class="meta">${esc(fmt(x.savedAt, {d: new Date(w.saved_at).toLocaleString(state.lang === "en" ? "en-GB" : "ru-RU")}))} · ${esc(w.stops.length)} ${esc(x.stops.toLowerCase())}</div>
            <div class="row"><button type="button" class="btn small" data-walk-open="${esc(w.id)}">${esc(x.open)}</button>
            <button type="button" class="btn small" data-walk-del="${esc(w.id)}">${icon("trash")} ${esc(x.remove)}</button></div></li>`).join("")}</ul>`
        : `<p class="meta">${esc(x.emptyWalks)}</p>`}
      <div class="row clear-row">${mine.confirmClear ? `<span class="meta">${esc(x.clearConfirm)}</span>
          <button type="button" class="btn small danger" id="clearYes">${esc(x.yes)}</button><button type="button" class="btn small" id="clearNo">${esc(x.no)}</button>`
        : `<button type="button" class="btn small" id="clearAll">${icon("trash")} ${esc(x.clearAll)}</button>`}</div>`;
    $("#mineClose").addEventListener("click", toggleMine);
    box.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => { mine.tab = b.dataset.tab; renderMine(); }));
    box.querySelectorAll("[data-filter]").forEach((b) => b.addEventListener("click", () => { mine.filter = b.dataset.filter; renderMine(); }));
    const on = $("#onlyNew"); if (on) on.addEventListener("change", () => { mine.onlyNew = on.checked; pref.set("seruen_only_new", mine.onlyNew); if (state.last) A.ask(); });
    const om = $("#mineOnMap"); if (om) om.addEventListener("change", () => { mine.onMap = om.checked; drawPersonal(); });
    box.querySelectorAll("[data-mine-map]").forEach((b) => b.addEventListener("click", () => {
      const p = placeView(mine.places.get(b.dataset.mineMap)); if (p && p.coords) { mine.onMap = true; drawPersonal(); A.showAt([p.coords.lat, p.coords.lon], 16); }
    }));
    box.querySelectorAll("[data-mine-del]").forEach((b) => b.addEventListener("click", async () => {
      try { await S.deletePlace(b.dataset.mineDel); } catch { /* memory copy below */ }
      mine.places.delete(b.dataset.mineDel); renderMine(); drawPersonal(); A.rerender();
    }));
    box.querySelectorAll("[data-walk-open]").forEach((b) => b.addEventListener("click", async () => {
      const w = mine.walks.find((q) => q.id === b.dataset.walkOpen) || await S.getWalk(b.dataset.walkOpen);
      if (w) startWalk(w, w.id);
    }));
    box.querySelectorAll("[data-walk-del]").forEach((b) => b.addEventListener("click", async () => {
      try { await S.deleteWalk(b.dataset.walkDel); } catch { /* memory copy below */ }
      mine.walks = mine.walks.filter((w) => w.id !== b.dataset.walkDel);
      if (walk && walk.savedId === b.dataset.walkDel) { walk = null; renderWalk(); }
      renderMine();
    }));
    const ca = $("#clearAll"); if (ca) ca.addEventListener("click", () => { mine.confirmClear = true; renderMine(); });
    const cn = $("#clearNo"); if (cn) cn.addEventListener("click", () => { mine.confirmClear = false; renderMine(); });
    const cy = $("#clearYes"); if (cy) cy.addEventListener("click", async () => {
      try { await S.clearAll(); } catch { /* memory copy below */ }
      try { localStorage.removeItem("seruen_visited"); } catch { /* private mode */ }
      mine.places.clear(); mine.walks = []; mine.confirmClear = false; walk = null;
      renderWalk(); renderMine(); drawPersonal(); A.rerender();
    });
  }
  function toggleMine() {
    const box = $("#mine"), btn = $("#mineBtn");
    box.hidden = !box.hidden; btn.setAttribute("aria-expanded", String(!box.hidden));
    if (!box.hidden) { renderMine(); box.scrollIntoView({behavior: "smooth", block: "start"}); }
  }
  function drawPersonal() {
    personal.clearLayers();
    if (!mine.onMap) return;
    mine.places.forEach((stored) => {
      const p = placeView(stored);
      if (!p.coords) return;
      const ic = p.favorite ? "heart" : p.want ? "flag" : "visit";
      const di = L.divIcon({className: "", iconSize: [24, 24], iconAnchor: [12, 12], html: `<div class="ppin">${icon(ic)}</div>`});
      L.marker([p.coords.lat, p.coords.lon], {icon: di, title: p.name}).addTo(personal).bindPopup(`<b>${esc(p.name)}</b>${p.note ? `<br>${esc(p.note)}` : ""}`);
    });
  }

  // ---------- wiring ----------
  ext.onHealth = () => { mountSpend(); mountFinish(); mountAtmosphere(); A.rerender(); if (walk) renderWalk(); };
  ext.onLang = () => { renderFinish(); renderAtmosphere(); renderMine(); renderWalk(); };
  // app.js has already started when this file runs, so wire up now
  function ready() {
    $("#mineBtn").addEventListener("click", toggleMine);
    window.addEventListener("online", () => renderWalk());
    window.addEventListener("offline", () => renderWalk());
    S.init().then(loadMine).then(() => { renderMine(); A.rerender(); }).catch(() => { mine.error = X().storeBlocked; });
  }
  window.SeruenFeatures = {mine, startWalk, saveWalk, planView, get walk() { return walk; }, get cons() { return cons; },
    setFinish: (f) => { finish = f; drawFinish(); renderFinish(); }, setAtmosphere: (a) => { atmosphere = a; }};
  ready();
  if (Object.keys(state.features || {}).length) ext.onHealth();
})();
