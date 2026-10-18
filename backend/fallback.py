from .activities import activity
from .schemas import Draft

WHY = {
    "ru": "Подходит по категории и укладывается в ваш бюджет времени.",
    "en": "Matches the requested category and fits your time budget.",
    "kk": "Сұралған санатқа сәйкес және уақыт шегіне сай келеді.",
}
ACTIONS = {
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


def drafts(hits, intent):
    result = []
    index = {"ru": 0, "en": 1, "kk": 2}[intent.lang]
    for hit in hits[:3]:
        why = WHY[intent.lang]
        if "outdoor_walk" in intent.tags:
            why = (
                f"Для прогулки на воздухе: {hit.candidate.walk_min} мин пешком и {hit.stay} мин на месте; обратная дорога учтена.",
                f"For an outdoor walk: {hit.candidate.walk_min} min on foot and {hit.stay} min there; return time is included.",
                f"Серуенге: жаяу {hit.candidate.walk_min} минут, сол жерде {hit.stay} минут; қайту уақыты ескерілген.",
            )[index]
        elif intent.companions == "child":
            why = (
                "В базе отмечено как подходящее для детей; время с дорогой укладывается в бюджет.",
                "Marked child-friendly in the dataset; the visit and return fit your time budget.",
                "Деректе балаларға қолайлы деп белгіленген; барып-қайту уақыт шегіне сай.",
            )[index]
        elif any(r.startswith(("tag:", "inferred_tag:")) for r in hit.candidate.reasons):
            labels = {
                "quiet": ("тихо", "quiet", "тыныш"),
                "sockets": ("розетки", "power sockets", "розеткалар"),
                "wifi": ("Wi-Fi", "Wi-Fi", "Wi-Fi"),
            }
            confirmed, inferred = [], []
            for reason in hit.candidate.reasons:
                kind, _, tag = reason.partition(":")
                if tag in labels and kind in ("tag", "inferred_tag"):
                    (inferred if kind == "inferred_tag" else confirmed).append(labels[tag][index])
            parts = []
            if confirmed:
                parts.append(("По данным: ", "Recorded: ", "Дерек бойынша: ")[index] + ", ".join(confirmed) + ".")
            if inferred:
                parts.append(
                    ("Обычно для этой категории: ", "Typical for this category: ", "Бұл санатта әдетте: ")[index]
                    + ", ".join(inferred)
                    + (" — уточните на месте.", " — confirm on arrival.", " — барған кезде нақтылаңыз.")[index]
                )
            why = " ".join(parts) or why
        action = ACTIONS.get(
            activity(hit.poi) or hit.poi.category,
            (
                "Осмотрите место с общедоступной территории; детали посещения уточните заранее.",
                "Explore from public areas; check visitor details beforehand.",
                "Қоғамдық аумақтан тамашалаңыз; бару шарттарын алдын ала тексеріңіз.",
            ),
        )[index]
        if hit.to_end is not None:
            why = WHY[intent.lang]
            if activity(hit.poi) in ("cinema", "theatre") or hit.poi.category == "park":
                action = (
                    "Уточните условия посещения; после остановки продолжайте путь к выбранному финишу.",
                    "Check visitor conditions, then continue to your chosen finish point.",
                    "Келу шарттарын нақтылап, аялдамадан кейін таңдалған мәреге барыңыз.",
                )[index]
        result.append(Draft(poi_id=hit.poi.poi_id, why=why, time_to_spend_min=hit.stay, what_to_do=action))
    return result
