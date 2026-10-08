"""Request/response and agent-output models for the Campus Customs chat endpoint."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

MAX_MESSAGE_CHARS = 500
MAX_HISTORY_TURNS = 8


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=2000)


class ChatRequest(BaseModel):
    message: str
    # Guests only: signed-in users' history is loaded from the database instead.
    history: list[ChatTurn] = Field(default_factory=list, max_length=MAX_HISTORY_TURNS)
    # Product page the shopper is viewing (for "do you have this in pink?"). Validated against the catalogue.
    product_id: str | None = Field(default=None, max_length=120, pattern=r"^[a-z0-9-]+$")

    @field_validator("message")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Please type a message.")
        if len(value) > MAX_MESSAGE_CHARS:
            raise ValueError(f"Messages can be at most {MAX_MESSAGE_CHARS} characters.")
        return value


class AgentReply(BaseModel):
    """Structured output the agent must return."""

    reply: str = Field(description="Short, friendly answer for the shopper. Plain text, no markdown tables.")
    product_ids: list[str] = Field(
        default_factory=list,
        max_length=4,
        description="ids of specific products discussed in the reply (e.g. the item whose price or stock was "
        "asked about), copied exactly from tool results. search_catalogue matches are shown automatically; "
        "don't repeat them here. Empty if none.",
    )


# ---------- Structured tool results (every value comes from the database) ----------

class ProductDescription(BaseModel):
    """Result of get_product_description."""

    found: bool
    product_id: str
    name: str | None = None
    garment_type: str | None = None
    description: str | None = None
    colors: list[str] = Field(default_factory=list)
    message: str | None = None


class ProductPrice(BaseModel):
    """Result of get_product_price."""

    found: bool
    product_id: str
    name: str | None = None
    price_usd: float | None = None
    price_display: str | None = None
    message: str | None = None


class SizeStock(BaseModel):
    size: str
    quantity: int
    in_stock: bool


class TotalInventory(BaseModel):
    """Result of get_total_inventory."""

    found: bool
    product_id: str
    name: str | None = None
    total_quantity: int | None = None
    in_stock: bool | None = None
    sizes: list[SizeStock] = Field(default_factory=list)
    sizes_in_stock: list[str] = Field(default_factory=list)
    sizes_out_of_stock: list[str] = Field(default_factory=list)
    message: str | None = None


class SizeInventory(BaseModel):
    """Result of get_size_inventory."""

    found: bool
    product_id: str
    name: str | None = None
    requested_size: str
    size: str | None = None
    size_offered: bool | None = None
    quantity: int | None = None
    in_stock: bool | None = None
    offered_sizes: list[str] = Field(default_factory=list)
    sizes_in_stock: list[str] = Field(default_factory=list)
    message: str | None = None


Category = Literal["t-shirt", "long-sleeve", "crewneck", "hoodie", "quarter-zip", "jacket"]
MAX_MATCHES = 12  # cards returned per reply; total_matches says how many exist


class ProductMatch(BaseModel):
    """One database-grounded product card."""

    id: str
    name: str
    image_path: str | None = Field(description="catalogue.image_file_path, e.g. products/yale-dad-hoodie.jpg")
    image_url: str | None = Field(description="Served URL for image_path; null if the file is missing")
    price_cents: int
    price_display: str
    short_description: str = Field(description="First sentence of catalogue.description (max 140 chars)")


class CatalogueSearch(BaseModel):
    """Result of search_catalogue."""

    category: Category | None
    keywords: list[str]
    max_price_dollars: float | None = None
    total_matches: int
    matches: list[ProductMatch] = Field(description=f"First {MAX_MATCHES} matches")
    relaxed: bool = Field(default=False, description="True if no product matched every word (closest matches shown)")
    message: str | None = None


class ChatResponse(BaseModel):
    """What the frontend receives: the reply plus product cards built from the database, not from the model."""

    reply: str
    matches: list[ProductMatch]
    total_matches: int = Field(description="How many products the catalogue search found (may exceed len(matches))")
    view_all_url: str | None = Field(default=None, description="Storefront link listing every match, e.g. /products?type=hoodie")


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    matches: list[ProductMatch] = Field(default_factory=list)
    created_at: str


class ChatHistory(BaseModel):
    messages: list[HistoryMessage]
