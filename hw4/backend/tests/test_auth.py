import json
import shutil
import sqlite3
import uuid
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from app import db
from main import app

client = TestClient(app)

SEED_EMAIL, SEED_PASSWORD = "test@campuscustoms.yale.edu", "password"


@pytest.fixture(autouse=True)
def temp_db(monkeypatch, tmp_path):
    """Run every auth test against a throwaway copy so the real database is never written."""
    copy = tmp_path / "campus_customs.db"
    shutil.copy2(db.DB_PATH, copy)
    monkeypatch.setattr(db, "DB_PATH", copy)
    return copy


def new_account(**overrides) -> dict:
    body = {
        "first_name": "Ada",
        "last_name": "Bulldog",
        "email": f"ada.{uuid.uuid4().hex[:8]}@yale.edu",
        "password": "s3cure-pass!",
        "confirm_password": "s3cure-pass!",
    }
    body.update(overrides)
    return body


def assert_no_password(response, *passwords: str) -> None:
    text = response.text
    assert "password_hash" not in text and "scrypt$" not in text
    for p in passwords:
        assert json.dumps(p) not in text  # as a JSON value; the word "password" may appear in messages


# ---------- Seeded login ----------

def test_seeded_user_can_log_in():
    r = client.post("/api/auth/login", json={"email": SEED_EMAIL, "password": SEED_PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"user", "token"}
    assert body["user"] == {"id": 1, "first_name": "Test", "last_name": "User", "email": SEED_EMAIL}
    assert body["token"].startswith("1.")  # user id + expiry + signature only
    assert_no_password(r, SEED_PASSWORD)


def test_login_email_is_case_insensitive():
    r = client.post("/api/auth/login", json={"email": "  TEST@CampusCustoms.Yale.edu ", "password": SEED_PASSWORD})
    assert r.status_code == 200


# ---------- Registration + new login ----------

def test_register_then_log_in():
    body = new_account()
    r = client.post("/api/auth/register", json=body)
    assert r.status_code == 201
    user = r.json()["user"]
    assert user["email"] == body["email"] and user["first_name"] == "Ada" and user["last_name"] == "Bulldog"
    assert set(user) == {"id", "first_name", "last_name", "email"}
    assert_no_password(r, body["password"])

    r = client.post("/api/auth/login", json={"email": body["email"], "password": body["password"]})
    assert r.status_code == 200
    assert r.json()["user"]["id"] == user["id"]
    assert_no_password(r, body["password"])


def test_register_trims_names_and_lowercases_email():
    body = new_account(first_name="  Grace ", last_name=" Hopper  ", email="Grace.Hopper@Yale.EDU")
    user = client.post("/api/auth/register", json=body).json()["user"]
    assert (user["first_name"], user["last_name"], user["email"]) == ("Grace", "Hopper", "grace.hopper@yale.edu")


# ---------- Incorrect passwords ----------

@pytest.mark.parametrize(
    "email,password",
    [
        (SEED_EMAIL, "wrong-password"),
        (SEED_EMAIL, "Password"),  # case matters
        (SEED_EMAIL, "password "),
        ("nobody@yale.edu", "password"),  # unknown email gets the same answer
    ],
)
def test_bad_credentials_are_rejected_identically(email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid email or password."
    assert_no_password(r, password)


def test_login_validation():
    assert client.post("/api/auth/login", json={"email": "not-an-email", "password": "x"}).status_code == 422
    assert client.post("/api/auth/login", json={"email": SEED_EMAIL, "password": ""}).status_code == 422
    assert client.post("/api/auth/login", json={"email": SEED_EMAIL}).status_code == 422


# ---------- Duplicate emails ----------

def test_duplicate_email_rejected_case_insensitively():
    body = new_account()
    assert client.post("/api/auth/register", json=body).status_code == 201
    for email in (body["email"], body["email"].upper()):
        r = client.post("/api/auth/register", json=new_account(email=email))
        assert r.status_code == 409
        assert r.json()["detail"] == "An account with this email already exists."


def test_seeded_email_cannot_be_registered_again():
    r = client.post("/api/auth/register", json=new_account(email=SEED_EMAIL))
    assert r.status_code == 409


# ---------- Password confirmation + validation ----------

def test_password_confirmation_must_match():
    body = new_account(confirm_password="different-pass!")
    r = client.post("/api/auth/register", json=body)
    assert r.status_code == 422
    assert {"field": None, "msg": "Passwords do not match."} in r.json()["detail"]
    assert_no_password(r, body["password"], body["confirm_password"])
    assert db.get_user_by_email(body["email"]) is None


@pytest.mark.parametrize(
    "overrides,field",
    [
        ({"first_name": "   "}, "first_name"),
        ({"last_name": ""}, "last_name"),
        ({"first_name": "x" * 51}, "first_name"),
        ({"email": "not-an-email"}, "email"),
        ({"password": "short7!", "confirm_password": "short7!"}, "password"),
        ({"password": "p" * 129, "confirm_password": "p" * 129}, "password"),
    ],
)
def test_register_validation(overrides, field):
    body = new_account(**overrides)
    r = client.post("/api/auth/register", json=body)
    assert r.status_code == 422
    assert field in [e["field"] for e in r.json()["detail"]]
    assert_no_password(r, body["password"])


def test_register_requires_every_field():
    for missing in ("first_name", "last_name", "email", "password", "confirm_password"):
        body = new_account()
        del body[missing]
        assert client.post("/api/auth/register", json=body).status_code == 422, missing


# ---------- Password secrecy ----------

def test_passwords_are_stored_as_salted_scrypt_hashes(temp_db):
    a = new_account(password="same-password-1", confirm_password="same-password-1")
    b = new_account(password="same-password-1", confirm_password="same-password-1")
    client.post("/api/auth/register", json=a)
    client.post("/api/auth/register", json=b)

    with closing(sqlite3.connect(temp_db)) as conn:
        hashes = dict(conn.execute("SELECT email, password_hash FROM users").fetchall())
        names = dict(conn.execute("SELECT email, name FROM users").fetchall())
        columns = [c[1] for c in conn.execute("PRAGMA table_info(users)")]

    assert "password" not in columns and "password_hash" in columns
    assert hashes[a["email"]].startswith("scrypt$") and hashes[b["email"]].startswith("scrypt$")  # new accounts
    assert hashes[SEED_EMAIL].startswith("pbkdf2_sha256$")  # course account left exactly as it was
    assert all(h.startswith(("scrypt$", "pbkdf2_sha256$")) for h in hashes.values())
    assert all("password" not in h.split("$", 1)[1] for h in hashes.values())  # no plain text anywhere
    assert hashes[a["email"]] != hashes[b["email"]]  # unique salt per user
    assert names[a["email"]] == "Ada Bulldog"  # course schema's required `name` column is filled


def test_existing_course_accounts_are_not_rewritten(temp_db):
    with closing(sqlite3.connect(temp_db)) as conn:
        before = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    client.post("/api/auth/login", json={"email": SEED_EMAIL, "password": SEED_PASSWORD})
    client.post("/api/auth/login", json={"email": SEED_EMAIL, "password": "wrong-password"})
    with closing(sqlite3.connect(temp_db)) as conn:
        assert conn.execute("SELECT * FROM users ORDER BY id").fetchall() == before


def test_no_endpoint_exposes_users():
    paths = set(app.openapi()["paths"])
    assert {p for p in paths if p.startswith("/api/auth")} == {"/api/auth/register", "/api/auth/login"}
    assert not any("user" in p for p in paths)
    assert client.get("/api/auth/login").status_code == 405
