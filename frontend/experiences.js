/* Additive, capability-gated city experiences. No accounts or location persistence. */
(() => {
  "use strict";
  const A = window.SeruenApp, F = window.SeruenFeatures, E = window.SeruenExt;
  if (!A || !F || !E) return;
  const {state, $, esc, L, map} = A;
  const X = () => window.SeruenExperienceText[state.lang] || window.SeruenExperienceText.ru;
  const has = f => !!state.features?.[f];
  const overlays = L.layerGroup().addTo(map);
  const participants = L.layerGroup().addTo(map);
  let tab = null, sequence = 0, second = null, picking = false, preview = null;
  let meetingResults = null, previewMeeting = null, activeMeeting = null, startingMeeting = null;
  let mode = "walk", winterEnabled = false, winterLimit = 10, meetLimit = 45, showStories = false;
  let activeStory = null;
  const storyLayer = L.layerGroup().addTo(map);
  let storyIndex = [], storyLang = null, storyPending = false;
  const point = p => ({lat: A.round3(p.lat), lon: A.round3(p.lon), precision_m: p.precision_m || 100, source: p.source || "map"});
  const inputsKey = () => JSON.stringify([point(state.loc), state.contextVersion, state.lang,
    mode, winterEnabled, winterLimit, meetLimit, second,
    ["query","budget","whenSel","whenAt","companions","weather"].map(id => $("#"+id)?.value),
    $("#budgetAuto").checked, $("#access").checked]);
  const stamp = () => JSON.stringify([state.locVersion, state.requestVersion, state.selectedPlaceId,
    F.walk?.plan?.server || null, inputsKey()]);
  const link = (url, label) => {
    try { if (new URL(url).protocol !== "https:") return ""; } catch { return ""; }
    return `<a class="btn small" href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`;
  };
  const normalized = name => String(name || "").split(",")[0].toLocaleLowerCase().replace(/[^\p{L}\p{N}]/gu, "");
  function matchedStory(place) {
    if (!has("city_history")) return null;
    const exact = storyIndex.find(p => p.poi_id === place.poi_id
      || (place.canonical_id && p.poi_id === place.canonical_id));
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
  E.previewAction = () => ""; // One finish confirmation replaces the duplicate preview entry points.
  const oldExtras = E.requestExtras;
  E.requestExtras = req => {
    const out = oldExtras?.(req) || {};
    if (winterEnabled && has("winter_plan")) {
      const weather = req?.context?.weather;
      const limit = weather && (weather.temp_c <= -15 || weather.wind_ms >= 10) ? 5 : winterLimit;
      out.preferences = {...out.preferences, indoor_only: true, winter_mode: true,
        max_walk_min: Math.min(out.preferences?.max_walk_min || 120, limit)};
    }
    if (mode === "meet") { delete out.end; delete out.finish_mode; }
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
          A.freezeLocation(); activeStory = p; E.focusPlace?.(); open("history");
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
    F.syncFinishMarker();
    A.setWalkActive(!!F.walk);
    drawParticipants();
  }
  E.hideSuggestionRoutes = () => mode === "meet" || tab === "preview";
  E.hideSearchFinish = () => mode === "meet";
  function drawParticipants() {
    participants.clearLayers();
    if (activeMeeting && activeMeeting.walk !== F.walk) activeMeeting = null;
    const pair = mode === "meet" ? (previewMeeting || {first: exactStart(), second}) : activeMeeting;
    if (!pair) return;
    pin(pair.first, "A", null, participants, "participant-pin participant-a");
    if (pair.second) pin(pair.second, "B", null, participants, "participant-pin participant-b");
  }
  // The «I'm here» dot sits on the exact point; state.loc keeps it rounded (~100 m) for the server only.
  function exactStart() {
    let me = null;
    map.eachLayer?.(l => { if (!me && l.getLatLng && /class="me"/.test(l.options?.icon?.options?.html || "")) me = l.getLatLng(); });
    return me && A.round3(me.lat) === state.loc.lat && A.round3(me.lng) === state.loc.lon ? {lat: me.lat, lon: me.lng} : state.loc;
  }
  const LIMITS = [15, 30, 45, 60];
  // Names only: the form never shows raw coordinates and makes no reverse-geocoding call.
  function startLabel() {
    const x = X(), p = state.presets.find(p => p.id === state.preset);
    return p ? A.presetName(p) : state.locKind === "gps" ? x.myLocation : x.pointOnMap;
  }
  function secondLabel(s) {
    const p = s?.preset && state.presets.find(q => q.id === s.preset);
    return p ? A.presetName(p) : X().pointOnMap;
  }
  function meetingForm(x) {
    const presets = state.presets.map(p => `<option value="${esc(p.id)}"${second?.preset === p.id ? " selected" : ""}>${esc(A.presetName(p))}</option>`).join("");
    const limits = LIMITS.map(n => [n, n === meetLimit, `${n} ${esc(x.minutes)}`]);
    return `<div class="meet-route">
        <span class="meet-label meet-label-a">${esc(x.startA)}</span>
        <span class="meet-dot meet-dot-a" aria-hidden="true">A</span>
        <span class="meet-field" id="meetStart">${esc(startLabel())}</span>
        <span class="meet-info-wrap"><button type="button" class="meet-icon meet-info" id="meetInfo" aria-label="${esc(x.privacyTitle)}" title="${esc(x.privacyTitle)}" aria-expanded="false" aria-controls="meetPrivacy"></button>
          <span class="meet-pop" id="meetPrivacy" role="note" hidden>${esc(x.privacy)}</span></span>
        <label class="meet-label meet-label-b" for="meetPreset">${esc(x.startB)}</label>
        <span class="meet-dot meet-dot-b" aria-hidden="true">B</span>
        <select id="meetPreset"><option value="">${esc(second ? secondLabel(second) : x.choose)}</option>${presets}</select>
        <button type="button" class="meet-icon meet-pick" id="meetPick" aria-label="${esc(x.pick)}" title="${esc(x.pick)}" aria-pressed="false"></button>
        <span class="meet-line" aria-hidden="true"></span>
      </div>
      <div class="meet-picking" hidden><p id="meetPoint" role="status"></p><button type="button" class="btn small" id="meetCancel" hidden>${esc(x.cancel)}</button></div>
      <div class="meet-limit"><span class="meet-limit-label" id="meetLimitLabel">${esc(x.walkMax)}</span>
        <div class="meet-tabs" role="group" aria-labelledby="meetLimitLabel">${limits.map(([n, on, text]) => `<button type="button" class="meet-tab${on ? " on" : ""}" data-meet-limit="${n}" aria-pressed="${on}">${text}</button>`).join("")}</div>
        <select id="meetLimit" class="sr-only" tabindex="-1" aria-hidden="true">${limits.map(([n, on, text]) => `<option value="${n}"${on ? " selected" : ""}>${text}</option>`).join("")}</select></div>`;
  }
  function bindMeetingForm() {
    $("#meetPreset").onchange = e => setSecond(state.presets.find(p => p.id === e.target.value) || null);
    // The pills drive the hidden select, so code and tests that change #meetLimit keep working.
    $("#meetLimit").onchange = e => {
      meetLimit = +e.target.value;
      $("#meetingFields").querySelectorAll("[data-meet-limit]").forEach(b => {
        const on = +b.dataset.meetLimit === meetLimit; b.classList.toggle("on", on); b.setAttribute("aria-pressed", String(on));
      });
      open(null);
    };
    $("#meetingFields").querySelectorAll("[data-meet-limit]").forEach(b => b.onclick = () => {
      $("#meetLimit").value = b.dataset.meetLimit; $("#meetLimit").dispatchEvent(new Event("change"));
    });
    $("#meetPick").onclick = () => {
      if (picking) { picking = false; syncPicking(); return; }
      picking = true; syncPicking(); $("#map").scrollIntoView({block:"nearest",behavior:"smooth"});
    };
    $("#meetCancel").onclick = () => { picking = false; syncPicking(); };
    $("#meetInfo").onclick = () => togglePrivacy();
  }
  function syncPicking() {
    const x = X(), on = picking && mode === "meet" && has("meet_halfway");
    if ($("#meetPick")) { $("#meetPick").classList.toggle("on", on); $("#meetPick").setAttribute("aria-pressed", String(on)); }
    if ($(".meet-picking")) $(".meet-picking").hidden = !on;
    if ($("#meetPoint")) $("#meetPoint").textContent = on ? x.picking : "";
    if ($("#meetCancel")) $("#meetCancel").hidden = !on;
    $("#map")?.classList.toggle("picking-meet", on);
    let hint = $("#meetMapHint");
    if (!hint && on && $(".map-wrap")) {
      hint = document.createElement("p"); hint.id = "meetMapHint"; hint.className = "map-pick-hint"; hint.setAttribute("aria-hidden", "true");
      $(".map-wrap").appendChild(hint);
    }
    if (hint) { hint.hidden = !on; hint.textContent = on ? x.picking : ""; }
  }
  function togglePrivacy(show) {
    const pop = $("#meetPrivacy"), button = $("#meetInfo");
    if (!pop || !button) return;
    show = show ?? pop.hidden;
    pop.hidden = !show; button.setAttribute("aria-expanded", String(show));
  }
  document.addEventListener("click", e => { if (!e.target.closest?.("#meetInfo")) togglePrivacy(false); });  // any other tap closes it
  document.addEventListener("keydown", e => {
    if (e.key === "Escape" && $("#meetPrivacy") && !$("#meetPrivacy").hidden) { togglePrivacy(false); $("#meetInfo").focus(); }
  });
  function mount() {
    const x = X();
    if (!has("meet_halfway")) mode = "walk";
    if (!has("winter_plan")) winterEnabled = false;
    $("#searchModeField").hidden = !has("meet_halfway");
    // «С кем» is about a walk; a meeting is always two people
    const withWhom = $("#companions")?.closest("label"); if (withWhom) withWhom.hidden = mode === "meet";
    $("#searchModeField").innerHTML = has("meet_halfway") ? `<fieldset class="search-intent"><legend>${esc(x.searchFor)}</legend>
      <label><input type="radio" name="searchIntent" value="walk"${mode === "walk" ? " checked" : ""}><span>${esc(x.walkMode)}</span></label>
      <label><input type="radio" name="searchIntent" value="meet"${mode === "meet" ? " checked" : ""}><span>${esc(x.meetMode)}</span></label></fieldset>` : "";
    $("#searchModeField").querySelectorAll("input").forEach(el => el.onchange = () => {
      A.freezeLocation(); E.cancelMapPick?.(); state.requestVersion++; mode = el.value; meetingResults = null; $("#goBtn").disabled = false; open(null); mount();
    });
    $("#meetingFields").innerHTML = has("meet_halfway") ? meetingForm(x) : "";
    if (has("meet_halfway")) bindMeetingForm();
    syncPicking();
    $("#winterField").hidden = !has("winter_plan");
    $("#winterField").innerHTML = has("winter_plan") ? `<label class="winter-toggle"><span class="winter-title">${esc(x.winterOption)}</span><input id="winterMode" type="checkbox" role="switch"${winterEnabled ? " checked" : ""}></label>
      <p class="winter-short">${esc(x.winterShort)}</p>
      <div id="winterSettings"${winterEnabled ? "" : " hidden"}><span class="winter-label">${esc(x.outdoors)}</span>
        <div class="winter-tabs" role="group" aria-label="${esc(x.outdoors)}">${[5,10,15].map(n => `<button type="button" class="winter-tab${n === winterLimit ? " on" : ""}" data-winter-limit="${n}" aria-pressed="${n === winterLimit}">${n} ${esc(x.minutes)}</button>`).join("")}</div>
        <select id="winterLimit" class="sr-only" tabindex="-1" aria-hidden="true">${[5,10,15].map(n => `<option value="${n}"${n === winterLimit ? " selected" : ""}>${n} ${esc(x.minutes)}</option>`).join("")}</select></div>` : "";
    if (has("winter_plan")) {
      $("#winterMode").onchange = e => { winterEnabled = e.target.checked; open(null); mount(); };
      $("#winterLimit").onchange = e => { winterLimit = +e.target.value; open(null); mount(); };
      $("#winterField").querySelectorAll("[data-winter-limit]").forEach(b => b.onclick = () => {
        $("#winterLimit").value = b.dataset.winterLimit; $("#winterLimit").dispatchEvent(new Event("change"));
      });
    }
    $("#storyLayerField").hidden = !has("city_history");
    $("#storyLayerField").innerHTML = has("city_history") ? `<label class="story-layer-toggle"><input id="showCityStories" type="checkbox" role="switch"${showStories ? " checked" : ""}> ${esc(x.storyLayer)}</label><button type="button" class="btn small" id="browseLandmarks">${esc(x.historyGo)}</button><p class="meta" id="storyLayerStatus" role="status"></p>` : "";
    if ($("#browseLandmarks")) $("#browseLandmarks").onclick=()=>{activeStory=null;E.focusPlace?.();open("history");$("#experiences").scrollIntoView({block:"start",behavior:"smooth"});};
    if (has("city_history")) $("#showCityStories").onchange = e => { showStories = e.target.checked; drawStories(); if (showStories) void loadStories(); };
    if (!$("#experienceBody")) $("#experiences").innerHTML = '<div id="experienceBody" hidden></div>';
    syncMode(); drawStories();
  }
  function open(next, meeting = null) {
    sequence++; picking = false; preview = null; previewMeeting = meeting; overlays.clearLayers(); tab = next;
    drawParticipants(); syncPicking(); A.setWalkActive(!!F.walk);
    document.body.classList.toggle("route-review-open", tab === "preview");
    $("#goBtn").disabled = false;
    $("#experiences").hidden = !tab;
    $("#experienceBody").hidden = !tab;
    if (tab) renderTab(); else $("#experienceBody").innerHTML = "";
  }
  function renderTab() {
    const x = X(), body = $("#experienceBody");
    if (!body || !tab) return;
    const heading = tab === "history" ? activeStory?.title || x.history : tab === "meet" ? x.meetingResults : x.preview;
    body.innerHTML = `<div class="experience-head"><h3>${esc(heading)}</h3><button class="btn small" id="experienceClose" type="button">${esc(tab === "preview" && previewMeeting ? x.meetBack : x.backToPlaces)}</button></div>
      <p id="experienceMessage" role="status" class="meta"></p><div id="experienceResult"></div>`;
    $("#experienceClose").onclick = () => {
      if (tab === "preview" && previewMeeting) {
        const saved = meetingResults;
        open(saved?.key === inputsKey() ? "meet" : null);
        if (tab === "meet") renderMeeting(saved);
        mount(); return;
      }
      if(tab === "history" && activeStory){activeStory=null;renderTab();return;}
      mode = "walk"; open(null); mount();
      (state.last ? $("#results") : $("#askForm")).scrollIntoView({block:"start",behavior:"smooth"});
    };
    if (tab === "history" && activeStory) {
      $("#experienceResult").innerHTML = `<article class="story-card">${storyContent(activeStory)}<div class="row"><button type="button" class="btn" id="storyPreview">${esc(x.routeHere)}</button></div></article>`;
      $("#storyPreview").onclick = () => { const p=activeStory; open("preview"); buildPreview({poi:p,source:"local"}); };
    } else if (tab === "history") {
      const sorted=[...storyIndex].sort((a,b)=>window.SeruenRoute.hav(state.loc,a.coords)-window.SeruenRoute.hav(state.loc,b.coords));
      $("#experienceResult").innerHTML=`<p class="meta">${esc(x.historyHint)}</p><div class="landmark-list">${sorted.map(p=>`<button type="button" class="landmark-option" data-landmark="${esc(p.id)}"><strong>${esc(p.title)}</strong><span>≈${Math.round(window.SeruenRoute.hav(state.loc,p.coords))} ${esc(x.distance)}</span></button>`).join("")}</div>`;
      $("#experienceResult").querySelectorAll("[data-landmark]").forEach(b=>b.onclick=()=>{activeStory=storyIndex.find(p=>p.id===b.dataset.landmark);renderTab();});
    } else if (tab === "meet") say(x.fairness);
  }
  // B keeps the exact point for its marker and label; point() rounds it (~100 m) only when it is sent.
  // A map pick leaves the view alone: re-framing right after the click moved B away from the finger.
  function setSecond(p, fit = true) {
    A.freezeLocation(); second = p ? {lat: p.lat, lon: p.lon, preset: p.id || null} : null;
    meetingResults = null; open(null); mount();
    if (second && fit) { const a = exactStart(); A.fitTo([[a.lat, a.lon], [second.lat, second.lon]]); }
  }
  function pin(coords, name, click, target = overlays, cls = "") {
    const icon = L.divIcon({className: "", iconSize: [30, 30], iconAnchor: [15, 15], html: `<div class="cpin experience-pin${cls ? " " + cls : ""}">${esc(click ? "●" : name)}</div>`});
    const marker=L.marker([coords.lat, coords.lon], {icon, title: name, alt: name, zIndexOffset:1200, interactive: !!click, bubblingMouseEvents:false}).addTo(target);
    if(click) marker.on("click", click);
    return marker;
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
      req.context.companions = "alone";  // a meeting is two people: the walk's «С кем» (child, group) does not apply
      if (!current()) return;
      const data = await A.postJSON("/meet/search", {request: req, second_location: point(second), max_walk_min: meetLimit}, 40000);
      if (!current()) return;
      meetingResults = {data, req, second: {...second}, key: inputsKey()};
      renderMeeting(meetingResults);
    });
  }
  function renderMeeting(saved) {
      const {data,req,second:meetingSecond} = saved, x = X(); overlays.clearLayers();
      const current = () => meetingResults === saved && saved.key === inputsKey() && tab === "meet";
      const valid = () => { if (current()) return true; say(X().stale); return false; };
      const fallback = data.warning_codes?.includes("local_catalog_fallback") ? " " + x.localFallback : "";
      say((data.items.length ? x.estimate + (req.context.simulate ? " " + x.simulated : "") : x.noMeet) + fallback);
      // Same place facts as a recommendation card: what it is, where, its photos and what Gemini sees on them.
      $("#experienceResult").innerHTML = data.items.map((p, i) => `<article class="story-card meet-place" data-meet-id="${esc(p.poi_id)}"><h3>${esc(p.name)}</h3>
        <p class="meta">${esc(A.catLabel(p.category))}${p.rating ? ` · ${A.icon("star")} ${esc(p.rating)}` : ""}</p>
        ${p.address ? `<p class="meta">${A.icon("pin")} ${esc(p.address)}</p>` : ""}
        <div class="meeting-times"><span>A · ${esc(x.personA)}<strong>≈${p.walk_min[0]} ${esc(x.minutes)}</strong></span><span>B · ${esc(x.personB)}<strong>≈${p.walk_min[1]} ${esc(x.minutes)}</strong></span></div>
        <p class="meta">${esc(x.difference)}: ${p.difference_min} ${esc(x.minutes)}</p>
        ${A.statusPill(p.open_status)}${E.cardBadges(p)}
        ${p.visit_condition.note ? `<p class="meta">${esc(p.visit_condition.note)}</p>` : ""}
        ${A.FEAT.photos ? `<div class="photos" aria-live="polite"></div>` : ""}
        ${p.coords ? storyBlock(p) : ""}
        <div class="row"><button class="btn small" type="button" data-meet-map="${i}">${esc(x.meetDetails)}</button><button class="btn small" type="button" data-meet-route="${i}">${esc(x.routeHere)}</button>
        ${p.coords ? `<a class="btn small" href="${esc(A.links(p).gisPlace)}" target="_blank" rel="noopener">${esc(A.T().openIn2gis)}</a>` : ""}</div></article>`).join("");
      $("#experienceResult").querySelectorAll("[data-meet-id]").forEach((el, i) =>
        void A.fillPhotos(el.querySelector(".photos"), data.items[i], () => current() && el.isConnected, req.query));
      const back=document.createElement("button");back.className="btn";back.id="meetBack";back.textContent=x.meetBack;back.hidden=true;
      $("#experienceResult").prepend(back);
      // nothing within the limit: one tap searches again with the next longer walk
      const wider = data.items.length ? null : LIMITS.find(n => n > meetLimit);
      if (wider) {
        const more = document.createElement("button"); more.type = "button"; more.className = "btn primary"; more.id = "meetWider";
        more.textContent = A.fmt(x.meetWider, {n: wider}); $("#experienceResult").append(more);
        more.onclick = () => { const s = $("#meetLimit"); s.value = String(wider); s.dispatchEvent(new Event("change")); $("#goBtn").click(); };  // the same path as the search button
      }
      const draw = selected => {
        overlays.clearLayers();drawParticipants();
        data.items.forEach((p,i)=>pin(p.coords,p.name,()=>selectMeeting(i)));
        if(selected){selected.paths.forEach((path,i)=>L.polyline(path.map(([lon,lat])=>[lat,lon]),{color:i?"#BD6C00":"#00708A",weight:3,dashArray:"6 6"}).addTo(overlays));
          A.fitTo(L.latLngBounds([...selected.paths[0],...selected.paths[1]].map(([lon,lat])=>[lat,lon])));}
      };
      const selectMeeting=index=>{
        if (!valid()) return;
        $("#experienceResult").querySelectorAll("[data-meet-id]").forEach((card,i)=>card.hidden=index!==null&&index!==i);
        back.hidden=index===null;draw(index===null?null:data.items[index]);
        $("#experiences").scrollIntoView({block:"start",behavior:"smooth"});
      };
      back.onclick=()=>selectMeeting(null);draw(null);
      $("#experiences").scrollIntoView({block:"start",behavior:"smooth"});
      $("#experienceResult").querySelectorAll("[data-meet-map]").forEach(b=>b.onclick=()=>selectMeeting(+b.dataset.meetMap));
      $("#experienceResult").querySelectorAll("[data-meet-route]").forEach(b => b.onclick = () => {
        if (!valid()) return;
        A.freezeLocation();
        const poi = data.items[+b.dataset.meetRoute]; open("preview", {first: exactStart(), second: meetingSecond});
        buildPreview({poi, source: data.source});
      });
  }
  async function buildPreview({winter = winterEnabled && has("winter_plan"), poi = null, source = null}) {
    if (!winter && !poi && !state.last?.recommendations?.length && !state.selectedPlaceId) { say(X().needPlan); return; }
    const lastPlace=poi || [...(state.last?.recommendations||[]),...(state.last?.nearby_places||[])].find(p=>p.poi_id===state.selectedPlaceId) || state.last?.recommendations?.at(-1);
    if(!lastPlace) {say(X().needPlan);return;}
    const meeting = previewMeeting;
    const pendingChoice = meeting ? Promise.resolve({finish_mode:"destination", destination:{...lastPlace.coords,source:"preset"},
      ...(has("finish_preferences") ? {finish_poi_id:lastPlace.poi_id} : {}), label:lastPlace.name})
      : F.chooseFinish({...lastPlace,name:lastPlace.name||lastPlace.title});
    const before=stamp(), choice=await pendingChoice;
    if(!choice || before!==stamp()) return;
    return run("#previewBuild", async current => {
      const req = await makeRequest(winter ? "кофе в помещении" : "прогулка");
      if (!current()) return;
      if (source) req.source = source;
      const selected = poi?.poi_id || state.selectedPlaceId;
      const ids = selected ? [selected] : winter ? [] : (state.last?.recommendations || []).map(p => p.poi_id);
      const dest=choice.destination;
      if(dest) req.end=dest; else delete req.end;
      if(has("finish_preferences")) req.finish_mode=choice.finish_mode;
      const payload = {request: req, stop_ids: ids, max_stops: selected ? 1 : winter ? 2 : 3,
        finish_mode: choice.finish_mode, destination: dest, ...(choice.finish_poi_id ? {finish_poi_id:choice.finish_poi_id} : {})};
      const result = await A.postJSON(winter ? "/plans/winter" : "/plans/build", winter
        ? {plan: payload, max_outdoor_min: winterLimit} : payload, 40000);
      if (!current()) return;
      if (!result.fits || !result.stops.length || !["ok","partial"].includes(result.status)
          || (selected && result.stops.length !== 1)
          || ids.some(id => !result.stops.some(s => s.poi_id === id))) { say(X().noPlan); return; }
      showPreview(result, req, false, choice.label, meeting);
    });
  }
  function showPreview(result, req, active, finishLabel, meeting) {
    sequence++; overlays.clearLayers();
    const x=X();say("");preview={result,req,active,stamp:stamp(),made:Date.now(),finishLabel,meeting};
    $("#experienceResult").innerHTML=`<section class="route-review">
      <p class="walk-left">≈${result.budget.total_min} ${esc(x.minutes)}</p>
      <ol>${result.stops.map((p,i)=>`<li><strong>${esc(p.name)}</strong> · ≈${result.legs[i]?.walk_min||0} ${esc(x.minutes)} ${esc(x.walk)}${A.statusPill(p.open_status)}</li>`).join("")}</ol>
      <p><strong>${esc(x.finish)}:</strong> ${esc(finishLabel || x.finish)}</p>
      <p class="meta">${result.routing_source==="distance_estimate"?esc(x.routeEstimate):""}</p>
      <details><summary>${esc(x.source)}</summary><p class="meta">${esc(result.notes.join(" "))}</p></details>
      ${active?"":`<button id="previewStart" class="btn primary" type="button">${esc(x.start)}</button>`}</section>`;
    if(result.geometry?.length){L.polyline(result.geometry.map(([lon,lat])=>[lat,lon]),{color:"#00708A",weight:4,dashArray:result.routing_source==="osrm_foot"?null:"5 5"}).addTo(overlays);
      const bounds=result.geometry.map(([lon,lat])=>[lat,lon]);
      if(meeting) bounds.push([meeting.second.lat,meeting.second.lon]);
      A.fitTo(L.latLngBounds(bounds));}
    drawParticipants();
    if($("#previewStart")) $("#previewStart").onclick=()=>{
      if(!preview||preview.stamp!==stamp()||Date.now()-preview.made>60000){say(x.stale);return;}
      const chosen=preview, plan=F.planView(chosen.result,chosen.req);plan.finish_label=chosen.finishLabel;
      startingMeeting=chosen.meeting;
      try { F.startWalk(plan,null); } finally { startingMeeting=null; }
    };
  }
  const oldClick=E.onMapClick;
  const oldCancelPick=E.cancelMapPick;
  E.cancelMapPick=()=>{
    oldCancelPick?.(); picking=false; syncPicking();
  };
  E.onMapClick=e=>{
    if (picking && mode==="meet") { setSecond({lat:e.latlng.lat,lon:e.latlng.lng}, false); return true; }
    return oldClick?.(e) || false;
  };
  const oldHealth=E.onHealth, oldLang=E.onLang;
  E.onHealth=h=>{ oldHealth?.(h); mount(); void loadStories(); };
  E.onLang=()=>{F.cancelSetup(); oldLang?.(); open(null); mount(); void loadStories(); };
  const oldLocation=E.onLocationChange;
  E.onLocationChange=()=>{oldLocation?.();if(mode==="meet"){meetingResults=null;open(null);mount();}};
  const oldRender=E.afterRender;
  E.afterRender=d=>{oldRender?.(d);syncMode();};
  const oldSearch=E.onSearch, oldScenario=E.onScenario;
  const oldWalkStart=E.onWalkStart;
  E.onWalkStart=()=>{
    oldWalkStart?.(); activeMeeting=startingMeeting ? {...startingMeeting,walk:F.walk} : null;
    mode="walk";open(null);mount();
  };
  const oldWalkContext=E.walkContext;
  E.walkContext=()=> (oldWalkContext?.() || "") + (activeMeeting?.walk === F.walk && activeMeeting
    ? `<p class="meta meeting-walk-context"><strong>${esc(X().startB)}:</strong> ${esc(secondLabel(activeMeeting.second))}. ${esc(X().meetingWalkInfo)}</p>` : "");
  E.onSearch=()=>{
    F.cancelSetup();
    if (mode === "meet" && has("meet_halfway")) { state.requestVersion++; meetingResults=null;open("meet"); void meet(); return true; }
    open(null); return oldSearch?.() || false;
  };
  E.onScenario=()=>{ oldScenario?.(); winterEnabled=false; mode="walk"; open(null); mount(); };
  window.addEventListener("seruen:walk-change",()=>{
    if (preview && preview.stamp !== stamp()) { preview=null; overlays.clearLayers(); if ($("#experienceResult")) $("#experienceResult").innerHTML=""; say(X().stale); }
    drawParticipants();
  });
  mount();
  void loadStories();
})();
