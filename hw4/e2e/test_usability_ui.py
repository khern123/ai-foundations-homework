"""The four usability improvements, checked in the running app (see output/usability.md)."""

import json
import re

from playwright.sync_api import Page, Route, expect

from conftest import WEB_URL

STUB = {"reply": "Here you go!", "matches": [], "total_matches": 0, "view_all_url": None}
PHONE = {"width": 375, "height": 812}


def open_chat(page: Page, path: str = "/"):
    page.goto(WEB_URL + path)
    page.get_by_role("button", name="Open chat").click()
    return page.get_by_role("dialog", name="Campus Customs chat")


def stub_chat(page: Page, responses: list, sent: list | None = None):
    """Answer successive /api/chat calls with the given (status, body) pairs."""
    def handle(route: Route):
        if sent is not None:
            sent.append(route.request.post_data_json)
        status, body = responses.pop(0) if len(responses) > 1 else responses[0]
        route.fulfill(status=status, content_type="application/json", body=json.dumps(body))
    page.route("**/api/chat", handle)


def bubble_text(panel, who="bot"):
    return panel.get_by_test_id(f"chat-{who}").last.locator("p").first


# ===================== 1. Responsive mobile layout =====================

def test_mobile_chat_is_full_screen(page: Page):
    page.set_viewport_size(PHONE)
    panel = open_chat(page)
    box = panel.bounding_box()
    assert (box["x"], box["y"], box["width"]) == (0, 0, 375) and box["height"] >= 800
    expect(page.locator(".chat-launcher")).to_be_hidden()  # header × closes it instead
    panel.get_by_role("button", name="Close chat").click()
    expect(panel).to_be_hidden()
    expect(page.get_by_role("button", name="Open chat")).to_be_visible()


def test_mobile_filter_chips_are_one_swipeable_row(page: Page):
    page.set_viewport_size(PHONE)
    page.goto(WEB_URL + "/products")
    expect(page.get_by_test_id("product-card")).to_have_count(102)
    chips = page.locator(".filters .chip")
    tops = {round(chips.nth(i).bounding_box()["y"]) for i in range(chips.count())}
    assert len(tops) == 1  # one row
    assert page.locator(".filters").evaluate("el => el.scrollWidth > el.clientWidth")  # scrolls sideways
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")  # page itself doesn't


def test_mobile_touch_targets_and_input_size(page: Page):
    page.set_viewport_size(PHONE)
    page.goto(WEB_URL + "/products")
    for sel in [".filters .chip", ".menu-toggle"]:
        assert page.locator(sel).first.bounding_box()["height"] >= 44, sel
    page.get_by_role("button", name="Toggle navigation").click()
    assert page.get_by_role("navigation", name="Main").get_by_role("link", name="Products").bounding_box()["height"] >= 44
    assert page.locator("#product-search").evaluate("el => getComputedStyle(el).fontSize") == "16px"

    panel = open_chat(page)
    assert panel.get_by_role("button", name="Send message").bounding_box()["height"] >= 44
    assert panel.locator(".chat-suggestion").first.bounding_box()["height"] >= 44
    assert panel.get_by_role("button", name="Close chat").bounding_box()["height"] >= 44
    assert panel.get_by_role("textbox", name="Chat message").evaluate("el => getComputedStyle(el).fontSize") == "16px"


def test_mobile_hero_buttons_stack(page: Page):
    page.set_viewport_size(PHONE)
    page.goto(WEB_URL)
    a = page.get_by_role("link", name="Shop the collection").bounding_box()
    b = page.get_by_role("link", name="Our story").bounding_box()
    assert b["y"] > a["y"] and a["width"] > 300


# ===================== 2. Chat suggestions, loading, errors, accessibility =====================

def test_suggestions_send_and_then_hide(page: Page):
    sent: list = []
    stub_chat(page, [(200, STUB)], sent)
    panel = open_chat(page)
    group = panel.get_by_role("group", name="Suggested questions")
    expect(group.get_by_role("button")).to_have_count(3)
    group.get_by_role("button", name="What hoodies do you have?").click()
    expect(bubble_text(panel)).to_have_text("Here you go!")
    assert sent[0]["message"] == "What hoodies do you have?"
    expect(group).to_have_count(0)  # general suggestions only before the first question


def test_product_page_suggestions(page: Page):
    sent: list = []
    stub_chat(page, [(200, STUB)], sent)
    panel = open_chat(page, "/products/davenport-college-crewneck")
    panel.get_by_role("button", name="What colors does this come in?").click()
    expect(bubble_text(panel)).to_have_text("Here you go!")
    assert sent[0] == {**sent[0], "message": "What colors does this come in?", "product_id": "davenport-college-crewneck"}


def test_loading_states(page: Page):
    held: list[Route] = []
    page.route("**/api/chat", lambda r: held.append(r))
    panel = open_chat(page)
    panel.get_by_role("textbox", name="Chat message").fill("hello")
    panel.get_by_role("button", name="Send message").click()
    typing = panel.get_by_role("status", name="Assistant is typing")
    expect(typing).to_be_visible()
    expect(typing).to_contain_text("Assistant is typing…")  # screen-reader text
    expect(panel.get_by_role("button", name="Send message")).to_be_disabled()
    expect(panel.get_by_role("group", name="Suggested questions")).to_have_count(0)
    for _ in range(50):
        if held:
            break
        page.wait_for_timeout(100)
    held[0].fulfill(status=200, content_type="application/json", body=json.dumps(STUB))
    expect(typing).to_have_count(0)


def test_history_loading_state(page: Page):
    page.goto(WEB_URL + "/login")
    page.get_by_label("Email").fill("test@campuscustoms.yale.edu")
    page.get_by_label("Password").fill("password")
    held: list[Route] = []
    page.route("**/api/chat/history", lambda r: held.append(r))
    page.get_by_role("main").get_by_role("button", name="Log in").click()
    expect(page.get_by_test_id("signed-in-user")).to_be_visible()
    page.get_by_role("button", name="Open chat").click()
    panel = page.get_by_role("dialog", name="Campus Customs chat")
    expect(panel.get_by_test_id("chat-history-loading")).to_have_text("Loading your conversation…")
    for _ in range(50):
        if held:
            break
        page.wait_for_timeout(100)
    held[0].continue_()
    expect(panel.get_by_test_id("chat-history-loading")).to_have_count(0)
    expect(panel.get_by_test_id("chat-user").first).to_be_visible()


def test_error_shows_retry_and_ref_then_recovers(page_allow_errors: Page):
    page = page_allow_errors
    sent: list = []
    stub_chat(page, [(502, {"detail": "The assistant couldn't answer right now. Please try again.",
                            "code": "assistant_error", "request_id": "ab12cd34"}), (200, STUB)], sent)
    panel = open_chat(page)
    panel.get_by_role("textbox", name="Chat message").fill("Do you have hoodies?")
    panel.get_by_role("button", name="Send message").click()
    err = panel.get_by_test_id("chat-bot").last
    expect(err.locator("p").first).to_have_text("The assistant couldn't answer right now. Please try again.")
    expect(err.locator(".ref")).to_have_text("Ref ab12cd34")
    err.get_by_role("button", name="Retry").click()
    expect(bubble_text(panel)).to_have_text("Here you go!")
    expect(panel.get_by_test_id("chat-user")).to_have_count(1)  # the question isn't duplicated
    expect(panel.locator(".chat-msg.error")).to_have_count(0)
    assert [s["message"] for s in sent] == ["Do you have hoodies?", "Do you have hoodies?"]


def test_offline_message_and_retry(page_allow_errors: Page):
    page = page_allow_errors  # going offline makes the browser log "disconnected" for background requests
    sent: list = []
    stub_chat(page, [(200, STUB)], sent)
    panel = open_chat(page)
    page.context.set_offline(True)
    panel.get_by_role("textbox", name="Chat message").fill("hello")
    panel.get_by_role("button", name="Send message").click()
    expect(bubble_text(panel)).to_have_text("You're offline. Check your connection, then tap Retry.")
    assert sent == []  # nothing was sent
    page.context.set_offline(False)
    panel.get_by_role("button", name="Retry").click()
    expect(bubble_text(panel)).to_have_text("Here you go!")


def test_real_backend_error_shows_its_request_id(page_allow_errors: Page):
    """A genuine backend 422 (message over 500 chars, sent past the input's limit) is shown concisely with its ref."""
    page = page_allow_errors
    ids: list = []

    def too_long(route: Route):
        resp = route.fetch(post_data=json.dumps({"message": "x" * 600, "history": [], "product_id": None}))
        ids.append(resp.headers.get("x-request-id"))
        route.fulfill(response=resp)

    page.route("**/api/chat", too_long)
    panel = open_chat(page)
    panel.get_by_role("textbox", name="Chat message").fill("hi")
    panel.get_by_role("button", name="Send message").click()
    err = panel.get_by_test_id("chat-bot").last
    expect(err.locator("p").first).to_have_text("Messages can be at most 500 characters.")
    expect(err.locator(".ref")).to_have_text(f"Ref {ids[0]}")
    expect(err.get_by_role("button", name="Retry")).to_have_count(0)  # retrying the same text can't succeed


def test_accessibility_roles_focus_and_counter(page: Page):
    page.goto(WEB_URL)
    launcher = page.get_by_role("button", name="Open chat")
    expect(launcher).to_have_attribute("aria-controls", "chat-panel")
    expect(launcher).to_have_attribute("aria-haspopup", "dialog")
    launcher.focus()
    page.keyboard.press("Enter")
    panel = page.get_by_role("dialog", name="Campus Customs chat")
    expect(panel.get_by_role("log", name="Conversation")).to_be_visible()
    box = panel.get_by_role("textbox", name="Chat message")
    expect(box).to_be_focused()

    box.fill("x" * 399)
    expect(panel.locator("#chat-counter")).to_have_count(0)
    box.fill("x" * 430)
    expect(panel.locator("#chat-counter")).to_have_text("430 / 500")
    expect(box).to_have_attribute("aria-describedby", "chat-counter")

    page.keyboard.press("Escape")
    expect(panel).to_be_hidden()
    expect(page.get_by_role("button", name="Open chat")).to_be_focused()  # focus returns to the launcher


def test_keyboard_focus_is_visible(page: Page):
    page.goto(WEB_URL + "/products")
    expect(page.get_by_test_id("product-card")).to_have_count(102)
    card = page.get_by_test_id("product-card").first
    card.focus()
    page.keyboard.press("Shift+Tab")
    page.keyboard.press("Tab")  # keyboard focus -> :focus-visible
    style = card.evaluate("el => getComputedStyle(el).outlineStyle + ' ' + getComputedStyle(el).outlineWidth")
    assert style.startswith("solid") and style.endswith("3px")


# ===================== 3. Normalized, deduplicated search (storefront search box) =====================

def search_for(page: Page, q: str):
    box = page.get_by_role("searchbox", name="Search products")
    box.fill(q)
    return page.get_by_test_id("result-status")


def test_search_variants_find_the_same_products(page: Page):
    page.goto(WEB_URL + "/products")
    for q, n in [("hoodies", 27), ("HOODY", 27), ("tees", 25), ("T-Shirts", 25), ("1/4 zip", 11), ("quarter zips", 11)]:
        expect(search_for(page, q)).to_have_text(f"{n} results for “{q}”")
        expect(page.get_by_test_id("product-card")).to_have_count(n)


def test_search_dedupes_and_finds_typos(page: Page):
    page.goto(WEB_URL + "/products")
    expect(search_for(page, "hoodie hoodies HOODIE")).to_have_text("27 results for “hoodie hoodies HOODIE”")
    hrefs = page.get_by_test_id("product-card").evaluate_all("els => els.map(e => e.getAttribute('href'))")
    assert len(hrefs) == len(set(hrefs)) == 27
    expect(search_for(page, "field hockey crewneck")).to_have_text("1 result for “field hockey crewneck”")
    expect(page.get_by_test_id("product-card")).to_contain_text("Yale Sports Creqneck Field Hockey")
    expect(search_for(page, "grey crewneck")).to_contain_text("results for “grey crewneck”")


def test_search_relaxed_empty_url_and_clear(page: Page):
    page.goto(WEB_URL + "/products")
    expect(search_for(page, "gift for my dad")).to_contain_text("no exact match, showing closest results")
    expect(search_for(page, "swimsuit")).to_have_text("0 results for “swimsuit”")
    empty = page.get_by_test_id("search-empty")
    expect(empty).to_contain_text("No products match “swimsuit”")
    empty.get_by_role("button", name="tees").click()
    expect(page).to_have_url(WEB_URL + "/products?q=tees")
    expect(page.get_by_test_id("product-card")).to_have_count(25)
    page.reload()
    expect(page.get_by_role("searchbox", name="Search products")).to_have_value("tees")
    expect(page.get_by_test_id("product-card")).to_have_count(25)
    page.get_by_role("button", name="Clear").click()
    expect(page.get_by_test_id("product-card")).to_have_count(102)


def test_search_combines_with_category_chip(page: Page):
    page.goto(WEB_URL + "/products")
    search_for(page, "navy")
    page.get_by_role("button", name="Crewnecks").click()  # clicked before the 250ms search debounce fires
    expect(page.get_by_test_id("result-status")).to_contain_text("results for “navy”")
    expect(page).to_have_url(re.compile(r"/products\?(?=.*\bq=navy\b)(?=.*\btype=crewneck\b)"))  # both kept
    ids = page.get_by_test_id("product-card").evaluate_all("els => els.map(e => e.getAttribute('href').split('/').pop())")
    api = page.request.get(f"{WEB_URL.replace('5174', '8001')}/api/products/search?q=navy&type=crewneck").json()
    assert ids == [p["id"] for p in api["results"]] and ids


# ===================== 4. Concise, safe errors (visible in the storefront) =====================

def test_search_error_state_shows_safe_message_and_ref(page_allow_errors: Page):
    page = page_allow_errors
    page.route("**/api/products/search**", lambda r: r.fulfill(
        status=500, content_type="application/json",
        body=json.dumps({"detail": "Something went wrong on our side. Please try again.",
                         "code": "internal_error", "request_id": "9f8e7d6c"})))
    page.goto(WEB_URL + "/products?q=hoodies")
    alert = page.get_by_role("alert")
    expect(alert).to_contain_text("Search isn't working right now")
    expect(alert).to_contain_text("Something went wrong on our side. Please try again.")
    expect(alert).to_contain_text("ref 9f8e7d6c")


def test_unknown_product_page(page_allow_errors: Page):
    page = page_allow_errors
    page.goto(WEB_URL + "/products/yale-unicorn-onesie")
    expect(page.get_by_role("heading", name="We couldn't find that item")).to_be_visible()
