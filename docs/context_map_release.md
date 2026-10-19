# Visible context and reproducible recommendations — 2026-10-19

## User behavior

- Time, companions, weather and finish are visible before Search. Start time, expenses, accessibility and winter options expand separately. Atmosphere has its own disclosure.
- Finish defaults to staying at the chosen venue. Other options: return to start, or a custom point. There is no second finish dialog at Start.
- Map picks and drag update a labelled finish marker without moving the start. Presets fit both points in the map.
- Three recommendations are alternatives. Start goes to the selected place; the overview button names the first recommendation explicitly. No silent three-stop itinerary.
- A fresh scenario resets the previous custom finish, expense/exclusion/atmosphere/winter filters. Changed settings are re-read before route building. Late responses for changed location/settings/selection cannot start a walk.
- Desktop divider supports pointer drag and arrow keys. Panel can move to either side. Full-screen map is an in-page overlay (including Safari); Exit/Escape restores the panel and route. Only layout preferences are stored.

## Algorithm

For a fixed request, candidate dataset and time, ordering and visit durations are reproducible. Gemini reviews the three highest-ranked verified candidates; it cannot reorder them or change visit durations. `selection_source=rules`, `ai_reviewed=true` only for an accepted model draft. Final explanations still derive from verified facts and the actual calculation; unsupported model prose is not shown. Local searches no longer consume an extra Gemini intent call.

Hard constraints precede ranking: category and exclusions, suitability for children, confirmed accessibility when requested, event validity, closed status, weather/night walking limits, distance, expenses, atmosphere restrictions and total time. A child scenario can include a game hall; provider rubrics `Детские игровые залы` identify an indoor place. An outdoor playground is not silently marked indoors.

Walking estimate: `ceil(haversine_metres × 1.3 / walking_speed)`. Speed is 60 m/min with children or winter, otherwise 75 m/min. This is a planning estimate, not a guarantee of road access or indoor navigation.

Suggested visit: `min(category_target, max(10, floor(time_budget / 2)))`. Targets in minutes: coffee/park/shopping/unusual 20, food/culture/library/night 30, kids/sport 25, viewpoint 15, cowork 40. Search and plan use the same function. The reserve is 5 min normally, or the airport reserve (60 min by default). The visit is not shortened by AI or by a widened search to force a fit. Theatre/cinema recommendations do not promise that a full show fits.

Total: `walk to venue + visit + final leg + reserve <= available time`. The final leg is zero for staying, venue-to-start for returning, or venue-to-custom-finish. The initial nearby radius reserves at least half of usable time for the visit/options, and widens 1.5× only if empty. Radius depends on the number of legs; the actual final leg is checked for each candidate. Safety/user radius caps remain authoritative.

Ranking: 0.40 semantic relevance + 0.25 proximity + 0.15 popularity + 0.10 hours confidence + 0.10 tag match, with existing documented atmosphere/weather bonuses. Ties use distance and then stable POI ID. Local catalogue diversification remains bounded. The provider catalogue is paginated; this is not a claim to enumerate every place in Astana at once.

Street routing is used when available and checked against the same time budget. Repeated identical endpoints cost zero, including OSRM street-snap offsets. For one indoor venue whose whole route falls within 100 m and within the start point's stated precision, show a labelled `nearby_indoor_estimate`, not an artificial street loop. It does not establish that the user and venue share a building; entrance, floors and accessible passages still require checking. A different, distant finish always remains in the calculation.

## Contract and compatibility

`/health.features.finish_preferences=1` gates new request fields.

`RecommendRequest.finish_mode`: optional `place | return | destination`. `place` and `return` must not contain `end`; `destination` requires it. Omitted field preserves the old contract: destination when `end` exists, otherwise round trip.

Plans still explicitly use `finish_mode=return|destination`. Staying at a place sends `destination` plus `finish_poi_id`. Backend resolves this public ID itself, so rounding personal coordinates cannot put the finish 50 m away from the selected venue. The optional ID survives `PlanState`, replanning, full licensed exports and refresh. Unknown IDs are rejected; user coordinates still round to three decimals. Old clients omit the field.

Publish backend first, then the **entire** `frontend/` on Netlify. Cache identifier: `seruen-v28-context-map`; include `layout.js`. Keep production `config.js` API address. No new API keys, subscriptions or dependencies.

## Alikhan design integration

Includes main PR #51 (`e927861`): photo scenarios stay only in the header menu, menu remains above map controls, multi-line search grows as typed, no header AI badge. These changes are retained in v28.

## Acceptance

Automated regressions cover finish modes, indoor family recommendations, fixed AI ordering/time, exact venue finish and replan, duplicate snap offsets, stale settings, marker drag/reset, scenario reset, resizing/side/full-screen and existing route-rest/undo flows. Local browser checks use explicitly synthetic places with external venue/AI APIs disabled; real 2GIS/Gemini checks are separate after Render deployment.

Local verification after merging Alikhan's design: 448 backend tests (including the eight-feature UI/API integration), 118 frontend tests, 30/30 Erlan scenarios against the 1,251-place dataset. A separate 30-query regression returned 78/78 cards within budget, with no invented IDs or unsupported open claims. These checks do not establish on-site accessibility or provider availability. Ruff passes for backend and changed regression tests; older unrelated test files still have existing lint findings.
