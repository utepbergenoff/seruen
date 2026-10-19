"""Evidence packs and conservative prose checks, without another model call.

Checks reject known unsupported claims; they cannot prove arbitrary prose true.
Calculations, hours, prices and missing-facility warnings remain server-owned.
"""
import re
from .activities import activity
from .embeddings import tokenize
from .geo import target_time

FACILITIES = {"quiet": r"тишин|тих\w*|quiet|silent|тыныш",
              "sockets": r"розет\w*|sockets?|outlets?", "wifi": r"wi-?fi|интернет|internet"}
UNKNOWN = {"ru": {"quiet": "тишина", "sockets": "розетки", "wifi": "Wi-Fi"},
           "en": {"quiet": "quietness", "sockets": "sockets", "wifi": "Wi-Fi"},
           "kk": {"quiet": "тыныштық", "sockets": "розеткалар", "wifi": "Wi-Fi"}}


def confirmed_tags(poi):
    return set(tokenize(" ".join(poi.tags))) - set(tokenize(" ".join(poi.tags_inferred)))


def unknown_facilities(hit, intent):
    return [tag for tag in FACILITIES if tag in intent.tags and tag not in confirmed_tags(hit.poi)]


def unknown_note(hit, intent):
    missing = unknown_facilities(hit, intent)
    prefix = {"ru": "Не подтверждены: ", "en": "Unconfirmed: ", "kk": "Расталмаған: "}[intent.lang]
    return prefix + ", ".join(UNKNOWN[intent.lang][tag] for tag in missing) + "." if missing else ""


def supported_numbers(text, hit):
    """Accept exact supplied walk/visit times, never arbitrary numeric claims."""
    text = text.replace(hit.poi.name.casefold(), "")
    for clause in re.split(r"[.!?;]", text):
        for number in re.finditer(r"\d+", clause):
            rest = clause[number.start():]
            if not re.match(r"\d+\s*[-–]?\s*(?:minutes?|mins?|минут\w*|мин\b)", rest):
                return False
            n = int(number.group())
            if re.search(r"пеш|ходьб|\bwalk|жаяу", clause):
                if n != hit.candidate.walk_min:
                    return False
            elif re.search(r"посещ|провед|побы|остать|\bvisit|\bspend|өткіз|болыңыз", clause):
                if n != hit.stay:
                    return False
            else:
                return False
    return True


def evidence(hit, request, intent, features=None):
    p = hit.poi
    facts = {"category": p.category, "walk": {"minutes": hit.candidate.walk_min},
             "visit": {"minutes": hit.stay}, "activity": activity(p) or p.category}
    if p.description and p.description_source != "generated":
        facts["description"] = p.description[:1200]
    for tag in sorted(confirmed_tags(p)):
        facts["tag:" + tag] = True
    for key, value in (("child_friendly", p.kid_friendly), ("indoor", p.indoor),
                       ("wheelchair", p.wheelchair == "yes")):
        if value:
            facts[key] = True
    if features:
        match = features.match(p.poi_id, request.preferences.atmosphere_example_id,
                               target_time(request, intent).date(), request.preferences.atmosphere_profile)
        for feature in match.matched_features:
            facts["photo:" + feature] = True
    return facts


def draft_failure(draft, hit, request, intent, features=None):
    facts = evidence(hit, request, intent, features)
    if not draft.evidence_ids or not set(draft.evidence_ids) <= facts.keys():
        return "evidence"
    text = (draft.why + ". " + draft.what_to_do).casefold()
    if re.search(r"гарант|безопасн|\bsafe\b|қауіпсіз|бесплат|тегін|\bfree (entry|food|meal|drink|coffee|seats)|for free|₸|тенге|\bprice|цен[ауы]|"
                 r"свободн.{0,12}(стол|мест)|available (tables|seats)|бос орын|"
                 r"сегодня.{0,18}(выстав|концерт|вечерин)|event today|live music|живая музыка|"
                 r"лучший|идеальн|\bbest\b|\bperfect\b", text):
        return "unsupported_claim"
    if not supported_numbers(text, hit):
        return "numeric_claim"
    known = confirmed_tags(hit.poi)
    uncertain = r"уточн|провер|не подтверж|неизвест|не гаран|\bcheck\b|\bask\b|unconfirm|unknown|нақтыла|тексер|расталма|белгісіз"
    for clause in re.split(r"[.!?;]", text):
        for tag, pattern in FACILITIES.items():
            if tag not in known and re.search(pattern, clause) and not re.search(uncertain, clause):
                return "unconfirmed_facility"
        for fact, pattern in (("wheelchair", r"безбарьер|доступн.{0,15}коляс|wheelchair.accessible"),
                              ("indoor", r"в помещении|\bindoors\b|ғимарат ішінде")):
            if fact not in facts and re.search(pattern, clause) and not re.search(uncertain, clause):
                return "unconfirmed_access"
    return "why_too_long" if len((draft.why + " " + unknown_note(hit, intent)).split()) > 25 else None


def supports_draft(draft, hit, request, intent, features=None):
    return draft_failure(draft, hit, request, intent, features) is None
