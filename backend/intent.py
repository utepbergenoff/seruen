import re

from .schemas import Intent


def detect_lang(query):
    if re.search("[әғқңөұүһі]", query.lower()):
        return "kk"
    if re.search("[а-яё]", query.lower()):
        return "ru"
    return "en" if re.search("[a-z]", query.lower()) else "ru"


def rule_intent(request):
    q = request.query.lower().replace("ё", "е")
    tags, categories = [], []
    if re.search(r"коф|кафе|cafe|coffee|кофе|ноут|laptop|розет|socket|wifi|wi-fi|wi fi|поработ|жұмыс", q):
        categories = ["coffee", "library", "cowork"]
    if re.search(r"тих|спокой|шумно|quiet|calm|тыныш", q):
        tags.append("quiet")
    if re.search(r"розет|socket|power|ноут|laptop", q):
        tags.append("sockets")
    if re.search(r"wi.?fi|вай.?фай|ноут|laptop", q):
        tags.append("wifi")
    child = (
        bool(re.search(r"\b(?:ребен|деть|дети|детск|дочк|сын|child|kid|балам|баламен|балалар)", q))
        or request.context.companions == "child"
    )
    if child:
        categories = ["kids", "park", "culture"]
    walking = bool(re.search(r"прогул|погул|прогуля|пройтись|подыш|walk|серуен|\bпарк|\bpark|сквер", q))
    indoor_visit = bool(re.search(r"музей|museum|мұражай|кино|cinema|театр|theat|галере|gallery|в помещении|indoors", q))
    if walking and not indoor_visit and (not categories or child):
        tags.append("outdoor_walk")
        if not categories:
            categories = ["park", "viewpoint", "culture", "unusual"]
    if not child and re.search(r"необыч|нестандарт|скрыт|unusual|hidden|ерекше|надоели", q):
        categories = ["culture", "viewpoint", "unusual"]
    if not categories and indoor_visit:
        categories = ["culture"]
    if not categories and re.search(r"поесть|еда|food|eat|тамақ", q):
        categories = ["food"]
    budget = 60
    range_match = re.search(r"(\d+)\s*[-–—]\s*(\d+)\s*(мин|minute|min|час|hour|сағат)", q)
    single = re.search(r"(\d+)\s*(мин|minute|min|час|hour|сағат)", q)
    if range_match:
        budget = int(range_match[2]) * (60 if range_match[3] in ("час", "hour", "сағат") else 1)
    elif single:
        budget = int(single[1]) * (60 if single[2] in ("час", "hour", "сағат") else 1)
    elif re.search(r"пар[ауеы] час|час-два|couple of hours|two hours|екі сағат", q):
        budget = 120
    elif re.search(r"полчаса-час|полчаса.?час", q):
        budget = 60
    elif "полчаса" in q:
        budget = 30
    elif re.search(r"час|hour|сағат", q):
        budget = 60
    excluded = set(request.context.exclude_categories)
    if re.search(r"(не|без|надоели|no|exclude|avoid).{0,20}(трц|mall|shopping)", q):
        excluded.add("shopping")
    when = "now"
    if re.search(r"вечер|evening|кешке", q):
        when = "evening"
    if re.search(r"ноч|23[:.]?00|22[:.]?00|night|late at night|түн", q):
        when = "night"
    if re.search(r"завтра|tomorrow|ертең", q):
        when = "tomorrow"
    before_flight = bool(re.search(r"вылет|аэропорт|транзит|flight|airport|ұшақ", q))
    if before_flight and not categories:
        categories = ["viewpoint", "culture", "park", "coffee", "unusual"]
    if (
        when == "night"
        and not child
        and categories in ([], ["culture", "viewpoint", "unusual"], ["park", "viewpoint", "culture", "unusual"])
    ):
        categories = ["night", "viewpoint", "food", "coffee", "unusual", "park"]
    unsafe = bool(re.search(r"выйти на лед|по льду|стройк|заброш|крыш[ауи]|trespass|construction site|on the ice", q))
    unrelated = bool(
        re.search(
            r"сколько стоит такси|цен[аыу] такси|такси заказать|taxi fare|напиши код|python|рецепт|лечени|лекарств|юрид|закон|bitcoin|крипт|ignore.{0,30}instruction",
            q,
        )
    )
    domain = re.search(
        r"прогул|погул|прогуля|пройтись|подыш|рядом|сходить|посмотр|коф|кафе|ноут|музей|мұражай|кино|cinema|театр|theat|галере|gallery|парк|park|сквер|тихо|розет|ноч|вечер|мест|час|минут|вылет|аэропорт|транзит|ребен|дет|доч|необыч|walk|near|place|cafe|coffee|museum|quiet|socket|night|hour|minute|flight|airport|child|kid|unusual|бала|сағат|қайда|серуен|ұшақ|көруге",
        q,
    )
    unrelated = unrelated or bool(q.strip() and not domain)
    return Intent(
        categories=categories,
        tags=tags,
        time_budget_min=request.context.time_budget_min or max(5, min(480, budget)),
        companions="child" if child else request.context.companions,
        when=when,
        lang=detect_lang(q) if request.context.lang == "auto" else request.context.lang,
        exclude_categories=sorted(excluded),
        before_flight=before_flight,
        relevant=not unrelated,
        unsafe=unsafe,
    )


def merge_intent(rules, generated, request):
    """AI may fill gaps, but never relax constraints found in text or context."""
    return generated.model_copy(
        update={
            "categories": rules.categories or generated.categories,
            "tags": sorted(set(rules.tags + generated.tags)),
            "time_budget_min": rules.time_budget_min,
            "companions": rules.companions,
            "when": rules.when if rules.when != "now" else generated.when,
            "lang": rules.lang,
            "exclude_categories": sorted(set(rules.exclude_categories + generated.exclude_categories)),
            "before_flight": rules.before_flight or generated.before_flight,
            "relevant": rules.relevant and generated.relevant,
            "unsafe": rules.unsafe or generated.unsafe,
        }
    )
