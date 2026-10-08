"""Structured catalogue search: tool accuracy (vs direct SQL) and the /api/chat matches contract."""

import sqlite3
from contextlib import closing

import pytest
from fastapi.testclient import TestClient
from pydantic_ai import RunContext
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

import agent as agent_module
from app import db
from main import app
from models import MAX_MATCHES, CatalogueSearch
from tools import ChatDeps, search_catalogue, short_description

client = TestClient(app)


def ctx() -> RunContext[ChatDeps]:
    return RunContext(deps=ChatDeps(), model=None, usage=None, prompt=None)  # type: ignore[arg-type]


def catalogue_rows() -> dict[str, tuple]:
    """Independent read: product_id -> (name, garment_type, description, image_file_path, price)."""
    with closing(sqlite3.connect(f"{db.DB_PATH.as_uri()}?mode=ro", uri=True)) as conn:
        rows = conn.execute(
            "SELECT product_id, name, garment_type, description, image_file_path, price FROM catalogue").fetchall()
    return {r[0]: r[1:] for r in rows}


ROWS = catalogue_rows()


def assert_match_is_accurate(m) -> None:
    name, _, desc, image_path, price = ROWS[m.id]
    assert m.name == name
    assert m.image_path == image_path
    assert m.image_url == f"/images/{image_path}"
    assert m.price_cents == round(price * 100) and m.price_display == f"${price:.2f}"
    assert desc.startswith(m.short_description.rstrip("…")) and len(m.short_description) <= 140


# ---------- Tool: matching category questions ----------

@pytest.mark.parametrize("category,expected_total", [
    ("hoodie", 27), ("crewneck", 29), ("t-shirt", 25), ("quarter-zip", 11), ("jacket", 8), ("long-sleeve", 2),
])
def test_category_totals_and_accuracy(category, expected_total):
    r = search_catalogue(ctx(), category=category)
    assert isinstance(r, CatalogueSearch)
    assert r.total_matches == expected_total
    assert len(r.matches) == min(expected_total, MAX_MATCHES)
    assert [m.name for m in r.matches] == sorted(m.name for m in r.matches)  # stable, alphabetical
    for m in r.matches:
        assert_match_is_accurate(m)
        assert db.category(ROWS[m.id][1]) == category


def test_hoodie_matches_are_all_hoodies():
    every = [pid for pid, row in ROWS.items() if "hood" in row[1].lower()]
    assert len(every) == 27
    r = search_catalogue(ctx(), category="hoodie")
    assert {m.id for m in r.matches} <= set(every)


def test_keywords_must_all_match():
    r = search_catalogue(ctx(), category="crewneck", keywords="navy")
    assert r.total_matches > 0
    for m in r.matches:
        p = db.get_product(m.id)
        text = " ".join([p["name"], p["description"], *p["colors"], *p["tags"]]).lower()
        assert "navy" in text and p["product_type"] == "crewneck"

    davenport = search_catalogue(ctx(), keywords="davenport crewneck")
    assert [m.id for m in davenport.matches] == ["davenport-college-crewneck"]


def test_price_filter():
    r = search_catalogue(ctx(), category="t-shirt", max_price_dollars=32)
    assert r.total_matches > 0 and all(m.price_cents <= 3200 for m in r.matches)
    assert search_catalogue(ctx(), category="jacket", max_price_dollars=10).total_matches == 0


def test_matches_become_seen_ids_and_are_recorded():
    c = ctx()
    r = search_catalogue(c, category="jacket")
    assert c.deps.seen_ids == {m.id for m in r.matches}
    assert c.deps.searches == [r]


# ---------- Tool: non-matching / empty ----------

@pytest.mark.parametrize("kwargs", [
    {"keywords": "swimsuit"},
    {"keywords": "unicorn onesie"},
    {"category": "hoodie", "keywords": "pink sparkle"},
    {"category": "jacket", "keywords": "davenport"},
])
def test_non_matching_searches_return_empty(kwargs):
    r = search_catalogue(ctx(), **kwargs)
    assert r.total_matches == 0 and r.matches == []
    assert "No products match" in r.message


def test_search_needs_category_or_keywords():
    r = search_catalogue(ctx())
    assert r.total_matches == 0 and r.matches == [] and "category or keywords" in r.message


def test_short_description():
    assert short_description("Navy hoodie. With pocket.") == "Navy hoodie."
    assert len(short_description("x" * 300)) == 140 and short_description("x" * 300).endswith("…")


def test_missing_image_file_gives_null_url_in_match(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "IMAGES_DIR", tmp_path)
    m = search_catalogue(ctx(), category="jacket").matches[0]
    assert m.image_path and m.image_url is None


# ---------- /api/chat returns reply + matches ----------

def scripted(tool_calls, reply, product_ids=()):
    def fn(messages, info: AgentInfo) -> ModelResponse:
        step = sum(1 for m in messages for p in m.parts if isinstance(p, ToolReturnPart))
        if step < len(tool_calls):
            name, args = tool_calls[step]
            return ModelResponse(parts=[ToolCallPart(name, args)])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,
                                                 {"reply": reply, "product_ids": list(product_ids)})])
    return FunctionModel(fn)


@pytest.fixture
def use_model():
    contexts = []

    def _use(model):
        c = agent_module.build_agent().override(model=model)
        c.__enter__()
        contexts.append(c)

    yield _use
    for c in contexts:
        c.__exit__(None, None, None)


def ask(message="What hoodies do you have?"):
    r = client.post("/api/chat", json={"message": message})
    assert r.status_code == 200
    return r.json()


def test_category_question_returns_reply_and_matches(use_model):
    use_model(scripted([("search_catalogue", {"category": "hoodie"})], "We have 27 hoodies, like the Yale Dad Hoodie."))
    body = ask()
    assert body["reply"] == "We have 27 hoodies, like the Yale Dad Hoodie."
    assert body["total_matches"] == 27
    assert len(body["matches"]) == MAX_MATCHES
    assert body["view_all_url"] == "/products?type=hoodie"
    expected = search_catalogue(ctx(), category="hoodie").matches
    assert body["matches"] == [m.model_dump() for m in expected]  # exactly the database result
    for m in body["matches"]:
        assert set(m) == {"id", "name", "image_path", "image_url", "price_cents", "price_display", "short_description"}
        assert client.get(f"/api/products/{m['id']}").json()["name"] == m["name"]  # card id -> right product
        assert client.get(m["image_url"]).status_code == 200


def test_small_category_has_no_view_all(use_model):
    use_model(scripted([("search_catalogue", {"category": "long-sleeve"})], "We have 2 long-sleeves."))
    body = ask("Any long sleeve shirts?")
    assert body["total_matches"] == 2 and len(body["matches"]) == 2 and body["view_all_url"] is None


def test_filtered_search_has_no_category_link(use_model):
    use_model(scripted([("search_catalogue", {"category": "crewneck", "keywords": "navy"})], "Here are navy crewnecks."))
    body = ask("Navy crewnecks?")
    assert body["total_matches"] > 0 and body["view_all_url"] is None  # the type link would drop the "navy" filter
    expected = search_catalogue(ctx(), category="crewneck", keywords="navy")
    assert [m["id"] for m in body["matches"]] == [m.id for m in expected.matches]


def test_non_matching_category_question_returns_no_cards(use_model):
    use_model(scripted([("search_catalogue", {"keywords": "swimsuit"})], "Sorry, we don't carry swimsuits."))
    body = ask("What swimsuits do you have?")
    assert body == {"reply": "Sorry, we don't carry swimsuits.", "matches": [], "total_matches": 0, "view_all_url": None}


def test_last_search_wins(use_model):
    use_model(scripted([("search_catalogue", {"keywords": "swimsuit"}), ("search_catalogue", {"category": "jacket"})],
                       "No swimsuits, but here are our jackets."))
    body = ask("Swimsuits or jackets?")
    assert body["total_matches"] == 8 and all(db.category(ROWS[m["id"]][1]) == "jacket" for m in body["matches"])


def test_model_ids_are_appended_only_if_seen(use_model):
    use_model(scripted([("search_catalogue", {"category": "long-sleeve"}), ("search_products", {"query": "dad hoodie"})],
                       "Also check the Dad Hoodie.", ["yale-dad-hoodie", "yale-unicorn-onesie"]))
    ids = [m["id"] for m in ask("long sleeves and dad hoodie")["matches"]]
    assert ids[-1] == "yale-dad-hoodie" and "yale-unicorn-onesie" not in ids and len(ids) == 3


def test_ordinary_reply_has_no_matches(use_model):
    use_model(scripted([], "Hi! Ask me about hoodies, tees or crewnecks."))
    assert ask("hello") == {"reply": "Hi! Ask me about hoodies, tees or crewnecks.", "matches": [],
                            "total_matches": 0, "view_all_url": None}
