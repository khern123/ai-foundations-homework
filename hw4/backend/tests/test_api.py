import hashlib
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import db
from main import app

client = TestClient(app)


def db_hash() -> str:
    return hashlib.sha256(db.DB_PATH.read_bytes()).hexdigest()


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_products_list_has_full_catalogue():
    r = client.get("/api/products")
    assert r.status_code == 200
    products = r.json()
    assert len(products) == 102
    for p in products:
        assert p["name"] and p["description"] and p["garment_type"]
        assert isinstance(p["price_cents"], int) and p["price_cents"] > 0
        assert p["image_path"].startswith("products/")
        assert p["product_type"] in {"t-shirt", "long-sleeve", "crewneck", "hoodie", "quarter-zip", "jacket"}


def test_product_detail_uses_course_catalogue_and_404():
    r = client.get("/api/products/yale-dad-hoodie")
    assert r.status_code == 200
    p = r.json()
    assert (p["name"], p["price_cents"], p["garment_type"]) == ("Yale Dad Hoodie", 6800, "pullover hoodie")
    assert client.get("/api/products/does-not-exist").status_code == 404


def test_every_database_image_path_is_served():
    for p in client.get("/api/products").json():
        assert p["image_url"] == f"/images/{p['image_path']}"
        r = client.get(p["image_url"])
        assert r.status_code == 200, p["id"]
        assert r.headers["content-type"] == "image/jpeg"


def test_missing_image_file_gives_null_url(monkeypatch, tmp_path):
    # Point the images folder somewhere empty: the DB still has paths, but no files exist.
    monkeypatch.setattr(db, "IMAGES_DIR", tmp_path)
    p = client.get("/api/products/yale-dad-hoodie").json()
    assert p["image_path"] == "products/yale-dad-hoodie.jpg"
    assert p["image_url"] is None


def test_read_connection_is_read_only():
    conn = db.connect()
    try:
        for sql in ("DELETE FROM catalogue", "UPDATE inventory SET quantity = 99", "DROP TABLE users"):
            with pytest.raises(sqlite3.OperationalError):
                conn.execute(sql)
    finally:
        conn.close()


def test_read_endpoints_never_change_the_database():
    before = db_hash()
    client.get("/api/products")
    for pid in ("yale-dad-hoodie", "davenport-college-crewneck", "nope"):
        client.get(f"/api/products/{pid}")
    assert db_hash() == before


def test_course_tables_are_intact():
    with db.connect() as conn:
        counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("catalogue", "inventory")}
    assert counts == {"catalogue": 102, "inventory": 612}


def test_cors_allows_frontend_origin():
    r = client.options(
        "/api/products",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
