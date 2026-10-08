"""Category search in the chat: dynamic product cards, images, empty results, ordinary replies, routing.

Stubbed tests build /api/chat responses from the REAL backend's product data, so card -> detail-page
routing is checked against real pages. test_live_category_search makes ONE real model call.
"""

import json
import sys
from pathlib import Path

import pytest
from playwright.sync_api import Page, Route, expect

from conftest import API_URL, WEB_URL

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import settings  # noqa: E402


def open_chat(page: Page):
    page.goto(WEB_URL)
    page.get_by_role("button", name="Open chat").click()
    return page.get_by_role("dialog", name="Campus Customs chat")


def ask(panel, text: str) -> None:
    panel.get_by_role("textbox", name="Chat message").fill(text)
    panel.get_by_role("button", name="Send").click()


def stub(page: Page, body: dict) -> None:
    page.route("**/api/chat", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(body)))


def real_matches(page: Page, product_type: str, n: int) -> tuple[list[dict], int]:
    """Matches in the API's shape, built from the real /api/products data."""
    products = [p for p in page.request.get(f"{API_URL}/api/products").json() if p["product_type"] == product_type]
    matches = [{
        "id": p["id"], "name": p["name"], "image_path": p["image_path"], "image_url": p["image_url"],
        "price_cents": p["price_cents"], "price_display": f"${p['price_cents'] / 100:.2f}",
        "short_description": p["description"].split(". ")[0],
    } for p in products[:n]]
    return matches, len(products)


def bot_cards(panel):
    return panel.get_by_test_id("chat-bot").last.get_by_test_id("chat-product")


# ---------- Dynamic cards + detail-page routing ----------

def test_category_cards_render_and_each_opens_its_detail_page(page: Page):
    matches, total = real_matches(page, "hoodie", 12)
    stub(page, {"reply": f"We have {total} hoodies.", "matches": matches, "total_matches": total,
                "view_all_url": "/products?type=hoodie"})
    panel = open_chat(page)
    ask(panel, "What hoodies do you have?")

    cards = bot_cards(panel)
    expect(cards).to_have_count(12)
    for i, m in enumerate(matches):
        card = cards.nth(i)
        expect(card).to_have_attribute("href", f"/products/{m['id']}")
        expect(card.locator("h3")).to_have_text(m["name"])
        expect(card.locator(".price")).to_have_text(m["price_display"])
        expect(card.locator(".product-card-desc")).to_have_text(m["short_description"])
        expect(card.locator("img")).to_have_attribute("src", API_URL + m["image_url"])

    # Every card routes to the matching detail page
    for i in (0, 5, 11):
        page.goto(WEB_URL)
        page.get_by_role("button", name="Open chat").click()
        panel = page.get_by_role("dialog", name="Campus Customs chat")
        ask(panel, "What hoodies do you have?")
        bot_cards(panel).nth(i).click()
        expect(page).to_have_url(f"{WEB_URL}/products/{matches[i]['id']}")
        expect(page.get_by_role("heading", level=1)).to_have_text(matches[i]["name"])
        expect(page.locator(".detail-price")).to_have_text(matches[i]["price_display"])


def test_reply_text_is_visible_above_many_cards(page: Page):
    matches, total = real_matches(page, "hoodie", 12)
    stub(page, {"reply": "We have 27 hoodies.", "matches": matches, "total_matches": total,
                "view_all_url": "/products?type=hoodie"})
    panel = open_chat(page)
    ask(panel, "What hoodies do you have?")
    expect(bot_cards(panel)).to_have_count(12)
    text = panel.get_by_test_id("chat-bot").last.locator("p").first
    expect(text).to_have_text("We have 27 hoodies.")
    expect(text).to_be_in_viewport()  # not scrolled away above the cards


def test_view_all_link_and_count(page: Page):
    matches, total = real_matches(page, "hoodie", 12)
    stub(page, {"reply": "Hoodies!", "matches": matches, "total_matches": total, "view_all_url": "/products?type=hoodie"})
    panel = open_chat(page)
    ask(panel, "What hoodies do you have?")
    more = panel.locator(".chat-more")
    expect(more).to_contain_text(f"Showing 12 of {total}")
    panel.get_by_test_id("chat-view-all").click()
    expect(page).to_have_url(WEB_URL + "/products?type=hoodie")
    expect(page.get_by_test_id("product-card")).to_have_count(total)


def test_card_images_load(page: Page):
    matches, total = real_matches(page, "jacket", 8)
    stub(page, {"reply": "Jackets.", "matches": matches, "total_matches": total, "view_all_url": None})
    panel = open_chat(page)
    ask(panel, "Jackets?")
    imgs = bot_cards(panel).locator("img")
    expect(imgs).to_have_count(8)
    for i in range(8):
        img = imgs.nth(i)
        img.scroll_into_view_if_needed()
        expect(img).to_have_js_property("complete", True)
        assert img.evaluate("el => el.naturalWidth") > 0
    expect(panel.locator(".chat-more")).to_have_count(0)  # all 8 shown, no "Showing x of y"


def test_missing_image_shows_fallback_in_card(page: Page):
    matches, total = real_matches(page, "long-sleeve", 2)
    matches[0]["image_url"] = None
    stub(page, {"reply": "Two long-sleeves.", "matches": matches, "total_matches": total, "view_all_url": None})
    panel = open_chat(page)
    ask(panel, "Long sleeves?")
    cards = bot_cards(panel)
    expect(cards).to_have_count(2)
    expect(cards.nth(0).get_by_test_id("img-fallback")).to_be_visible()
    expect(cards.nth(1).locator("img")).to_have_count(1)


# ---------- Empty results + ordinary replies ----------

def test_empty_results_show_reply_only(page: Page):
    stub(page, {"reply": "Sorry, we don't carry swimsuits.", "matches": [], "total_matches": 0, "view_all_url": None})
    panel = open_chat(page)
    ask(panel, "What swimsuits do you have?")
    bot = panel.get_by_test_id("chat-bot").last
    expect(bot.locator("p").first).to_have_text("Sorry, we don't carry swimsuits.")
    expect(bot.get_by_test_id("chat-product")).to_have_count(0)
    expect(panel.locator(".chat-more")).to_have_count(0)


def test_ordinary_reply_has_no_cards(page: Page):
    stub(page, {"reply": "Hi! Ask me about hoodies, tees or crewnecks.", "matches": [], "total_matches": 0, "view_all_url": None})
    panel = open_chat(page)
    ask(panel, "hello")
    expect(panel.get_by_test_id("chat-bot").last.locator("p").first).to_have_text("Hi! Ask me about hoodies, tees or crewnecks.")
    expect(panel.get_by_test_id("chat-product")).to_have_count(0)


# ---------- Storefront still uses the same card component ----------

def test_storefront_and_chat_share_the_card_component(page: Page):
    page.goto(WEB_URL + "/products")
    grid_card = page.get_by_test_id("product-card").first
    expect(grid_card).to_have_class("product-card grid")
    matches, total = real_matches(page, "jacket", 1)
    stub(page, {"reply": "One.", "matches": matches, "total_matches": 1, "view_all_url": None})
    panel = open_chat(page)
    ask(panel, "a jacket")
    expect(bot_cards(panel).first).to_have_class("product-card compact")


# ---------- Real path: browser -> FastAPI -> agent -> search_catalogue (one model call) ----------

@pytest.mark.skipif(not settings.portkey_api_key, reason="PORTKEY_API_KEY not configured")
def test_live_category_search(page: Page):
    panel = open_chat(page)
    ask(panel, "What hoodies do you have?")
    expect(panel.get_by_role("status", name="Assistant is typing")).to_have_count(0, timeout=60_000)
    bot = panel.get_by_test_id("chat-bot").last
    expect(bot).not_to_have_class("chat-msg bot error")
    cards = bot.get_by_test_id("chat-product")
    expect(cards).to_have_count(12)
    expect(panel.locator(".chat-more")).to_contain_text("Showing 12 of 27")

    # Every live card is a real hoodie from the database, with the database's name and price
    hrefs = [cards.nth(i).get_attribute("href") for i in range(12)]
    assert len(set(hrefs)) == 12
    for i, href in enumerate(hrefs):
        p = page.request.get(f"{API_URL}/api{href}").json()
        assert p["product_type"] == "hoodie"
        expect(cards.nth(i).locator("h3")).to_have_text(p["name"])
        expect(cards.nth(i).locator(".price")).to_have_text(f"${p['price_cents'] / 100:.2f}")

    cards.nth(3).click()
    expect(page).to_have_url(WEB_URL + hrefs[3])
