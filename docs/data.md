# Данные «Серуен»: контракт `data/poi.json`

Владелец: Ерлан (поток A). Цифры покрытия — в [`data/quality_report.md`](../data/quality_report.md), он пересобирается вместе с данными.

## Как получить / пересобрать

```bash
pip install -r requirements-data.txt
python -m pipeline.run          # из сырых файлов в data/raw/ — без ключей и без интернета
python -m pipeline.run --fresh  # заново OSM + Google place_id + Wikipedia (+ Gemini, если есть ключ)
# Mac/Linux: make data / make data-fresh
```

Снимок `data/poi.json` лежит в репозитории — бэкенду и жюри пересбор не нужен.

## Формат файла

```json
{"_meta": {"pipeline_version": "0.1.0", "built_at": "ISO-8601 UTC", "osm_collected_at": "...",
           "places_complete": false, "gemini_model": null, "descriptions": {...}, "count": 1251},
 "pois": [ {запись}, ... ]}
```

## Поля записи

| Поле | Тип / значения | Что значит |
|---|---|---|
| `poi_id` | `osm_node_123` / `osm_way_45` / `osm_relation_7` | Уникальный id; ИИ ссылается только на него |
| `name`, `name_kk`, `name_en` | str / null | Названия из OSM. У безымянных площадок/скверов — общее название и `name_generic: true` |
| `lat`, `lon` | float | Для полигонов (парки, ТРЦ) — центр |
| `category` | одна из 12: `coffee food park kids culture viewpoint shopping sport night unusual library cowork` | Ровно одна |
| `tags` | list[str] | Настроения/признаки: `wi-fi`, `терраса`, `розетки`, `тихо`, `кофе`, `бесплатно`, `ночью`, `крытое`, `на воздухе`, `фото`, `история`. Всегда ≥ 1 |
| `tags_inferred` | list[str] | Теги, **предположенные по категории** (у библиотек «тихо», «розетки», «бесплатно»; у коворкингов «wi-fi»). Для поиска — можно; в «почему» — только как «обычно», не как факт о месте |
| `opening_hours_raw` | str / null | Строка OSM как есть. **Статус считать через `pipeline.hours.open_status(raw, now)`** → `open` / `closed` / `unknown`. `now` с часовым поясом переводится во время Астаны (UTC+5); праздничные (`PH`) и неоднозначные правила → `unknown` |
| `hours_source` | `osm` / null | Источник часов (для FR-7: «по данным OSM») |
| `phone`, `website` | str / null | Из OSM |
| `wheelchair` | `yes` / `limited` / `no` / `unknown` | Нет тега → `unknown`, не `no`. Фильтр «без ступеней» = только `yes` (+ `limited` по решению) |
| `kid_friendly`, `adult_only`, `indoor` | bool | `night` → `adult_only`; `kids`, `park` → `kid_friendly`. С ребёнком исключать `adult_only` |
| `description` | str, никогда не пусто | Короткое описание |
| `description_source` | `wikipedia` / `generated` | FR-8: `generated` показывать с меткой «сгенерировано по тегам» |
| `description_method` | `llm` / `template` | Только для `generated` |
| `description_url`, `description_lang`, `descriptions` | str / `ru`·`kk`·`en` / {lang: text} | Только для `wikipedia`; `descriptions` — все доступные языки (фишка «3 языка») |
| `google_place_id` | str / нет поля | Сопоставление с Google Places. **Рейтинг/часы Google в репозитории не храним (условия Google)** — при наличии ключа бэкенд может запросить их вживую по этому id (Place Details) |
| `rating`, `rating_count` | всегда null в снимке | См. выше |
| `popularity` | 0–1 | Оценка по признакам OSM (сайт, телефон, Wikipedia, часы, языки, теги); `popularity_source: "osm_features"` — так и подписывать |
| `wikidata` | `Q…` / null | Из OSM |
| `sources` | list: `osm`, `google_places`, `wikipedia`, `gemini` | Откуда данные записи |
| `last_checked` | `YYYY-MM-DD` | Дата сборки; показывать в статусе («проверено 18.10») |

## Что важно знать бэкенду (честно)

- Часы есть у ~21 % мест; у остальных статус `unknown` → «проверьте перед визитом» (FR-7/FR-9).
- Доступность известна у ~5 % мест (данные OSM). В выдаче «без ступеней» — только места с `yes`/`limited`.
- В OSM по Астане почти нет коворкингов (1) и «необычных» мест (2): для S1 брать `coffee` + `library` + `cowork`;
  для S4 — `unusual` + `viewpoint` + `culture`.
- Описания Wikipedia проверены: ни одной статьи «не про то место» (правила в `pipeline/wiki.py`, тесты в `tests/test_wiki.py`).
- Отсеянные записи и причины — `data/raw/dropped.json`.
