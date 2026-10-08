"""Capture app_check.html evidence from the RUNNING app (:5173 + :8000) as a guest (no personal data).
Run from hw4/:  .\\backend\\.venv\\Scripts\\python.exe output\\app_check_images\\capture.py
Makes 2 real chat calls. Prints the database values each screenshot must match."""
import sqlite3
from pathlib import Path
from playwright.sync_api import expect, sync_playwright

OUT = Path(__file__).resolve().parent
DB = Path(__file__).resolve().parents[2] / "backend" / "data" / "campus_customs.db"
WEB = "http://localhost:5173"

with sqlite3.connect(f"file:{DB}?mode=ro", uri=True) as c:
    price = c.execute("SELECT price FROM catalogue WHERE product_id='davenport-college-crewneck'").fetchone()[0]
    stock = dict(c.execute("SELECT size, quantity FROM inventory WHERE product_id='davenport-college-crewneck'"))
    hoodies = c.execute("SELECT COUNT(*) FROM catalogue WHERE lower(garment_type) LIKE '%hood%'").fetchone()[0]
print(f"DB: Davenport price ${price:.2f}, stock {stock}, total {sum(stock.values())}; hoodies {hoodies}")

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True, args=["--no-proxy-server"])
    pg = b.new_page(viewport={"width": 1280, "height": 860})

    # 1. Price + inventory (live model, tools read SQLite)
    pg.goto(WEB + "/products/davenport-college-crewneck")
    pg.get_by_role("button", name="Open chat").click()
    panel = pg.get_by_role("dialog", name="Campus Customs chat")
    panel.get_by_role("textbox", name="Chat message").fill(
        "How much is this crewneck, and how many do you have in medium and in small?")
    panel.get_by_role("button", name="Send message").click()
    expect(panel.get_by_role("status", name="Assistant is typing")).to_have_count(0, timeout=60_000)
    reply1 = panel.get_by_test_id("chat-bot").last.locator("p").first.inner_text()
    pg.wait_for_timeout(500)
    pg.screenshot(path=OUT / "1_price_inventory_chat.png")
    print("REPLY 1:", reply1)

    # 2. Dynamic category cards (live)
    pg.goto(WEB)
    pg.get_by_role("button", name="Open chat").click()
    panel = pg.get_by_role("dialog", name="Campus Customs chat")
    panel.get_by_role("button", name="What hoodies do you have?").click()
    expect(panel.get_by_role("status", name="Assistant is typing")).to_have_count(0, timeout=60_000)
    cards = panel.get_by_test_id("chat-bot").last.get_by_test_id("chat-product")
    expect(cards).to_have_count(12)
    more = panel.locator(".chat-more").inner_text()
    pg.wait_for_timeout(600)
    pg.screenshot(path=OUT / "2_dynamic_category_cards.png")
    print("CARDS:", cards.count(), "|", more, "|", panel.get_by_test_id("chat-bot").last.locator("p").first.inner_text()[:120])

    # 3. Usability feature: normalized search ("1/4 zip" finds items named "1 4 Zip")
    pg.goto(WEB + "/products")
    pg.get_by_role("searchbox", name="Search products").fill("1/4 zip")
    expect(pg.get_by_test_id("result-status")).to_have_text("11 results for “1/4 zip”")
    pg.wait_for_timeout(600)
    pg.screenshot(path=OUT / "3_usability_normalized_search.png")
    print("SEARCH:", pg.get_by_test_id("result-status").inner_text())
    b.close()
