"""Append-only audit trail: output/audit_trail.json (a JSON list).

One entry per tool call and one per run outcome:
  {timestamp, run_id, event, tool, args, result, stop_reason, model, shopper, page_product_id}
- Never recorded: keys, tokens, passwords, emails, user ids, chat message text or history.
  Only the message LENGTH is logged; args/results are short and redacted.
- Never erased: entries are only appended. Writes are serialized with a lock and replace the file
  atomically. An unreadable file is renamed to audit_trail.corrupt-<time>.json (kept), not overwritten.
"""

import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings

AUDIT_PATH = Path(os.getenv("AUDIT_PATH") or Path(__file__).resolve().parents[1] / "output" / "audit_trail.json")
MAX_FIELD = 160
_lock = threading.Lock()

_REDACTIONS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[email]"),
    (re.compile(r"(?i)bearer\s+\S+"), "Bearer [redacted]"),
    (re.compile(r"(?i)(api[_-]?key|password|secret|token)\s*[=:]\s*\S+"), r"\1=[redacted]"),
    (re.compile(r"\b(sk|pk)-[A-Za-z0-9_-]{6,}"), "[redacted-key]"),
    # Long token-like strings (hex/base64 secrets, hashes): 32+ chars with at least one digit. Hyphenated
    # product slugs like "davenport-college-crewneck" are not tokens and stay readable.
    (re.compile(r"(?<![\w-])(?=[A-Za-z0-9_+/=]*\d)[A-Za-z0-9_+/=]{32,}(?![\w-])"), "[redacted]"),
    (re.compile(r"(pbkdf2_sha256|scrypt)\$\S+"), "[redacted-hash]"),
]


def sanitize(value, limit: int = MAX_FIELD) -> str:
    """Short, redacted text for an argument or result."""
    text = value if isinstance(value, str) else json.dumps(value, default=str, separators=(",", ":"))
    for secret in (settings.portkey_api_key, settings.session_secret):
        if secret:
            text = text.replace(secret, "[redacted]")
    for pattern, repl in _REDACTIONS:
        text = pattern.sub(repl, text)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def summarize_result(content) -> str:
    """Compact description of a tool result (counts, found/not found, key values), not the full payload."""
    data = content.model_dump() if hasattr(content, "model_dump") else content
    if isinstance(data, dict):
        if "total_matches" in data and "matches" in data:  # CatalogueSearch
            s = f"total_matches={data['total_matches']}, shown={len(data['matches'])}"
            return s + (", relaxed" if data.get("relaxed") else "")
        if "results" in data:  # search_products
            return f"{len(data['results'])} results: " + ", ".join(r["id"] for r in data["results"][:3])
        if "categories" in data:
            return f"{len(data['categories'])} categories"
        if data.get("found") is False:
            return "not found"
        keys = ["product_id", "price_display", "total_quantity", "size", "size_offered", "quantity", "in_stock"]
        return ", ".join(f"{k}={data[k]}" for k in keys if data.get(k) is not None) or "ok"
    return sanitize(data)


def append(entries: list[dict]) -> None:
    """Append entries to the audit file without ever dropping existing ones."""
    if not entries:
        return
    with _lock:
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        existing: list = []
        if AUDIT_PATH.exists():
            try:
                existing = json.loads(AUDIT_PATH.read_text(encoding="utf-8") or "[]")
                if not isinstance(existing, list):
                    raise ValueError("not a list")
            except ValueError:
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
                AUDIT_PATH.rename(AUDIT_PATH.with_name(f"audit_trail.corrupt-{stamp}.json"))  # preserved, not erased
                existing = []
        tmp = AUDIT_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(existing + entries, indent=2), encoding="utf-8")
        tmp.replace(AUDIT_PATH)  # atomic: a crash can't leave a half-written file


def entry(run_id: str, event: str, *, tool: str | None = None, args=None, result=None, stop_reason: str,
          shopper: str = "guest", page_product_id: str | None = None, extra: str | None = None) -> dict:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "run_id": run_id,
        "event": event,  # "tool_call" | "run_end" | "rejected"
        "tool": tool,
        "args": sanitize(args) if args is not None else None,
        "result": result if result is None else sanitize(result),
        "stop_reason": stop_reason,
        "model": settings.chat_model,
        "shopper": shopper,  # "guest" or "signed_in": never a name, email or id
        "page_product_id": page_product_id,
        **({"detail": sanitize(extra)} if extra else {}),
    }
