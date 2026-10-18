# Gemini и Google Places

Секреты хранятся в Environment сервиса Render `seruen-backend`. Локальный `.env` не создавался.

## Переменные

- `GEMINI_API_KEY`: Gemini Developer API; `GEMINI_MODEL` по умолчанию `gemini-3.5-flash-lite`.
- `GOOGLE_PLACES_API_KEY`: Places API (New), серверный ключ. Для совместимости поддерживается `GOOGLE_API_KEY`, если первая переменная пустая.
- `GOOGLE_PLACES_ENABLED=false` по умолчанию. Наличие ключа **не включает** запросы рейтингов и часов.

`/health.mode_available` показывает наличие конфигурации Gemini, а не успешность обращения к Google.
Проверка Gemini: ответ `/recommend` должен иметь `mode=ai` и `why_source=ai`; при повторе допустим `cached` с `why_source=ai`.
Ошибки диагностируются в Render Logs по `mode=gemini`: код HTTP и разрешённая категория ошибки, без ключа, текста запроса или ответа провайдера.
Неудачные ответы кешируются максимум 30 секунд, затем возможна повторная попытка.

## Places: готовый серверный контракт

`GET /places/{poi_id}/details?lang=ru` (также `en`, `kk`; для `kk` пока возвращаются часы на русском с `language=ru`).
Принимаются только `poi_id` из нашей базы с сохранённым `google_place_id`. 175 из 1251 мест имеют такую привязку.
Возвращаются `rating`, `rating_count`, `open_now`, `current_weekday_hours`, `regular_weekday_hours`, `business_status`,
`checked_at`, `google_maps_url` и `attributions`. Отсутствующие рейтинг и статус — `null`, а не ноль или «закрыто».
`open_now` относится к реальному моменту `checked_at`, **не** к времени симуляции в рекомендациях.
Данные Google не записываются в POI, индекс RAG или кеш рекомендаций и не передаются Gemini. Ответ HTTP: `Cache-Control: no-store`.

Ошибки: 503 `places_disabled`, `places_not_configured`, `places_unavailable`, `places_timeout`;
404 `poi_not_found`, `place_not_mapped`, `place_not_found`; 429 `places_local_limit`; 502 `places_invalid_response`.
Сбой Places не влияет на `/recommend` и исходные часы OSM.

При старте с ключом выполняется один запрос с маской `id` (бесплатный SKU IDs Only).
Результат виден в `/health.google_places.ids_probe` и в логах. Это проверка доступа к API, **не** подтверждение квоты Enterprise.
Ссылки `recommendations[].links.google` теперь включают сохранённый `query_place_id`, если он известен.

## Что должен проверить владелец Google Cloud до включения

Рейтинги и часы относятся к Place Details Enterprise: на дату 18.10.2026 бесплатны 1000 запросов в месяц на SKU;
далее возможно списание. Квота общая для проекта/биллинга, а не отдельного API-ключа нашего сервиса.

1. В проекте ключа проверить включение Places API (New), ограничения ключа и текущее использование Enterprise.
2. В Google Maps Platform → Quotas проверить доступные жёсткие ограничения для Place Details.
   Если доступна дневная квота, 25 запросов в день дают до 775 запросов за 31 день; учесть другие приложения проекта.
   Ограничение только в минуту и alerts-only budget **не гарантируют** отсутствие списаний.
3. Пока жёсткий лимит и остаток бесплатной квоты не подтверждены, оставить `GOOGLE_PLACES_ENABLED=false`.
4. После проверки установить `GOOGLE_PLACES_ENABLED=true` в Render и Save, rebuild and deploy.
5. Проверить один `/places/{poi_id}/details` и его актуальные данные. Не прогревать все места автоматически.

В коде дополнительно стоят 5 запросов в минуту и 25 в сутки на процесс. Они сбрасываются при перезапуске и **не заменяют**
квоты Google. Платные планы и биллинг автоматически не включаются.

## Алихану: отображение Places

Текущий фронтенд использует OpenStreetMap. Данные Places нельзя наносить на эту карту.
Показывать рейтинг/часы отдельным экраном без карты с видимой атрибуцией Google Maps и всеми `attributions`.
Не смешивать Google `open_now` с `open_status` OSM и временем демо-сценария.
Добавить ссылку на `google_maps_url`, указать время проверки. На публичном сайте нужны условия и политика конфиденциальности
со ссылками на условия и политику Google. Подключение этого экрана — отдельное изменение фронтенда;
существующий контракт `/recommend` сохраняется.

Источники:
- https://developers.google.com/maps/documentation/places/web-service/place-details
- https://developers.google.com/maps/billing-and-pricing/pricing
- https://developers.google.com/maps/documentation/places/web-service/usage-and-billing
- https://developers.google.com/maps/documentation/places/web-service/policies
- https://developers.google.com/maps/documentation/urls/get-started
