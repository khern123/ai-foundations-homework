import json
import re

from playwright.sync_api import Page, expect

from conftest import WEB_URL

NAV = [
    ("Home", "/", "Wear your campus."),
    ("Products", "/products", "Shop Campus Customs"),
    ("About Us", "/about", "Made on campus"),
    ("Log in", "/login", "Log in"),
    ("Create account", "/signup", "Create account"),
]


def nav(page: Page):
    return page.get_by_role("navigation", name="Main")


# ---------- Navigation ----------

def test_navigation_links_reach_each_page(page: Page):
    page.goto(WEB_URL)
    for label, path, heading in NAV:
        nav(page).get_by_role("link", name=label, exact=True).click()
        expect(page).to_have_url(WEB_URL + path)
        expect(page.get_by_role("heading", level=1)).to_contain_text(heading)


def test_unknown_route_shows_not_found(page: Page):
    page.goto(WEB_URL + "/nowhere")
    expect(page.get_by_role("heading", name="Page not found")).to_be_visible()


# ---------- Product cards ----------

def test_products_page_lists_every_catalogue_item(page: Page):
    page.goto(WEB_URL + "/products")
    cards = page.get_by_test_id("product-card")
    expect(cards).to_have_count(102)
    first = cards.first
    expect(first.locator("img")).to_have_attribute("src", re.compile(r"/images/products/.+\.jpg$"))
    expect(first.locator("h3")).not_to_be_empty()
    expect(first.locator(".price")).to_have_text(re.compile(r"^\$\d+\.\d{2}$"))
    expect(first.locator(".product-card-desc")).not_to_be_empty()


def test_type_filter(page: Page):
    page.goto(WEB_URL + "/products")
    page.get_by_role("button", name="Hoodies").click()
    expect(page).to_have_url(WEB_URL + "/products?type=hoodie")
    expect(page.get_by_test_id("product-card")).to_have_count(27)


def test_home_shows_featured_cards(page: Page):
    page.goto(WEB_URL)
    expect(page.get_by_test_id("product-card")).to_have_count(4)


# ---------- Detail links ----------

def test_each_card_opens_its_own_detail_page(page: Page):
    page.goto(WEB_URL + "/products")
    cards = page.get_by_test_id("product-card")
    expect(cards).to_have_count(102)
    targets = [(cards.nth(i).get_attribute("href"), cards.nth(i).locator("h3").inner_text()) for i in range(102)]
    assert len({href for href, _ in targets}) == 102  # every card links somewhere unique

    for href, name in targets[::17]:  # sample across the catalogue
        page.goto(WEB_URL + "/products")
        page.locator(f'a[href="{href}"]').click()
        expect(page).to_have_url(WEB_URL + href)
        expect(page.get_by_role("heading", level=1)).to_have_text(name)
        expect(page.locator(".detail-price")).to_have_text(re.compile(r"^\$\d+\.\d{2}$"))
        expect(page.locator(".detail-desc")).not_to_be_empty()


def test_detail_back_link_and_unknown_product(page_allow_errors: Page):
    page = page_allow_errors  # the unknown product deliberately returns a 404
    page.goto(WEB_URL + "/products/yale-dad-hoodie")
    expect(page.get_by_role("heading", level=1)).to_have_text("Yale Dad Hoodie")
    page.get_by_role("link", name="Back to all products").click()
    expect(page).to_have_url(WEB_URL + "/products")

    page.goto(WEB_URL + "/products/not-a-real-item")
    expect(page.get_by_role("heading", name="We couldn't find that item")).to_be_visible()


# ---------- Images ----------

def test_images_actually_load(page: Page):
    page.goto(WEB_URL + "/products")
    imgs = page.locator(".product-card img")
    expect(imgs).to_have_count(102)
    for i in range(102):  # scroll each into view so lazy images load
        img = imgs.nth(i)
        img.scroll_into_view_if_needed()
        expect(img).to_have_js_property("complete", True)
        assert img.evaluate("el => el.naturalWidth") > 0, img.get_attribute("src")
    expect(page.get_by_test_id("img-fallback")).to_have_count(0)


def test_broken_image_shows_fallback(page_allow_errors: Page):
    page = page_allow_errors  # image requests are deliberately aborted
    page.route("**/images/products/**", lambda route: route.abort())
    page.goto(WEB_URL + "/products")
    expect(page.get_by_test_id("img-fallback").first).to_be_visible()
    expect(page.get_by_test_id("img-fallback").first).to_contain_text("Photo coming soon")

    page.goto(WEB_URL + "/products/yale-dad-hoodie")
    expect(page.locator(".detail-media").get_by_test_id("img-fallback")).to_be_visible()


def test_null_image_url_shows_fallback(page: Page):
    def no_image(route):
        response = route.fetch()
        product = response.json()
        product["image_url"] = None
        route.fulfill(response=response, body=json.dumps(product))

    page.route("**/api/products/yale-dad-hoodie", no_image)
    page.goto(WEB_URL + "/products/yale-dad-hoodie")
    expect(page.get_by_test_id("img-fallback")).to_be_visible()
    expect(page.locator(".detail-media img")).to_have_count(0)


# ---------- Responsive ----------

def no_horizontal_overflow(page: Page) -> bool:
    return page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def grid_columns(page: Page) -> int:
    return page.locator(".product-grid").evaluate("el => getComputedStyle(el).gridTemplateColumns.split(' ').length")


def test_desktop_layout(page: Page):
    page.goto(WEB_URL + "/products")
    expect(page.get_by_test_id("product-card")).to_have_count(102)
    expect(page.get_by_role("button", name="Toggle navigation")).to_be_hidden()
    expect(nav(page)).to_be_visible()
    assert grid_columns(page) >= 4
    assert no_horizontal_overflow(page)


def test_mobile_layout_and_menu(page: Page):
    page.set_viewport_size({"width": 375, "height": 812})
    for path in ["/", "/products", "/products/yale-dad-hoodie", "/about", "/login", "/signup"]:
        page.goto(WEB_URL + path)
        expect(page.get_by_role("heading", level=1)).to_be_visible()
        assert no_horizontal_overflow(page), path

    page.goto(WEB_URL + "/products")
    expect(page.get_by_test_id("product-card")).to_have_count(102)
    assert grid_columns(page) == 2

    toggle = page.get_by_role("button", name="Toggle navigation")
    expect(nav(page)).to_be_hidden()
    toggle.click()
    expect(nav(page)).to_be_visible()
    nav(page).get_by_role("link", name="About Us").click()
    expect(page).to_have_url(WEB_URL + "/about")
    expect(nav(page)).to_be_hidden()  # menu closes after navigating


def test_detail_stacks_on_mobile(page: Page):
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(WEB_URL + "/products/yale-dad-hoodie")
    media = page.locator(".detail-media").bounding_box()
    info = page.locator(".detail-info").bounding_box()
    assert info["y"] >= media["y"] + media["height"] - 1


# ---------- Chat stub ----------

def test_chat_panel_opens_and_closes(page: Page):
    page.goto(WEB_URL)
    vw, vh = 1280, 900

    launcher = page.get_by_role("button", name="Open chat")
    box = launcher.bounding_box()
    assert box["x"] + box["width"] > vw - 60 and box["y"] + box["height"] > vh - 60  # bottom-right

    launcher.click()
    panel = page.get_by_role("dialog", name="Campus Customs chat")
    expect(panel).to_be_visible()
    expect(panel).to_contain_text("Campus Customs assistant")
    expect(panel.get_by_role("textbox", name="Chat message")).to_be_focused()

    page.keyboard.press("Escape")
    expect(panel).to_be_hidden()
    page.get_by_role("button", name="Open chat").click()
    panel.get_by_role("button", name="Close chat").click()
    expect(panel).to_be_hidden()
    # Sending messages is covered in test_chat_ui.py


def test_chat_fits_on_mobile(page: Page):
    page.set_viewport_size({"width": 375, "height": 667})
    page.goto(WEB_URL)
    page.get_by_role("button", name="Open chat").click()
    box = page.get_by_role("dialog", name="Campus Customs chat").bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= 375
    assert box["y"] >= 0
