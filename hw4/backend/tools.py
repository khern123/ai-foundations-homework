"""Read-only catalogue and inventory tools for the Campus Customs agent.

Every fact the agent can state comes from these tools. They read the course database through a
read-only connection (app.db) with parameterized queries, and never guess: unknown products, sizes
that aren't offered, and sold-out sizes each come back as explicit structured results.
Shipping, returns, discounts and order status are not in the data.
"""

import re
from dataclasses import dataclass, field

from pydantic_ai import RunContext

import search
from app import db
from models import (
    MAX_MATCHES,
    CatalogueSearch,
    Category,
    ProductDescription,
    ProductMatch,
    ProductPrice,
    SizeInventory,
    SizeStock,
    TotalInventory,
)

NOT_IN_DATA = "Shipping, returns, discounts and order status are not in the data. Do not state or guess them."
SIZE_ALIASES = {
    "xs": "XS", "x-small": "XS", "xsmall": "XS", "extra small": "XS", "extra-small": "XS",
    "s": "S", "sm": "S", "small": "S",
    "m": "M", "med": "M", "medium": "M",
    "l": "L", "lg": "L", "large": "L",
    "xl": "XL", "x-large": "XL", "xlarge": "XL", "extra large": "XL", "extra-large": "XL",
    "xxl": "XXL", "2xl": "XXL", "xx-large": "XXL", "xxlarge": "XXL", "2x": "XXL", "double xl": "XXL",
}


@dataclass
class ChatDeps:
    # Product ids returned by tools during this run; only these may appear in the final reply.
    seen_ids: set[str] = field(default_factory=set)
    # search_catalogue results this run; the API returns these as product cards.
    searches: list[CatalogueSearch] = field(default_factory=list)
    # Session context. Only the signed-in user's name and email (from the database), never ids, hashes
    # or passwords; plus the product page being viewed (validated against the catalogue).
    shopper_name: str | None = None
    shopper_email: str | None = None
    page_product_id: str | None = None
    page_product_name: str | None = None


def _price(cents: int) -> str:
    return f"${cents / 100:.2f}"


def _not_found(product_id: str) -> str:
    return f"No product with id {product_id!r}. Use search_products to find valid ids; do not guess."


def normalize_size(size: str) -> str | None:
    """'medium' -> 'M', '2XL' -> 'XXL'. None if it isn't a recognisable size."""
    return SIZE_ALIASES.get(re.sub(r"\s+", " ", size.strip().lower()))


# ---------- Discovery ----------

def short_description(text: str, limit: int = 140) -> str:
    first = re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)[0]
    return first if len(first) <= limit else first[: limit - 1].rstrip(" ,;") + "…"


def to_match(p: dict) -> ProductMatch:
    """Card data straight from a catalogue row (via app.db)."""
    return ProductMatch(
        id=p["id"],
        name=p["name"],
        image_path=p["image_path"],
        image_url=p["image_url"],
        price_cents=p["price_cents"],
        price_display=_price(p["price_cents"]),
        short_description=short_description(p["description"]),
    )


def search_catalogue(
    ctx: RunContext[ChatDeps],
    category: Category | None = None,
    keywords: str = "",
    max_price_dollars: float | None = None,
) -> CatalogueSearch:
    """Browse the catalogue: use for "what hoodies do you have?", "show me navy crewnecks", "tees under $40".
    The matches are shown to the shopper as product cards.

    Args:
        category: One of t-shirt, long-sleeve, crewneck, hoodie, quarter-zip, jacket (map "tees"/"shirts" to
            t-shirt, "sweatshirts"/"crewnecks" to crewneck, "1/4 zips" to quarter-zip). Omit if none fits.
        keywords: Extra words that must ALL match, e.g. "navy", "davenport", "dad", "hockey". Don't repeat the category.
        max_price_dollars: Optional maximum price in US dollars.
    """
    max_cents = round(max_price_dollars * 100) if max_price_dollars is not None else None
    found = search.search(db.list_products(), keywords, category=category, max_price_cents=max_cents)
    category, terms, products = found["category"], found["terms"], found["results"]
    if category is None and not terms:
        result = CatalogueSearch(category=None, keywords=[], max_price_dollars=max_price_dollars, total_matches=0,
                                 matches=[], message="Give a category or keywords. Use list_categories for an overview.")
        ctx.deps.searches.append(result)
        return result

    matches = [to_match(p) for p in products[:MAX_MATCHES]]
    if not products:
        message = "No products match. Say so plainly; do not suggest items that weren't returned."
    elif found["relaxed"]:
        message = "No product matched every word; these match the most words. Say they're the closest matches."
    else:
        message = None
    result = CatalogueSearch(
        category=category, keywords=terms, max_price_dollars=max_price_dollars,
        total_matches=len(products), matches=matches, relaxed=found["relaxed"], message=message,
    )
    ctx.deps.seen_ids.update(m.id for m in matches)
    ctx.deps.searches.append(result)
    return result


def _summary(p: dict) -> dict:
    return {
        "id": p["id"],
        "name": p["name"],
        "type": p["garment_type"],
        "price": _price(p["price_cents"]),
        "colors": p["colors"],
    }


def search_products(
    ctx: RunContext[ChatDeps],
    query: str,
    product_type: str | None = None,
    max_price_dollars: float | None = None,
    limit: int = 6,
) -> dict:
    """Look up a specific item's product_id (e.g. "Davenport College Crewneck") before asking about its
    price, description or stock. For browsing a category, use search_catalogue instead.

    Args:
        query: Keywords from the shopper's request.
        product_type: Optional filter: one of t-shirt, long-sleeve, crewneck, hoodie, quarter-zip, jacket.
        max_price_dollars: Optional maximum price in US dollars.
        limit: Maximum results to return (1-8).
    """
    category = product_type.strip().lower() if product_type else None
    max_cents = round(max_price_dollars * 100) if max_price_dollars is not None else None
    products = search.search(db.list_products(), query, category=category, max_price_cents=max_cents)["results"]
    results = [_summary(p) for p in products[: max(1, min(limit, 8))]]
    ctx.deps.seen_ids.update(r["id"] for r in results)
    return {"results": results, "total_matches": len(products), "note": NOT_IN_DATA}


def list_categories(ctx: RunContext[ChatDeps]) -> dict:
    """Product categories in the catalogue with item counts and price ranges."""
    by_type: dict[str, list[int]] = {}
    for p in db.list_products():
        by_type.setdefault(p["product_type"], []).append(p["price_cents"])
    return {
        "categories": [
            {"type": t, "items": len(prices), "price_range": f"{_price(min(prices))}-{_price(max(prices))}"}
            for t, prices in sorted(by_type.items())
        ],
    }


# ---------- Product facts ----------

def get_product_description(ctx: RunContext[ChatDeps], product_id: str) -> ProductDescription:
    """Catalogue description, garment type and colors for one product.

    Args:
        product_id: Exact product id from search_products, e.g. "yale-dad-hoodie".
    """
    p = db.get_product(product_id.strip())
    if p is None:
        return ProductDescription(found=False, product_id=product_id, message=_not_found(product_id))
    ctx.deps.seen_ids.add(p["id"])
    return ProductDescription(
        found=True, product_id=p["id"], name=p["name"], garment_type=p["garment_type"],
        description=p["description"], colors=p["colors"],
    )


def get_product_price(ctx: RunContext[ChatDeps], product_id: str) -> ProductPrice:
    """Current catalogue price for one product.

    Args:
        product_id: Exact product id from search_products.
    """
    p = db.get_product(product_id.strip())
    if p is None:
        return ProductPrice(found=False, product_id=product_id, message=_not_found(product_id))
    ctx.deps.seen_ids.add(p["id"])
    return ProductPrice(
        found=True, product_id=p["id"], name=p["name"],
        price_usd=p["price_cents"] / 100, price_display=_price(p["price_cents"]),
    )


# ---------- Inventory ----------

def get_total_inventory(ctx: RunContext[ChatDeps], product_id: str) -> TotalInventory:
    """Total units in stock for one product, with the per-size breakdown.

    Args:
        product_id: Exact product id from search_products.
    """
    p = db.get_product(product_id.strip())
    if p is None:
        return TotalInventory(found=False, product_id=product_id, message=_not_found(product_id))
    ctx.deps.seen_ids.add(p["id"])
    stock = db.get_inventory(p["id"])
    if not stock:
        return TotalInventory(found=True, product_id=p["id"], name=p["name"],
                              message="No inventory records for this product. Stock is unknown; do not guess.")
    sizes = [SizeStock(size=s, quantity=q, in_stock=q > 0) for s, q in stock]
    total = sum(q for _, q in stock)
    return TotalInventory(
        found=True, product_id=p["id"], name=p["name"], total_quantity=total, in_stock=total > 0,
        sizes=sizes,
        sizes_in_stock=[s.size for s in sizes if s.in_stock],
        sizes_out_of_stock=[s.size for s in sizes if not s.in_stock],
    )


def get_size_inventory(ctx: RunContext[ChatDeps], product_id: str, size: str) -> SizeInventory:
    """Units in stock for one product in one size (XS, S, M, L, XL, XXL; words like "medium" work too).

    Args:
        product_id: Exact product id from search_products.
        size: The size the shopper asked about.
    """
    p = db.get_product(product_id.strip())
    if p is None:
        return SizeInventory(found=False, product_id=product_id, requested_size=size, message=_not_found(product_id))
    ctx.deps.seen_ids.add(p["id"])
    stock = dict(db.get_inventory(p["id"]))
    base = dict(
        found=True, product_id=p["id"], name=p["name"], requested_size=size,
        offered_sizes=list(stock), sizes_in_stock=[s for s, q in stock.items() if q > 0],
    )
    norm = normalize_size(size)
    if norm is None or norm not in stock:
        offered = ", ".join(stock) or "none recorded"
        return SizeInventory(**base, size=norm, size_offered=False,
                             message=f"Size {size!r} is not offered for this product. Offered sizes: {offered}.")
    qty = stock[norm]
    return SizeInventory(
        **base, size=norm, size_offered=True, quantity=qty, in_stock=qty > 0,
        message=None if qty > 0 else f"Size {norm} is out of stock.",
    )


TOOLS = [
    search_catalogue,
    search_products,
    list_categories,
    get_product_description,
    get_product_price,
    get_total_inventory,
    get_size_inventory,
]
