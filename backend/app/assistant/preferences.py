"""Rule-based preference parser — the OFFLINE-FIRST brain of the assistant.

Given a free-text message in Russian, Kazakh, or English, this module extracts
a structured :class:`Preferences` object: the service topic, a price ceiling/
floor, currency, resident vs non-resident, a city, a sort order, a result
limit, the detected language, and the user's intent.

It is intentionally dependency-free (only ``re`` + the standard library) and
deterministic, so the chatbot works with zero network access and no API key —
the LLM tier in :mod:`app.assistant.llm` is a strict enhancement layered on top.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from .schemas import Preferences

# --------------------------------------------------------------------------- #
# Currency handling                                                            #
# --------------------------------------------------------------------------- #
# Budgets are usually quoted in tenge; when a user states USD/RUB we convert to
# KZT so the ceiling can be compared against the stored (KZT) prices. Rates
# mirror the "default" reference rates shipped in app/data/fx_rates.json.
_FX_TO_KZT: dict[str, Decimal] = {
    "KZT": Decimal("1"),
    "USD": Decimal("500"),
    "RUB": Decimal("5.5"),
}
_CURRENCY_WORDS: list[tuple[str, str]] = [
    (r"\$|usd|доллар\w*|dollars?|бакс\w*", "USD"),
    (r"₽|руб\w*|rub\b|roubles?|rubles?", "RUB"),
    (r"₸|тг\b|тенге|kzt|tenge", "KZT"),
]
_CURRENCY_CONSUME_RE = re.compile("|".join(p for p, _ in _CURRENCY_WORDS), re.IGNORECASE)

# --------------------------------------------------------------------------- #
# City gazetteer (variant -> canonical RU name as stored on Partner.city)      #
# --------------------------------------------------------------------------- #
_CITY_VARIANTS: dict[str, str] = {
    "алматы": "Алматы", "алмата": "Алматы", "almaty": "Алматы", "алма-ата": "Алматы",
    "астана": "Астана", "astana": "Астана", "нур-султан": "Астана",
    "нурсултан": "Астана", "nur-sultan": "Астана",
    "шымкент": "Шымкент", "shymkent": "Шымкент", "чимкент": "Шымкент",
    "караганда": "Караганда", "karaganda": "Караганда", "қарағанды": "Караганда",
    "актобе": "Актобе", "aktobe": "Актобе", "ақтөбе": "Актобе",
    "тараз": "Тараз", "taraz": "Тараз",
    "павлодар": "Павлодар", "pavlodar": "Павлодар",
    "семей": "Семей", "semey": "Семей",
    "атырау": "Атырау", "atyrau": "Атырау",
    "костанай": "Костанай", "kostanay": "Костанай", "қостанай": "Костанай",
    "кызылорда": "Кызылорда", "kyzylorda": "Кызылорда", "қызылорда": "Кызылорда",
    "уральск": "Уральск", "uralsk": "Уральск",
    "петропавловск": "Петропавловск", "petropavl": "Петропавловск",
    "актау": "Актау", "aktau": "Актау",
    "туркестан": "Туркестан", "turkestan": "Туркестан", "түркістан": "Туркестан",
    "усть-каменогорск": "Усть-Каменогорск", "oskemen": "Усть-Каменогорск",
    "өскемен": "Усть-Каменогорск", "талдыкорган": "Талдыкорган",
    "кокшетау": "Кокшетау", "kokshetau": "Кокшетау",
}
_VOWELS = "аеёиоуыэюя"
# Plausible Russian/Kazakh noun case endings a city stem may take. Restricting
# to these (instead of "any Cyrillic suffix") stops the stem from swallowing
# adjectives like "семейный" (which would otherwise read as the city "Семей").
_CASE_ENDINGS = r"(?:ом|ой|ах|ам|да|де|та|те|е|а|у|ы|и|я|ю)?"


def _city_regex(variant: str) -> re.Pattern:
    """Build a case-insensitive matcher tolerant of Russian noun inflection.

    Cyrillic place names inflect (Астана → Астане/Астаны), so we match the stem
    (variant minus a trailing vowel) plus at most one common case ending. Latin
    variants don't inflect, so they use plain word boundaries.
    """
    if re.search(r"[а-яё]", variant):
        stem = variant[:-1] if (len(variant) > 4 and variant[-1] in _VOWELS) else variant
        return re.compile(r"(?<!\w)" + re.escape(stem) + _CASE_ENDINGS + r"(?!\w)", re.IGNORECASE)
    return re.compile(r"(?<!\w)" + re.escape(variant) + r"(?!\w)", re.IGNORECASE)


# Longest variant first so "усть-каменогорск" wins over "уральск", etc.
_CITY_PATTERNS: list[tuple[re.Pattern, str]] = [
    (_city_regex(v), canon)
    for v, canon in sorted(_CITY_VARIANTS.items(), key=lambda kv: -len(kv[0]))
]

# --------------------------------------------------------------------------- #
# Lexical cues                                                                 #
# --------------------------------------------------------------------------- #
_NONRESIDENT_RE = re.compile(
    r"нерезидент\w*|не\s+резидент\w*|иностран\w*|foreigner\w*|non[\s-]?residen\w*",
    re.IGNORECASE,
)
_RESIDENT_RE = re.compile(
    r"\bрезидент\w*|граждан\w*|местн\w*|citizen\w*|\blocal\b|\bresident\w*",
    re.IGNORECASE,
)

_CHEAP_RE = re.compile(
    r"деш[её]в\w*|подеш[её]вл\w*|недорог\w*|бюджетн\w*|эконом\w*|"
    r"cheap\w*|affordable|inexpensive|low(?:est)?[\s-]?price\w*|lowest",
    re.IGNORECASE,
)
_EXPENSIVE_RE = re.compile(
    r"дорог\w*|подорож\w*|премиум|премиальн\w*|expensive|premium|high[\s-]?end",
    re.IGNORECASE,
)

_PARTNER_CUE_RE = re.compile(
    r"клиник\w*|больниц\w*|медцентр\w*|мед\s*центр\w*|\bцентр\b|лаборатори\w*|"
    r"clinic\w*|hospital\w*|\bcenter\b|\bcentre\b|provider\w*|partner\w*",
    re.IGNORECASE,
)
_COMPARE_CUE_RE = re.compile(
    r"сравн\w*|где\s+деш[её]вл\w*|compar\w*|\bvs\b|versus|cheapest\s+among|"
    r"котор\w+\s+деш[её]вл\w*",
    re.IGNORECASE,
)

# Filler / stop words removed when distilling the service topic.
_STOPWORDS = {
    # ru
    "найди", "найти", "найдите", "хочу", "хочется", "нужен", "нужна", "нужно",
    "нужны", "надо", "покажи", "покажите", "дай", "дайте", "ищу", "искать",
    "посоветуй", "посоветуйте", "подскажи", "подскажите", "где", "сделать",
    "сделай", "услуга", "услугу", "услуги", "услуг", "цена", "цену", "цены",
    "ценам", "прайс", "сколько", "стоит", "стоимость", "самый", "самая",
    "самое", "мне", "пожалуйста", "плиз", "для", "по", "на", "во", "и",
    "с", "за", "около", "примерно", "вариант", "варианта",
    "вариантов", "результат", "результата", "результатов", "которые",
    "которая", "который", "есть", "это",
    # en
    "find", "show", "me", "want", "need", "looking", "for", "please", "the",
    "a", "an", "of", "in", "at", "to", "with", "service", "services", "price",
    "prices", "cost", "how", "much", "is", "are", "best", "any",
    "some", "i", "get", "give", "list", "option", "options", "result",
    "results", "that", "which", "where",
    # kk (common)
    "керек", "табу", "қызмет", "баға", "арзан",
    # greetings / smalltalk -> distilled away so a bare "привет" reads as unknown
    "привет", "приветствую", "здравствуй", "здравствуйте", "добрый", "день",
    "вечер", "утро", "хай", "hello", "hi", "hey", "yo", "спасибо", "thanks",
    "thank", "you", "ok", "окей", "ладно",
}

# --------------------------------------------------------------------------- #
# Number / amount parsing                                                      #
# --------------------------------------------------------------------------- #
_MULTIPLIERS = {
    "к": 1000, "k": 1000, "тыс": 1000, "тысяч": 1000,
    "тысячи": 1000, "тысяча": 1000, "thousand": 1000, "thousands": 1000,
    "млн": 1_000_000, "миллион": 1_000_000, "миллиона": 1_000_000,
    "миллионов": 1_000_000, "m": 1_000_000, "mln": 1_000_000, "million": 1_000_000,
    "millions": 1_000_000, "м": 1_000_000,
}
_MULT_ALT = r"млн\.?|миллион\w*|тыс\w*\.?|thousand\w*|million\w*|mln|[kкmм]"
# A money amount: digits with optional space/comma/dot grouping + optional unit.
# The digit run is bounded (<= 17 chars) so a pathological number from untrusted
# input can never overflow Decimal's quantize context downstream.
_AMOUNT = r"(?P<num>\d[\d\s.,]{0,15}\d|\d)\s*(?P<mult>" + _MULT_ALT + r")?"

# NEGATED triggers ("не дороже" = ceiling, "не дешевле" = floor) are matched in
# a dedicated first pass and consumed before the BARE triggers run, so the bare
# "дешевле" ceiling never sees a "не дешевле" floor. The negation particle is
# anchored with a left word boundary so a word ending in "...не" (e.g. "астанЕ")
# can't masquerade as the particle. Bare prepositions (до/под/от) likewise carry
# a left boundary so they don't match the tails of words like "живот".
_NEG_CEIL_TRIG = (
    r"(?<!\w)не\s+(?:дороже|больше|более)"
    r"|(?<!\w)(?:no|not)\s+(?:more|higher)\s+than"
)
_NEG_FLOOR_TRIG = (
    r"(?<!\w)не\s+(?:деш[её]вле|меньше|менее)"
    r"|(?<!\w)(?:no|not)\s+(?:cheaper|less)\s+than"
)
_CEILING_TRIGGERS = (
    r"деш[её]вле|максимум|макс\.?|в\s+пределах|(?<!\w)до|(?<!\w)под|бюджет\w*|"
    r"cheaper\s+than|less\s+than|under|below|up\s+to|within|at\s+most|"
    r"max\.?|maximum|<=|<"
)
_FLOOR_TRIGGERS = (
    r"дороже|минимум|мин\.?|(?<!\w)от|more\s+than|greater\s+than|above|over|"
    r"at\s+least|starting\s+from|from|min\.?|minimum|>=|>"
)

# Range regex uses plain numbered groups (named groups can't repeat in one
# pattern): group 1 = low number, 2 = low unit, 3 = high number, 4 = high unit.
_RANGE_RE = re.compile(
    r"(?:(?<!\w)от|between|from)\s*(\d[\d\s.,]{0,15}\d|\d)\s*(" + _MULT_ALT + r")?\s*"
    r"(?:до|to|and|[-—–])\s*(\d[\d\s.,]{0,15}\d|\d)\s*(" + _MULT_ALT + r")?",
    re.IGNORECASE,
)
_NEG_CEIL_RE = re.compile(r"(?:" + _NEG_CEIL_TRIG + r")\s*" + _AMOUNT, re.IGNORECASE)
_NEG_FLOOR_RE = re.compile(r"(?:" + _NEG_FLOOR_TRIG + r")\s*" + _AMOUNT, re.IGNORECASE)
_CEILING_RE = re.compile(r"(?:" + _CEILING_TRIGGERS + r")\s*" + _AMOUNT, re.IGNORECASE)
_FLOOR_RE = re.compile(r"(?:" + _FLOOR_TRIGGERS + r")\s*" + _AMOUNT, re.IGNORECASE)
_LIMIT_RE = re.compile(
    r"(?:топ|top|первы\w*|first|показать|show)\s*(\d{1,2})\b"
    r"|(\d{1,2})\s*(?:вариант\w*|результат\w*|клиник\w*|options?|results?|clinics?|providers?)",
    re.IGNORECASE,
)


def _parse_amount(num: str, mult: str | None) -> Decimal | None:
    """Parse a grouped numeric token (+ optional multiplier word) to Decimal."""
    s = (num or "").strip().replace(" ", "").replace(" ", "")
    if not s:
        return None
    # Resolve the decimal separator heuristically (prices are usually integers).
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        head, _, tail = s.rpartition(",")
        s = (head + "." + tail) if (head and len(tail) in (1, 2)) else s.replace(",", "")
    elif "." in s:
        head, _, tail = s.rpartition(".")
        if not (head and len(tail) in (1, 2)):
            s = s.replace(".", "")
    try:
        value = Decimal(s)
    except (InvalidOperation, ValueError):
        return None
    factor = _MULTIPLIERS.get((mult or "").lower().strip("."))
    if factor:
        value *= factor
    return value


def _detect_currency(text: str) -> str:
    for pattern, code in _CURRENCY_WORDS:
        if re.search(pattern, text, re.IGNORECASE):
            return code
    return "KZT"


# Upper bound on a sane price; anything beyond is treated as noise. Also keeps
# Decimal.quantize from ever overflowing the default 28-digit context on
# untrusted input (which would otherwise raise InvalidOperation -> HTTP 500).
_MAX_PRICE_KZT = Decimal("1000000000000")  # 1 trillion ₸


def _to_kzt(amount: Decimal | None, currency: str) -> Decimal | None:
    if amount is None:
        return None
    try:
        value = (amount * _FX_TO_KZT.get(currency, Decimal("1"))).quantize(Decimal("1"))
    except (InvalidOperation, ArithmeticError):
        return None
    if value <= 0 or value > _MAX_PRICE_KZT:
        return None
    return value


def _detect_language(text: str) -> str | None:
    if re.search(r"[әғқңөұүһі]", text, re.IGNORECASE):
        return "kk"
    cyr = len(re.findall(r"[а-яё]", text, re.IGNORECASE))
    lat = len(re.findall(r"[a-z]", text, re.IGNORECASE))
    if cyr == 0 and lat == 0:
        return None
    return "ru" if cyr >= lat else "en"


def _detect_city(text: str) -> tuple[str | None, str | None]:
    """Return (canonical_city, matched_substring) found in ``text``."""
    for pattern, canon in _CITY_PATTERNS:
        m = pattern.search(text)
        if m:
            return canon, m.group(0)
    return None, None


def parse_preferences(message: str, max_results: int = 5) -> Preferences:
    """Extract a structured :class:`Preferences` from a free-text ``message``.

    Deterministic and side-effect-free. Always returns a valid object; an empty
    or unparsable message yields ``intent="unknown"`` with an empty topic.
    """
    text = (message or "").strip()
    prefs = Preferences(limit=max_results, raw_query="", intent="find_service")
    if not text:
        prefs.intent = "unknown"
        return prefs

    prefs.language = _detect_language(text)
    currency = _detect_currency(text)
    working = text  # mutated copy: matched spans are blanked as we consume them

    def _consume(pattern: re.Pattern) -> list[re.Match]:
        """Match ``pattern`` against the *remaining* text and blank the spans.

        Searching the progressively-blanked ``working`` string (rather than the
        original) prevents overlapping triggers from double-firing — e.g. the
        ``дороже`` floor trigger never matches once ``не дороже`` was already
        consumed as a ceiling.
        """
        nonlocal working
        matches = list(pattern.finditer(working))
        for m in matches:
            working = working[: m.start()] + " " * (m.end() - m.start()) + working[m.end():]
        return matches

    # --- price: range, then ceiling, then floor (mutually exclusive) --- #
    range_matches = _consume(_RANGE_RE)
    if range_matches:
        m = range_matches[0]
        lo_k = _to_kzt(_parse_amount(m.group(1), m.group(2)), currency)
        hi_k = _to_kzt(_parse_amount(m.group(3), m.group(4)), currency)
        if lo_k is not None and hi_k is not None:
            prefs.min_price_kzt, prefs.max_price_kzt = min(lo_k, hi_k), max(lo_k, hi_k)
            prefs.notes.append(
                f"price between {prefs.min_price_kzt} and {prefs.max_price_kzt} ₸"
            )
    else:
        # Negated forms first (consume "не дороже"/"не дешевле" precisely), then
        # the bare ceiling/floor. Each kind keeps the first valid amount found.
        def _apply(regex, is_ceiling):
            for m in _consume(regex):
                kzt = _to_kzt(_parse_amount(m.group("num"), m.group("mult")), currency)
                if kzt is None:
                    continue
                if is_ceiling and prefs.max_price_kzt is None:
                    prefs.max_price_kzt = kzt
                    prefs.notes.append(f"budget ≤ {kzt} ₸")
                elif not is_ceiling and prefs.min_price_kzt is None:
                    prefs.min_price_kzt = kzt
                    prefs.notes.append(f"price ≥ {kzt} ₸")

        _apply(_NEG_CEIL_RE, True)
        _apply(_NEG_FLOOR_RE, False)
        _apply(_CEILING_RE, True)
        _apply(_FLOOR_RE, False)

    if currency != "KZT" and (prefs.max_price_kzt or prefs.min_price_kzt):
        prefs.notes.append(f"converted {currency} → KZT")

    # --- result limit --- #
    for m in _consume(_LIMIT_RE):
        digits = next((g for g in m.groups() if g and g.isdigit()), None)
        if digits:
            prefs.limit = max(1, min(20, int(digits)))
            break

    # --- resident preference (non-resident checked first) --- #
    if _NONRESIDENT_RE.search(text):
        prefs.resident = "nonresident"
        prefs.notes.append("non-resident pricing")
    elif _RESIDENT_RE.search(text):
        prefs.resident = "resident"
        prefs.notes.append("resident pricing")
    _consume(_NONRESIDENT_RE)
    _consume(_RESIDENT_RE)

    # --- sort order --- #
    if _EXPENSIVE_RE.search(text):
        prefs.sort = "expensive"
    elif _CHEAP_RE.search(text):
        prefs.sort = "cheapest"
    elif prefs.max_price_kzt is not None:
        prefs.sort = "cheapest"  # a budget implies "cheapest within it"
    _consume(_CHEAP_RE)
    _consume(_EXPENSIVE_RE)

    # --- currency words (so "тенге"/"usd" don't pollute the topic) --- #
    _consume(_CURRENCY_CONSUME_RE)

    # --- city --- #
    city, city_word = _detect_city(working)
    if city:
        prefs.city = city
        prefs.notes.append(f"in {city}")
        if city_word:
            working = working.replace(city_word, " ")

    # --- intent cues --- #
    wants_partner = bool(_PARTNER_CUE_RE.search(text))
    wants_compare = bool(_COMPARE_CUE_RE.search(text))
    _consume(_COMPARE_CUE_RE)
    _consume(_PARTNER_CUE_RE)

    # --- distil the service topic from whatever remains --- #
    leftover = re.sub(r"[^\w\s/+-]", " ", working, flags=re.UNICODE)
    tokens = [t for t in leftover.lower().split() if t]
    topic_tokens = [
        t for t in tokens
        if t not in _STOPWORDS and not t.isdigit() and len(t) > 1
    ]
    raw_query = " ".join(topic_tokens).strip()
    prefs.services = topic_tokens
    prefs.raw_query = raw_query

    # --- final intent resolution --- #
    if wants_compare and raw_query:
        prefs.intent = "compare"
    elif raw_query:
        prefs.intent = "find_service"
    elif wants_partner or prefs.city:
        prefs.intent = "find_partner"
        prefs.raw_query = raw_query or (city or "")
    else:
        prefs.intent = "unknown"

    return prefs
