# What the website sends and reads (for Tomiris)

The website follows appendix A of the plan. This page lists exactly what it uses, so the backend
can be checked against it. Fields marked *optional* are computed by the website when missing.

## Requests the website makes

| Call | When | Body / notes |
|---|---|---|
| `GET /health` | page load | reads `ai` (`"gemini"` → badge "ИИ", `"no_ai"` → "без ИИ"), `data_snapshot`, `places` (all optional) |
| `GET /scenarios` | page load | list of `{id, title:{ru,en,kk}, preset, query, context}`; `query` may be a string or `{q: ...}`. If this fails, the site uses its own `scenarios.json` |
| `POST /recommend` | every request | see below |
| `POST /candidates` | only if `/recommend` has no `candidates` | same body as `/recommend`; **POST, not GET**, so coordinates never appear in URLs / server logs. Reads `candidates`, `excluded` |

Presets come from the website's own `presets.json` (coordinates checked against OSM objects).

### `POST /recommend` body

```json
{
  "location": {"lat": 51.089, "lon": 71.416, "precision_m": 100, "source": "gps | map | preset"},
  "query": "text, may be empty",
  "context": {
    "lang": "auto", "mode": "walk", "companions": "alone | child | group", "accessibility": false,
    "time_budget_min": 60,                      // only when the slider was moved
    "now": "2026-10-18T23:00:00+05:00", "simulate": true,   // only when "другое время" is chosen
    "weather": {"temp_c": -12, "wind_ms": 9, "precip_mm": 0}   // only if weather is on
  }
}
```

`lat`/`lon` always have at most 3 decimals (rounded in the browser, FR-10). The weather is measured for
the Astana centre (Open-Meteo), never for the user's point. The website sends only these contract fields
(the deployed backend rejects anything else with 422).

## Response fields the website reads

**Required:** `mode` (`ai | no_ai | cached`), `recommendations[]`, and in each recommendation:
`poi_id`, `name`, `category`, `coords{lat,lon}`, `distance_m`, `walk_min`, `why`, `why_source`,
`what_to_do`, `what_to_do_source`, `time_to_spend_min`, `open_status{state}`.

**Optional, shown when present:**

| Field | Shown as |
|---|---|
| `open_status.source`, `checked_at`, `closes_at`, `hours`, `confidence` | text in the status pill / tooltip |
| `kind_label` or `category_label` | category text (else the website's own label for `category`) |
| `description` + `description_source` (`wikipedia / osm / generated…`) | description; generated ones are folded behind their label |
| `accessibility` (`yes / limited / no / unknown`) | ♿ chip |
| `rating`, `rating_count` | ★ |
| `tag_labels[]`, `sources[]`, `last_checked` | chips and the "Источники" line |
| `budget{walk_there_min, stay_min, walk_back_min, total_min, budget_min}` per card | budget bar (else computed from `walk_min`, `time_to_spend_min` and the budget) |
| `budget_breakdown` | line in "Что я учёл" |
| `considered{location, location_rounded_to_m, radius_m, radius_expanded, time_budget_min, effective_budget_min, time, time_simulated, goal, categories, tags, filters, walk_speed_m_per_min, street_factor, weather, candidates_found, data_snapshot, places_in_database}` | "Что я учёл" panel (each row only if present) |
| `candidates[]{name, category, category_label, distance_m, score, reasons[]}` | candidates table |
| `excluded[]{name, category_label, distance_m, excluded_because, excluded_label}` | "Отсеяно" table |
| `notes[]`, `safety[]`, `disclaimer` | grey notes, yellow 🛡 notes, footer line |
| `timing_ms`, `cached_from` | small text near the mode badge |

Links to 2GIS / Google Maps are built by the website from `coords` (destination only), so the backend
`links` field is not needed. The mini-route is computed in the browser from the cards, so `POST /route` is not needed either.

## CORS

The backend must allow the website's origin, e.g. `https://seruen-astana.netlify.app`, for `GET` and `POST`
with header `Content-Type: application/json`.
