"""Backend improvements: (3) normalized, deduplicated search and (4) concise, safe error handling."""

import json

import pytest
from fastapi.testclient import TestClient
from pydantic_ai import RunContext

import search
from app import db
from main import app
from tools import ChatDeps, search_catalogue, search_products

client = TestClient(app)
PRODUCTS = db.list_products()


def ctx():
    return RunContext(deps=ChatDeps(), model=None, usage=None, prompt=None)  # type: ignore[arg-type]


def ids(results):
    return [p["id"] for p in results]


# ===================== Improvement 3: normalized, deduplicated search =====================

@pytest.mark.parametrize("query,category,total", [
    ("hoodies", "hoodie", 27), ("Hoodies!!", "hoodie", 27), ("HOODY", "hoodie", 27),
    ("tees", "t-shirt", 25), ("T-Shirts", "t-shirt", 25), ("t shirt", "t-shirt", 25),
    ("1/4 zip", "quarter-zip", 11), ("quarter zips", "quarter-zip", 11), ("qtr-zip", "quarter-zip", 11),
    ("crew neck", "crewneck", 29), ("crewnecks", "crewneck", 29),
    ("long sleeve", "long-sleeve", 2), ("jackets", "jacket", 8),
])
def test_spelling_variants_reach_the_same_category(query, category, total):
    r = search.search(PRODUCTS, query)
    assert r["category"] == category and len(r["results"]) == total
    assert all(p["product_type"] == category for p in r["results"])


def test_grey_matches_gray():
    grey = search.search(PRODUCTS, "grey crewneck")
    gray = search.search(PRODUCTS, "gray crewneck")
    assert ids(grey["results"]) == ids(gray["results"]) and grey["results"]


def test_catalogue_typos_and_odd_names_are_found():
    # "Yale Sports Creqneck Field Hockey" (typo in the data) and "Benjamin Franklin 1 4 Zip"
    assert ids(search.search(PRODUCTS, "field hockey crewneck")["results"]) == ["yale-sports-creqneck-field-hockey"]
    assert "benjamin-franklin-1-4-zip" in ids(search.search(PRODUCTS, "benjamin franklin quarter zip")["results"])


def test_normalization_steps():
    assert search.tokens("Café") == ["cafe"]
    assert search.tokens("Dad's hoodies!") == ["dad", "hoodie"]
    assert search.tokens("Show me some T-Shirts for my Mum") == ["tshirt", "mom"]


def test_duplicate_words_count_once():
    assert search.tokens("hoodie hoodies HOODIE Hoody") == ["hoodie"]
    a = search.search(PRODUCTS, "navy navy NAVY hoodie")
    b = search.search(PRODUCTS, "navy hoodie")
    assert a["terms"] == ["navy"] and ids(a["results"]) == ids(b["results"])


def test_each_product_appears_once():
    for q in ["hoodie", "yale", "navy gray white", "dad mom grandma", "hockey"]:
        r = search.search(PRODUCTS, q)["results"]
        assert len(ids(r)) == len(set(ids(r))), q


def test_merge_unique_dedupes_by_id():
    a = search.search(PRODUCTS, "hockey")["results"]
    b = search.search(PRODUCTS, "hoodie")["results"]
    merged = search.merge_unique(a, b)
    assert len(ids(merged)) == len(set(ids(a)) | set(ids(b))) and ids(merged)[: len(a)] == ids(a)


def test_category_word_is_not_double_counted():
    plain = search_catalogue(ctx(), category="hoodie")
    doubled = search_catalogue(ctx(), category="hoodie", keywords="hoodies")
    assert doubled.total_matches == plain.total_matches == 27 and doubled.keywords == []


def test_keyword_only_category_is_inferred_by_the_tool():
    r = search_catalogue(ctx(), keywords="hoodies")
    assert r.category == "hoodie" and r.total_matches == 27


def test_relaxed_fallback_for_extra_words():
    r = search_catalogue(ctx(), keywords="gift for my dad")
    assert r.relaxed and r.total_matches >= 1 and all("dad" in m.id for m in r.matches)
    assert "closest matches" in r.message
    assert search_catalogue(ctx(), keywords="swimsuit").total_matches == 0  # single unknown word: no fallback


def test_lookup_tool_uses_same_engine():
    found = search_products(ctx(), "Davenport College Crew Neck")["results"]
    assert found[0]["id"] == "davenport-college-crewneck"


# Endpoint used by the storefront search box
def test_search_endpoint():
    r = client.get("/api/products/search", params={"q": "Hoodies"}).json()
    assert r["category"] == "hoodie" and r["total"] == 27 and len(r["results"]) == 27
    assert r["terms"] == [] and r["relaxed"] is False
    tees = client.get("/api/products/search", params={"q": "tees", "max_price": 32}).json()
    assert tees["total"] > 0 and all(p["price_cents"] <= 3200 for p in tees["results"])
    none = client.get("/api/products/search", params={"q": "swimsuit"}).json()
    assert none["total"] == 0 and none["results"] == []


def test_search_endpoint_matches_chat_tool():
    api = client.get("/api/products/search", params={"q": "navy crewneck"}).json()
    tool = search_catalogue(ctx(), keywords="navy crewneck")
    assert api["total"] == tool.total_matches and ids(api["results"])[:12] == [m.id for m in tool.matches]


# ===================== Improvement 4: concise, safe errors =====================

def assert_error(r, status, code, detail=None):
    body = r.json()
    assert r.status_code == status
    assert set(body) == {"detail", "code", "request_id"}, body
    assert body["code"] == code
    assert len(body["request_id"]) == 8 and r.headers["x-request-id"] == body["request_id"]
    if detail is not None:
        assert body["detail"] == detail
    return body


def test_unknown_route_and_method():
    assert_error(client.get("/api/nope"), 404, "not_found", "Not found.")
    assert_error(client.delete("/api/products"), 405, "method_not_allowed", "That action isn't allowed here.")


def test_unknown_product_has_specific_code():
    assert_error(client.get("/api/products/yale-unicorn-onesie"), 404, "product_not_found", "We couldn't find that product.")


def test_successful_responses_also_carry_request_id():
    r = client.get("/api/health")
    assert r.status_code == 200 and len(r.headers["x-request-id"]) == 8


@pytest.mark.parametrize("body,field,msg", [
    ({"first_name": "A", "last_name": "B", "email": "nope", "password": "longenough1", "confirm_password": "longenough1"},
     "email", "Enter a valid email address."),
    ({"first_name": "A", "last_name": "B", "email": "a@yale.edu", "password": "short", "confirm_password": "short"},
     "password", "Use at least 8 characters."),
    ({"first_name": "  ", "last_name": "B", "email": "a@yale.edu", "password": "longenough1", "confirm_password": "longenough1"},
     "first_name", "This field can't be blank."),
    ({"last_name": "B", "email": "a@yale.edu", "password": "longenough1", "confirm_password": "longenough1"},
     "first_name", "This field is required."),
])
def test_validation_messages_are_plain_english(body, field, msg):
    detail = assert_error(client.post("/api/auth/register", json=body), 422, "validation_error")["detail"]
    assert {"field": field, "msg": msg} in detail
    assert "pydantic" not in json.dumps(detail).lower() and "input" not in json.dumps(detail)


def test_one_message_per_field():
    detail = client.post("/api/chat", json={"message": "hi", "history": [{"role": "x", "content": 5}] * 9}).json()["detail"]
    fields = [e["field"] for e in detail]
    assert len(fields) == len(set(fields))


def test_bad_query_params():
    detail = assert_error(client.get("/api/products/search", params={"q": "x" * 101}), 422, "validation_error")["detail"]
    assert detail == [{"field": "q", "msg": "Use at most 100 characters."}]
    detail = client.get("/api/products/search", params={"type": "socks"}).json()["detail"]
    assert detail[0]["field"] == "type" and detail[0]["msg"].startswith("Must be one of")


def test_invalid_json():
    r = client.post("/api/chat", content="{not json", headers={"Content-Type": "application/json"})
    detail = assert_error(r, 422, "validation_error")["detail"]
    assert [e["msg"] for e in detail] == ["The request body isn't valid JSON."]


def test_oversized_body_is_refused():
    r = client.post("/api/chat", json={"message": "x" * 20_000})
    assert_error(r, 413, "too_large", "That request is too large.")


def test_unexpected_crash_is_hidden(monkeypatch):
    def boom():
        raise RuntimeError(r"sqlite failed at C:\secret\campus_customs.db: SELECT * FROM users")

    monkeypatch.setattr(db, "list_products", boom)
    c = TestClient(app, raise_server_exceptions=False)
    r = c.get("/api/products", headers={"Origin": "http://localhost:5173"})
    body = assert_error(r, 500, "internal_error", "Something went wrong on our side. Please try again.")
    assert "secret" not in r.text and "sqlite" not in r.text.lower() and "Traceback" not in r.text
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"  # browser can read the message
    assert body["request_id"]


def test_chat_errors_have_specific_codes(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "portkey_api_key", None)
    assert_error(client.post("/api/chat", json={"message": "hi"}), 503, "assistant_unavailable")
