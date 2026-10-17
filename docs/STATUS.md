# Seruen — project status & to-do (18.10.2026, ~01:30)

Living note for the team. Owner: Yerlan. Update it when something changes.

---

## 1. The big picture in plain words

The product has 3 parts that talk to each other:

```
 [Frontend]  --request-->  [Backend]  --reads-->  [Data: list of places]
  Alikhan                   Tomiris                 Yerlan
  website/phone app         finds places,           data/poi.json
  (Netlify)                 asks Gemini to explain  (1 251 real places of Astana)
                            (Render)
```

| Part | Where it lives | State |
|---|---|---|
| Frontend | https://seruen-astana.netlify.app | ✅ works; **code is NOT in the GitHub repo yet** |
| Backend | https://seruen-backend-f36d.onrender.com (`/docs`, `/health`) | ✅ works, deployed |
| Data | `data/poi.json` in branch `feat/data-pipeline` (PR #1) | ✅ built, **not used yet** |

### ⚠️ The most important thing right now

**The live app currently runs on 24 fake (synthetic) places, not on our real data.**

Tomiris built the backend before the real data existed, so she used a test file `data/poi_sample.json`
(places like "Световая скульптура (демо)" with made-up ratings). You can see it on the site footer:
"Снимок данных: 2026-10-17 **(24)**" and the banner "Тестовый набор: места смоделированы".

Our real data (1 251 places from OpenStreetMap + Wikipedia) is ready in **PR #1**, already converted to exactly
the format her backend expects (a test proves it loads with 0 errors). To switch the live app to real data:

1. Tomiris reviews and **merges PR #1** into `main`.
2. On Render she sets `POI_PATH=data/poi.json`, `DATA_KIND=real`, rebuilds the index (`python scripts/reindex.py`),
   redeploys.
3. After that: the eval, screenshots and video must be redone on real data (judges will try real places).

---

## 2. GitHub — how we work now

- `main` = the shared, always-working version (created 18.10 from Tomiris's `codex/backend-rag`; default branch).
- Everyone works in their own branch `feat/...` and opens a **Pull Request (PR) into `main`**.
  A teammate runs it, then merges. Nobody pushes straight to `main`.
- Render still deploys from `codex/backend-rag` (unchanged) — switch it to `main` after PR #1 is merged.
- Open PRs: **#1** `feat/data-pipeline → main` (data + Windows fixes) — https://github.com/utepbergenoff/seruen/pull/1
- Never commit `.env` or API keys. (Checked: no keys in history.)

---

## 3. Messages to send

### To Tomiris
> Создал `main` из твоей `codex/backend-rag` (Render не трогал) и PR #1 `feat/data-pipeline → main`: реальные 1 251
> место Астаны в формате твоего контракта (тест грузит их твоим `load_pois`, 0 отклонено). Там же 2 фикса под Windows
> в твоём коде: `tzdata` в requirements (иначе `ZoneInfo("Asia/Almaty")` падает на Windows) и `encoding="utf-8"` при
> чтении файлов (иначе кириллица ломалась и LSA тихо откатывался на BM25) — посмотри, пожалуйста.
> Для переключения на реальные данные: `POI_PATH=data/poi.json`, `DATA_KIND=real`, `scripts/reindex.py`.
> Замечание: твой дедуп (одинаковое имя < 80 м) убирает 96 соседних безымянных «Детская площадка».
> Ещё: ночная заметка безопасности появилась в S4 в 01:04, но не в S2 (с ребёнком) в то же время; парк в 01:00
> «открыто сейчас» — проверь после переключения на реальные данные.
> Дальше работаем через `feat/*` → PR в `main`.

### To Alikhan
> Проверил фронт в браузере — всё работает: пресеты, чипсы, карточки, «Что я учёл», погода, KZ, PWA,
> 0 ошибок в консоли 🔥 Что нужно:
> 1. **Запушь код** в ветку `feat/frontend` (папка `frontend/`) + PR в `main` — без этого жюри не увидит фронт.
>    Не коммить `.env` и ключи.
> 2. Когда бэкенд переключится на реальные данные, `rating` будет `null` (рейтинги Google хранить нельзя) —
>    скрывай ★, если рейтинга нет.
> 3. «Что я учёл → Время: Sun 01:04» — день недели на английском в RU-интерфейсе.
> 4. Бейдж «Powered by Netlify» перекрывает чипсы на телефоне — отключи в настройках Netlify (важно для видео).
> 5. После переключения на реальные данные — скриншоты 6 сценариев (телефон + ноутбук) для документа.

---

## 4. Yerlan's to-do (in order)

| # | What | When | Notes |
|---|---|---|---|
| 1 | Send the two messages above | now | |
| 2 | Find out the **exact closing time of the submission form (19.10)** and post it in the chat | today morning | Everything on Monday depends on it |
| 3 | Raise Google quota → tell Claude to finish A3 | any time | See section 5 |
| 4 | After ~13:00 Astana: re-run A3 (if quota not raised) + Gemini descriptions, rebuild, push to PR #1 | Sun 13:00+ | Claude does it |
| 5 | D5 presentation (12 slides, ≤ 6.5 min) | Sun evening / Mon morning | |
| 6 | D4 document: fill real answers, screenshots, eval numbers | after real-data switch | Draft: `docs/scenarios_and_ethics.md` |
| 7 | D7 clean-folder check: `git clone` → README commands in order → tests → app opens | Mon | on Windows (and Mac/Linux if possible) |
| 8 | D8 form: 4 links (repo, presentation, document, video), check access from another account | ≥ 3 h before closing | screenshot to chat |
| 9 | Rehearse pitch twice with a timer | Mon evening | I speak, Alikhan demos, Tomiris answers |

---

## 5. Quotas (why some things "wait until tomorrow")

Free API plans have **daily limits**. Nothing is paid; all answers already received are cached on disk
(`data/cache/`, not in git) and are never requested again.

**Google Places (A3 — linking our places to Google's IDs):**
- Needs ~272 requests; Google's default limit is ~100/day → it stopped at 106. 125 places matched so far.
- **Can be finished now** without waiting: Google Cloud Console → APIs & Services → Places API (New) →
  *Quotas & System Limits* → "SearchNearby requests per day" → Edit → **300**. Then run `python -m pipeline.enrich`.
  If editing is blocked, the limit resets at midnight Pacific time = **~13:00 Astana**.
- We store **only Google's place ID**, never ratings/hours (Google's terms forbid storing them). That's why the
  real data has no ★ ratings.

**Gemini (A5 — short AI descriptions):**
- Free tier ≈ 20 requests/day → ran out tonight. Until then all descriptions are honest templates
  ("Кофейня «X». По данным OpenStreetMap: Wi-Fi, терраса."). After the reset: ~17 requests fill the AI descriptions.
- This limit **cannot** be raised for free — wait for the reset (or use a paid key).

---

## 6. Overall progress ≈ 75 %

| Stream | Status |
|---|---|
| A data (Yerlan) | ✅ ~85 %: 1 251 places, hours 100 % parsed, 22 Wikipedia descriptions (all checked), quality report, one command. Left: A3 Google IDs, AI descriptions |
| B backend (Tomiris) | ✅ ~95 %: deployed, eval 30/30 — but on fake data. Left: real data, live Gemini test |
| C frontend (Alikhan) | ✅ ~95 %: everything from the plan + extras. Left: code into repo, small fixes above |
| D materials | 🟡 ~35 %: D1 scenarios ✅, D2 eval (fake data), D3 README (backend part), D4 draft. Not started: D5 slides, D6 video, D7 clean check, D8 form |

## 7. Honest numbers about our data (for slides / jury questions)

From `data/quality_report.md`:
- 1 251 places, 12 categories (but only 1 coworking and 2 "unusual" — OpenStreetMap has almost none in Astana).
- Opening hours known for ~21 % → others show "unknown — check before visiting" (that's our honesty rule).
- Wheelchair data for ~5 %.
- 100 % have a description: 22 from Wikipedia, the rest generated from tags and labelled as generated.
- 181 records dropped (no name 104, duplicates 74, junk 3).
- Tests: 141 passing (backend 86 + data 55).

## 8. Where things are

- Plan of my stream: `yerlan.md` (private, not in git). Full team plan: `TA.pdf` (private).
- Data format for the backend: `docs/data.md`. Draft document D4: `docs/scenarios_and_ethics.md`.
- Rebuild data: `python -m pipeline.run` (no keys needed). Full re-collect: `python -m pipeline.run --fresh`.
- Keys go only in `.env` (never committed): `GEMINI_API_KEY`, `GOOGLE_PLACES_API_KEY`.
