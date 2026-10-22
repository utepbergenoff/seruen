# Серуен API v0.1

Владелец: Томирис. Основано на приложении А плана команды v2.1 и персональном плане потока B. Контракт проверен кодом; Алихан подтвердил совместимость на шести сценариях. OpenAPI: `/openapi.json`, интерактивная проверка: `/docs`.

База локально: `http://127.0.0.1:8000`. JSON, UTF-8; расстояния в метрах, длительности в целых минутах. Все времена с часовым поясом, расчёт в `Asia/Almaty`.

Публичная база: `https://seruen-backend-f36d.onrender.com`, [Swagger](https://seruen-backend-f36d.onrender.com/docs). Сервис Render Free, с 18.10.2026 проверена конфигурация — `data_kind=real`, 1 251 место, режимы `ai`/`no_ai`/`cached`. Текущую версию проверять через `/health`; сведения о развёртывании — в [handoff.md](archive/handoff.md). CORS разрешает `https://seruen-astana.netlify.app`, `http://localhost:5173`, `http://127.0.0.1:5173`, `http://localhost:3000`; методы GET/POST/OPTIONS и заголовок Content-Type. Публичный origin проверен после перезапуска: [cors_verification.json](archive/cors_verification.json). Ключ ИИ фронту не передавать.

## POST /recommend

Полный проверенный запрос: [request.json](request.json). Полный ответ на него: [response.json](response.json).

```json
{
  "location": {"lat": 51.089, "lon": 71.417, "precision_m": 100, "source": "preset"},
  "query": "Хочу тихое место с кофе и розеткой на 1–2 часа",
  "context": {
    "time_budget_min": 120,
    "companions": "alone",
    "mode": "walk",
    "now": "2026-10-18T14:00:00+05:00",
    "lang": "auto",
    "accessibility": false,
    "exclude_categories": [],
    "weather": null,
    "simulate": true
  }
}
```

| Поле | Правило |
|---|---|
| location | Обязательно; lat −90…90, lon −180…180. Сервер округляет до 3 знаков, примерно 100 м. |
| precision_m / source | По умолчанию 100 / preset; source = gps, map, preset. precision_m 100…10000 — заявленная точность входа. |
| query | 0…1000 символов. Пустая строка даёт общую прогулку по контексту. |
| context | Необязательно; отсутствующие параметры получают значения по умолчанию. |
| time_budget_min | 5…480; при конфликте текста и контекста применяется меньший лимит. «Осталось N минут» обновляет прежний запрос. Без явного лимита используется 60. |
| companions / mode | alone, child, group / только walk. Упоминание ребёнка в тексте усиливает защиту. |
| now / simulate | Время применяется только при simulate=true; иначе используются серверные часы. Наивное время без пояса отклоняется. |
| lang | ru, kk, en, auto. В auto определяется по письменности запроса. |
| exclude_categories | Категории ниже; mall принимается как alias shopping. Исключения никогда не ослабляются. |
| accessibility | true допускает только wheelchair=yes; limited/unknown не считаются подтверждённой доступностью. |
| weather | null или {temp_c, wind_ms, precip_mm}; присылает фронт. Бэкенд не делает погодных сетевых запросов. |

Категории: `coffee`, `food`, `park`, `kids`, `culture`, `viewpoint`, `shopping`, `sport`, `night`, `unusual`, `library`, `cowork`.

### Ответ и семантика

| Поле | Содержимое |
|---|---|
| mode | ai / no_ai / cached. В кеше сохраняются selection_source и why_source исходного ответа. |
| recommendations | До 3 **альтернативных** мест; 0 при отказе, нехватке бюджета или пустом поиске. Это не последовательный маршрут. Порядок и состав определяет код, `selection_source=rules`. Принятый текст Gemini имеет `why_source=ai` / `what_to_do_source=ai`; отклонённый или недоступный заменяется `template` отдельно для каждой карточки. |
| recommendations[].poi_id/name/category/coords | Только из локальной базы или проверенного ответа 2ГИС; координаты места, не пользователя. Для каталога ID имеет вид `2gis_<id>`. |
| distance_m / walk_min | Расстояние по haversine, оценка пешком с коэффициентом улиц 1,3; минуты округляются вверх. |
| why / what_to_do | ≤25 / ≤35 слов. Источник: ai или template. |
| time_to_spend_min | Вычисляется кодом по категории и бюджету. Gemini не меняет длительность и не укорачивает визит ради включения далёкого места. |
| open_status | state: open / likely_open / unknown / closed; confidence: high / medium / low; hours, source, checked_at допускают null там, где данных нет. |
| facts_source / description_source | poi_db / wikipedia, source или generated. Вычисляемые расстояния получены из координат базы; provenance описан ниже. |
| accessibility | yes / limited / no / unknown. |
| description / sources / last_checked | Описание с явным description_source; источники записи и дата снимка. generated не является подтверждённым фактом. |
| links | 2gis и google для настоящих данных. В сэмпле `{}`, чтобы не вести к выдуманным местам. |
| rating / rating_count | Число либо null; отсутствие рейтинга не превращается в ноль. |
| recommendations[].budget_breakdown | Путь туда + посещение + путь к выбранному финишу + резерв = total_min. Для возврата используется walk_back_min, для другого финиша walk_to_end_min, для finish_mode=place после посещения путь равен нулю. |
| budget_breakdown | Повторяет бюджет **первой альтернативы**; null, если карточек нет. |
| considered | Точность входа, радиус, факт расширения, бюджет, фильтры, время, число допустимых кандидатов до ограничения разнообразия, погода, retrieval_mode, intent_source, target_time. |
| considered.effective_budget_min / reserve_min | Бюджет прогулки без аэропортового резерва / сам резерв. Мини-маршрут использует effective_budget_min; карточка альтернативы — полный time_budget_min. |
| considered.walk_speed_m_per_min / street_factor | Фактическая скорость с учётом ребёнка/зимы и коэффициент 1,3. |
| considered.lang / companions / time_simulated | Язык ответа, состав группы, признак симуляции. time локализован, target_time — ISO. |
| notes / safety | Массивы сообщений на выбранном языке; показывать пользователю. |
| route | В /recommend остаётся null; составной маршрут строится через /plans/build. См. контракт расширений. |
| disclaimer | Показывать всегда. |
| data_kind / mock | sample или real / явный признак режима интеграционного мока. |

### Уточнения к исходному плану

Названия исходных полей сохранены. Необязательный `description_url` содержит ссылку на описание Wikipedia. Добавлены `template` к источникам объяснений, `data_kind`, `mock`, `reserve_min`, бюджет каждой карточки и диагностические поля `considered`. Это делает режим без ИИ и тестовые данные честными. `open_status.hours` и `checked_at` nullable. Исходные обязательные поля сохранены; Алихан подтвердил контракт шести сценариев.

Статус open означает только попадание в распознанное расписание со свежей датой (0–30 дней), не подтверждённую работу в реальном времени. Неизвестный синтаксис часов → unknown. Неполные события не рекомендуются. Для детского запроса нужны kid_friendly=true и adult_only=false. Если категория не помещается в бюджет, допускается близкая альтернатива с отдельной нотой; слова «только/only/тек» запрещают такое ослабление. Явные исключения сохраняются.

## Остальные методы

- `GET /health` → status, mode_available, data_snapshot_date, poi_count, data_kind, retrieval_mode, mock. Наличие ai означает настроенный ключ, а не выполненный контрольный вызов модели.
- `GET /scenarios` → массив из 6 объектов `{id, title, request, data_kind}`. Кнопка отправляет `request` в `/recommend`.
- `POST /candidates` → тот же JSON, что `/recommend`; возвращает candidates, excluded, radius_m, radius_expanded, time_budget_min, target_time, retrieval_mode, data_kind. Для гарантированной диагностики без генерации задавать `source=local`: каталожный вариант использует обработчик рекомендаций.
- `GET /candidates` → lat, lon обязательны; остальные параметры плоские: query, time_budget_min, companions, now, lang, accessibility, simulate, precision_m, source, mode; exclude_categories повторяется. Погода: temp_c + wind_ms + precip_mm. Для приватности предпочитать POST: внешние прокси могут журналировать URL GET.

Кандидат: `{poi_id, name, category, distance_m, walk_min, score, reasons[], excluded_because}`. В candidates только допущенные записи (до 10), в excluded — отфильтрованные; причины: closed, out_of_radius, over_budget, excluded_category, category_mismatch, not_child_friendly, accessibility_unconfirmed, event_unverified, night_safety_unconfirmed.

## Ошибки, CORS и приватность

Неверный ввод → HTTP 422, `{error:{code:"invalid_request",fields:[...]}}`; тело и значения запроса обратно не отражаются. Внутренняя ошибка → 500 с обезличенным кодом. Обычный пустой поиск и отказ по теме/городу → 200 с пустым recommendations и пояснением. Ошибка/таймаут Gemini → 200 с no_ai.

Фронт отправляет Content-Type: application/json. CORS по явному CORS_ORIGINS, локально разрешены порты 5173 и 3000. Cookies не нужны. Не включать wildcard для рабочего фронта без необходимости.

Бэкенд не пишет запросы и координаты в прикладные логи и на диск; ключ кеша — SHA-256 от округлённой локации, запроса, контекста, окна 30 минут, версии данных и режима. Ограниченный кеш ответов хранится в памяти. Ответы имеют Cache-Control: no-store. В Gemini уходят текст, контекст и факты кандидатов, без отдельных координат пользователя/финиша и истории ID. Личные сведения внутри текста автоматически не удаляются. Правила хранения у хостинга и провайдеров рассматриваются отдельно от логов приложения.

### Диагностика исходного ответа

`/recommend` возвращает `candidates` (до 10 записей, именно использованных при этом ответе), `excluded` (до 20 ближайших исключённых) и `excluded_count` (общее число). Панель использует их вместо нового поиска `/candidates`, который мог отличаться после уточнения намерения Gemini. В кеше сохраняется контекст исходного ответа.


## Источники текста — релиз grounded-rag (19.10.2026)

`selection_source=rules`: порядок мест и время рассчитаны сервером. `why_source` и `what_to_do_source`
равны `ai` только если именно показанные строки получены от Gemini и прошли проверку.
`ai_reviewed` сохранён для старых клиентов и теперь означает наличие принятого текста модели в карточке;
он не является независимой проверкой места человеком. `explanation_evidence` — необязательный список
ключей фактов, на которые ссылается генерация (`category`, `walk`, `tag:wifi` и т.д.).
Неподтверждённые запрошенные удобства дописывает сервер. Это не гарантирует истинность произвольной прозы.

Ответ `mode=ai` содержит хотя бы одну карточку с принятым текстом; остальные могут быть `template`.
Если все генерации отклонены или модель недоступна — `no_ai`, полный ответ по правилам и заметка.
Отдельный источник фактов остаётся `facts_source=poi_db|2gis`. Часы/цены/расчёты не извлекаются из текста ИИ.

Фото требуют разрешённой связки точного POI и SHA-256 файла из `data/photo_identity_review.json`.
Старый индекс фронтенда не может вернуть исключённый снимок. `no_photos` означает отсутствие
подтверждённых материалов, не отсутствие самого места. Формат ответа фотографий сохранён.

### Пустой каталог в auto

При `source=auto` и завершённом пустом поиске 2ГИС сервер может вернуть локальные варианты с `source=local` и явным пояснением в `notes`. Все исходные ограничения сохраняются. `source=2gis` и запросы с `cursor` не переключаются на локальную базу.
