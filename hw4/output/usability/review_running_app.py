"""Review output/usability.md against the RUNNING app (frontend :5173, backend :8000).

Run from hw4/ while both servers are running:
    .\\backend\\.venv\\Scripts\\python.exe output\\usability\\review_running_app.py

Prints PASS/FAIL for every claim in usability.md and saves screenshots next to this file.
Makes 2 real chat calls (success + empty result); everything else is free.
"""

import json
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import Route, expect, sync_playwright

WEB, API = "http://localhost:5173", "http://localhost:8000"
OUT = Path(__file__).resolve().parent
PHONE = {"width": 390, "height": 844}
results: list[tuple[str, bool, str]] = []


def check(name: str, fn) -> None:
    try:
        note = fn() or ""
        results.append((name, True, str(note)))
    except Exception as exc:  # report and keep going
        results.append((name, False, f"{type(exc).__name__}: {str(exc).splitlines()[0][:160]}"))


def api(path: str):
    try:
        with urllib.request.urlopen(API + path) as r:
            return r.status, dict(r.headers), json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), json.loads(e.read())


def no_h_overflow(page) -> bool:
    return page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True, args=["--no-proxy-server"])

    # ===================== 1. Mobile layout =====================
    m = browser.new_page(viewport=PHONE)

    def mobile_pages_fit():
        for path in ["/", "/products", "/products/davenport-college-crewneck", "/about", "/login", "/signup"]:
            m.goto(WEB + path)
            m.get_by_role("heading", level=1).first.wait_for()
            assert no_h_overflow(m), path
        return "6 pages, no sideways scrolling at 390px"
    check("1. Mobile: every page fits the phone width", mobile_pages_fit)

    def mobile_chips():
        m.goto(WEB + "/products")
        m.get_by_test_id("product-card").first.wait_for()
        chips = m.locator(".filters .chip")
        rows = {round(chips.nth(i).bounding_box()["y"]) for i in range(chips.count())}
        assert len(rows) == 1 and m.locator(".filters").evaluate("e => e.scrollWidth > e.clientWidth")
        return f"{chips.count()} chips in one swipeable row"
    check("1. Mobile: category chips are one swipeable row", mobile_chips)

    def mobile_targets():
        h = {s: m.locator(s).first.bounding_box()["height"] for s in [".filters .chip", ".menu-toggle", "#product-search"]}
        assert min(h.values()) >= 44, h
        assert m.locator("#product-search").evaluate("e => getComputedStyle(e).fontSize") == "16px"
        return f"min height {min(h.values()):.0f}px, search input 16px"
    check("1. Mobile: 44px touch targets, 16px inputs", mobile_targets)
    m.get_by_role("searchbox", name="Search products").fill("hoodies")
    m.get_by_test_id("result-status").filter(has_text="27 results").wait_for()
    m.screenshot(path=OUT / "1_mobile_products_search.png")

    def mobile_chat():
        m.get_by_role("button", name="Open chat").click()
        panel = m.get_by_role("dialog", name="Campus Customs chat")
        b = panel.bounding_box()
        assert (b["x"], b["y"], b["width"]) == (0, 0, PHONE["width"]) and b["height"] >= PHONE["height"] - 1
        assert not m.locator(".chat-launcher").is_visible()
        send = panel.get_by_role("button", name="Send message").bounding_box()["height"]
        close = panel.get_by_role("button", name="Close chat").bounding_box()["height"]
        assert send >= 44 and close >= 44
        return "full-screen sheet; Send/Close ≥ 44px"
    check("1. Mobile: chat opens full-screen", mobile_chat)
    m.screenshot(path=OUT / "2_mobile_chat_suggestions.png")
    m.close()

    # ===================== 2. Chat suggestions / loading / errors / a11y =====================
    d = browser.new_page(viewport={"width": 1280, "height": 900})

    def suggestions():
        d.goto(WEB)
        d.get_by_role("button", name="Open chat").click()
        g = d.get_by_role("group", name="Suggested questions")
        labels = g.get_by_role("button").all_inner_texts()
        assert labels == ["What hoodies do you have?", "Gift ideas for my dad", "Tees under $40"], labels
        d.goto(WEB + "/products/davenport-college-crewneck")
        d.get_by_role("button", name="Open chat").click()
        prod = d.get_by_role("group", name="Suggested questions").get_by_role("button").all_inner_texts()
        assert prod[0] == "What colors does this come in?", prod
        return f"home: {len(labels)} general · product page: {len(prod)} product questions"
    check("2. Chat: suggestions (general and product-page)", suggestions)

    def loading_and_success():
        d.goto(WEB)
        held: list[Route] = []
        d.route(f"{API}/api/chat", lambda r: held.append(r))
        d.get_by_role("button", name="Open chat").click()
        panel = d.get_by_role("dialog", name="Campus Customs chat")
        panel.get_by_role("button", name="What hoodies do you have?").click()
        typing = panel.get_by_role("status", name="Assistant is typing")
        typing.wait_for()
        assert "Assistant is typing" in typing.inner_text()
        d.wait_for_timeout(300)
        d.screenshot(path=OUT / "3_chat_loading.png")
        while not held:
            d.wait_for_timeout(50)
        held[0].continue_()  # now let the REAL request through
        d.unroute(f"{API}/api/chat")
        expect(typing).to_have_count(0, timeout=60_000)
        cards = panel.get_by_test_id("chat-bot").last.get_by_test_id("chat-product")
        expect(cards).to_have_count(12)
        expect(panel.locator(".chat-more")).to_contain_text("Showing 12 of 27")
        d.wait_for_timeout(500)
        d.screenshot(path=OUT / "4_chat_success_cards.png")
        return "typing indicator with screen-reader text, then real reply + 12 cards (Showing 12 of 27)"
    check("2. Chat: loading indicator then successful reply (live)", loading_and_success)

    def empty_result():
        panel = d.get_by_role("dialog", name="Campus Customs chat")
        panel.get_by_role("textbox", name="Chat message").fill("What swimsuits do you have?")
        panel.get_by_role("button", name="Send message").click()
        expect(panel.get_by_role("status", name="Assistant is typing")).to_have_count(0, timeout=60_000)
        last = panel.get_by_test_id("chat-bot").last
        assert last.get_by_test_id("chat-product").count() == 0
        return "reply: " + last.locator("p").first.inner_text()[:90]
    check("2. Chat: empty result shows reply only, no cards (live)", empty_result)

    def error_retry():
        d.goto(WEB)
        calls = {"n": 0}

        def flaky(route: Route):
            calls["n"] += 1
            if calls["n"] == 1:  # the REAL backend rejects an over-long message: genuine 422 + request id
                route.fulfill(response=route.fetch(post_data=json.dumps({"message": "x" * 600, "history": [], "product_id": None})))
            else:
                route.fulfill(status=502, content_type="application/json", body=json.dumps(
                    {"detail": "The assistant couldn't answer right now. Please try again.", "code": "assistant_error", "request_id": "demo1234"}))
        d.route(f"{API}/api/chat", flaky)
        d.get_by_role("button", name="Open chat").click()
        panel = d.get_by_role("dialog", name="Campus Customs chat")
        panel.get_by_role("textbox", name="Chat message").fill("hello")
        panel.get_by_role("button", name="Send message").click()
        err = panel.get_by_test_id("chat-bot").last
        expect(err.locator("p").first).to_have_text("Messages can be at most 500 characters.")
        ref422 = err.locator(".ref").inner_text()
        panel.get_by_role("textbox", name="Chat message").fill("Do you have hoodies?")
        panel.get_by_role("button", name="Send message").click()
        err = panel.get_by_test_id("chat-bot").last
        expect(err.get_by_role("button", name="Retry")).to_be_visible()
        expect(err.locator(".ref")).to_have_text("Ref demo1234")
        d.screenshot(path=OUT / "5_chat_error_retry.png")
        d.unroute(f"{API}/api/chat")
        return f"real 422 shown as plain message ({ref422}); 502 shows Retry + Ref"
    check("2. Chat: concise error with Ref and Retry", error_retry)

    def offline():
        d.context.set_offline(True)
        panel = d.get_by_role("dialog", name="Campus Customs chat")
        panel.get_by_role("textbox", name="Chat message").fill("hello")
        panel.get_by_role("button", name="Send message").click()
        expect(panel.get_by_test_id("chat-bot").last.locator("p").first).to_have_text(
            "You're offline. Check your connection, then tap Retry.")
        d.context.set_offline(False)
        return "offline message without sending"
    check("2. Chat: offline state", offline)

    def a11y():
        d.goto(WEB)
        launcher = d.get_by_role("button", name="Open chat")
        assert launcher.get_attribute("aria-controls") == "chat-panel"
        launcher.focus()
        d.keyboard.press("Enter")
        panel = d.get_by_role("dialog", name="Campus Customs chat")
        assert panel.get_by_role("log", name="Conversation").is_visible()
        box = panel.get_by_role("textbox", name="Chat message")
        assert box.evaluate("e => e === document.activeElement")
        box.fill("x" * 450)
        expect(panel.locator("#chat-counter")).to_have_text("450 / 500")
        d.keyboard.press("Escape")
        assert d.get_by_role("button", name="Open chat").evaluate("e => e === document.activeElement")
        return "role=log, focus moves in and back, Escape closes, 450 / 500 counter"
    check("2. Chat: accessibility (roles, focus, Escape, counter)", a11y)

    # ===================== 3. Normalized, deduplicated search =====================
    def search_variants():
        d.goto(WEB + "/products")
        box = d.get_by_role("searchbox", name="Search products")
        seen = {}
        for q in ["hoodies", "HOODY", "tees", "T-Shirts", "1/4 zip", "quarter zips", "hoodie hoodies HOODIE"]:
            box.fill(q)
            status = d.get_by_test_id("result-status")
            expect(status).to_contain_text(f"for “{q}”")
            hrefs = d.get_by_test_id("product-card").evaluate_all("es => es.map(e => e.getAttribute('href'))")
            assert len(hrefs) == len(set(hrefs)), q
            seen[q] = len(hrefs)
        assert seen["hoodies"] == seen["HOODY"] == seen["hoodie hoodies HOODIE"] == 27
        assert seen["tees"] == seen["T-Shirts"] == 25 and seen["1/4 zip"] == seen["quarter zips"] == 11
        box.fill("hoodies")
        expect(d.get_by_test_id("result-status")).to_have_text("27 results for “hoodies”")
        d.screenshot(path=OUT / "6_search_results.png")
        return ", ".join(f"{k}={v}" for k, v in seen.items())
    check("3. Search: spelling variants agree, no duplicates", search_variants)

    def search_typo_relaxed_empty():
        box = d.get_by_role("searchbox", name="Search products")
        box.fill("field hockey crewneck")
        expect(d.get_by_test_id("product-card")).to_have_count(1)
        name = d.get_by_test_id("product-card").locator("h3").inner_text()
        box.fill("gift for my dad")
        expect(d.get_by_test_id("result-status")).to_contain_text("showing closest results")
        box.fill("swimsuit")
        expect(d.get_by_test_id("search-empty")).to_contain_text("No products match “swimsuit”")
        d.screenshot(path=OUT / "7_search_empty.png")
        return f"typo found: {name}; relaxed note shown; empty state with suggestions"
    check("3. Search: typo, closest-match and empty states", search_typo_relaxed_empty)

    # ===================== 4. Concise, safe errors =====================
    def error_shape():
        out = []
        for path, status, code in [("/api/nope", 404, "not_found"), ("/api/products/yale-unicorn-onesie", 404, "product_not_found"),
                                   ("/api/products/search?q=" + "x" * 101, 422, "validation_error")]:
            s, headers, body = api(path)
            assert s == status and body["code"] == code and set(body) == {"detail", "code", "request_id"}
            assert headers.get("x-request-id") == body["request_id"]
            out.append(f"{s} {code}")
        s, headers, body = api("/api/health")
        assert s == 200 and len(headers.get("x-request-id", "")) == 8
        return "; ".join(out) + "; X-Request-ID on success too"
    check("4. Errors: one concise shape with request id", error_shape)

    def error_visible():
        d.route(f"{API}/api/products/search**", lambda r: r.fulfill(status=500, content_type="application/json", body=json.dumps(
            {"detail": "Something went wrong on our side. Please try again.", "code": "internal_error", "request_id": "c0ffee12"})))
        d.goto(WEB + "/products?q=hoodies")
        alert = d.get_by_role("alert")
        expect(alert).to_contain_text("Search isn't working right now")
        expect(alert).to_contain_text("ref c0ffee12")
        d.screenshot(path=OUT / "8_search_error.png")
        d.unroute(f"{API}/api/products/search**")
        d.goto(WEB + "/products/yale-unicorn-onesie")
        expect(d.get_by_role("heading", name="We couldn't find that item")).to_be_visible()
        return "search error panel with ref; unknown product page"
    check("4. Errors: visible in the storefront", error_visible)

    browser.close()

width = max(len(n) for n, _, _ in results)
for name, ok, note in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name:<{width}}  {note}")
failed = [n for n, ok, _ in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
sys.exit(1 if failed else 0)
