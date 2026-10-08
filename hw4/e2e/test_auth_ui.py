"""Browser tests for Create account / Log in (run against a throwaway DB copy)."""

import sqlite3
import uuid
from contextlib import closing

from playwright.sync_api import Page, expect

from conftest import WEB_URL

SEED_EMAIL, SEED_PASSWORD = "test@campuscustoms.yale.edu", "password"
NEW_PASSWORD = "Bulldog-Pass-2026"


def unique_email() -> str:
    return f"ada.{uuid.uuid4().hex[:8]}@yale.edu"


def signed_in(page: Page):
    return page.get_by_test_id("signed-in-user")


def log_in(page: Page, email: str, password: str) -> None:
    page.goto(WEB_URL + "/login")
    page.get_by_label("Email").fill(email)
    page.get_by_label("Password").fill(password)
    page.get_by_role("main").get_by_role("button", name="Log in").click()


def sign_up(page: Page, email: str, password=NEW_PASSWORD, confirm=None, first="Ada", last="Bulldog") -> None:
    page.goto(WEB_URL + "/signup")
    page.get_by_label("First name").fill(first)
    page.get_by_label("Last name").fill(last)
    page.get_by_label("Email").fill(email)
    page.get_by_label("Password", exact=True).fill(password)
    page.get_by_label("Confirm password").fill(confirm if confirm is not None else password)
    page.get_by_role("main").get_by_role("button", name="Create account").click()


def log_out(page: Page) -> None:
    page.get_by_role("button", name="Log out").click()
    expect(signed_in(page)).to_have_count(0)
    expect(page.get_by_role("navigation", name="Main").get_by_role("link", name="Log in")).to_be_visible()


def record_auth_traffic(page: Page) -> list[str]:
    bodies: list[str] = []
    page.on("response", lambda r: bodies.append(r.text()) if "/api/auth/" in r.url else None)
    return bodies


def stored_values(page: Page) -> str:
    return page.evaluate("JSON.stringify({...localStorage}) + JSON.stringify({...sessionStorage})")


# ---------- Seeded login ----------

def test_seeded_login_and_logout(page: Page):
    traffic = record_auth_traffic(page)
    log_in(page, SEED_EMAIL, SEED_PASSWORD)
    expect(page).to_have_url(WEB_URL + "/")
    expect(signed_in(page)).to_have_text("Hi, Test")

    page.reload()  # stays signed in for the tab session
    expect(signed_in(page)).to_have_text("Hi, Test")
    log_out(page)

    assert traffic and all('"password"' not in b and "scrypt$" not in b for b in traffic)


# ---------- New registration + new login ----------

def test_register_new_account_then_log_in(page: Page, test_db):
    email = unique_email()
    traffic = record_auth_traffic(page)

    sign_up(page, email)
    expect(page).to_have_url(WEB_URL + "/")
    expect(signed_in(page)).to_have_text("Hi, Ada")
    assert NEW_PASSWORD not in stored_values(page)
    log_out(page)

    log_in(page, email, NEW_PASSWORD)
    expect(page).to_have_url(WEB_URL + "/")
    expect(signed_in(page)).to_have_text("Hi, Ada")

    assert all(NEW_PASSWORD not in b and "scrypt$" not in b for b in traffic)
    with closing(sqlite3.connect(test_db)) as conn:
        stored = conn.execute("SELECT password_hash FROM users WHERE email = ?", (email,)).fetchone()[0]
    assert stored.startswith("scrypt$") and NEW_PASSWORD not in stored


# ---------- Incorrect passwords ----------

def test_wrong_password_is_rejected(page_allow_errors: Page):
    page = page_allow_errors  # the 401 response logs a console error
    for password in ("wrong-password", "Password"):
        log_in(page, SEED_EMAIL, password)
        expect(page.get_by_role("alert")).to_have_text("Invalid email or password.")
        expect(page).to_have_url(WEB_URL + "/login")
        expect(page.get_by_label("Password")).to_have_value("")  # rejected password is cleared
        expect(signed_in(page)).to_have_count(0)


def test_unknown_email_gets_same_message(page_allow_errors: Page):
    page = page_allow_errors
    log_in(page, unique_email(), SEED_PASSWORD)
    expect(page.get_by_role("alert")).to_have_text("Invalid email or password.")


# ---------- Duplicate emails ----------

def test_duplicate_email_is_rejected(page_allow_errors: Page):
    page = page_allow_errors  # the 409 response logs a console error
    sign_up(page, SEED_EMAIL.upper())
    expect(page.locator("#email-error")).to_have_text("An account with this email already exists.")
    expect(page).to_have_url(WEB_URL + "/signup")
    expect(signed_in(page)).to_have_count(0)


# ---------- Password confirmation + validation ----------

def test_password_confirmation_mismatch_blocks_submit(page: Page):
    posts = []
    page.on("request", lambda r: posts.append(r.url) if r.method == "POST" else None)
    sign_up(page, unique_email(), confirm="Different-Pass-2026")
    expect(page.locator("#confirm_password-error")).to_have_text("Passwords do not match.")
    expect(page).to_have_url(WEB_URL + "/signup")
    assert posts == []  # caught before anything is sent


def test_empty_and_invalid_fields_show_errors(page: Page):
    posts = []
    page.on("request", lambda r: posts.append(r.url) if r.method == "POST" else None)
    page.goto(WEB_URL + "/signup")
    page.get_by_role("main").get_by_role("button", name="Create account").click()
    for field in ("first_name", "last_name", "email", "password", "confirm_password"):
        expect(page.locator(f"#{field}-error")).to_be_visible()

    sign_up(page, "not-an-email", password="short", confirm="short")
    expect(page.locator("#email-error")).to_have_text("Enter a valid email address.")
    expect(page.locator("#password-error")).to_have_text("Use at least 8 characters.")

    page.goto(WEB_URL + "/login")
    page.get_by_role("main").get_by_role("button", name="Log in").click()
    expect(page.locator("#email-error")).to_be_visible()
    expect(page.locator("#password-error")).to_be_visible()
    assert posts == []


# ---------- Password secrecy ----------

def test_password_fields_are_masked(page: Page):
    page.goto(WEB_URL + "/signup")
    expect(page.get_by_label("Password", exact=True)).to_have_attribute("type", "password")
    expect(page.get_by_label("Confirm password")).to_have_attribute("type", "password")
    page.goto(WEB_URL + "/login")
    expect(page.get_by_label("Password")).to_have_attribute("type", "password")


def test_password_never_leaves_a_trace_after_login(page: Page):
    traffic = record_auth_traffic(page)
    log_in(page, SEED_EMAIL, SEED_PASSWORD)
    expect(signed_in(page)).to_be_visible()
    assert '"password"' not in stored_values(page)
    assert "password_hash" not in stored_values(page)
    assert all('"password"' not in b for b in traffic)
    assert '"password"' not in page.content()
