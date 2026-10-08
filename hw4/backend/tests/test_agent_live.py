"""LIVE tests: the real model (gpt-5.6-luna via Portkey) must pick the right tool and never invent values.

Skipped by default (they cost API calls). Run with:
    .\\.venv\\Scripts\\python.exe -m pytest -m live -v

Each case checks:
  1. the expected tool was called (with the right product id / size),
  2. every number in the reply (prices, quantities) appears in what the tools returned,
  3. case-specific wording (sold out, not offered, not found, no discount info).
"""

import asyncio
import json
import re

import pytest
from pydantic_ai.messages import ToolCallPart, ToolReturnPart

from agent import run_agent
from app.config import settings

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not settings.portkey_api_key, reason="PORTKEY_API_KEY not configured"),
]

CASES = [
    # id, question, expected tool, expected args subset, phrases (any) the reply must contain
    ("description", "What does the Davenport College Crewneck look like?",
     "get_product_description", {"product_id": "davenport-college-crewneck"}, ["gray", "grey", "crest", "shield"]),
    ("price", "How much is the Yale Dad Hoodie?",
     "get_product_price", {"product_id": "yale-dad-hoodie"}, ["$68.00", "$68"]),
    ("total_stock", "How many Basic Hoodie Big Yale hoodies do you have in stock in total, across all sizes?",
     "get_total_inventory", {"product_id": "basic-hoodie-big-yale"}, ["60"]),
    ("size_stock", "Do you have the Davenport College Crewneck in a medium? How many?",
     "get_size_inventory", {"product_id": "davenport-college-crewneck"}, ["5"]),
    ("out_of_stock", "Can I get the Davenport College Crewneck in size small?",
     "get_size_inventory", {"product_id": "davenport-college-crewneck"}, ["sold out", "out of stock", "not in stock", "none"]),
    ("missing_size", "Is the Yale Dad Hoodie available in XXXL?",
     "get_size_inventory", {"product_id": "yale-dad-hoodie"}, ["not offered", "doesn't come", "does not come", "isn't offered", "not available", "only"]),
    ("category_match", "What hoodies do you have?",
     "search_catalogue", {"category": "hoodie"}, ["27"]),
    ("category_no_match", "What swimsuits do you have?",
     "search_catalogue", {}, ["don't", "do not", "no swimsuits", "couldn't", "not carry", "doesn't", "didn't find", "no matches"]),
    ("unknown_product", "How many Yale Unicorn Onesies do you have in stock?",
     "search_products", {}, ["couldn't find", "could not find", "don't have", "do not have", "don't carry", "no ", "not find"]),
]


def numbers(text: str) -> set[str]:
    """Numbers as they'd be quoted: '68', '68.00' -> {'68'}; ignores sizes like 'XL'."""
    out = set()
    for n in re.findall(r"\d+(?:\.\d+)?", text):
        out.add(n.rstrip("0").rstrip(".") if "." in n else n)
    return out


def trace(result):
    calls, returns = [], []
    for m in result.all_messages():
        for p in m.parts:
            if isinstance(p, ToolCallPart) and p.tool_name != "final_result":
                calls.append((p.tool_name, p.args_as_dict()))
            elif isinstance(p, ToolReturnPart) and p.tool_name != "final_result":
                c = p.content
                returns.append(c.model_dump_json() if hasattr(c, "model_dump_json") else json.dumps(c))
    return calls, returns


@pytest.mark.parametrize("case_id,question,tool,args,phrases", CASES, ids=[c[0] for c in CASES])
def test_agent_uses_correct_tool_and_real_values(case_id, question, tool, args, phrases):
    result, deps = asyncio.run(run_agent(question, []))
    reply = result.output.reply.replace("’", "'").replace("‘", "'")  # curly -> straight apostrophes
    calls, returns = trace(result)
    print(f"\n[{case_id}] Q: {question}\n  tools: {calls}\n  A: {reply}")

    # 1. correct tool, correct arguments
    matching = [a for name, a in calls if name == tool and all(a.get(k) == v for k, v in args.items())]
    assert matching, f"expected {tool}{args}, got {calls}"

    # 2. no invented numbers: every number in the reply came from a tool result
    tool_numbers = numbers(" ".join(returns))
    invented = numbers(reply) - tool_numbers
    assert not invented, f"reply has numbers no tool returned: {invented}"

    # 3. case-specific wording
    assert any(p.lower() in reply.lower() for p in phrases), f"reply missing any of {phrases}"

    if case_id.startswith("category"):
        from agent import build_response
        cards = build_response(result.output, deps)
        if case_id == "category_match":
            assert cards.total_matches == 27 and len(cards.matches) == 12
            assert cards.view_all_url == "/products?type=hoodie"
        else:
            assert cards.matches == [] and cards.total_matches == 0
    if case_id == "unknown_product":
        assert result.output.product_ids == [] or all(i in deps.seen_ids for i in result.output.product_ids)
        assert not any(n.isdigit() and int(n) > 0 for n in numbers(reply) - tool_numbers)
    if case_id == "missing_size":
        size_calls = [a for name, a in calls if name == "get_size_inventory"]
        assert any("XXXL" in str(a.get("size", "")).upper() for a in size_calls)
    if case_id in ("size_stock", "out_of_stock"):
        size_calls = [a for name, a in calls if name == "get_size_inventory"]
        wanted = "M" if case_id == "size_stock" else "S"
        assert any(str(a.get("size", "")).strip().upper() in {wanted, {"M": "MEDIUM", "S": "SMALL"}[wanted]} for a in size_calls)


# ---------- Context: signed-in name/email and current product page ----------

def test_agent_uses_name_and_email_context():
    shopper = {"name": "Test User", "email": "test@campuscustoms.yale.edu"}
    result, _ = asyncio.run(run_agent("What name and email do you have for me?", [], shopper=shopper))
    reply = result.output.reply
    print(f"\n[name_email] A: {reply}")
    assert "Test" in reply and "test@campuscustoms.yale.edu" in reply

    guest, _ = asyncio.run(run_agent("What's my name?", []))
    print(f"[guest_name] A: {guest.output.reply}")
    assert "Test User" not in guest.output.reply and "@" not in guest.output.reply


def test_agent_resolves_this_to_the_page_product():
    result, deps = asyncio.run(run_agent("Do you have this in pink?", [], page_product_id="davenport-college-crewneck"))
    reply = result.output.reply.replace("’", "'")
    calls, returns = trace(result)
    print(f"\n[page_context] tools: {calls}\n  A: {reply}")
    assert any(a.get("product_id") == "davenport-college-crewneck" for _, a in calls)  # looked up the page product
    assert "davenport" in reply.lower() and "pink" in reply.lower()
    assert not numbers(reply) - numbers(" ".join(returns))
