# Контракт восьми функций (предложение фронтенда, v0)

Статус: **черновик Алихана для согласования с Томирис.** Поля и коды можно менять; после согласования
файл фиксирует версию, а фронтенд и тесты подстраиваются под неё. Примеры ответов (синтетические,
помечены `"synthetic": true`): `tests/frontend/fixtures/feature_examples.json`.

## 0. Общие правила

- Все новые поля запроса **необязательны**; старый запрос остаётся валидным (строгая схема: неизвестные поля → 422,
  поэтому фронтенд не отправляет новое поле, пока сервер его не объявил).
- `GET /health` объявляет готовые функции: `features: {"replan": 1, "end_point": 1, "constraints": 1, "comfort": 1,
  "cost": 1, "atmosphere": 1, "plan_export": 1}` (число — версия формата). Нет ключа → фронтенд скрывает функцию.
- Координаты пользователя (старт, текущая точка, финиш) — только в теле POST, округлены до 3 знаков, `precision_m ≥ 100`.
- Итоговые минуты, выполнимость и оставшееся время считает **сервер**; фронтенд их только показывает.
- Каждый ответ содержит `request_id` (эхо из запроса, строка ≤ 40). Фронтенд отбрасывает ответ, если уже отправил более новый.
- Ошибки: `{"error": {"code": "...", "fields": [...]}}`; `503 provider_unavailable`, `429 quota_exceeded`, `422 invalid_request`.

## F1. Планы изменились — `POST /walk/replan`

Запрос:
```json
{"request_id": "r7", "lang": "ru", "plan": <plan_export v1>, "current": {"lat": 51.128, "lon": 71.43, "precision_m": 100},
 "change": "less_time | cold | tired | closed | skip", "target_poi_id": "osm_node_1 (для closed/skip)", "remaining_min": 40}
```
Ответ: `{"request_id", "plan": <plan_export v1>, "explanation": "одна-две фразы, что изменилось", "changed": ["removed:osm_node_1", "added:..."]}`.
Выполненные (`status: done`) остановки сервер не меняет и не предлагает снова. `409 replan_impossible` + `reasons`, `suggestions`.

## F2. По пути к… — поле `end` в `/recommend`

`"end": {"lat": 51.13, "lon": 71.44, "precision_m": 100, "source": "map | landmark"}`. В каждой рекомендации
`budget_breakdown.walk_to_end_min` вместо `walk_back_min`, плюс `arrival_estimate` (ISO, подпись «оценка»).
Невозможно: пустые `recommendations`, `route_impossible: {"reason": "budget | distance", "need_min": 75,
"suggestions": [{"kind": "more_time", "min": 75}, {"kind": "fewer_stops"}]}`.

## F3. Почему не подходит? — поле `constraints`

```json
"constraints": {"exclude_ids": ["osm_node_1"], "max_distance_m": 600, "exclude_categories": ["food"],
                "no_spend": "strict | lenient", "replace_poi_id": "osm_node_2"}
```
`replace_poi_id`: вернуть одну замену для этой карточки, остальные не менять. Ответ: `considered.constraints_applied`
(список кодов) и при пустой выдаче `relaxable: [{"constraint": "max_distance_m", "would_find": 2}]`.
Кнопки → поля: «Далеко» → `max_distance_m` (−40 %), «Уже был» → `exclude_ids`, «Не мой формат» → `exclude_categories`
(пользователь выбирает категорию), «Хочу без расходов» → `no_spend: strict`, «Другое место» → `replace_poi_id`.

## F4. Точки комфорта — `POST /comfort`

Запрос: `{"near": [{"lat","lon"}...до 10 точек плана], "kinds": ["warm","toilet","sit","water","entrance"], "radius_m": 300}`.
Ответ: `{"points": [{"id","kind","name","coords","access":"free | customers | unknown","conditions":"...","source":"osm | 2gis | team","checked_at":"YYYY-MM-DD","limits":"..."}]}`.
«Добавить остановку» → `POST /walk/replan` с `"change": "add_stop", "target_poi_id": id`.

## F5. Без обязательных расходов — поле `cost` в рекомендации

`"cost": {"status": "free | optional_purchase | paid_entry | unknown", "note": "вход свободный, услуги платно",
"source": "osm | 2gis | team", "checked_at": "YYYY-MM-DD"}`. `unknown` никогда не превращается в бесплатно.
Фильтр: `constraints.no_spend` (`strict` — только `free`; `lenient` — `free` и `optional_purchase`).

## F6. Сохранённая прогулка — формат `plan_export` v1

```json
{"version": 1, "saved_at": "ISO", "lang": "ru", "query": "...", "start": {"lat","lon"}, "end": null,
 "budget_min": 60, "total_min": 52,
 "stops": [{"poi_id","name","address","coords","walk_min","stay_min","hours_text","open_state","source","checked_at",
            "status": "next | done | skipped"}],
 "disclaimer": "часы и условия могли измениться"}
```
Хранится только на устройстве (IndexedDB), без фото и без полного ответа провайдера. Сервер принимает этот же формат в F1.
**Вопрос к Томирис:** можно ли сохранять на устройстве название/адрес мест из 2ГИС (условия демоключа)?

## F7. Поиск по атмосфере

`GET /atmosphere/examples` → `[{"id","title":{"ru","kk","en"},"image_url","credit","features":["bright","greenery","open_space","architecture"]}]`
(эталоны Ерлана). В `/recommend`: `"atmosphere_id": "bright_interior"`; в рекомендации
`"atmosphere_match": {"features": ["bright"], "source": "manual | ai"}`. Без ИИ — подбор по ручной разметке, `source: manual`.
Не выводить «тихо», «есть Wi-Fi», «свободно» из фото.

## F8. Личная карта

Всё на устройстве. На сервер уходит только `constraints.exclude_ids` (посещённые) при «Показывать только новое».
Заметки, избранное, «хочу сходить» сервер не получает.
