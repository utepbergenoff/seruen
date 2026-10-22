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

## Файлы

- **`data/poi.json`** — контракт бэкенда: JSON-массив записей ровно с полями `backend/schemas.py: POI`
  (`extra="forbid"`). Тест `tests/test_data_contract.py` грузит его через `backend.loader.load_pois` и требует 0 отклонённых.
- **`data/poi_full.json`** — полная версия: `{"_meta": {...}, "pois": [...]}` со всеми полями ниже
  (`google_place_id`, `tags_inferred`, `descriptions` на всех языках, `description_url`, `description_method`, …).

`name_generic`, `tags_inferred`, `google_place_id` и `description_url` передаются также в контрактный снимок. Проверка требует все 1 251 запись и 0 удалённых дублей.

## Поля записи (в `poi.json` — только поля контракта; остальные — в `poi_full.json`)

| Поле | Тип / значения | Что значит |
|---|---|---|
| `poi_id` | `osm_node_123` / `osm_way_45` / `osm_relation_7` | Уникальный id; ИИ ссылается только на него |
| `name`, `name_kk`, `name_en` | str / null | Названия из OSM. У безымянных площадок/скверов — общее название и `name_generic: true` |
| `lat`, `lon` | float | Для полигонов (парки, ТРЦ) — центр |
| `category` | одна из 12: `coffee food park kids culture viewpoint shopping sport night unusual library cowork` | Ровно одна |
| `tags` | list[str] | Настроения/признаки: `wi-fi`, `терраса`, `розетки`, `тихо`, `кофе`, `бесплатно`, `ночью`, `крытое`, `на воздухе`, `фото`, `история`. Всегда ≥ 1 |
| `tags_inferred` | list[str] | Теги, **предположенные по категории**. Они исключаются из фактического текстового представления RAG, подтверждённых совпадений удобств и пакета фактов Gemini. Не доказывают тишину, розетки или бесплатность конкретного места |
| `opening_hours_raw` | str / null | Строка OSM как есть. Сборщик проверяет синтаксис через `pipeline.hours`; API рассчитывает статус через `backend.hours.open_status` с учётом источника, свежести и контекста. Поддерживаются `open` / `likely_open` / `closed` / `unknown`. `now` с часовым поясом переводится во время Астаны (UTC+5); праздничные (`PH`) и неоднозначные правила → `unknown` |
| `hours_source` | `osm` / null | Источник часов (для FR-7: «по данным OSM») |
| `phone`, `website` | str / null | Из OSM |
| `wheelchair` | `yes` / `limited` / `no` / `unknown` | Нет тега → `unknown`, не `no`. Фильтр «без ступеней» = только `yes` (+ `limited` по решению) |
| `kid_friendly`, `adult_only`, `indoor` | bool | `night` → `adult_only`; `kids`, `park` → `kid_friendly`. С ребёнком исключать `adult_only` |
| `description` | str, никогда не пусто | Короткое описание |
| `description_source` | `wikipedia` / `generated` | FR-8: `generated` показывать с меткой «сгенерировано по тегам» |
| `description_method` | `llm` / `template` | Только для `generated` |
| `description_url`, `description_lang`, `descriptions` | str / `ru`·`kk`·`en` / {lang: text} | Только для `wikipedia`; `descriptions` — все доступные языки (фишка «3 языка») |
| `google_place_id` | str / нет поля | Сопоставление с Google Places. **Рейтинг/часы Google в репозитории не храним (условия Google)** — сейчас бэкенд не делает запросов Google Places; ID сохранён для будущего подключения |
| `rating`, `rating_count` | всегда null в снимке | См. выше |
| `popularity` | 0–1 | Оценка по признакам OSM (сайт, телефон, Wikipedia, часы, языки, теги); `popularity_source: "osm_features"` — так и подписывать |
| `wikidata` | `Q…` / null | Из OSM |
| `sources` | list: `osm`, `google_places`, `wikipedia`, `gemini` | Откуда данные записи |
| `last_checked` | `YYYY-MM-DD` | Дата сборки снимка; не подтверждение работы или проверки на месте |

## Что важно знать бэкенду (честно)

- Часы есть у 270 из 1 251 места (бэкенд распознаёт 268; два неоднозначных праздничных расписания остаются unknown); у остальных статус `unknown` → «проверьте перед визитом» (FR-7/FR-9).
- Доступность известна у ~5 % мест (данные OSM). В выдаче «без ступеней» — только места с `yes`/`limited`.
- В OSM по Астане почти нет коворкингов (1) и «необычных» мест (2): для S1 брать `coffee` + `library` + `cowork`;
  для S4 — `unusual` + `viewpoint` + `culture`.
- Описания Wikipedia проверены: ни одной статьи «не про то место» (правила в `pipeline/wiki.py`, тесты в `tests/test_wiki.py`).
- Отсеянные записи и причины — `data/raw/dropped.json`.
