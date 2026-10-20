"""Small, deterministic text constraints; never infer prices or venue facilities."""
import re


def normalized(query):
    return query.casefold().replace("ё", "е").replace("’", "'")


def with_children(query):
    q = normalized(query)
    q = re.sub(r"\bбез\s+(?:ребен\w*|дет\w*)|\b(?:without|no)\s+(?:my\s+)?(?:children|child|kids?)\b|баласыз", "", q)
    return bool(re.search(
        r"\b(?:ребен\w*|дети|детей|детьми|детск\w*|малыш\w*|дочк\w*|сын\w*|children|child|kids?|"
        r"балам\w*|балалар\w*)\b", q))


def time_limit(query):
    """Total available time, distinct from money, clock time and a walking-leg limit."""
    q = normalized(query)
    q = re.sub(r"\d+\s*(?:минут\w*|minutes?|min)\s+(?:пешком|ходьбы|walk\w*)", "", q)
    q = re.sub(r"(?:идти|дойти|дорога|walk takes)\s+(?:до\s+|около\s+)?\d+\s*(?:минут\w*|minutes?|min)", "", q)
    if re.search(r"полчаса\s*[-–—]\s*час", q):
        return 60
    if re.search(r"пар[ауеы]\s+час|час[-–—]два|couple of hours|two hours|екі сағат", q):
        return 120
    if re.search(r"полтора\s+час|one and a half hours|бір жарым сағат", q):
        return 90
    if "полчаса" in q or "half an hour" in q or "жарты сағат" in q:
        return 30
    unit = r"(минут\w*|minutes?|mins?|час\w*|hours?|hrs?|сағат)"
    span = re.search(rf"(\d+)\s*[-–—]\s*(\d+)\s*{unit}", q)
    if span:
        return min(480, max(5, int(span[2]) * (1 if re.match(r"мин|min", span[3]) else 60)))
    remaining = re.search(r"(?:осталось|есть только|only have)\s+(.+)", q)
    if remaining:
        q = remaining[1]
    combined = re.search(r"(\d+)\s*(?:час\w*|hours?|hrs?|сағат)\s*(?:и|and)?\s*(\d+)\s*(?:минут\w*|minutes?|mins?)", q)
    if combined:
        return min(480, max(5, int(combined[1]) * 60 + int(combined[2])))
    # Separate durations are constraints, not automatically an additive itinerary.
    amounts = re.findall(rf"(?<![\d:])(\d+(?:[.,]\d+)?)\s*{unit}", q)
    if amounts:
        minutes = min(float(n.replace(",", ".")) * (1 if re.match(r"мин|min", u) else 60) for n, u in amounts)
        return min(480, max(5, int(minutes)))
    if re.search(r"\bчас(?:ик)?\b|\b(?:an?|one)\s+hour\b|\bбір\s+сағат", q):
        return 60
    return None


def spending_limit(query):
    """Only an explicit currency amount or budget phrase, never arbitrary numbers."""
    q = normalized(query)
    amount = r"(\d{1,3}(?:[ \u00a0]\d{3})+|\d+)"
    match = re.search(rf"{amount}\s*(?:тенге|тг\b|₸|kzt\b)", q)
    if not match:
        match = re.search(rf"\bбюджет\s*(?:до|не больше|:)?\s*{amount}(?!\d)\b(?!\s*(?:мин|час))", q)
    return int(match[1].replace(" ", "").replace("\u00a0", "")) if match else None


def expense_mode(query):
    q = normalized(query)
    # Keep negated requests and a free Wi-Fi requirement out of the spending constraint.
    q = re.sub(r"не обязательно бесплатно|не только бесплатно|not necessarily free|"
               r"бесплатн\w*\s+(?:wi.?fi|вай.?фай)|free\s+wi.?fi", "", q)
    if re.search(r"без обязательн\w* покуп|без покуп|не покупать|no (?:required )?purchase", q):
        return "no_required_purchase"
    if spending_limit(q) is not None or re.search(
        r"\bбесплатн\w*|без (?:расход\w*|денег|затрат\w*|трат)|не (?:хочу|хотим) тратить|"
        r"\bfree\b|no spend\w*|without spending|no money|ақшасыз|тегін|шығынсыз", q):
        return "free_only"
    return "any"
