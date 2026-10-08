"""Access to the course Campus Customs database (SQLite).

Tables (course schema, never altered by this app):
  catalogue(product_id, name, garment_type, description, colors, search_tags, image_file_path, price)
  inventory(product_id, size, quantity)          -- sizes XS..XXL
  users(id, name, email, password_hash, created_at, first_name, last_name)
  chat_messages(...)                             -- not used yet

Catalogue and inventory are read through a read-only connection. Only `users` is ever written
(new registrations). Every query is parameterized.
"""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from .config import settings

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DB_PATH = settings.database_path
# catalogue.image_file_path is relative to this folder, e.g. "products/yale-dad-hoodie.jpg"
IMAGES_DIR = DATA_DIR / "images"

SIZE_ORDER = ["XS", "S", "M", "L", "XL", "XXL"]
CATALOGUE_COLUMNS = "product_id, name, garment_type, description, colors, search_tags, image_file_path, price"


def connect() -> sqlite3.Connection:
    # Open read-only so catalogue/inventory reads can never modify the database.
    conn = sqlite3.connect(f"{DB_PATH.as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def connect_rw() -> sqlite3.Connection:
    """Writable connection, used only for inserting into the users table."""
    conn = sqlite3.connect(f"{DB_PATH.as_uri()}?mode=rw", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def category(garment_type: str) -> str:
    """Map the catalogue's free-text garment_type to one of six shop categories (for filters)."""
    g = garment_type.lower()
    if "t-shirt" in g or "t shirt" in g:
        return "t-shirt"
    if "quarter-zip" in g:
        return "quarter-zip"
    if "hood" in g:
        return "hoodie"
    if "jacket" in g:
        return "jacket"
    if "long-sleeve" in g:
        return "long-sleeve"
    return "crewneck"  # crewneck / raglan / mockneck sweatshirts


def image_url(image_path: str | None) -> str | None:
    """Public URL for a stored image path, or None when the file is missing."""
    if not image_path or not (IMAGES_DIR / image_path).is_file():
        return None
    return f"/images/{image_path}"


def row_to_product(row: sqlite3.Row) -> dict:
    return {
        "id": row["product_id"],
        "name": row["name"],
        "product_type": category(row["garment_type"]),
        "garment_type": row["garment_type"],
        "price_cents": round(row["price"] * 100),
        "description": row["description"],
        "image_path": row["image_file_path"],
        "image_url": image_url(row["image_file_path"]),
        "colors": json.loads(row["colors"]),
        "tags": json.loads(row["search_tags"]),
    }


def list_products() -> list[dict]:
    with closing(connect()) as conn:
        rows = conn.execute(f"SELECT {CATALOGUE_COLUMNS} FROM catalogue ORDER BY name").fetchall()
    return [row_to_product(r) for r in rows]


def get_product(product_id: str) -> dict | None:
    with closing(connect()) as conn:
        row = conn.execute(
            f"SELECT {CATALOGUE_COLUMNS} FROM catalogue WHERE product_id = ?", (product_id,)
        ).fetchone()
    return row_to_product(row) if row else None


def get_inventory(product_id: str) -> list[tuple[str, int]]:
    """[(size, quantity), ...] in XS..XXL order. Empty if the product has no inventory rows."""
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT size, quantity FROM inventory WHERE product_id = ?", (product_id,)
        ).fetchall()
    order = {s: i for i, s in enumerate(SIZE_ORDER)}
    return sorted(((r["size"], r["quantity"]) for r in rows), key=lambda sq: order.get(sq[0], len(order)))


# ---------- Users ----------

class DuplicateEmailError(Exception):
    pass


def get_user_by_email(email: str) -> dict | None:
    """User including password_hash. Never return this directly from the API."""
    with closing(connect()) as conn:
        row = conn.execute(
            "SELECT id, name, first_name, last_name, email, password_hash FROM users WHERE lower(email) = ?",
            (email.lower(),),
        ).fetchone()
    if row is None:
        return None
    # Older rows may only have `name`; split it if first/last are empty.
    first, last = row["first_name"], row["last_name"]
    if not first:
        first, _, last = (row["name"] or "").partition(" ")
    return {
        "id": row["id"],
        "first_name": first,
        "last_name": last or "",
        "email": row["email"],
        "password_hash": row["password_hash"],
    }


def get_user_public(user_id: int) -> dict | None:
    """{id, name, email} only, never the password hash. Used for session lookups and agent context."""
    with closing(connect()) as conn:
        row = conn.execute(
            "SELECT id, name, first_name, last_name, email FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    if row is None:
        return None
    name = row["name"] or f"{row['first_name'] or ''} {row['last_name'] or ''}".strip()
    return {"id": row["id"], "name": name, "first_name": row["first_name"] or name.partition(" ")[0], "email": row["email"]}


# ---------- Chat history (course table chat_messages) ----------

def save_chat_turn(user_id: int, user_text: str, reply_text: str, products_json: str) -> None:
    """Store one exchange for a signed-in user. Parameterized; only ever inserts."""
    with closing(connect_rw()) as conn, conn:
        conn.executemany(
            "INSERT INTO chat_messages (user_id, role, content, products_json) VALUES (?, ?, ?, ?)",
            [(user_id, "user", user_text, None), (user_id, "assistant", reply_text, products_json)],
        )


def get_chat_history(user_id: int, limit: int = 50) -> list[dict]:
    """The user's own most recent messages, oldest first. Always filtered by the session's user id."""
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT id, role, content, products_json, created_at FROM chat_messages "
            "WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def create_user(first_name: str, last_name: str, email: str, password_hash: str) -> int:
    with closing(connect_rw()) as conn, conn:
        # users.email is UNIQUE but case-sensitive in the course schema, so check case-insensitively too.
        if conn.execute("SELECT 1 FROM users WHERE lower(email) = ?", (email.lower(),)).fetchone():
            raise DuplicateEmailError(email)
        try:
            cur = conn.execute(
                "INSERT INTO users (name, first_name, last_name, email, password_hash) VALUES (?, ?, ?, ?, ?)",
                (f"{first_name} {last_name}", first_name, last_name, email, password_hash),
            )
        except sqlite3.IntegrityError as exc:
            raise DuplicateEmailError(email) from exc
        return cur.lastrowid
