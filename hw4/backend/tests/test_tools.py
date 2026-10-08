"""Catalogue/inventory tools: every value checked against direct SQL on the course database."""

import hashlib
import shutil
import sqlite3
from contextlib import closing

import pytest
from pydantic_ai import RunContext

from app import db
from models import ProductDescription, ProductPrice, SizeInventory, TotalInventory
from tools import (
    ChatDeps,
    get_product_description,
    get_product_price,
    get_size_inventory,
    get_total_inventory,
    list_categories,
    normalize_size,
    search_products,
)

UNKNOWN = "yale-unicorn-onesie"


def ctx() -> RunContext[ChatDeps]:
    return RunContext(deps=ChatDeps(), model=None, usage=None, prompt=None)  # type: ignore[arg-type]


def sql(query: str, *params):
    """Independent read of the database: the expected values the tools must match."""
    with closing(sqlite3.connect(f"{db.DB_PATH.as_uri()}?mode=ro", uri=True)) as conn:
        return conn.execute(query, params).fetchall()


ALL_IDS = [r[0] for r in sql("SELECT product_id FROM catalogue ORDER BY product_id")]


# ---------- Real descriptions ----------

def test_description_matches_catalogue_for_every_product():
    for pid in ALL_IDS:
        r = get_product_description(ctx(), pid)
        assert isinstance(r, ProductDescription) and r.found
        name, garment, desc = sql("SELECT name, garment_type, description FROM catalogue WHERE product_id=?", pid)[0]
        assert (r.name, r.garment_type, r.description) == (name, garment, desc)


def test_description_example():
    r = get_product_description(ctx(), "davenport-college-crewneck")
    assert r.name == "Davenport College Crewneck" and r.garment_type == "crewneck sweatshirt"
    assert r.description.startswith(sql("SELECT description FROM catalogue WHERE product_id='davenport-college-crewneck'")[0][0][:40])


# ---------- Real prices ----------

def test_price_matches_catalogue_for_every_product():
    for pid in ALL_IDS:
        r = get_product_price(ctx(), pid)
        (price,) = sql("SELECT price FROM catalogue WHERE product_id=?", pid)[0]
        assert isinstance(r, ProductPrice) and r.found
        assert r.price_usd == price and r.price_display == f"${price:.2f}"


@pytest.mark.parametrize("pid,display", [
    ("davenport-college-crewneck", "$58.00"),
    ("yale-dad-hoodie", "$68.00"),
    ("2025-yale-vs-harvard-t-shirt", "$32.00"),
])
def test_price_examples(pid, display):
    assert get_product_price(ctx(), pid).price_display == display


# ---------- Total stock ----------

def test_total_inventory_matches_sum_for_every_product():
    for pid in ALL_IDS:
        r = get_total_inventory(ctx(), pid)
        (total,) = sql("SELECT SUM(quantity) FROM inventory WHERE product_id=?", pid)[0]
        assert isinstance(r, TotalInventory) and r.found
        assert r.total_quantity == total and r.in_stock == (total > 0)
        assert sum(s.quantity for s in r.sizes) == total


def test_total_inventory_example():
    r = get_total_inventory(ctx(), "davenport-college-crewneck")
    assert r.total_quantity == 65  # 20 + 0 + 5 + 12 + 20 + 8
    assert [(s.size, s.quantity) for s in r.sizes] == [("XS", 20), ("S", 0), ("M", 5), ("L", 12), ("XL", 20), ("XXL", 8)]
    assert r.sizes_out_of_stock == ["S"]
    assert r.sizes_in_stock == ["XS", "M", "L", "XL", "XXL"]


# ---------- Size stock ----------

def test_size_inventory_matches_every_inventory_row():
    rows = sql("SELECT product_id, size, quantity FROM inventory")
    assert len(rows) == 612
    for pid, size, qty in rows:
        r = get_size_inventory(ctx(), pid, size)
        assert isinstance(r, SizeInventory)
        assert (r.found, r.size_offered, r.size, r.quantity, r.in_stock) == (True, True, size, qty, qty > 0)


@pytest.mark.parametrize("asked,size,qty", [
    ("M", "M", 5), ("medium", "M", 5), (" Medium ", "M", 5), ("xl", "XL", 20),
    ("extra large", "XL", 20), ("2XL", "XXL", 8), ("XXL", "XXL", 8), ("extra small", "XS", 20),
])
def test_size_aliases(asked, size, qty):
    r = get_size_inventory(ctx(), "davenport-college-crewneck", asked)
    assert (r.size, r.quantity, r.in_stock, r.requested_size) == (size, qty, True, asked)


# ---------- Out-of-stock sizes ----------

def test_every_zero_quantity_row_is_reported_out_of_stock():
    zeros = sql("SELECT product_id, size FROM inventory WHERE quantity = 0")
    assert len(zeros) == 145
    for pid, size in zeros:
        r = get_size_inventory(ctx(), pid, size)
        assert r.size_offered is True and r.quantity == 0 and r.in_stock is False
        assert r.message == f"Size {size} is out of stock."
        assert size not in r.sizes_in_stock


def test_out_of_stock_example_lists_alternatives():
    r = get_size_inventory(ctx(), "baseball-left-chest-crewneck", "XL")
    assert (r.quantity, r.in_stock) == (0, False)
    assert r.sizes_in_stock == ["S", "M", "L", "XXL"]


# ---------- Missing (not offered) sizes ----------

@pytest.mark.parametrize("asked", ["XXXL", "3XL", "4XL", "10", "one size", "", "kids M", "XXS"])
def test_sizes_not_offered(asked):
    r = get_size_inventory(ctx(), "yale-dad-hoodie", asked)
    assert r.found is True and r.size_offered is False
    assert r.quantity is None and r.in_stock is None  # no number is invented
    assert r.offered_sizes == ["XS", "S", "M", "L", "XL", "XXL"]
    assert "not offered" in r.message


def test_product_without_inventory_rows_reports_unknown(monkeypatch, tmp_path):
    copy = tmp_path / "db.sqlite"
    shutil.copy2(db.DB_PATH, copy)
    with closing(sqlite3.connect(copy)) as conn, conn:
        conn.execute("DELETE FROM inventory WHERE product_id = 'yale-dad-hoodie'")
    monkeypatch.setattr(db, "DB_PATH", copy)

    total = get_total_inventory(ctx(), "yale-dad-hoodie")
    assert total.found and total.total_quantity is None and total.in_stock is None
    assert "unknown" in total.message.lower()
    size = get_size_inventory(ctx(), "yale-dad-hoodie", "M")
    assert size.size_offered is False and size.quantity is None


# ---------- Unknown products ----------

@pytest.mark.parametrize("tool,args", [
    (get_product_description, ()),
    (get_product_price, ()),
    (get_total_inventory, ()),
    (get_size_inventory, ("M",)),
])
@pytest.mark.parametrize("pid", [UNKNOWN, "", "YALE-DAD-HOODIE", "yale dad hoodie"])
def test_unknown_products(tool, args, pid):
    c = ctx()
    r = tool(c, pid, *args)
    assert r.found is False and r.product_id == pid
    assert "No product with id" in r.message and "do not guess" in r.message
    dumped = r.model_dump()
    assert all(dumped[k] in (None, [], False) for k in dumped if k not in {"found", "product_id", "requested_size", "message"})
    assert c.deps.seen_ids == set()  # unknown ids can never become product cards


# ---------- Safety: parameterized, read-only ----------

@pytest.mark.parametrize("evil", ["x' OR '1'='1", "yale-dad-hoodie'; DROP TABLE inventory;--", "%", "_"])
def test_sql_injection_is_inert(evil):
    before = hashlib.sha256(db.DB_PATH.read_bytes()).hexdigest()
    assert get_product_price(ctx(), evil).found is False
    assert get_total_inventory(ctx(), evil).found is False
    r = get_size_inventory(ctx(), "yale-dad-hoodie", evil)
    assert r.size_offered is False
    assert sql("SELECT COUNT(*) FROM inventory")[0][0] == 612
    assert hashlib.sha256(db.DB_PATH.read_bytes()).hexdigest() == before


def test_tools_never_modify_the_database():
    before = hashlib.sha256(db.DB_PATH.read_bytes()).hexdigest()
    for pid in ALL_IDS + [UNKNOWN]:
        c = ctx()
        get_product_description(c, pid)
        get_product_price(c, pid)
        get_total_inventory(c, pid)
        for size in ("XS", "M", "XXXL"):
            get_size_inventory(c, pid, size)
    search_products(ctx(), "hoodie")
    list_categories(ctx())
    assert hashlib.sha256(db.DB_PATH.read_bytes()).hexdigest() == before


# ---------- Discovery tools ----------

def test_search_and_categories():
    c = ctx()
    found = search_products(c, "davenport crewneck")
    assert found["results"][0]["id"] == "davenport-college-crewneck"
    assert found["results"][0]["price"] == "$58.00"
    assert "davenport-college-crewneck" in c.deps.seen_ids
    cheap = search_products(c, "hoodie", product_type="hoodie", max_price_dollars=60)["results"]
    assert all(float(r["price"][1:]) <= 60 for r in cheap)
    assert {x["type"] for x in list_categories(c)["categories"]} == {
        "t-shirt", "long-sleeve", "crewneck", "hoodie", "quarter-zip", "jacket"}


def test_normalize_size():
    assert normalize_size("Medium") == "M" and normalize_size("2xl") == "XXL" and normalize_size("XXXL") is None
