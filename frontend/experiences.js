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
  let storyIndex = [], storyLang = null, storyPending = false;
  const point = p => ({lat: A.round3(p.lat), lon: A.round3(p.lon), precision_m: 100, source: p.source || "map"});
  const stamp = () => JSON.stringify([state.locVersion, state.requestVersion, state.selectedPlaceId, state.lang,
    F.walk?.plan?.server || null]);
  const link = (url, label) => {
    try { if (new URL(url).protocol !== "https:") return ""; } catch { return ""; }
    return `<a class="btn small" href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`;
  };
  const normalized = name => String(name || "").split(",")[0].toLocaleLowerCase().replace(/[^\p{L}\p{N}]/gu, "");
  function matchedStory(place) {
    const exact = storyIndex.find(p => p.poi_id === place.poi_id);
    if (exact) return exact;
    if (!place.coords) return null;
    return storyIndex.find(p => p.aliases.some(a => normalized(a) === normalized(place.name))
      && window.SeruenRoute.hav(p.coords, place.coords) <= 200) || null;
  }
  const oldCard = E.cardExtras, oldSelected = E.selectedPlaceActions;
  const storyLink = place => {
    const story = matchedStory(place);
    return story ? `<p class="meta city-article">${link(story.wikipedia_url, X().more)}</p>` : "";
  };
  E.cardExtras = p => (oldCard?.(p) || "") + storyLink(p);
  E.selectedPlaceActions = p => (oldSelected?.(p) || "") + (state.last?.recommendations?.some(r => r.poi_id === p.poi_id) ? "" : storyLink(p));
  async function loadStories() {
    if (!has("city_history") || storyLang === state.lang || storyPending) return;
    storyPending = true; const lang = state.lang;
    try {
      const data = await A.getJSON(A.API + "/city/stories?lang=" + encodeURIComponent(lang));
      if (state.lang === lang) { storyIndex = data.items; storyLang = lang; A.rerender(); }
    } catch { /* Stories have their own explicit retry button. */ }
    finally { storyPending = false; if (state.lang !== lang) void loadStories(); }
  }
  function mount() {
    const box = $("#experiences"), x = X();
    box.hidden = false;
    const buttons = [["history", "city_history"], ["meet", "meet_halfway"], ["winter", "winter_plan"], ["preview", "plan_export"]];
    box.innerHTML = `<h2>${esc(x.title)}</h2><div class="experience-tabs" role="group" aria-label="${esc(x.title)}">${buttons
      .filter(([, cap]) => has(cap)).map(([id]) => `<button class="btn small${tab === id ? " primary" : ""}" type="button" data-experience="${id}" aria-expanded="${tab === id}">${esc(x[id])}</button>`).join("")}</div>
      <div id="experienceBody"${tab ? "" : " hidden"}></div>`;
    box.hidden = !box.querySelector("[data-experience]");
    box.querySelectorAll("[data-experience]").forEach(b => b.addEventListener("click", () => open(tab === b.dataset.experience ? null : b.dataset.experience)));
    if (tab) renderTab();
  }
  function open(next) {
    sequence++; picking = false; preview = null; overlays.clearLayers(); tab = next;
    mount();
  }
  function renderTab() {
    const x = X(), body = $("#experienceBody");
    if (!body || !tab) return;
    body.innerHTML = `<div class="experience-head"><h3>${esc(x[tab])}</h3><button class="btn small" id="experienceClose" type="button">${esc(x.close)}</button></div>`;
    $("#experienceClose").onclick = () => open(null);
    if (tab === "history") {
      body.insertAdjacentHTML("beforeend", `<p class="meta">${esc(x.historyHint)}</p><button class="btn" id="historyLoad" type="button">${esc(x.historyGo)}</button>`);
      $("#historyLoad").onclick = history;
    } else if (tab === "meet") {
      body.insertAdjacentHTML("beforeend", `<p class="meta">${esc(x.first)}</p><label for="meetPreset">${esc(x.second)}</label>
        <select id="meetPreset"><option value="">${esc(x.choose)}</option>${state.presets.map(p => `<option value="${esc(p.id)}">${esc(p.label?.[state.lang] || p.label?.ru || p.id)}</option>`).join("")}</select>
        <div class="row"><button type="button" class="btn small" id="meetPick">${esc(x.pick)}</button><button type="button" class="btn small" id="meetCancel" hidden>${esc(x.cancel)}</button></div>
        <p class="meta" id="meetPoint">${second ? esc(x.chosen) + ": " + esc(second.label) : ""}</p>
        <label>${esc(x.limit)} <select id="meetLimit"><option value="15">15 ${esc(x.minutes)}</option><option value="30" selected>30 ${esc(x.minutes)}</option><option value="45">45 ${esc(x.minutes)}</option><option value="60">60 ${esc(x.minutes)}</option></select></label>
        <p class="meta">${esc(x.privacy)}</p><p class="meta">${esc(x.fairness)}</p><button type="button" class="btn" id="meetFind">${esc(x.find)}</button>`);
      $("#meetPreset").onchange = e => {
        const p = state.presets.find(p => p.id === e.target.value);
        if (p) setSecond(p, p.label?.[state.lang] || p.label?.ru || p.id);
      };
      $("#meetPick").onclick = () => { picking = true; $("#meetPoint").textContent = x.picking; $("#meetCancel").hidden = false; };
      $("#meetCancel").onclick = () => { picking = false; $("#meetCancel").hidden = true; $("#meetPoint").textContent = second ? `${x.chosen}: ${second.label}` : ""; };
      $("#meetFind").onclick = meet;
    } else if (tab === "winter") {
      body.insertAdjacentHTML("beforeend", `<p class="meta">${esc(x.winterHint)}</p><label>${esc(x.outdoors)} <select id="winterLimit"><option value="5">5 ${esc(x.minutes)}</option><option value="10" selected>10 ${esc(x.minutes)}</option><option value="15">15 ${esc(x.minutes)}</option></select></label>
        <button type="button" class="btn" id="winterBuild">${esc(x.winterGo)}</button>`);
      $("#winterBuild").onclick = () => buildPreview({winter: true});
    } else {
      body.insertAdjacentHTML("beforeend", `<p class="meta">${esc(x.previewHint)}</p><button type="button" class="btn" id="previewBuild">${esc(x.previewGo)}</button>`);
      $("#previewBuild").onclick = () => {
        if (F.walk?.plan?.server) showPreview(F.walk.plan.server, F.walk.plan.request, true);
        else buildPreview({});
      };
    }
    body.insertAdjacentHTML("beforeend", '<p id="experienceMessage" role="status" class="meta"></p><div id="experienceResult"></div>');
  }
  function setSecond(p, label) {
    sequence++; preview = null; second = {...point(p), label}; picking = false;
    $("#meetCancel").hidden = true; $("#meetPoint").textContent = `${X().chosen}: ${label}`;
    $("#experienceResult").innerHTML = ""; overlays.clearLayers(); pin(second, "B");
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
    finally { if (button?.isConnected) button.disabled = false; if (seq === sequence && version !== stamp()) say(X().stale); }
  }
  async function makeRequest(fallbackQuery = "кофе") {
    let req = {location: point(state.loc), query: $("#query").value.trim() || fallbackQuery,
      context: {...await A.context(), lang: state.lang}};
    Object.assign(req, E.requestExtras?.(req) || {});
    // Text and per-request controls, not an old result's location/time, are authoritative.
    delete req.request_id;
    return req;
  }
  function history() {
    return run("#historyLoad", async current => {
      const data = await A.postJSON("/city/history", {location: point(state.loc), radius_m: 3000, lang: state.lang});
      if (!current()) return;
      const x = X(); overlays.clearLayers();
      say(data.items.length ? "" : x.emptyHistory);
      $("#experienceResult").innerHTML = data.items.map((p, i) => `<article class="story-card"><p class="eyebrow">${esc(p.distance_m)} ${esc(x.distance)}</p><h3>${esc(p.title)}</h3>
        <p>${esc(p.story)}</p><p class="meta"><strong>${esc(x.look)}:</strong> ${esc(p.look_for)}</p>
        <p class="src">${esc(x.source)}: ${link(p.source_url, p.source_title)} · ${esc(p.checked_at)}</p><div class="row">${link(p.wikipedia_url, x.more)}
        <button class="btn small" type="button" data-story="${i}">${esc(x.onMap)}</button><button class="btn small" type="button" data-story-route="${i}">${esc(x.routeHere)}</button></div></article>`).join("");
      $("#experienceResult").querySelectorAll("[data-story]").forEach(b => b.onclick = () => {
        const p = data.items[+b.dataset.story]; overlays.clearLayers(); pin(p.coords, "◈"); A.showAt([p.coords.lat, p.coords.lon], 16);
      });
      $("#experienceResult").querySelectorAll("[data-story-route]").forEach(b => b.onclick = () => buildPreview({poi: data.items[+b.dataset.storyRoute], source: "local"}));
    });
  }
  function meet() {
    if (!second) { say(X().selectionMissing); return; }
    return run("#meetFind", async current => {
      const req = await makeRequest(); delete req.end;
      const data = await A.postJSON("/meet/search", {request: req, second_location: point(second), max_walk_min: +$("#meetLimit").value}, 40000);
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
      $("#experienceResult").querySelectorAll("[data-meet-map]").forEach(b => b.onclick = () => draw(data.items[+b.dataset.meetMap]));
      $("#experienceResult").querySelectorAll("[data-meet-route]").forEach(b => b.onclick = () => buildPreview({poi: data.items[+b.dataset.meetRoute], source: data.source, oneWay: true}));
    });
  }
  async function buildPreview({winter = false, poi = null, source = null, oneWay = false}) {
    if (!winter && !poi && !state.last?.recommendations?.length && !state.selectedPlaceId) { say(X().needPlan); return; }
    return run(winter ? "#winterBuild" : "#previewBuild", async current => {
      const req = await makeRequest(winter ? "кофе в помещении" : "прогулка");
      if (!current()) return;
      if (source) req.source = source;
      const selected = poi?.poi_id || state.selectedPlaceId;
      const ids = selected ? [selected] : winter ? [] : (state.last?.recommendations || []).map(p => p.poi_id);
      const dest = oneWay ? point(poi.coords) : req.end || null;
      const payload = {request: req, stop_ids: ids, max_stops: selected ? 1 : winter ? 2 : 3,
        finish_mode: dest ? "destination" : "return", destination: dest};
      const result = await A.postJSON(winter ? "/plans/winter" : "/plans/build", winter
        ? {plan: payload, max_outdoor_min: +$("#winterLimit").value} : payload, 40000);
      if (!current()) return;
      if (!result.fits || !result.stops.length || !["ok","partial"].includes(result.status)
          || ids.some(id => !result.stops.some(s => s.poi_id === id))) { say(X().noPlan); return; }
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
      const chosen = preview; open(null);
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
  E.onMapClick=e=>{
    if (picking && tab==="meet") { setSecond({lat:e.latlng.lat,lon:e.latlng.lng},X().chosen); return true; }
    return oldClick?.(e) || false;
  };
  const oldHealth=E.onHealth, oldLang=E.onLang;
  E.onHealth=h=>{ oldHealth?.(h); mount(); void loadStories(); };
  E.onLang=()=>{ oldLang?.(); sequence++; preview=null; picking=false; overlays.clearLayers(); mount(); void loadStories(); };
  window.addEventListener("seruen:walk-change",()=>{
    if (preview && preview.stamp !== stamp()) { preview=null; overlays.clearLayers(); if ($("#experienceResult")) $("#experienceResult").innerHTML=""; say(X().stale); }
  });
  mount();
  void loadStories();
})();
