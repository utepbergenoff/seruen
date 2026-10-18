# Серуен API v0.1

Владелец: Томирис. Основано на приложении А плана команды v2.1 и персональном плане потока B. Контракт проверен кодом; Алихан подтвердил совместимость на шести сценариях. OpenAPI: `/openapi.json`, интерактивная проверка: `/docs`.

База локально: `http://127.0.0.1:8000`. JSON, UTF-8; расстояния в метрах, длительности в целых минутах. Все времена с часовым поясом, расчёт в `Asia/Almaty`.

Публичная база: `https://seruen-backend-f36d.onrender.com`, [Swagger](https://seruen-backend-f36d.onrender.com/docs). Сервис Render Free, с 18.10.2026 проверена конфигурация — `data_kind=real`, 1 251 место, режимы `ai`/`no_ai`/`cached`. Текущую версию проверять через `/health`; сведения о развёртывании — в [handoff.md](handoff.md). CORS разрешает `https://seruen-astana.netlify.app`, `http://localhost:5173`, `http://127.0.0.1:5173`, `http://localhost:3000`; методы GET/POST/OPTIONS и заголовок Content-Type. Публичный origin проверен после перезапуска: [cors_verification.json](cors_verification.json). Ключ ИИ фронту не передавать.

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
| time_budget_min | 5…480; явное значение важнее текста. Если нет — правила извлекают из текста, иначе 60. |
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
| mode | ai / no_ai / cached. В кеше сохраняется why_source исходного ответа. |
| recommendations | 1–3 **альтернативных** места; 0 при отказе, нехватке бюджета или пустом поиске. Это не последовательный маршрут. |
| recommendations[].poi_id/name/category/coords | Только из загруженной базы, координаты места, не пользователя. |
| distance_m / walk_min | Расстояние по haversine, оценка пешком с коэффициентом улиц 1,3; минуты округляются вверх. |
| why / what_to_do | ≤25 / ≤35 слов. Источник: ai или template. |
| time_to_spend_min | Вычисляется кодом; предложение ИИ ограничивается ±30% и оставшимся бюджетом. |
| open_status | state: open / likely_open / unknown / closed; confidence: high / medium / low; hours, source, checked_at допускают null там, где данных нет. |
| facts_source / description_source | poi_db / wikipedia, source или generated. Вычисляемые расстояния получены из координат базы; provenance описан ниже. |
| accessibility | yes / limited / no / unknown. |
| description / sources / last_checked | Описание с явным description_source; источники записи и дата снимка. generated не является подтверждённым фактом. |
| links | 2gis и google для настоящих данных. В сэмпле `{}`, чтобы не вести к выдуманным местам. |
| rating / rating_count | Число либо null; отсутствие рейтинга не превращается в ноль. |
| recommendations[].budget_breakdown | walk_there_min + stay_min + walk_back_min + reserve_min = total_min. |
| budget_breakdown | Повторяет бюджет **первой альтернативы**; null, если карточек нет. |
| considered | Точность входа, радиус, факт расширения, бюджет, фильтры, время, число допустимых кандидатов до ограничения разнообразия, погода, retrieval_mode, intent_source, target_time. |
| considered.effective_budget_min / reserve_min | Бюджет прогулки без аэропортового резерва / сам резерв. Мини-маршрут использует effective_budget_min; карточка альтернативы — полный time_budget_min. |
| considered.walk_speed_m_per_min / street_factor | Фактическая скорость с учётом ребёнка/зимы и коэффициент 1,3. |
| considered.lang / companions / time_simulated | Язык ответа, состав группы, признак симуляции. time локализован, target_time — ISO. |
| notes / safety | Массивы сообщений на выбранном языке; показывать пользователю. |
| route | null; построение составного маршрута вне B1–B12. |
| disclaimer | Показывать всегда. |
| data_kind / mock | sample или real / явный признак режима интеграционного мока. |

### Уточнения к исходному плану

Названия исходных полей сохранены. Необязательный `description_url` содержит ссылку на описание Wikipedia. Добавлены `template` к источникам объяснений, `data_kind`, `mock`, `reserve_min`, бюджет каждой карточки и диагностические поля `considered`. Это делает режим без ИИ и тестовые данные честными. `open_status.hours` и `checked_at` nullable. Исходные обязательные поля сохранены; Алихан подтвердил контракт шести сценариев.

Статус open означает только попадание в распознанное расписание со свежей датой (0–30 дней), не подтверждённую работу в реальном времени. Неизвестный синтаксис часов → unknown. Неполные события не рекомендуются. Для детского запроса нужны kid_friendly=true и adult_only=false. Если категория не помещается в бюджет, допускается близкая альтернатива с отдельной нотой; слова «только/only/тек» запрещают такое ослабление. Явные исключения сохраняются.

## Остальные методы

- `GET /health` → status, mode_available, data_snapshot_date, poi_count, data_kind, retrieval_mode, mock. Наличие ai означает настроенный ключ, а не выполненный контрольный вызов модели.
- `GET /scenarios` → массив из 6 объектов `{id, title, request, data_kind}`. Кнопка отправляет `request` в `/recommend`.
- `POST /candidates` → тот же JSON, что `/recommend`; возвращает candidates, excluded, radius_m, radius_expanded, time_budget_min, target_time, retrieval_mode, data_kind. Без вызова ИИ.
- `GET /candidates` → lat, lon обязательны; остальные параметры плоские: query, time_budget_min, companions, now, lang, accessibility, simulate, precision_m, source, mode; exclude_categories повторяется. Погода: temp_c + wind_ms + precip_mm. Для приватности предпочитать POST: внешние прокси могут журналировать URL GET.

Кандидат: `{poi_id, name, category, distance_m, walk_min, score, reasons[], excluded_because}`. В candidates только допущенные записи (до 10), в excluded — отфильтрованные; причины: closed, out_of_radius, over_budget, excluded_category, category_mismatch, not_child_friendly, accessibility_unconfirmed, event_unverified, night_safety_unconfirmed.

## Ошибки, CORS и приватность

Неверный ввод → HTTP 422, `{error:{code:"invalid_request",fields:[...]}}`; тело и значения запроса обратно не отражаются. Внутренняя ошибка → 500 с обезличенным кодом. Обычный пустой поиск и отказ по теме/городу → 200 с пустым recommendations и пояснением. Ошибка/таймаут Gemini → 200 с no_ai.

Фронт отправляет Content-Type: application/json. CORS по явному CORS_ORIGINS, локально разрешены порты 5173 и 3000. Cookies не нужны. Не включать wildcard для рабочего фронта без необходимости.

Бэкенд не пишет запросы и координаты в логи и на диск; ключ кеша — SHA-256 от округлённой локации, запроса, контекста, окна 30 минут, версии данных и режима. В значениях кеша только карточки мест. Ответы имеют Cache-Control: no-store. В Gemini при наличии ключа уходят текст, контекст, округлённая локация и кандидаты, без идентификаторов пользователей. Политику хранения у хостинга и Google нужно рассматривать отдельно от логов приложения.

### Диагностика исходного ответа

`/recommend` возвращает `candidates` (до 10 записей, именно использованных при этом ответе), `excluded` (до 20 ближайших исключённых) и `excluded_count` (общее число). Панель использует их вместо нового поиска `/candidates`, который мог отличаться после уточнения намерения Gemini. В кеше сохраняется контекст исходного ответа.
