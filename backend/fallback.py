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
        "Осмотрите доступную экспозицию; билеты и программу уточните на месте.",
        "Explore the available exhibition; check tickets and the programme on arrival.",
        "Қолжетімді көрмені қараңыз; билет пен бағдарламаны сол жерде нақтылаңыз.",
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
        if intent.companions == "child":
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
            hit.poi.category,
            (
                "Осмотрите место с общедоступной территории; детали посещения уточните заранее.",
                "Explore from public areas; check visitor details beforehand.",
                "Қоғамдық аумақтан тамашалаңыз; бару шарттарын алдын ала тексеріңіз.",
            ),
        )[index]
        result.append(Draft(poi_id=hit.poi.poi_id, why=why, time_to_spend_min=hit.stay, what_to_do=action))
    return result
