# Seruen — project status & to-do (18.10.2026, ~12:30 Astana)

Living note for the team. Owner: Yerlan. Backend details: [real_data_integration.md](real_data_integration.md),
[handoff.md](handoff.md); Heroku plan: PR #5 / `docs/heroku.md`.

---

## 1. The big picture in plain words

```
 [Frontend]  --request-->  [Backend]  --reads-->  [Data: list of places]
  Alikhan                   Tomiris                 Yerlan
  frontend/ (Netlify)       backend/ (Render)       data/poi.json — 1 251 real places of Astana
```

| Part | Where it lives | State |
|---|---|---|
| Frontend | https://seruen-astana.netlify.app · code in `frontend/` (PR #2, merged) | ✅ |
| Backend | https://seruen-backend-f36d.onrender.com (`/docs`, `/health`) | ✅ live on **real data** (`/health` → `poi_count: 1251, data_kind: real`) |
| Data | `data/poi.json` (contract) + `data/poi_full.json` (all fields) | ✅ in `main` (PR #1, #3, #4) |

All 6 scenarios were checked on the live backend with real data (18.10): 1–3 relevant cards each; S2 (child) only
playgrounds/parks; S6 at 23:00 only places open at night + safety note.

**Not yet:** answers are all **"без ИИ"** — Render has no `GEMINI_API_KEY` (see section 5).

---

## 2. GitHub — how we work

- `main` = the shared, always-working version (default branch). Work in `feat/...` → **PR into `main`** → a
  teammate runs it → merge. Nobody pushes straight to `main`. Never commit `.env` or keys.
- Merged: #1 data pipeline, #2 frontend, #3 real-data integration, #4 real-data deployment checks.
- Open: **#5** Heroku preparation (Tomiris) — waits for the Heroku student credits; Render stays live until Heroku
  is verified. Then Alikhan switches the API address (`python scripts/set_api_url.py <heroku-url>`).
- This branch: `feat/data-a3-gemini` — AI descriptions + more Google matches (see section 6).

---

## 3. Open items for teammates

**Tomiris**
- «Что я учёл → Время: Sun 01:04» — the weekday in `considered.time` comes from the backend in English, also in the
  RU/KZ interface.
- Decide on Gemini for the live backend (section 5) and test `eval/run.py --ai` once a key is set.
- `tests/test_real_integration.py` pins the snapshot counts (Google matches now 175; will change once more when A3 is
  finished).

**Alikhan**
- Turn off the "Powered by Netlify" badge (covers the chips on a phone) — before recording the video.
- Screenshots of the 6 scenarios (phone + laptop) on real data for the document (D4); `scripts/screenshots.py`.
- Video (D6) on real data.

---

## 4. Yerlan's to-do (in order)

| # | What | When | Notes |
|---|---|---|---|
| 1 | Find out the **exact closing time of the submission form (19.10)** → post in chat | ASAP | Everything on Monday depends on it |
| 2 | Activate Heroku student credits | today | Tomiris's PR #5 is ready |
| 3 | Decide Gemini budget with Tomiris (section 5) | today | |
| 4 | Finish A3: last 61 Google calls | after next reset (~12:00 Astana 19.10) or after raising the daily limit to 300 | Claude runs `python -m pipeline.enrich` + rebuild |
| 5 | D5 presentation (12 slides, ≤ 6.5 min) | today evening | |
| 6 | D4 document: real answers, screenshots, eval numbers | after screenshots + eval | Draft: `docs/scenarios_and_ethics.md` |
| 7 | D7 clean-folder check: `git clone` → README in order → tests → app opens | Mon | Windows (+ Mac/Linux if possible) |
| 8 | D8 form: 4 links (repo, presentation, document, video), check access from another account | ≥ 3 h before closing | screenshot to chat |
| 9 | Rehearse pitch twice with a timer | Mon evening | I speak, Alikhan demos, Tomiris answers |

---

## 5. APIs, quotas and money

| API | Used by | When it is called | Limit we hit |
|---|---|---|---|
| Google Places (New) | **only** the data pipeline (`pipeline/enrich.py`) | once, when we collect data — never by users or judges | ~100 requests/day (default). Total needed: **272**; done **211** (cached, never repeated) |
| Gemini | data pipeline (descriptions, once) **and** the backend (every user question, if a key is set) | backend: ~2 calls per question | free tier ≈ 20 requests/day |

- Google Places stays free (5 000 calls/month free; we need 272 once). We store **only Google's place ID** —
  Google's terms forbid storing ratings/hours, so the real data has no ★.
- **Judges + free Gemini key = AI runs out after ~10–20 questions**; the app then falls back to "без ИИ"
  automatically (it never breaks).
- Recommended: a **separate Google Cloud project** for the backend key, billing on, **budget alert $5**, daily
  request cap ~1 000. Estimated cost: gemini-2.5-flash ≈ $0.002 per question → ~500 questions ≈ $1.
  Key only in Render/Heroku settings, never in git.
- Render Free sleeps after 15 min (first request ~1 min). Heroku Basic (student credits) doesn't sleep. Until then:
  open `/health` and run `scripts/warm_cache.py` before the video and judging.

---

## 6. Data — honest numbers (for slides / jury questions)

From `data/quality_report.md` (rebuilt 18.10):
- **1 251 places**, 12 categories (only 1 coworking and 2 "unusual" — OpenStreetMap has almost none in Astana).
- Opening hours known for **22 %** (100 % of them parsed) → others show "unknown — check before visiting".
- Wheelchair data for **5 %**.
- **100 % have a description:** 22 from Wikipedia (each checked to be about the right place), 807 written by Gemini
  from the place's tags (checked: no hype words, no invented numbers, must name the place), 422 templates
  (mostly unnamed playgrounds/squares). All generated ones are labelled `description_source = generated`.
- Google place ID for **175** places (14 %, partial run).
- 181 records dropped (no name 104, duplicates 74, junk 3).
- Tests: **166 passing** (backend + data + frontend checks).

## 7. Where things are

- My stream plan: `yerlan.md`; full team plan: `TA.pdf` (both private, not in git).
- Data format: `docs/data.md`. Draft document D4: `docs/scenarios_and_ethics.md`.
- Rebuild data: `python -m pipeline.run` (no keys needed). Full re-collect: `python -m pipeline.run --fresh`.
  After rebuilding data: `python scripts/reindex.py` (search index).
- Keys only in `.env` (never committed): `GEMINI_API_KEY`, `GOOGLE_PLACES_API_KEY`.
