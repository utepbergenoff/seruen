MESSAGES = {
    "alternative": (
        "В запрошенной категории нет подходящего места в бюджете времени; показаны ближайшие альтернативы других категорий.",
        "No place in the requested category fits your time budget; nearby alternatives in other categories are shown.",
        "Сұралған санатта уақыт шегіне сай орын жоқ; басқа санаттардағы жақын баламалар көрсетілді.",
    ),
    "sample": (
        "Тестовый набор: места и их свойства смоделированы, не используйте их для реального посещения.",
        "Test dataset: places and properties are simulated; do not use them for actual visits.",
        "Сынақ деректері: орындар мен қасиеттері модельденген, нақты бару үшін қолданбаңыз.",
    ),
    "unknown": (
        "Часы работы одного места неизвестны — проверьте перед визитом.",
        "Some opening hours are unknown; check before visiting.",
        "Кейбір орындардың жұмыс уақыты белгісіз, барар алдында тексеріңіз.",
    ),
    "expanded": (
        "В исходном радиусе подходящих мест нет: радиус расширен один раз, бюджет времени сохранён.",
        "No matches in the initial radius: expanded once while keeping the time budget.",
        "Бастапқы радиуста орын жоқ: радиус бір рет кеңейтілді, уақыт шегі сақталды.",
    ),
    "empty": (
        "Рядом нет подходящих мест в вашем бюджете времени; можно увеличить бюджет или рассмотреть транспорт.",
        "No suitable places nearby within your time budget; allow more time or consider transport.",
        "Уақыт шегіне сай жақын орын жоқ; уақытты ұлғайтуға немесе көлікті қарастыруға болады.",
    ),
    "out": (
        "Я подбираю места для прогулок только в Астане.",
        "I suggest places for walks only in Astana.",
        "Мен тек Астанада серуендейтін орындарды ұсынамын.",
    ),
    "unrelated": (
        "Я помогу подобрать место для прогулки в Астане — опишите, как хотите провести время.",
        "I can suggest places to visit in Astana; describe how you would like to spend your time.",
        "Мен Астанада серуендейтін орын табуға көмектесемін; уақытты қалай өткізгіңіз келетінін айтыңыз.",
    ),
    "unsafe": (
        "Выберите безопасную прогулку по общедоступным местам; я не предлагаю выход на лёд, стройки и закрытые территории.",
        "Choose a safe walk in public places; I do not suggest ice, construction sites or restricted areas.",
        "Қоғамдық жерде қауіпсіз серуенді таңдаңыз; мұзға, құрылысқа және жабық аумақтарға баруды ұсынбаймын.",
    ),
    "night": (
        "Ночью выбирайте освещённые людные места; возвращайтесь на такси или транспорте.",
        "At night choose well-lit busy places; return by taxi or public transport.",
        "Түнде жарық, адам көп жерлерді таңдаңыз; таксимен не қоғамдық көлікпен қайтыңыз.",
    ),
    "weather": (
        "Сильный холод или ветер: предпочтительны помещения и короткие переходы.",
        "Severe cold or wind: prefer indoor places and short walks.",
        "Қатты суық немесе жел: жабық орындар мен қысқа жолдарды таңдаңыз.",
    ),
    "flight": (
        "Из бюджета зарезервировано время на дорогу в аэропорт; это условный запас, проверьте маршрут и время регистрации.",
        "Time is reserved for airport travel; this is a fixed estimate, check your route and check-in time.",
        "Әуежайға жол үшін уақыт бөлінді; бұл шартты есеп, жол мен тіркелу уақытын тексеріңіз.",
    ),
    "limited": (
        "Об одном месте в базе есть только базовые сведения; подробности не подтверждены.",
        "Only basic data is available for one place; further details are unconfirmed.",
        "Бір орын туралы тек негізгі мәлімет бар; қосымша деректер расталмаған.",
    ),
    "disclaimer": (
        "Данные о местах могут устареть — проверяйте на месте. Время пешком приблизительное.",
        "Place data may be outdated; verify locally. Walking times are estimates.",
        "Орындар туралы мәлімет ескіруі мүмкін, барған кезде тексеріңіз. Жаяу жүру уақыты шамамен есептелген.",
    ),
    "mock": (
        "Мок-режим для подключения интерфейса; ответ не является результатом ИИ.",
        "Mock mode for frontend integration; this is not an AI response.",
        "Интерфейсті қосуға арналған сынақ режимі; жауап ЖИ нәтижесі емес.",
    ),
    "ai_fallback": (
        "ИИ недоступен или ответ не прошёл проверку; показаны рекомендации по правилам.",
        "AI is unavailable or its response failed validation; rule-based recommendations are shown.",
        "ЖИ қолжетімсіз немесе жауап тексеруден өтпеді; ережелер бойынша ұсыныстар көрсетілді.",
    ),
}


def message(key, lang):
    return MESSAGES[key][{"ru": 0, "en": 1, "kk": 2}[lang]]


def safety_notes(request, now, lang):
    notes = []
    if now.hour >= 22 or now.hour < 6:
        notes.append(message("night", lang))
    w = request.context.weather
    if w and (w.temp_c <= -15 or w.wind_ms >= 10):
        notes.append(message("weather", lang))
    return notes
