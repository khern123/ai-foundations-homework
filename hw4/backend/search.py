"""Normalized, deduplicated catalogue search (shared by the chat tools and GET /api/products/search).

Normalization makes different spellings meet: case, accents, punctuation, plurals, possessives and
synonyms ("Tees", "t-shirts", "T Shirt" -> tshirt; "1/4 zip", "1 4 Zip", "quarter zips" -> quarterzip;
"grey" -> gray; "crew neck"/"Creqneck" -> crewneck). Products and queries go through the same steps.

Deduplication: repeated query words count once, each product appears at most once, and results from
several searches can be merged by id (merge_unique).
"""

import re
import unicodedata
from functools import lru_cache

STOPWORDS = {
    "a", "an", "and", "any", "are", "can", "do", "for", "get", "have", "i", "in", "is", "it", "me", "my",
    "of", "on", "or", "please", "show", "some", "something", "the", "to", "want", "what", "with", "you",
    "your", "yale", "looking", "find", "got", "sell", "carry", "stock", "all", "which", "there",
}
# Multi-word phrases first (applied to normalized text), then single-word synonyms.
PHRASES = [
    (r"\b1\s*/\s*4\s*zips?\b", "quarterzip"),
    (r"\b1 4 zips?\b", "quarterzip"),
    (r"\bquarter[\s-]*zips?\b", "quarterzip"),
    (r"\b(qtr|1/4)[\s-]*zips?\b", "quarterzip"),
    (r"\bt[\s-]*shirts?\b", "tshirt"),
    (r"\bcrew[\s-]*necks?\b", "crewneck"),
    (r"\blong[\s-]*sleeves?\b", "longsleeve"),
    (r"\bl s\b", "longsleeve"),
    (r"\bfull[\s-]*zips?\b", "fullzip"),
    (r"\bhalf[\s-]*zips?\b", "quarterzip"),
]
SYNONYMS = {
    "tee": "tshirt", "tees": "tshirt", "tshirts": "tshirt", "shirt": "tshirt", "shirts": "tshirt",
    "hoody": "hoodie", "hoodies": "hoodie", "hooded": "hoodie", "hood": "hoodie",
    "creqneck": "crewneck", "crewnecks": "crewneck", "crew": "crewneck",
    "grey": "gray", "jackets": "jacket", "coat": "jacket", "coats": "jacket",
    "sweatshirts": "sweatshirt", "sweater": "sweatshirt", "sweaters": "sweatshirt",
    "mom": "mom", "mother": "mom", "mum": "mom", "father": "dad", "daddy": "dad",
    "grandmother": "grandma", "granny": "grandma", "grandfather": "grandpa",
}
# Words that name one of the six shop categories.
CATEGORY_WORDS = {
    "hoodie": "hoodie", "tshirt": "t-shirt", "crewneck": "crewneck", "quarterzip": "quarter-zip",
    "jacket": "jacket", "longsleeve": "long-sleeve",
}


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    text = text.replace("&", " and ").replace("'s", "").replace("’s", "")
    text = re.sub(r"[^a-z0-9/]+", " ", text)
    for pattern, repl in PHRASES:
        text = re.sub(pattern, repl, text)
    text = text.replace("/", " ")
    return re.sub(r"\s+", " ", text).strip()


def singular(word: str) -> str:
    if len(word) > 3 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def tokens(text: str, drop_stopwords: bool = True) -> list[str]:
    """Normalized, synonym-mapped, singular tokens with duplicates removed (order kept)."""
    out: list[str] = []
    for w in normalize_text(text).split():
        w = SYNONYMS.get(w, w)
        w = SYNONYMS.get(singular(w), singular(w))
        if drop_stopwords and w in STOPWORDS:
            continue
        if w not in out:
            out.append(w)
    return out


def split_category(terms: list[str]) -> tuple[str | None, list[str]]:
    """'hoodie' in the query -> category filter instead of a keyword."""
    cats = [CATEGORY_WORDS[t] for t in terms if t in CATEGORY_WORDS]
    if len(set(cats)) == 1:
        return cats[0], [t for t in terms if t not in CATEGORY_WORDS]
    return None, terms


@lru_cache(maxsize=512)
def _product_fields(name: str, garment: str, colors: tuple, tags: tuple, desc: str, category: str):
    name_t = set(tokens(name, drop_stopwords=False))
    tag_t = set(tokens(" ".join([garment, category.replace("-", " "), *colors, *tags]), drop_stopwords=False))
    desc_t = set(tokens(desc, drop_stopwords=False))
    return name_t, tag_t, desc_t


def _fields(p: dict):
    return _product_fields(p["name"], p["garment_type"], tuple(p["colors"]), tuple(p["tags"]),
                           p["description"], p["product_type"])


def _hit(term: str, words: set[str]) -> bool:
    return term in words or (len(term) >= 4 and any(w.startswith(term) for w in words))


def score(p: dict, terms: list[str]) -> tuple[int, int]:
    """(number of terms matched, weighted score). Name hits count most."""
    name_t, tag_t, desc_t = _fields(p)
    matched = weighted = 0
    for t in terms:
        w = 3 * _hit(t, name_t) + 2 * _hit(t, tag_t) + _hit(t, desc_t)
        matched += w > 0
        weighted += w
    return matched, weighted


def search(
    products: list[dict],
    query: str = "",
    category: str | None = None,
    max_price_cents: int | None = None,
    relax: bool = True,
) -> dict:
    """Returns {terms, category, relaxed, results}. All terms must match; if none do and `relax`,
    products matching the most terms are returned instead (relaxed=True). Each product appears once."""
    terms = tokens(query)
    if category is None:
        category, terms = split_category(terms)
    else:
        terms = [t for t in terms if CATEGORY_WORDS.get(t) != category]  # "hoodie" + category=hoodie: no double filter

    pool = [p for p in products if (category is None or p["product_type"] == category)
            and (max_price_cents is None or p["price_cents"] <= max_price_cents)]
    pool = list({p["id"]: p for p in pool}.values())  # one entry per product id

    relaxed = False
    if terms:
        scored = [(score(p, terms), p) for p in pool]
        full = [(s, p) for s, p in scored if s[0] == len(terms)]
        if not full and relax and len(terms) > 1:
            best = max((s[0] for s, _ in scored), default=0)
            full = [(s, p) for s, p in scored if best and s[0] == best]
            relaxed = bool(full)
        results = [p for _, p in sorted(full, key=lambda sp: (-sp[0][1], sp[1]["name"]))]
    else:
        results = sorted(pool, key=lambda p: p["name"]) if category or max_price_cents is not None else []
    return {"terms": terms, "category": category, "relaxed": relaxed, "results": results}


def merge_unique(*result_lists: list[dict]) -> list[dict]:
    """Concatenate result lists, keeping the first occurrence of each product id."""
    seen: dict[str, dict] = {}
    for results in result_lists:
        for p in results:
            seen.setdefault(p["id"], p)
    return list(seen.values())
