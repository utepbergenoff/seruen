/* Additive, capability-gated city experiences. No accounts or location persistence. */
(() => {
  "use strict";
  const A = window.SeruenApp, F = window.SeruenFeatures, E = window.SeruenExt;
  if (!A || !F || !E) return;
  const {state, $, esc, L, map} = A;
  const X = () => window.SeruenExperienceText[state.lang] || window.SeruenExperienceText.ru;
  const has = f => !!state.features?.[f];
  const overlays = L.layerGroup().addTo(map);
  let tab = null, sequence = 0, second = null, picking = false, preview = null;
  let mode = "walk", winterEnabled = false, winterLimit = 10, meetLimit = 30, showStories = false;
  let activeStory = null;
  const storyLayer = L.layerGroup().addTo(map);
  let storyIndex = [], storyLang = null, storyPending = false;
  const point = p => ({lat: A.round3(p.lat), lon: A.round3(p.lon), precision_m: 100, source: p.source || "map"});
  const stamp = () => JSON.stringify([state.locVersion, state.requestVersion, state.selectedPlaceId, state.lang,
    F.walk?.plan?.server || null, mode, winterEnabled, winterLimit, meetLimit, second,
    ["query","budget","whenSel","whenAt","companions","weather"].map(id => $("#"+id)?.value),
    $("#budgetAuto").checked, $("#access").checked]);
  const link = (url, label) => {
    try { if (new URL(url).protocol !== "https:") return ""; } catch { return ""; }
    return `<a class="btn small" href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`;
  };
  const normalized = name => String(name || "").split(",")[0].toLocaleLowerCase().replace(/[^\p{L}\p{N}]/gu, "");
  function matchedStory(place) {
    if (!has("city_history")) return null;
    // A 2GIS card points to the story's object through the server's verified canonical_id.
    const exact = storyIndex.find(p => p.poi_id === place.poi_id || (place.canonical_id && p.poi_id === place.canonical_id));
    if (exact) return exact;
    if (!place.coords) return null;
    return storyIndex.find(p => p.aliases.some(a => normalized(a) === normalized(place.name))
      && window.SeruenRoute.hav(p.coords, place.coords) <= 200) || null;
  }
  function storyContent(p) {
    const x = X();
    return `<p>${esc(p.story)}</p><p class="meta"><strong>${esc(x.look)}:</strong> ${esc(p.look_for)}</p>
      <p class="src">${esc(x.source)}: ${link(p.source_url, p.source_title)} · ${esc(p.checked_at)}</p>${link(p.wikipedia_url, x.more)}`;
  }
  function storyBlock(place) {
    const story = matchedStory(place);
    return story ? `<details class="place-story"><summary>${esc(X().placeStory)}</summary>${storyContent(story)}</details>` : "";
  }
  const oldCard = E.cardExtras, oldSelected = E.selectedPlaceActions;
  E.cardExtras = p => storyBlock(p) + (oldCard?.(p) || "");
  E.selectedPlaceActions = p => (oldSelected?.(p) || "") + (state.last?.recommendations?.some(r => r.poi_id === p.poi_id) ? "" : storyBlock(p));
  E.walkStopExtras = storyBlock;
  E.previewAction = where => has("plan_export") ? `<button type="button" class="btn${where === "active" ? " small" : ""}" data-plan-preview="${where}">${esc(X().previewGo)}</button>` : "";
  const oldExtras = E.requestExtras;
  E.requestExtras = req => {
    const out = oldExtras?.(req) || {};
    if (winterEnabled && has("winter_plan")) {
      const weather = req?.context?.weather;
      const limit = weather && (weather.temp_c <= -15 || weather.wind_ms >= 10) ? 5 : winterLimit;
      out.preferences = {...out.preferences, indoor_only: true, winter_mode: true,
        max_walk_min: Math.min(out.preferences?.max_walk_min || 120, limit)};
    }
    if (mode === "meet") delete out.end;
    return out;
  };
  async function loadStories() {
    if (!has("city_history") || storyLang === state.lang || storyPending) return;
    storyPending = true; const lang = state.lang;
    try {
      const data = await A.getJSON(A.API + "/city/stories?lang=" + encodeURIComponent(lang));
      if (state.lang === lang) {
        storyIndex = data.items.map(p => ({...p, ...p.translations?.[lang]})); storyLang = lang;
        A.rerender(); F.renderWalk(); drawStories();
      }
    } catch {
      if ($("#storyLayerStatus")) $("#storyLayerStatus").textContent = X().storyUnavailable;
    } finally { storyPending = false; if (state.lang !== lang) void loadStories(); }
  }
  function drawStories() {
    storyLayer.clearLayers();
    if (!showStories || !has("city_history") || storyLang !== state.lang) return;
    storyIndex.forEach(p => {
      const icon = L.divIcon({className: "", iconSize: [30, 30], iconAnchor: [15, 15], html: '<div class="cpin story-pin">◈</div>'});
      L.marker([p.coords.lat, p.coords.lon], {icon, title: p.title, alt: p.title, bubblingMouseEvents: false})
        .addTo(storyLayer).on("click", () => {
          A.freezeLocation(); activeStory = p; open("history");
          $("#experiences").scrollIntoView({block: "start", behavior: "smooth"});
        });
    });
    if ($("#storyLayerStatus")) $("#storyLayerStatus").textContent = `${storyIndex.length} ${X().verifiedStories}`;
  }
  function syncMode() {
    $("#goBtn").textContent = mode === "meet" ? X().find : A.T().go;
    $("#meetingFields").hidden = mode !== "meet";
    $("#results").hidden = mode === "meet";
    if (mode === "meet") map.removeLayer(A.layer); else A.layer.addTo(map);
    $("#scenarioStrip").hidden = mode === "meet" || !state.scenarios.length;
    if ($("#finishField")) $("#finishField").hidden = mode === "meet";
  }
  function mount() {
    const x = X();
    if (!has("meet_halfway")) mode = "walk";
    if (!has("winter_plan")) winterEnabled = false;
    $("#searchModeField").hidden = !has("meet_halfway");
    $("#searchModeField").innerHTML = has("meet_halfway") ? `<fieldset class="search-intent"><legend>${esc(x.searchFor)}</legend>
      <label><input type="radio" name="searchIntent" value="walk"${mode === "walk" ? " checked" : ""}><span>${esc(x.walkMode)}</span></label>
      <label><input type="radio" name="searchIntent" value="meet"${mode === "meet" ? " checked" : ""}><span>${esc(x.meetMode)}</span></label></fieldset>` : "";
    $("#searchModeField").querySelectorAll("input").forEach(el => el.onchange = () => {
      A.freezeLocation(); E.cancelMapPick?.(); state.requestVersion++; mode = el.value; $("#goBtn").disabled = false; open(null); mount();
    });
    $("#meetingFields").innerHTML = has("meet_halfway") ? `<p class="meta">${esc(x.first)}</p>
      <label for="meetPreset">${esc(x.second)}</label><div class="row"><select id="meetPreset"><option value="">${esc(x.choose)}</option>${state.presets.map(p => `<option value="${esc(p.id)}"${second?.preset === p.id ? " selected" : ""}>${esc(p.label?.[state.lang] || p.label?.ru || p.id)}</option>`).join("")}</select>
      <button type="button" class="btn small" id="meetPick">${esc(x.pick)}</button><button type="button" class="btn small" id="meetCancel" hidden>${esc(x.cancel)}</button></div>
      <p class="meta" id="meetPoint">${second ? esc(x.chosen) + ": " + esc(second.label) : ""}</p>
      <label>${esc(x.limit)} <select id="meetLimit">${[15,30,45,60].map(n => `<option value="${n}"${n === meetLimit ? " selected" : ""}>${n} ${esc(x.minutes)}</option>`).join("")}</select></label>
      <details class="meeting-privacy"><summary>${esc(x.privacyTitle)}</summary><p class="meta">${esc(x.privacy)}</p></details>` : "";
    if (has("meet_halfway")) {
      $("#meetPreset").onchange = e => { const p = state.presets.find(p => p.id === e.target.value); if (p) setSecond(p, p.label?.[state.lang] || p.label?.ru || p.id); };
      $("#meetLimit").onchange = e => { meetLimit = +e.target.value; open(null); };
      $("#meetPick").onclick = () => { picking = true; $("#meetPoint").textContent = x.picking; $("#meetCancel").hidden = false; $("#map").scrollIntoView({block:"center",behavior:"smooth"}); };
      $("#meetCancel").onclick = () => { picking = false; $("#meetCancel").hidden = true; $("#meetPoint").textContent = second ? `${x.chosen}: ${second.label}` : ""; };
    }
    $("#winterField").hidden = !has("winter_plan");
    $("#winterField").innerHTML = has("winter_plan") ? `<label class="winter-toggle"><input id="winterMode" type="checkbox"${winterEnabled ? " checked" : ""}><span><strong>${esc(x.winterOption)}</strong><small>${esc(x.winterShort)}</small></span></label>
      <div id="winterSettings"${winterEnabled ? "" : " hidden"}><label>${esc(x.outdoors)} <select id="winterLimit">${[5,10,15].map(n => `<option value="${n}"${n === winterLimit ? " selected" : ""}>${n} ${esc(x.minutes)}</option>`).join("")}</select></label><p class="meta">${esc(x.winterHint)}</p></div>` : "";
    if (has("winter_plan")) {
      $("#winterMode").onchange = e => { winterEnabled = e.target.checked; open(null); mount(); };
      $("#winterLimit").onchange = e => { winterLimit = +e.target.value; open(null); };
    }
    $("#storyLayerField").hidden = !has("city_history");
    $("#storyLayerField").innerHTML = has("city_history") ? `<label class="story-layer-toggle"><input id="showCityStories" type="checkbox"${showStories ? " checked" : ""}> ${esc(x.storyLayer)}</label><p class="meta" id="storyLayerStatus" role="status"></p>` : "";
    if (has("city_history")) $("#showCityStories").onchange = e => { showStories = e.target.checked; drawStories(); if (showStories) void loadStories(); };
    if (!$("#experienceBody")) $("#experiences").innerHTML = '<div id="experienceBody" hidden></div>';
    syncMode(); drawStories();
  }
  function open(next) {
    sequence++; picking = false; preview = null; overlays.clearLayers(); tab = next;
    $("#goBtn").disabled = false;
    $("#experiences").hidden = !tab;
    $("#experienceBody").hidden = !tab;
    if (tab) renderTab(); else $("#experienceBody").innerHTML = "";
  }
  function renderTab() {
    const x = X(), body = $("#experienceBody");
    if (!body || !tab) return;
    const heading = tab === "history" ? activeStory?.title : tab === "meet" ? x.meetingResults : x.preview;
    body.innerHTML = `<div class="experience-head"><h3>${esc(heading)}</h3><button class="btn small" id="experienceClose" type="button">${esc(x.backToPlaces)}</button></div>
      <p id="experienceMessage" role="status" class="meta"></p><div id="experienceResult"></div>`;
    $("#experienceClose").onclick = () => {
      mode = "walk"; open(null); mount();
      (state.last ? $("#results") : $("#askForm")).scrollIntoView({block:"start",behavior:"smooth"});
    };
    if (tab === "history" && activeStory) {
      $("#experienceResult").innerHTML = `<article class="story-card">${storyContent(activeStory)}<div class="row"><button type="button" class="btn" id="storyPreview">${esc(x.routeHere)}</button></div></article>`;
      $("#storyPreview").onclick = () => { const p=activeStory; open("preview"); buildPreview({poi:p,source:"local"}); };
    } else if (tab === "meet") say(x.fairness);
  }
  function setSecond(p, label) {
    sequence++; preview = null; second = {...point(p), label, preset: p.id || null}; picking = false;
    $("#meetCancel").hidden = true; $("#meetPoint").textContent = `${X().chosen}: ${label}`;
    if ($("#experienceResult")) $("#experienceResult").innerHTML = "";
    $("#goBtn").disabled = false; overlays.clearLayers(); pin(second, "B");
  }
  function pin(coords, name) {
    const icon = L.divIcon({className: "", iconSize: [30, 30], iconAnchor: [15, 15], html: `<div class="cpin experience-pin">${esc(name)}</div>`});
    return L.marker([coords.lat, coords.lon], {icon, title: name, interactive: false}).addTo(overlays);
  }
  function say(message) { if ($("#experienceMessage")) $("#experienceMessage").textContent = message; }
  async function run(buttonId, fn) {
    const seq = ++sequence, version = stamp(), button = $(buttonId);
    if (button) button.disabled = true;
    say(X().loading);
    const current = () => seq === sequence && version === stamp();
    try { await fn(current); }
    catch { if (current()) say(X().error); }
    finally { if (button?.isConnected && seq === sequence) button.disabled = false; if (seq === sequence && version !== stamp()) say(X().stale); }
  }
  async function makeRequest(fallbackQuery = "кофе") {
    let req = {location: point(state.loc), query: $("#query").value.trim() || fallbackQuery,
      context: {...await A.context(), lang: state.lang}};
    Object.assign(req, E.requestExtras?.(req) || {});
    // Text and per-request controls, not an old result's location/time, are authoritative.
    delete req.request_id;
    return req;
  }
  function meet() {
    if (!second) { say(X().selectionMissing); return; }
    return run("#goBtn", async current => {
      const req = await makeRequest(); delete req.end;
      if (!current()) return;
      const data = await A.postJSON("/meet/search", {request: req, second_location: point(second), max_walk_min: meetLimit}, 40000);
      if (!current()) return;
      const x = X(); overlays.clearLayers();
      say(data.items.length ? x.estimate + (req.context.simulate ? " " + x.simulated : "") : x.noMeet);
      $("#experienceResult").innerHTML = data.items.map((p, i) => `<article class="story-card"><h3>${esc(p.name)}</h3><div class="meeting-times"><span>A · ${esc(x.personA)}<strong>≈${p.walk_min[0]} ${esc(x.minutes)}</strong></span><span>B · ${esc(x.personB)}<strong>≈${p.walk_min[1]} ${esc(x.minutes)}</strong></span></div>
        <p class="meta">${esc(x.difference)}: ${p.difference_min} ${esc(x.minutes)} · ${esc(x.hours[p.open_status.state] || x.hours.unknown)} · ${esc(x.cost[p.visit_condition.kind] || x.cost.unknown)}</p>
        ${p.visit_condition.note ? `<p class="meta">${esc(p.visit_condition.note)}</p>` : ""}
        <div class="row"><button class="btn small" type="button" data-meet-map="${i}">${esc(x.onMap)}</button><button class="btn small" type="button" data-meet-route="${i}">${esc(x.routeHere)}</button></div></article>`).join("");
      const draw = p => { overlays.clearLayers(); pin(req.location, "A"); pin(second, "B"); pin(p.coords, "●");
        p.paths.forEach((path, i) => L.polyline(path.map(([lon,lat]) => [lat,lon]), {color: i ? "#BD6C00" : "#00708A", weight: 3, dashArray: "6 6"}).addTo(overlays));
        A.fitTo(L.latLngBounds([...p.paths[0], ...p.paths[1]].map(([lon,lat]) => [lat,lon])));
      };
      if (data.items.length) draw(data.items[0]);
      $("#experiences").scrollIntoView({block:"start",behavior:"smooth"});
      $("#experienceResult").querySelectorAll("[data-meet-map]").forEach(b => b.onclick = () => draw(data.items[+b.dataset.meetMap]));
      $("#experienceResult").querySelectorAll("[data-meet-route]").forEach(b => b.onclick = () => {
        const poi = data.items[+b.dataset.meetRoute]; open("preview");
        buildPreview({poi, source: data.source, oneWay: true});
      });
    });
  }
  async function buildPreview({winter = winterEnabled && has("winter_plan"), poi = null, source = null, oneWay = false}) {
    if (!winter && !poi && !state.last?.recommendations?.length && !state.selectedPlaceId) { say(X().needPlan); return; }
    return run("#previewBuild", async current => {
      const req = await makeRequest(winter ? "кофе в помещении" : "прогулка");
      if (!current()) return;
      if (source) req.source = source;
      const selected = poi?.poi_id || state.selectedPlaceId;
      const ids = selected ? [selected] : winter ? [] : (state.last?.recommendations || []).map(p => p.poi_id);
      const dest = oneWay ? point(poi.coords) : req.end || null;
      const payload = {request: req, stop_ids: ids, max_stops: selected ? 1 : winter ? 2 : 3,
        finish_mode: dest ? "destination" : "return", destination: dest};
      const result = await A.postJSON(winter ? "/plans/winter" : "/plans/build", winter
        ? {plan: payload, max_outdoor_min: winterLimit} : payload, 40000);
      if (!current()) return;
      // One chosen place must be in the plan; for the top places a partial plan is fine, as in «Начать прогулку».
      if (!result.fits || !result.stops.length || !["ok","partial"].includes(result.status)
          || (selected && !result.stops.some(s => s.poi_id === selected))) { say(X().noPlan); return; }
      showPreview(result, req, false);
    });
  }
  function showPreview(result, req, active) {
    sequence++; overlays.clearLayers();
    const x = X(); say(active ? x.active : "");
    preview = {result, req, active, stamp: stamp(), made: Date.now(), index: 0};
    const time = value => new Intl.DateTimeFormat(state.lang === "kk" ? "kk-KZ" : state.lang === "en" ? "en-GB" : "ru-RU", {hour:"2-digit",minute:"2-digit",timeZone:"Asia/Almaty"}).format(new Date(value));
    preview.stages = [{name:x.startPoint, coords:req.location, at:result.departure_at, walk:0, stay:0},
      ...result.stops.map((s,i) => ({name:s.name,coords:s.coords,at:s.arrival_at,walk:result.legs[i]?.walk_min || 0,stay:s.stay_min,condition:s.visit_condition,hours:s.open_status})),
      {name:x.finish,coords:result.state.finish,at:result.estimated_arrival_at,walk:result.legs.at(-1)?.walk_min || 0,stay:0}];
    preview.time = time;
    $("#experienceResult").innerHTML = `<section class="preview-card"><h3>${esc(x.preview)}</h3><p>${esc(x.total)}: ≈${result.budget.total_min} ${esc(x.minutes)} · ${esc(x.reserve)}: ${result.budget.reserve_min} ${esc(x.minutes)}</p>
      <p class="meta">${esc(result.notes.join(" "))}</p>${result.warning_codes.includes("weather_unknown") ? `<p class="msg warn">${esc(x.unknownWeather)}</p>` : ""}
      ${req.context.simulate || ["cold","mild"].includes($("#weather").value) ? `<p class="msg warn">${esc(x.simulated)}</p>` : ""}
      <label class="preview-range">${esc(x.step)} <input id="previewStep" type="range" min="0" max="${preview.stages.length-1}" value="0" step="1"></label><div id="previewStage" aria-live="polite"></div>
      <div class="row"><button id="previewBack" type="button" class="btn small">${esc(x.back)}</button><button id="previewNext" type="button" class="btn small">${esc(x.next)}</button></div>
      <p class="meta">${esc(x.noPhoto)} ${result.routing_source === "distance_estimate" ? esc(x.routeEstimate) : ""}</p>
      ${active ? "" : `<button id="previewStart" class="btn primary" type="button">${esc(x.start)}</button>`}</section>`;
    $("#previewStep").oninput = e => renderStage(+e.target.value);
    $("#previewBack").onclick = () => renderStage(preview.index-1);
    $("#previewNext").onclick = () => renderStage(preview.index+1);
    if ($("#previewStart")) $("#previewStart").onclick = () => {
      if (!preview || preview.stamp !== stamp() || Date.now()-preview.made > 60000) { say(x.stale); return; }
      const chosen = preview; mode = "walk"; open(null); mount();
      F.startWalk(F.planView(chosen.result, chosen.req), null);
    };
    renderStage(0);
  }
  function renderStage(index) {
    if (!preview) return;
    const x=X(), p=preview; p.index=Math.max(0,Math.min(index,p.stages.length-1)); const stage=p.stages[p.index];
    $("#previewStep").value=String(p.index);
    $("#previewBack").disabled=p.index===0; $("#previewNext").disabled=p.index===p.stages.length-1;
    $("#previewStage").innerHTML=`<p class="eyebrow">${p.index+1} / ${p.stages.length} · ≈${esc(p.time(stage.at))}</p><h3>${esc(stage.name)}</h3><p>${esc(x.walk)}: ${stage.walk} ${esc(x.minutes)} · ${esc(x.stay)}: ${stage.stay} ${esc(x.minutes)}</p>
      ${stage.condition ? `<p class="meta">${esc(x.cost[stage.condition.kind] || x.cost.unknown)} · ${esc(x.hours[stage.hours?.state] || x.hours.unknown)}</p>` : ""}`;
    overlays.clearLayers();
    if (p.result.geometry?.length) L.polyline(p.result.geometry.map(([lon,lat])=>[lat,lon]),{color:"#B87900",weight:3,dashArray:"5 5"}).addTo(overlays);
    pin(stage.coords,String(p.index+1)); A.showAt([stage.coords.lat,stage.coords.lon],16);
  }
  const oldClick=E.onMapClick;
  const oldCancelPick=E.cancelMapPick;
  E.cancelMapPick=()=>{
    oldCancelPick?.(); picking=false;
    if ($("#meetCancel")) $("#meetCancel").hidden=true;
    if ($("#meetPoint")) $("#meetPoint").textContent=second ? `${X().chosen}: ${second.label}` : "";
  };
  E.onMapClick=e=>{
    if (picking && mode==="meet") { setSecond({lat:e.latlng.lat,lon:e.latlng.lng},X().chosen); return true; }
    return oldClick?.(e) || false;
  };
  const oldHealth=E.onHealth, oldLang=E.onLang;
  E.onHealth=h=>{ oldHealth?.(h); mount(); void loadStories(); };
  E.onLang=()=>{ oldLang?.(); open(null); mount(); void loadStories(); };
  const oldRender=E.afterRender;
  E.afterRender=d=>{oldRender?.(d);syncMode();};
  const oldSearch=E.onSearch, oldScenario=E.onScenario;
  E.onSearch=()=>{
    if (mode === "meet" && has("meet_halfway")) { state.requestVersion++; open("meet"); void meet(); return true; }
    open(null); return oldSearch?.() || false;
  };
  E.onScenario=()=>{ oldScenario?.(); mode="walk"; open(null); mount(); };
  document.addEventListener("click",e=>{
    const button=e.target.closest("[data-plan-preview]");
    if (!button || !has("plan_export")) return;
    A.freezeLocation(); open("preview");
    if (button.dataset.planPreview === "active" && F.walk?.plan?.server) showPreview(F.walk.plan.server,F.walk.plan.request,true);
    else void buildPreview({});
    $("#experiences").scrollIntoView({block:"start",behavior:"smooth"});
  });
  window.addEventListener("seruen:walk-change",()=>{
    if (preview && preview.stamp !== stamp()) { preview=null; overlays.clearLayers(); if ($("#experienceResult")) $("#experienceResult").innerHTML=""; say(X().stale); }
  });
  mount();
  void loadStories();
})();
