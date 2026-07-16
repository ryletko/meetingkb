from __future__ import annotations

import html
import re
from functools import lru_cache

WORD_RE = re.compile(r"\w[\w.+#-]*", re.UNICODE)

CYR_TO_LAT = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "kh",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "shch",
    "ы": "y",
    "э": "e",
    "ю": "yu",
    "я": "ya",
    "ь": "",
    "ъ": "",
}

LAT_TO_CYR_MULTI = [
    ("shch", "щ"),
    ("sch", "щ"),
    ("yo", "е"),
    ("yu", "ю"),
    ("ya", "я"),
    ("zh", "ж"),
    ("ch", "ч"),
    ("sh", "ш"),
    ("kh", "х"),
    ("ph", "ф"),
    ("ts", "ц"),
    ("ye", "е"),
]

LAT_TO_CYR_SINGLE = {
    "a": "а",
    "b": "б",
    "c": "к",
    "d": "д",
    "e": "е",
    "f": "ф",
    "g": "г",
    "h": "х",
    "i": "и",
    "j": "дж",
    "k": "к",
    "l": "л",
    "m": "м",
    "n": "н",
    "o": "о",
    "p": "п",
    "q": "к",
    "r": "р",
    "s": "с",
    "t": "т",
    "u": "у",
    "v": "в",
    "w": "в",
    "x": "кс",
    "y": "й",
    "z": "з",
}


RUSSIAN_ENDINGS = [
    "иями",
    "ями",
    "ами",
    "ого",
    "ему",
    "ыми",
    "ими",
    "ого",
    "его",
    "ому",
    "ему",
    "ая",
    "яя",
    "ое",
    "ее",
    "ые",
    "ие",
    "ой",
    "ей",
    "ою",
    "ею",
    "ах",
    "ях",
    "ам",
    "ям",
    "ом",
    "ем",
    "ов",
    "ев",
    "ей",
    "ы",
    "и",
    "а",
    "я",
    "е",
    "у",
    "ю",
]


def normalize_token(value: str) -> str:
    return value.strip().lower().replace("ё", "е").strip("._+#-")


def tokenize(value: str) -> list[str]:
    return [token for token in (normalize_token(match.group(0)) for match in WORD_RE.finditer(value)) if token]  # noqa: E501


def normalize_phrase(value: str) -> str:
    return " ".join(tokenize(value))


def has_cyrillic(value: str) -> bool:
    return bool(re.search(r"[а-яе]", normalize_token(value)))


def has_latin(value: str) -> bool:
    return bool(re.search(r"[a-z]", normalize_token(value)))


def cyrillic_to_latin(value: str) -> str:
    return "".join(CYR_TO_LAT.get(ch, ch) for ch in normalize_token(value))


def latin_to_cyrillic(value: str) -> str:
    source = normalize_token(value)
    result = []
    i = 0
    while i < len(source):
        matched = False
        for latin, cyrillic in LAT_TO_CYR_MULTI:
            if source.startswith(latin, i):
                result.append(cyrillic)
                i += len(latin)
                matched = True
                break
        if matched:
            continue
        result.append(LAT_TO_CYR_SINGLE.get(source[i], source[i]))
        i += 1
    return "".join(result)


def collapse_repeats(value: str) -> str:
    return re.sub(r"([0-9A-Za-zА-Яа-яЁё])\1+", r"\1", normalize_token(value))


def stem_variants(value: str) -> set[str]:
    token = normalize_token(value)
    variants = {token}
    if not has_cyrillic(token):
        return variants
    for ending in RUSSIAN_ENDINGS:
        if token.endswith(ending) and len(token) - len(ending) >= 5:
            variants.add(token[: -len(ending)])
            break
    return variants


@lru_cache(maxsize=4096)
def expand_token(token: str) -> tuple[str, ...]:
    normalized = normalize_token(token)
    if not normalized:
        return ()
    variants = {normalized}
    for variant in list(variants):
        variants.add(collapse_repeats(variant))
        variants.update(stem_variants(variant))
    for variant in list(variants):
        variants.update(stem_variants(collapse_repeats(variant)))
    for variant in list(variants):
        if has_cyrillic(variant):
            variants.add(cyrillic_to_latin(variant))
        if has_latin(variant):
            variants.add(latin_to_cyrillic(variant))
    cleaned = {normalize_phrase(variant) for variant in variants}
    cleaned = {variant for variant in cleaned if variant}
    return tuple(sorted(cleaned, key=lambda item: (item != normalized, len(item), item)))


def query_variants(query: str, max_variants: int = 12) -> list[str]:
    raw = query.strip()
    if not raw:
        return [""]

    variants: list[str] = []

    def add(value: str) -> None:
        normalized = normalize_phrase(value)
        if normalized and normalized not in variants:
            variants.append(normalized)

    add(raw)
    tokens = tokenize(raw)
    if len(tokens) == 1:
        for variant in expand_token(tokens[0]):
            add(variant)
    elif tokens:
        all_latin = []
        all_cyrillic = []
        for token in tokens:
            token_variants = expand_token(token)
            for variant in token_variants[:4]:
                replacement = [variant if current == token else current for current in tokens]
                add(" ".join(replacement))
            all_latin.append(cyrillic_to_latin(token) if has_cyrillic(token) else token)
            all_cyrillic.append(latin_to_cyrillic(token) if has_latin(token) else token)
        add(" ".join(all_latin))
        add(" ".join(all_cyrillic))

    return variants[:max_variants]


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def allowed_distance(a: str, b: str) -> int:
    size = max(len(a), len(b))
    if size < 5:
        return 0
    if size < 7:
        return 1
    return 2


def token_match_score(query_variant: str, text_token: str) -> int:
    query_variant = normalize_token(query_variant)
    text_token = normalize_token(text_token)
    if not query_variant or not text_token:
        return 0
    if query_variant == text_token:
        return 100
    if min(len(query_variant), len(text_token)) >= 5 and (
        query_variant.startswith(text_token) or text_token.startswith(query_variant)
    ):
        return 92
    distance = levenshtein(query_variant, text_token)
    if distance <= allowed_distance(query_variant, text_token):
        return 85 - distance
    return 0


def fuzzy_match_query(query: str, text: str) -> tuple[bool, int, list[str]]:
    query_tokens = tokenize(query)
    if not query_tokens:
        return True, 0, []
    text_tokens = tokenize(text)
    if not text_tokens:
        return False, 0, []

    total_score = 0
    matched_tokens: list[str] = []
    for query_token in query_tokens:
        variants = expand_token(query_token)
        best_score = 0
        best_token = ""
        for text_token in text_tokens:
            text_variants = expand_token(text_token)
            for variant in variants:
                for text_variant in text_variants:
                    score = token_match_score(variant, text_variant)
                    if score > best_score:
                        best_score = score
                        best_token = text_token
        if best_score <= 0:
            return False, 0, []
        total_score += best_score
        matched_tokens.append(best_token)

    return True, total_score, matched_tokens


def highlight_fuzzy(text: str, matched_tokens: list[str]) -> str:
    normalized_matches = {normalize_token(token) for token in matched_tokens if token}
    if not normalized_matches:
        return html.escape(text)

    parts = []
    offset = 0
    for match in WORD_RE.finditer(text):
        parts.append(html.escape(text[offset : match.start()]))
        value = match.group(0)
        escaped = html.escape(value)
        if normalize_token(value) in normalized_matches:
            parts.append(f"<mark>{escaped}</mark>")
        else:
            parts.append(escaped)
        offset = match.end()
    parts.append(html.escape(text[offset:]))
    return "".join(parts)
