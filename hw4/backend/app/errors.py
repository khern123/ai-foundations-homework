"""Concise, safe error responses for every endpoint.

Every error has one shape:
    {"detail": "<short message>" | [{"field", "msg"}...], "code": "<machine code>", "request_id": "<8 hex>"}
- No stack traces, exception text, SQL, file paths or submitted values ever reach the client.
- Every response carries an X-Request-ID header; server logs use the same id, so a shopper can quote it.
- Validation messages are rewritten into plain English, one per field.
- Bodies over MAX_BODY_BYTES are refused with 413 before any parsing.
"""

import logging
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("campus_customs")

MAX_BODY_BYTES = 16 * 1024
CODES = {
    400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found", 405: "method_not_allowed",
    409: "conflict", 413: "too_large", 422: "validation_error", 429: "rate_limited", 500: "internal_error",
    502: "upstream_error", 503: "unavailable", 504: "timeout",
}
DEFAULT_MESSAGES = {
    404: "Not found.",
    405: "That action isn't allowed here.",
    413: "That request is too large.",
    500: "Something went wrong on our side. Please try again.",
}


class AppError(HTTPException):
    """HTTPException with a specific machine-readable code, e.g. AppError(503, "...", "assistant_unavailable")."""

    def __init__(self, status_code: int, message: str, code: str):
        super().__init__(status_code, message)
        self.code = code


def request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "-")


def error_json(request: Request, status: int, detail, code: str | None = None) -> JSONResponse:
    rid = request_id(request)
    return JSONResponse(
        status_code=status,
        content={"detail": detail, "code": code or CODES.get(status, "error"), "request_id": rid},
        headers={"X-Request-ID": rid},
    )


def friendly(err: dict) -> str:
    """Plain-English message for one pydantic validation error (never includes the submitted value)."""
    kind, ctx = err.get("type", ""), err.get("ctx") or {}
    field = str(err["loc"][-1]) if len(err.get("loc", ())) > 1 else ""
    msg = str(err.get("msg", ""))
    if kind == "missing":
        return "This field is required."
    if kind == "json_invalid":
        return "The request body isn't valid JSON."
    if kind == "string_too_short":
        return "This field can't be blank." if ctx.get("min_length") == 1 else f"Use at least {ctx.get('min_length')} characters."
    if kind == "string_too_long":
        return f"Use at most {ctx.get('max_length')} characters."
    if kind == "too_long":
        return f"Too many items (max {ctx.get('max_length')})."
    if kind == "string_pattern_mismatch":
        return "That value isn't in the expected format."
    if kind == "literal_error":
        return f"Must be one of {ctx.get('expected')}."
    if "email" in field and kind == "value_error":
        return "Enter a valid email address."
    if kind == "value_error":
        return msg.removeprefix("Value error, ")
    if kind.endswith("_type") or kind.endswith("_parsing"):
        return "That value has the wrong type."
    return "That value isn't valid."


def audit_rejected_chat(request: Request, status: int, reason: str) -> None:
    """Chat requests refused before reaching the agent are audited too (reason only, never the content)."""
    if request.url.path != "/api/chat":
        return
    import audit  # local import: audit depends on app.config

    audit.append([audit.entry(request_id(request), "rejected", result=f"HTTP {status}", stop_reason="rejected_input",
                              extra=reason)])


def install(app: FastAPI) -> None:
    """Register the middleware and handlers. Call before adding CORS, so CORS wraps error responses too."""

    @app.middleware("http")
    async def request_ids_and_limits(request: Request, call_next):
        request.state.request_id = uuid.uuid4().hex[:8]
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
            audit_rejected_chat(request, 413, f"body {length} bytes > {MAX_BODY_BYTES}")
            return error_json(request, 413, DEFAULT_MESSAGES[413])
        if request.method in {"POST", "PUT", "PATCH"} and not length:
            size = len(await request.body())  # chunked uploads without a length
            if size > MAX_BODY_BYTES:
                audit_rejected_chat(request, 413, f"body {size} bytes > {MAX_BODY_BYTES}")
                return error_json(request, 413, DEFAULT_MESSAGES[413])
        try:
            response = await call_next(request)
        except Exception:
            # Unexpected bug: full traceback goes to the server log only; the client gets a short message + id.
            log.exception("[%s] unhandled error on %s %s", request.state.request_id, request.method, request.url.path)
            return error_json(request, 500, DEFAULT_MESSAGES[500])
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) and exc.detail != "Not Found" else DEFAULT_MESSAGES.get(
            exc.status_code, "Request failed.")
        if exc.status_code == 405:
            detail = DEFAULT_MESSAGES[405]
        return error_json(request, exc.status_code, detail, getattr(exc, "code", None))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # FastAPI's default 422 echoes the submitted "input" (e.g. passwords). Return only field + message,
        # one message per field.
        seen: set = set()
        errors = []
        for e in exc.errors():
            field = str(e["loc"][-1]) if len(e["loc"]) > 1 else None
            if field in seen:
                continue
            seen.add(field)
            errors.append({"field": field, "msg": friendly(e)})
        audit_rejected_chat(request, 422, "; ".join(f"{e['field'] or 'body'}: {e['msg']}" for e in errors))
        return error_json(request, 422, errors)
