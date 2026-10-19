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


def supports_draft(draft, hit, request, intent, features=None):
    facts = evidence(hit, request, intent, features)
    if not draft.evidence_ids or not set(draft.evidence_ids) <= facts.keys():
        return False
    text = (draft.why + ". " + draft.what_to_do).casefold()
    if re.search(r"гарант|безопасн|\bsafe\b|қауіпсіз|бесплат|тегін|\bfree (entry|food|meal|drink|coffee|seats)|for free|₸|тенге|\bprice|цен[ауы]|"
                 r"свободн.{0,12}(стол|мест)|available (tables|seats)|бос орын|"
                 r"сегодня.{0,18}(выстав|концерт|вечерин)|event today|live music|живая музыка|"
                 r"лучший|идеальн|\bbest\b|\bperfect\b", text):
        return False
    if re.search(r"\d", text.replace(hit.poi.name.casefold(), "")):
        return False
    known = confirmed_tags(hit.poi)
    uncertain = r"уточн|провер|не подтверж|неизвест|не гаран|\bcheck\b|\bask\b|unconfirm|unknown|нақтыла|тексер|расталма|белгісіз"
    for clause in re.split(r"[.!?;]", text):
        for tag, pattern in FACILITIES.items():
            if tag not in known and re.search(pattern, clause) and not re.search(uncertain, clause):
                return False
        for fact, pattern in (("wheelchair", r"безбарьер|доступн.{0,15}коляс|wheelchair.accessible"),
                              ("indoor", r"в помещении|\bindoors\b|ғимарат ішінде")):
            if fact not in facts and re.search(pattern, clause) and not re.search(uncertain, clause):
                return False
    return len((draft.why + " " + unknown_note(hit, intent)).split()) <= 25
