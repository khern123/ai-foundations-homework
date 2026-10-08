"""Chat widget browser tests.

Most tests stub /api/chat in the browser to check UI states without model calls.
test_live_frontend_to_agent sends ONE real message through FastAPI -> PydanticAI -> Portkey.
"""

import json
import sys
from pathlib import Path

import pytest
from playwright.sync_api import Page, Route, expect

from conftest import API_URL, WEB_URL

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import settings  # noqa: E402  (to check the key never reaches the browser)

STUB_REPLY = {
    "reply": "The Davenport College Crewneck is $58.00 in heather gray.",
    "matches": [{
        "id": "davenport-college-crewneck",
        "name": "Davenport College Crewneck",
        "image_path": "products/davenport-college-crewneck.jpg",
        "image_url": "/images/products/davenport-college-crewneck.jpg",
        "price_cents": 5800,
        "price_display": "$58.00",
        "short_description": "Heather gray crewneck sweatshirt with a small Davenport crest.",
    }],
    "total_matches": 1,
    "view_all_url": None,
}


def open_chat(page: Page):
    page.goto(WEB_URL)
    page.get_by_role("button", name="Open chat").click()
    return page.get_by_role("dialog", name="Campus Customs chat")


def ask(panel, text: str) -> None:
    panel.get_by_role("textbox", name="Chat message").fill(text)
    panel.get_by_role("button", name="Send").click()


def stub_chat(page: Page, status: int = 200, body: dict | None = None, sent: list | None = None):
    def handle(route: Route):
        if sent is not None:
            sent.append(route.request.post_data_json)
        route.fulfill(status=status, content_type="application/json", body=json.dumps(body or STUB_REPLY))

    page.route("**/api/chat", handle)


# ---------- Structured replies ----------

def test_structured_reply_renders_text_and_product_cards(page: Page):
    sent: list = []
    stub_chat(page, sent=sent)
    panel = open_chat(page)
    ask(panel, "Do you have Davenport crewnecks?")

    bot = panel.get_by_test_id("chat-bot").last
    expect(bot).to_contain_text("The Davenport College Crewneck is $58.00")
    card = bot.get_by_test_id("chat-product")
    expect(card).to_have_count(1)
    expect(card).to_contain_text("Davenport College Crewneck")
    expect(card).to_contain_text("$58.00")
    expect(card.locator("img")).to_have_attribute("src", f"{API_URL}/images/products/davenport-college-crewneck.jpg")

    assert sent == [{"message": "Do you have Davenport crewnecks?", "history": [], "product_id": None}]
    card.click()
    expect(page).to_have_url(WEB_URL + "/products/davenport-college-crewneck")


def test_follow_up_sends_history(page: Page):
    sent: list = []
    stub_chat(page, sent=sent)
    panel = open_chat(page)
    ask(panel, "Do you have Davenport crewnecks?")
    expect(panel.get_by_test_id("chat-bot")).to_have_count(2)
    ask(panel, "Any in black?")
    expect(panel.get_by_test_id("chat-bot")).to_have_count(3)
    assert sent[1] == {
        "message": "Any in black?",
        "history": [
            {"role": "user", "content": "Do you have Davenport crewnecks?"},
            {"role": "assistant", "content": STUB_REPLY["reply"]},
        ],
        "product_id": None,
    }  # greeting is not sent as history


def test_typing_indicator_while_waiting(page: Page):
    release = []

    def slow(route: Route):
        release.append(route)

    page.route("**/api/chat", slow)
    panel = open_chat(page)
    ask(panel, "hello")
    expect(panel.get_by_role("status", name="Assistant is typing")).to_be_visible()
    expect(panel.get_by_role("button", name="Send")).to_be_disabled()
    for _ in range(50):  # wait until the request has reached the route
        if release:
            break
        page.wait_for_timeout(100)
    release[0].fulfill(status=200, content_type="application/json", body=json.dumps({"reply": "Hi!", "products": []}))
    expect(panel.get_by_role("status", name="Assistant is typing")).to_have_count(0)
    expect(panel.get_by_test_id("chat-bot").last.locator("p").first).to_have_text("Hi!")


# ---------- Empty messages ----------

def test_empty_and_whitespace_messages_are_not_sent(page: Page):
    sent: list = []
    stub_chat(page, sent=sent)
    panel = open_chat(page)
    box = panel.get_by_role("textbox", name="Chat message")
    send = panel.get_by_role("button", name="Send")
    expect(send).to_be_disabled()
    box.fill("    ")
    expect(send).to_be_disabled()
    box.press("Enter")
    expect(panel.get_by_test_id("chat-user")).to_have_count(0)
    assert sent == []
    expect(box).to_have_attribute("maxlength", "500")


# ---------- Safe API errors ----------

@pytest.mark.parametrize("status,body,shown", [
    (502, {"detail": "The assistant couldn't answer right now. Please try again."},
     "The assistant couldn't answer right now. Please try again."),
    (503, {"detail": "The assistant isn't available right now. Please try again later."},
     "The assistant isn't available right now. Please try again later."),
    (422, {"detail": [{"field": "message", "msg": "Please type a message."}]}, "Please type a message."),
])
def test_api_errors_show_friendly_message(page_allow_errors: Page, status, body, shown):
    page = page_allow_errors
    stub_chat(page, status=status, body=body)
    panel = open_chat(page)
    ask(panel, "hello")
    bubble = panel.get_by_test_id("chat-bot").last
    expect(bubble.locator("p").first).to_have_text(shown)
    expect(bubble).to_have_class("chat-msg bot error")
    expect(panel.get_by_role("textbox", name="Chat message")).to_be_focused()  # can retry right away


def test_network_failure_shows_generic_message(page_allow_errors: Page):
    page = page_allow_errors
    page.route("**/api/chat", lambda route: route.abort())
    panel = open_chat(page)
    ask(panel, "hello")
    expect(panel.get_by_test_id("chat-bot").last.locator("p").first).to_have_text("We couldn't reach Campus Customs. Check your connection and try again.")


# ---------- Real path: browser -> FastAPI -> PydanticAI agent -> Portkey (one model call) ----------

@pytest.mark.skipif(not settings.portkey_api_key, reason="PORTKEY_API_KEY not configured")
def test_live_frontend_to_agent(page: Page):
    key = settings.portkey_api_key
    bodies: list[str] = []
    page.on("response", lambda r: bodies.append(r.text()) if r.request.resource_type in ("fetch", "xhr", "script") else None)

    panel = open_chat(page)
    ask(panel, "Do you have a Davenport College crewneck?")
    bot = panel.get_by_test_id("chat-bot").last
    expect(bot).not_to_have_class("chat-msg bot error", timeout=60_000)
    expect(panel.get_by_role("status", name="Assistant is typing")).to_have_count(0, timeout=60_000)

    expect(bot).to_contain_text("$58.00")  # the real price from the database
    expect(bot.get_by_test_id("chat-product").filter(has_text="Davenport College Crewneck")).to_have_count(1)

    assert key not in page.content()
    assert bodies and all(key not in b for b in bodies)  # not in API responses or the JS the browser loaded
