# Передача бэкенда команде

Обновление 18.10.2026: интеграция реального снимка. Рабочий процесс — `feat/*` → PR → `main`.

Обновление API, 18.10.2026: ключи сохранены в Render, локального `.env` нет. `gemini-3.5-flash-lite` проверен публично: 6/6 демо отвечают, 5/6 с текстами ИИ, S1 с защитным fallback. Бесплатная проверка Google Places успешна; рейтинги и часы выключены до подтверждения квоты владельцем Google Cloud. Теперь 185 тестов проходят, Ruff PASS. [Контракт и инструкция](api_integrations.md), [измерения](api_integrations_verification.json). Ниже сохранены результаты предыдущей интеграции данных; утверждения об отложенных ключах относятся к ней.

## Готово

1 251 место из данных Ерлана, строгий API, BM25 + локальный LSA, расчёт бюджета, детские и ночные ограничения, часы/источники, режим без ИИ, кеш, обезличенные логи. `tzdata` и чтение UTF-8 сохранены. Подключение ключей Gemini и Google отложено пользователем.

**166 тестов проходят, Ruff PASS.** Два набора по 30 запросов проходят на реальной базе: [исходные фикстуры](../eval/real/report.json), [сценарии Ерлана](../eval/real_spec/report.json). Подробности и ограничения — [real_data_integration.md](real_data_integration.md). Один warning относится к устаревающему адаптеру тестового клиента. Измерения eval локальные; они не обещают скорость сети или холодного старта.

## Существующий Render Free

- API: https://seruen-backend-f36d.onrender.com
- Контракт: https://seruen-backend-f36d.onrender.com/docs
- Состояние и фактический снимок: https://seruen-backend-f36d.onrender.com/health
- Панель: https://dashboard.render.com/web/srv-db9r92ajnfac73dc07gg
- Один Python web service в My Workspace, Frankfurt, без БД/диска; auto-deploy выключен.
- Build: `pip install -r requirements.txt && python scripts/reindex.py`.
- Start: `python -m scripts.serve`; health check: `/health`.
- Проверенные параметры сервиса: branch=`main`, `POI_PATH=data/poi.json`, `DATA_KIND=real`; HOST=0.0.0.0, PYTHON_VERSION=3.12.10, WARM_CACHE=true, OPENBLAS_NUM_THREADS=1, OMP_NUM_THREADS=1. Порт задаёт Render.
- CORS: `https://seruen-astana.netlify.app`, `http://localhost:5173`, `http://127.0.0.1:5173`, `http://localhost:3000`; GET/POST/OPTIONS, Content-Type.

**Реальные данные развёрнуты 18.10.2026, Live с 06:26:53 UTC (11:26 по Астане).** Деплой `dep-dba6crvbtjjs73dvjfqg`, коммит `898f73757b38b22e556af6bd6a995b241eca11ad`, ветка `main`, тариф `free`. `/health`: `data_kind=real`, `poi_count=1251`, `retrieval_mode=bm25+lsa`, `mode_available=[no_ai]`.

Публичные проверки: /health, /docs, /openapi.json, /scenarios — 200; 6/6 демо и кандидаты, повторные ответы cached, 30/30 сценариев Ерлана, S2/S4 ночью в 01:04, 10 CORS-проверок (включая чужой origin). В браузере на сайте Алихана S1 показывает Drinkit и Starbucks, две метки и заметку о времени демо; снимок — 1 251 место. В 84 JSON-записях приложения за окно проверки нет лишних полей или внутренних ошибок. Отрицательные CORS-запросы дали ожидаемый http_400. Это не полная приёмка интерфейса/нагрузки и не проверка внешних логов прокси.

Машиночитаемое подтверждение: [real_data_deployment_verification.json](real_data_deployment_verification.json). Старые [deployment_verification.json](deployment_verification.json) и [cors_verification.json](cors_verification.json) сохраняют историю проверок на сэмпле от 17.10.

Две переменные снимка обновлены без замены остальных, тариф не менялся. Для следующих изменений: тесты → PR → main → Manual Deploy → Deploy latest commit → /health и проверка сценариев. Изменение переменных Render само запускает деплой; не дублировать его вручную.

Render Free засыпает после 15 минут без трафика; следующий старт может занять около минуты ([условия Render](https://render.com/docs/free)). Перед показом открыть /health и прогреть сценарии:

```bash
.venv/bin/python scripts/warm_cache.py https://seruen-backend-f36d.onrender.com
```

## Алихану

Базовый адрес API не меняется. Брать `request` из GET /scenarios, отправлять POST /recommend; кандидатов получать POST /candidates. Карточки — альтернативы, не составной маршрут. Отображать mode, data_kind, notes, safety, disclaimer и метки источников. Для sample показывать явную тестовую пометку; реальные данные идут с `data_kind=real`.

Необязательный `description_url` — ссылка на Wikipedia. Демозапрос с фиксированным временем возвращает явную заметку о дате/часе: ночная безопасность рассчитывается для времени запроса. «По расписанию открыто» не означает проверку на месте. Категорийные предположения об удобствах помечены словом «обычно».

## Оставшаяся приёмка

Реальные данные и сценарии Ерлана получены. Нужны ручные оценки 3×30, согласование текстов, полная проверка UI/видео и финальный тег команды. Живой Gemini отложен пользователем. Docker Engine локально не запускался; проверен Python API. Точное состояние B1–B12 — [checklist.md](checklist.md).
