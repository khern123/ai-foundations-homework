"""Campus Customs API (FastAPI).

Run (from hw4/backend), one process with auto-reload disabled:
  .\\.venv\\Scripts\\python.exe -m uvicorn main:app --port 8000
"""

import asyncio
import json
import logging
import os
from typing import Annotated

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")  # keep server logs clean

from fastapi import Depends, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from pydantic_ai.exceptions import UsageLimitExceeded

import audit
import search
from agent import MAX_MODEL_REQUESTS, AssistantUnavailable, run_chat
from app import auth, db, errors
from app.auth import current_user, require_user
from app.config import settings
from app.errors import AppError
from models import (
    MAX_HISTORY_TURNS,
    Category,
    ChatHistory,
    ChatRequest,
    ChatResponse,
    ChatTurn,
    HistoryMessage,
    ProductMatch,
)
from tools import to_match

log = logging.getLogger("campus_customs")
CHAT_TIMEOUT_SECONDS = 60

app = FastAPI(title=settings.app_name)
app.include_router(auth.router)
errors.install(app)  # one safe error shape + request ids; before CORS so errors get CORS headers too

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Product photos referenced by products.image_path
app.mount("/images", StaticFiles(directory=db.IMAGES_DIR, check_dir=False), name="images")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "campus-customs-api",
        "environment": settings.app_env,
    }


@app.get("/api/products")
def list_products() -> list[dict]:
    return db.list_products()


@app.get("/api/products/search")
def search_products(
    q: Annotated[str, Query(max_length=100)] = "",
    type: Annotated[Category | None, Query()] = None,
    max_price: Annotated[float | None, Query(ge=0, le=10_000)] = None,
) -> dict:
    """Normalized, deduplicated catalogue search (same engine as the chat's search tools)."""
    found = search.search(db.list_products(), q, category=type,
                          max_price_cents=round(max_price * 100) if max_price is not None else None)
    return {
        "query": q,
        "terms": found["terms"],
        "category": found["category"],
        "relaxed": found["relaxed"],
        "total": len(found["results"]),
        "results": found["results"],
    }


@app.get("/api/products/{product_id}")
def get_product(product_id: str) -> dict:
    product = db.get_product(product_id)
    if product is None:
        raise AppError(404, "We couldn't find that product.", "product_not_found")
    return product


def stored_matches(products_json: str | None) -> list[ProductMatch]:
    """Cards for a saved reply, rebuilt from the stored product ids and re-read from the catalogue.
    Works for this app's rows ("id") and the course's original rows ("product_id")."""
    try:
        items = json.loads(products_json or "[]")
    except ValueError:
        return []
    ids = [i.get("id") or i.get("product_id") for i in items if isinstance(i, dict)]
    return [to_match(p) for pid in dict.fromkeys(ids) if pid and (p := db.get_product(pid))]


def history_turns(user_id: int) -> list[ChatTurn]:
    """Signed-in users: the agent's conversation context comes from their saved messages, not the client."""
    return [ChatTurn(role=m["role"], content=m["content"][:2000])
            for m in db.get_chat_history(user_id, limit=MAX_HISTORY_TURNS)]


@app.get("/api/chat/history", response_model=ChatHistory)
def chat_history(user: Annotated[dict, Depends(require_user)]) -> ChatHistory:
    """The signed-in user's own messages. The user comes only from the session token; there is no user id parameter."""
    return ChatHistory(messages=[
        HistoryMessage(role=m["role"], content=m["content"], matches=stored_matches(m["products_json"]),
                       created_at=m["created_at"])
        for m in db.get_chat_history(user["id"])
    ])


@app.post("/api/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest, request: Request, user: Annotated[dict | None, Depends(current_user)]
) -> ChatResponse:
    """Structured chat. Guests: nothing is stored. Signed-in users: history comes from and is saved to the database.
    Errors never include internal details."""
    history = history_turns(user["id"]) if user else body.history
    rid = errors.request_id(request)

    def audit_failure(stop_reason: str, result: str) -> None:
        audit.append([audit.entry(rid, "run_end", args={"message_chars": len(body.message), "history_turns": len(history)},
                                  result=result, stop_reason=stop_reason, shopper="signed_in" if user else "guest",
                                  page_product_id=body.product_id)])

    try:
        response = await asyncio.wait_for(
            run_chat(body.message, history, shopper=user, page_product_id=body.product_id, run_id=rid),
            timeout=CHAT_TIMEOUT_SECONDS,
        )
        if user:
            try:
                db.save_chat_turn(user["id"], body.message, response.reply,
                                  json.dumps([m.model_dump() for m in response.matches]))
            except Exception as exc:  # the shopper still gets their answer
                log.error("[%s] saving chat failed: %s", errors.request_id(request), type(exc).__name__)
        return response
    except AssistantUnavailable as exc:
        log.warning("[%s] chat unavailable: %s", rid, exc)
        audit_failure("unavailable", "assistant not configured (no key or prompt)")
        raise AppError(503, "The assistant isn't available right now. Please try again later.", "assistant_unavailable")
    except TimeoutError:
        log.warning("[%s] chat timed out after %ss", rid, CHAT_TIMEOUT_SECONDS)
        audit_failure("timeout", f"no answer within {CHAT_TIMEOUT_SECONDS}s")
        raise AppError(504, "The assistant took too long to answer. Please try again.", "assistant_timeout")
    except UsageLimitExceeded:
        log.warning("[%s] chat hit the model request limit", rid)
        audit_failure("usage_limit", f"more than {MAX_MODEL_REQUESTS} model requests")
        raise AppError(502, "The assistant couldn't answer right now. Please try again.", "assistant_error")
    except Exception as exc:
        # Log only the error type: provider messages can echo request details.
        log.error("[%s] chat failed: %s", rid, type(exc).__name__)
        audit_failure("error", f"{type(exc).__name__}")
        raise AppError(502, "The assistant couldn't answer right now. Please try again.", "assistant_error")
