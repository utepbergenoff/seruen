from .activities import activity
from .schemas import Draft

ACTIONS = {
    "night": (
        "Загляните на вечерний перекус или напиток; меню и формат заведения уточните перед заказом.",
        "Stop for an evening snack or drink; check the menu and venue format before ordering.",
        "Кешкі асқа не сусынға кіріңіз; тапсырыс алдында мәзір мен орын форматын нақтылаңыз.",
    ),
    "shopping": (
        "Пройдитесь по торговой галерее; для перерыва найдите зону отдыха и проверьте условия на месте.",
        "Explore the shopping gallery; look for a rest area and check visitor conditions on arrival.",
        "Сауда галереясын аралаңыз; демалыс аймағын тауып, келу шарттарын сол жерде нақтылаңыз.",
    ),
    "coffee": (
        "Выпейте кофе; перед заказом уточните наличие свободных мест.",
        "Have a coffee; check seating before ordering.",
        "Кофе ішіңіз; тапсырыс алдында бос орынды сұраңыз.",
    ),
    "food": (
        "Сделайте перерыв на еду; меню уточните на месте.",
        "Take a meal break; check the menu on arrival.",
        "Тамақтануға үзіліс жасаңыз; мәзірді сол жерде қараңыз.",
    ),
    "kids": (
        "Проведите время с ребёнком; проверьте возрастные ограничения на месте.",
        "Spend time with your child; check age restrictions on arrival.",
        "Баламен уақыт өткізіңіз; жас шектеулерін сол жерде тексеріңіз.",
    ),
    "park": (
        "Прогуляйтесь по общедоступным дорожкам и вернитесь тем же путём.",
        "Walk along public paths and return the same way.",
        "Қоғамдық жолдармен серуендеп, сол жолмен қайтыңыз.",
    ),
    "culture": (
        "Уточните формат посещения, билеты и программу заранее; выбирайте занятие в пределах доступного времени.",
        "Check visitor access, tickets and the programme beforehand; choose an activity within your available time.",
        "Келу шарттарын, билет пен бағдарламаны алдын ала нақтылаңыз; уақыт шегіне сай іс таңдаңыз.",
    ),
    "cinema": (
        "Посмотрите афишу; выбирайте сеанс, только если фильм и дорога укладываются в ваше время.",
        "Check showtimes; choose a screening only if the film and return journey fit your available time.",
        "Афишаны қараңыз; фильм мен барып-қайту уақыты жеткілікті болса ғана сеанс таңдаңыз.",
    ),
    "theatre": (
        "Проверьте афишу, билеты и длительность спектакля; учитывайте время на обратную дорогу.",
        "Check the programme, tickets and performance duration; allow time for the return journey.",
        "Афишаны, билетті және қойылым ұзақтығын тексеріңіз; қайту уақытын ескеріңіз.",
    ),
    "museum": (
        "Осмотрите доступную экспозицию; билеты и программу уточните заранее.",
        "Explore the available exhibition; check tickets and the programme beforehand.",
        "Қолжетімді көрмені қараңыз; билет пен бағдарламаны алдын ала нақтылаңыз.",
    ),
    "library": (
        "Почитайте или поработайте; условия посещения уточните у сотрудников.",
        "Read or work; check visitor rules with staff.",
        "Кітап оқыңыз немесе жұмыс істеңіз; келу шарттарын қызметкерлерден сұраңыз.",
    ),
    "cowork": (
        "Поработайте за ноутбуком; стоимость и свободные места уточните заранее.",
        "Work on your laptop; check prices and availability beforehand.",
        "Ноутбукпен жұмыс істеңіз; баға мен бос орынды алдын ала сұраңыз.",
    ),
}


CATEGORIES = {
    'coffee': ('Кофейня', 'Coffee stop', 'Кофехана'),
    'food': ('Место для еды', 'Food stop', 'Тамақтанатын орын'),
    'park': ('Прогулка в парке', 'Park walk', 'Саябақта серуен'),
    'kids': ('Детское место', 'Children’s venue', 'Балаларға арналған орын'),
    'culture': ('Культурное место', 'Cultural stop', 'Мәдени орын'),
    'viewpoint': ('Осмотр достопримечательности', 'Landmark visit', 'Көрікті орынды көру'),
    'unusual': ('Необычное место', 'Unusual stop', 'Ерекше орын'),
    'library': ('Библиотека', 'Library visit', 'Кітапхана'),
    'cowork': ('Коворкинг', 'Coworking venue', 'Коворкинг'),
    'shopping': ('Торговый центр', 'Shopping centre', 'Сауда орталығы'),
    'sport': ('Место для спорта', 'Sports venue', 'Спорт орны'),
    'night': ('Вечернее заведение', 'Evening venue', 'Кешкі орын'),
}
FACILITIES = {
    'quiet': ('тишина', 'quietness', 'тыныштық'),
    'sockets': ('розетки', 'sockets', 'розеткалар'),
    'wifi': ('Wi-Fi', 'Wi-Fi', 'Wi-Fi'),
}
VISUAL = {
    'natural_light': ('дневной свет', 'daylight', 'күндізгі жарық'),
    'bright': ('светло', 'bright', 'жарық'), 'dim': ('приглушённый свет', 'dim lighting', 'бәсең жарық'),
    'greenery': ('зелень', 'greenery', 'өсімдіктер'), 'open_space': ('простор', 'spacious', 'кеңістік'),
    'small_space': ('небольшое пространство', 'small space', 'шағын кеңістік'),
    'visible_seating': ('видимые сиденья', 'visible seats', 'көрінетін орындықтар'),
    'modern': ('современный стиль', 'modern style', 'заманауи стиль'),
    'traditional': ('традиционный стиль', 'traditional style', 'дәстүрлі стиль'),
    'unusual_architecture': ('необычная архитектура', 'unusual architecture', 'ерекше сәулет'),
    'outdoor': ('снаружи', 'outdoors', 'сыртта'), 'indoor': ('в помещении', 'indoors', 'ғимарат ішінде'),
}


def action(hit, intent):
    index = {'ru': 0, 'en': 1, 'kk': 2}[intent.lang]
    if set(intent.tags) & {'wifi', 'sockets'} and hit.poi.category in ('coffee', 'library', 'cowork'):
        return (
            'Перед работой уточните Wi-Fi, розетки и свободные места; условия посещения — у сотрудников.',
            'Before working, check Wi-Fi, sockets and available seating; ask staff about visitor rules.',
            'Жұмыс алдында Wi-Fi, розеткалар мен бос орынды тексеріңіз; келу шарттарын қызметкерлерден сұраңыз.',
        )[index]
    result = ACTIONS.get(activity(hit.poi), ACTIONS.get(hit.poi.category, (
        'Осмотрите место с общедоступной территории; детали посещения уточните заранее.',
        'Explore from public areas; check visitor details beforehand.',
        'Қоғамдық аумақтан тамашалаңыз; бару шарттарын алдын ала тексеріңіз.',
    )))[index]
    if hit.to_end is not None and (activity(hit.poi) in ('cinema', 'theatre') or hit.poi.category == 'park'):
        result = (
            'Уточните условия посещения; после остановки продолжайте путь к выбранному финишу.',
            'Check visitor conditions, then continue to your chosen finish point.',
            'Келу шарттарын нақтылап, аялдамадан кейін таңдалған мәреге барыңыз.',
        )[index]
    return result


def drafts(hits, intent):
    """Selection fallback. Final explanations are rendered after duration clamping."""
    index = {'ru': 0, 'en': 1, 'kk': 2}[intent.lang]
    return [Draft(poi_id=h.poi.poi_id, why=CATEGORIES.get(h.poi.category, ('Место', 'Place', 'Орын'))[index],
                  time_to_spend_min=h.stay, what_to_do=action(h, intent)) for h in hits[:3]]


def explanation(hit, request, intent, budget, condition, visual, category_relaxed=False):
    """Explain observable matches and the exact final budget. No free-form model claims."""
    index = {'ru': 0, 'en': 1, 'kk': 2}[intent.lang]
    category = CATEGORIES.get(hit.poi.category, ('Место', 'Place', 'Орын'))[index]
    head = category + '.'
    # Only attributes actually requested by the person are reasons for recommending.
    wanted = [tag for tag in FACILITIES if tag in intent.tags]
    confirmed = set(hit.poi.tags) - set(hit.poi.tags_inferred)
    known = [FACILITIES[tag][index] for tag in wanted if tag in confirmed]
    unknown = [FACILITIES[tag][index] for tag in wanted if tag not in confirmed]
    if category_relaxed:
        head = ('Альтернатива: ', 'Alternative: ', 'Балама: ')[index] + category.lower() + '.'
    elif (request.preferences.atmosphere_example_id or request.preferences.atmosphere_profile) and visual.matched_features:
        labels = [VISUAL[f][index] for f in visual.matched_features if f in VISUAL][:2]
        if labels:
            head = ('По фото: ', 'From photos: ', 'Фото бойынша: ')[index] + ', '.join(labels) + '.'
    elif request.preferences.expense_mode != 'any' and condition.kind in ('free', 'optional_purchase'):
        head = (('Вход бесплатный по проверенным данным.', 'Verified free entry.', 'Расталған дерек бойынша кіру тегін.')
                if condition.kind == 'free' else
                ('По проверенным данным покупка необязательна.', 'Verified: purchase is optional.', 'Расталған дерек: сатып алу міндетті емес.'))[index]
    elif known:
        head = ('По данным места: ', 'Venue data: ', 'Орын дерегі: ')[index] + ', '.join(known) + '.'
    elif intent.companions == 'child' and hit.poi.kid_friendly:
        head = ('В базе отмечено для детей.', 'Listed as child-friendly.', 'Деректе балаларға қолайлы деп белгіленген.')[index]
    elif hit.poi.indoor and (request.preferences.indoor_only or request.context.weather and
                            (request.context.weather.temp_c <= -15 or request.context.weather.wind_ms >= 10)):
        head = ('В помещении по данным места.', 'Listed as indoors.', 'Дерек бойынша ғимарат ішінде.')[index]
    finish = hit.to_end is not None
    total, limit, walk = budget.total_min, intent.time_budget_min, budget.walk_there_min
    timing = (
        f'≈{walk} мин пешком; всего {total}/{limit} мин ' + ('до финиша.' if finish else 'с возвращением.'),
        f'≈{walk} min walking; {total}/{limit} min total ' + ('to your finish.' if finish else 'including return.'),
        f'Жаяу ≈{walk} мин; ' + ('мәреге дейін' if finish else 'барып-қайтуға') + f' барлығы {total}/{limit} мин.',
    )[index]
    missing = (('Не подтверждены: ', 'Unconfirmed: ', 'Расталмаған: ')[index] + ', '.join(unknown) + '.') if unknown else ''
    # Preserve the requested missing facts and final budget when a translated reason is long.
    if len(' '.join([head, timing, missing]).split()) > 25:
        head = category + '.'
    return ' '.join(part for part in (head, timing, missing) if part), action(hit, intent)
