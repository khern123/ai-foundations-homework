"""Chat memory and context in the browser: guest chat, reloaded history, authorization, privacy, page context.

Saved conversations are written straight into the throwaway test database (test_db fixture), so reload
and privacy are checked without model calls. test_live_memory_and_page_context makes ONE real call.
"""

import json
import sqlite3
import sys
import uuid
from contextlib import closing
from pathlib import Path

import pytest
from playwright.sync_api import Page, Route, expect

from conftest import WEB_URL

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import settings  # noqa: E402

SEED_EMAIL, SEED_PASSWORD = "test@campuscustoms.yale.edu", "password"
STUB = {"reply": "Stub reply.", "matches": [], "total_matches": 0, "view_all_url": None}


def save_messages(test_db, user_id: int, *pairs: tuple[str, str]) -> None:
    with closing(sqlite3.connect(test_db)) as conn, conn:
        for q, a in pairs:
            conn.execute("INSERT INTO chat_messages (user_id, role, content) VALUES (?, 'user', ?)", (user_id, q))
            conn.execute("INSERT INTO chat_messages (user_id, role, content, products_json) VALUES (?, 'assistant', ?, ?)",
                         (user_id, a, json.dumps([{"id": "yale-dad-hoodie"}])))


def log_in(page: Page, email=SEED_EMAIL, password=SEED_PASSWORD) -> None:
    page.goto(WEB_URL + "/login")
    page.get_by_label("Email").fill(email)
    page.get_by_label("Password").fill(password)
    page.get_by_role("main").get_by_role("button", name="Log in").click()
    expect(page.get_by_test_id("signed-in-user")).to_be_visible()


def open_chat(page: Page):
    page.get_by_role("button", name="Open chat").click()
    return page.get_by_role("dialog", name="Campus Customs chat")


def capture_chat(page: Page, sent: list) -> None:
    def handle(route: Route):
        sent.append({"headers": route.request.headers, "body": route.request.post_data_json})
        route.fulfill(status=200, content_type="application/json", body=json.dumps(STUB))
    page.route("**/api/chat", handle)


def ask(panel, text: str) -> None:
    panel.get_by_role("textbox", name="Chat message").fill(text)
    panel.get_by_role("button", name="Send").click()


# ---------- Saved and reloaded history ----------

def test_signed_in_user_sees_saved_history(page: Page, test_db):
    save_messages(test_db, 1, ("Saved Q one", "Saved A one"))
    log_in(page)
    panel = open_chat(page)
    expect(panel.get_by_test_id("chat-context")).to_have_text("Chat history saved to your account")
    expect(panel.get_by_test_id("chat-bot").first).to_contain_text("Hi Test!")
    expect(panel.get_by_test_id("chat-user").filter(has_text="What hoodies do you have?")).to_have_count(1)  # course seed
    expect(panel.get_by_test_id("chat-user").last.locator("p").first).to_have_text("Saved Q one")
    last_bot = panel.get_by_test_id("chat-bot").last
    expect(last_bot.locator("p").first).to_have_text("Saved A one")
    expect(last_bot.get_by_test_id("chat-product")).to_have_attribute("href", "/products/yale-dad-hoodie")  # card rebuilt


def test_history_reloads_after_page_reload(page: Page, test_db):
    log_in(page)
    save_messages(test_db, 1, ("Asked before the reload", "Answered before the reload"))
    page.reload()
    panel = open_chat(page)
    expect(panel.get_by_test_id("chat-user").last.locator("p").first).to_have_text("Asked before the reload")


# ---------- Guest chat ----------

def test_guest_chat_works_but_is_not_kept(page: Page):
    sent: list = []
    capture_chat(page, sent)
    page.goto(WEB_URL)
    panel = open_chat(page)
    expect(panel.get_by_test_id("chat-context")).to_have_text("Guest chat · not saved")
    ask(panel, "guest question")
    expect(panel.get_by_test_id("chat-bot").last.locator("p").first).to_have_text("Stub reply.")
    assert "authorization" not in sent[0]["headers"]

    page.reload()
    panel = open_chat(page)
    expect(panel.get_by_test_id("chat-user")).to_have_count(0)


# ---------- Authorization + privacy ----------

def test_each_user_sees_only_their_own_history(page: Page, test_db):
    save_messages(test_db, 3, ("User three's private question", "Private answer"))
    log_in(page)
    panel = open_chat(page)
    expect(panel.get_by_test_id("chat-user").first).to_be_visible()
    expect(panel.get_by_text("User three's private question")).to_have_count(0)

    # A brand-new account starts empty and never sees the test user's messages
    page.get_by_role("button", name="Log out").click()
    page.goto(WEB_URL + "/signup")
    page.get_by_label("First name").fill("Nora")
    page.get_by_label("Last name").fill("New")
    page.get_by_label("Email").fill(f"nora.{uuid.uuid4().hex[:6]}@yale.edu")
    page.get_by_label("Password", exact=True).fill("bulldog-pass-1")
    page.get_by_label("Confirm password").fill("bulldog-pass-1")
    page.get_by_role("main").get_by_role("button", name="Create account").click()
    expect(page.get_by_test_id("signed-in-user")).to_have_text("Hi, Nora")
    panel = open_chat(page)
    expect(panel.get_by_test_id("chat-bot")).to_have_count(1)
    expect(panel.get_by_test_id("chat-bot").first).to_contain_text("Hi Nora!")
    expect(panel.get_by_test_id("chat-user")).to_have_count(0)


def test_logging_out_clears_the_conversation(page: Page):
    log_in(page)
    panel = open_chat(page)
    expect(panel.get_by_test_id("chat-user").first).to_be_visible()
    page.get_by_role("button", name="Log out").click()
    panel = page.get_by_role("dialog", name="Campus Customs chat")
    expect(panel.get_by_test_id("chat-user")).to_have_count(0)
    expect(panel.get_by_test_id("chat-bot")).to_have_count(1)
    expect(panel.get_by_test_id("chat-bot").first).to_contain_text("Hi! I'm")


def test_signed_in_requests_carry_token_not_secrets(page: Page):
    log_in(page)
    sent: list = []
    capture_chat(page, sent)
    panel = open_chat(page)
    ask(panel, "hello")
    expect(panel.get_by_test_id("chat-bot").last.locator("p").first).to_have_text("Stub reply.")
    req = sent[0]
    assert req["headers"]["authorization"].startswith("Bearer 1.")
    assert req["body"]["history"] == []  # signed-in history comes from the server
    raw = json.dumps(req)
    assert SEED_PASSWORD + '"' not in raw and SEED_EMAIL not in raw and "pbkdf2" not in raw
    stored = page.evaluate("JSON.stringify({...sessionStorage, ...localStorage})")
    assert "password" not in stored.lower() and "pbkdf2" not in stored


def test_expired_session_falls_back_to_guest(page_allow_errors: Page):
    page = page_allow_errors  # the rejected history request logs a 401
    log_in(page)
    page.evaluate("sessionStorage.setItem('cc_token', '1.1.tampered')")
    page.reload()
    expect(page.get_by_test_id("signed-in-user")).to_have_count(0)
    expect(page.get_by_role("navigation", name="Main").get_by_role("link", name="Log in")).to_be_visible()


# ---------- Product-page context ----------

def test_product_page_is_sent_as_context(page: Page):
    sent: list = []
    capture_chat(page, sent)
    page.goto(WEB_URL + "/products/davenport-college-crewneck")
    panel = open_chat(page)
    expect(panel.get_by_test_id("chat-context")).to_have_text("Asking about this product")
    ask(panel, "Do you have this in pink?")
    expect(panel.get_by_test_id("chat-bot").last.locator("p").first).to_have_text("Stub reply.")
    assert sent[0]["body"]["product_id"] == "davenport-college-crewneck"

    page.get_by_role("navigation", name="Main").get_by_role("link", name="Home").click()
    ask(page.get_by_role("dialog", name="Campus Customs chat"), "and now?")
    expect(page.get_by_test_id("chat-bot").last.locator("p").first).to_have_text("Stub reply.")
    assert sent[1]["body"]["product_id"] is None


# ---------- Live: real agent, saved, reloaded, page context (one model call) ----------

@pytest.mark.skipif(not settings.portkey_api_key, reason="PORTKEY_API_KEY not configured")
def test_live_memory_and_page_context(page: Page, test_db):
    log_in(page)
    page.goto(WEB_URL + "/products/davenport-college-crewneck")
    panel = open_chat(page)
    ask(panel, "Do you have this in pink?")
    expect(panel.get_by_role("status", name="Assistant is typing")).to_have_count(0, timeout=60_000)
    reply = panel.get_by_test_id("chat-bot").last.locator("p").first.inner_text()
    assert "pink" in reply.lower() and any(w in reply.lower() for w in ("don't", "not", "only", "isn't", "doesn't"))
    assert "davenport" in reply.lower()  # "this" was resolved to the page's product

    with closing(sqlite3.connect(test_db)) as conn:
        last_two = conn.execute("SELECT role, content FROM chat_messages WHERE user_id=1 ORDER BY id DESC LIMIT 2").fetchall()
    assert last_two[1] == ("user", "Do you have this in pink?") and last_two[0] == ("assistant", reply)

    page.reload()
    panel = open_chat(page)
    expect(panel.get_by_test_id("chat-user").last.locator("p").first).to_have_text("Do you have this in pink?")
    expect(panel.get_by_test_id("chat-bot").last.locator("p").first).to_have_text(reply)
