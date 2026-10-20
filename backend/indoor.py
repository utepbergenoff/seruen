"""Interpret shelter requests without inventing a temperature or venue facilities."""
import re


def shelter_requested(query):
    q = query.casefold().replace("ё", "е").replace("’", "'")
    # A drink's temperature, a negated complaint or an explicit outdoor choice is not a shelter request.
    q = re.sub(r"\bне\s+(?:очень\s+)?(?:холодно|замерз\w*|мерзн\w*)\b|"
               r"\b(?:not|isn't|aren't)\s+(?:very\s+)?(?:cold|freezing)\b|суық\s+емес|тоңған\s+жоқ\w*", "", q)
    q = re.sub(r"\bcold\s+(?:brew|coffee|tea|drinks?|beer|food)\b|"
               r"\bхолодн\w*\s+(?:кофе|чай|напит\w*|пиво|ед\w*)\b", "", q)
    explicit_inside = bool(re.search(
        r"в помещени|под крышей|крыт\w*\s+(?:игров|площад|центр)|"
        r"\bindoors?\b|inside\s+(?:a\s+)?(?:building|play)|ғимарат ішінде|жабық\s+(?:орын|ойын)", q))
    negated_inside = bool(re.search(
        r"(?:не хочу|не хотим|без)\s+(?:быть\s+)?в помещени|"
        r"(?:not|don't want|do not want)\s+(?:to be\s+)?indoors?", q))
    explicit_inside = explicit_inside and not negated_inside
    avoids_outside = bool(re.search(
        r"не\s+(?:хочу|хотим|хочется).{0,30}(?:на улице|в парк)|"
        r"(?:don't|do not)\s+want.{0,30}(?:outdoors?|outside)", q))
    explicit_outside = bool(re.search(
        r"(?:но|все равно|именно|несмотря).{0,60}(?:на улице|в парк|по парку)|"
        r"(?:but|still|despite).{0,60}(?:outdoors?|outside|in the park)|"
        r"бәрібір.{0,40}(?:далада|сыртта)|суыққа қарамастан", q))
    warmth = bool(re.search(
        r"\b(?:холодно|прохладно|зябко)\b|холодн\w*\s+погод|\bмороз\w*|\bзамерз\w*|\bмерзн\w*|\bпродрог\w*|"
        r"\b(?:согрет|погрет|отогрет)\w*|тепл\w*\s+мест|"
        r"\bcold\b|\bfreezing\b|\bwarm up\b|somewhere warm|"
        r"суық|тоң(?:дым|дық|ып|ған)|жылын|жылы\s+жер", q))
    return explicit_inside or avoids_outside or (warmth and not explicit_outside)


def indoor_required(request):
    return request.preferences.indoor_only or shelter_requested(request.query)


def catalog_indoor(category, rubrics, attributes):
    """Only source rubrics/attributes establish an indoor venue; a playground name does not."""
    facts = " ".join([rubrics, *attributes])
    if re.search(r"под открытым небом|на открытом воздухе|уличн|открыт\w*\s+площад|"
                 r"\boutdoor\b|\bopen.air\b|ашық аспан|ашық алаң", facts, re.I):
        return False
    if category in ("coffee", "food", "library", "cowork", "shopping", "night"):
        return True
    if category == "kids":
        return bool(re.search(
            r"игров\w*\s+(?:зал|комнат|центр)|развлекательн\w*\s+центр|"
            r"indoor\s+play|балалар.{0,25}(?:ойын|ойын-сауық)\s+ортал", rubrics, re.I))
    if category == "culture":
        return bool(re.search(r"музе|театр|галере|cinema|museum|theat|gallery|мұражай", rubrics, re.I))
    return False
