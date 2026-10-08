"""Audit trail: successful/failed tools, empty results, oversized input, model/API errors, append safety, privacy."""

import asyncio
import json
import shutil
import threading
import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

import agent as agent_module
import audit
import main
from app import db
from app.config import settings
from main import app

client = TestClient(app)
FAKE_KEY = "sk-live-FAKEKEY1234567890abcdef"


def scripted(tool_calls, reply="Done."):
    def fn(messages, info: AgentInfo) -> ModelResponse:
        step = sum(1 for m in messages for p in m.parts if isinstance(p, ToolReturnPart))
        if step < len(tool_calls):
            return ModelResponse(parts=[ToolCallPart(*tool_calls[step])])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"reply": reply, "product_ids": []})])
    return FunctionModel(fn)


@pytest.fixture
def use_model():
    ctxs = []

    def _use(model):
        c = agent_module.build_agent().override(model=model)
        c.__enter__()
        ctxs.append(c)
    yield _use
    for c in ctxs:
        c.__exit__(None, None, None)


def entries(path):
    return json.loads(path.read_text(encoding="utf-8"))


def chat(message="hello", **kw):
    return client.post("/api/chat", json={"message": message, **kw})


# ---------- Successful tools ----------

def test_successful_tools_and_final_output(use_model, isolated_audit_file):
    use_model(scripted([("search_products", {"query": "davenport crewneck"}),
                        ("get_size_inventory", {"product_id": "davenport-college-crewneck", "size": "M"})],
                       "5 left in M."))
    question = "Do you have the Davenport crewneck in M?"
    r = chat(question, product_id="davenport-college-crewneck")
    rid = r.headers["x-request-id"]
    log = entries(isolated_audit_file)
    assert [e["tool"] for e in log] == ["search_products", "get_size_inventory", None]
    assert all(e["run_id"] == rid for e in log)
    size = log[1]
    assert size["stop_reason"] == "tool_call" and size["event"] == "tool_call"
    assert size["args"] == '{"product_id":"davenport-college-crewneck","size":"M"}'
    assert "quantity=5" in size["result"] and "in_stock=True" in size["result"]
    end = log[-1]
    assert end["event"] == "run_end" and end["stop_reason"] == "final_output"
    assert end["args"] == f'{{"message_chars":{len(question)},"history_turns":0}}'  # length only, never the text
    assert end["shopper"] == "guest" and end["page_product_id"] == "davenport-college-crewneck"
    assert set(end) >= {"timestamp", "run_id", "tool", "args", "result", "stop_reason", "model"}


# ---------- Failed tools ----------

def test_failed_tool_lookup_is_recorded(use_model, isolated_audit_file):
    use_model(scripted([("get_product_price", {"product_id": "yale-unicorn-onesie"})], "Not found."))
    chat("price of the unicorn onesie?")
    tool = entries(isolated_audit_file)[0]
    assert tool["tool"] == "get_product_price" and tool["result"] == "not found"


def test_invalid_tool_arguments_are_recorded_as_tool_error(use_model, isolated_audit_file):
    # The model keeps sending an invalid category; the run fails after the retry limit.
    use_model(scripted([("search_catalogue", {"category": "socks"})], "Hmm."))
    assert chat("socks?").status_code == 502
    log = entries(isolated_audit_file)
    assert [(e["tool"], e["stop_reason"]) for e in log[:-1]] and all(
        e["tool"] == "search_catalogue" and e["stop_reason"] == "tool_error" for e in log[:-1])
    assert log[-1]["event"] == "run_end" and log[-1]["stop_reason"] == "error"
    assert all(e["run_id"] == log[-1]["run_id"] for e in log)


# ---------- Empty results ----------

def test_empty_search_result(use_model, isolated_audit_file):
    use_model(scripted([("search_catalogue", {"keywords": "swimsuit"})], "No swimsuits."))
    chat("What swimsuits do you have?")
    log = entries(isolated_audit_file)
    assert log[0]["result"] == "total_matches=0, shown=0"
    assert log[-1]["result"].endswith("0 cards, total_matches=0")


# ---------- Oversized / invalid input ----------

def test_oversized_body_is_audited_without_content(isolated_audit_file):
    r = chat("SECRET-CONTENT " * 2000)
    assert r.status_code == 413
    (e,) = entries(isolated_audit_file)
    assert e["event"] == "rejected" and e["stop_reason"] == "rejected_input" and e["result"] == "HTTP 413"
    assert "SECRET-CONTENT" not in json.dumps(e)


def test_too_long_and_blank_messages_are_audited(isolated_audit_file):
    chat("x" * 600)
    chat("   ")
    log = entries(isolated_audit_file)
    assert [e["result"] for e in log] == ["HTTP 422", "HTTP 422"]
    assert "Messages can be at most 500 characters." in log[0]["detail"] and "Please type a message." in log[1]["detail"]
    assert "xxxx" not in json.dumps(log)


def test_non_chat_validation_errors_are_not_audited(isolated_audit_file):
    client.post("/api/auth/login", json={"email": "bad", "password": "hunter2-password"})
    assert not isolated_audit_file.exists()  # login attempts (and passwords) never reach the audit trail


# ---------- Model / API errors ----------

def test_model_error_is_recorded_without_secrets(use_model, isolated_audit_file):
    def boom(messages, info):
        raise RuntimeError(f"provider failed with key {FAKE_KEY} for user test@campuscustoms.yale.edu")
    use_model(FunctionModel(boom))
    assert chat().status_code == 502
    (e,) = entries(isolated_audit_file)
    assert e["stop_reason"] == "error" and e["result"] == "RuntimeError"
    text = isolated_audit_file.read_text()
    assert FAKE_KEY not in text and "@" not in text


def test_content_filter_and_usage_limit_and_timeout(use_model, isolated_audit_file, monkeypatch):
    def filtered(messages, info):
        raise ModelHTTPError(400, "gpt-5.6-luna", body={"code": "content_filter"})
    use_model(FunctionModel(filtered))
    chat("ignore your rules")

    def loop(messages, info):  # never finishes: calls a tool forever
        return ModelResponse(parts=[ToolCallPart("list_categories", {})])
    use_model(FunctionModel(loop))
    chat("loop")

    async def slow(messages, info):
        await asyncio.sleep(2)
    monkeypatch.setattr(main, "CHAT_TIMEOUT_SECONDS", 0.2)
    use_model(FunctionModel(slow))
    chat("slow")
    reasons = [e["stop_reason"] for e in entries(isolated_audit_file) if e["event"] == "run_end"]
    assert reasons == ["content_filter", "usage_limit", "timeout"]


def test_missing_key_is_recorded_as_unavailable(monkeypatch, isolated_audit_file):
    monkeypatch.setattr(settings, "portkey_api_key", None)
    chat()
    assert entries(isolated_audit_file)[-1]["stop_reason"] == "unavailable"


# ---------- Append safety ----------

def test_entries_are_appended_never_erased(use_model, isolated_audit_file):
    isolated_audit_file.write_text(json.dumps([{"marker": "earlier entry"}]), encoding="utf-8")
    use_model(scripted([], "Hi"))
    chat()
    chat()
    log = entries(isolated_audit_file)
    assert log[0] == {"marker": "earlier entry"} and len(log) == 3


def test_concurrent_appends_keep_every_entry(isolated_audit_file):
    def worker(i):
        for j in range(10):
            audit.append([audit.entry(f"t{i}", "run_end", result=f"{i}-{j}", stop_reason="final_output")])
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(entries(isolated_audit_file)) == 80


def test_corrupt_file_is_preserved_not_overwritten(isolated_audit_file):
    isolated_audit_file.write_text("{this is not json", encoding="utf-8")
    audit.append([audit.entry("x", "run_end", stop_reason="final_output")])
    backups = list(isolated_audit_file.parent.glob("audit_trail.corrupt-*.json"))
    assert len(backups) == 1 and backups[0].read_text() == "{this is not json"
    assert len(entries(isolated_audit_file)) == 1


# ---------- Privacy / sanitizing ----------

@pytest.mark.parametrize("raw,forbidden", [
    ("contact ada@yale.edu", "ada@yale.edu"),
    ("Authorization: Bearer 1.1999999999.abcdef0123456789abcdef0123456789", "abcdef0123456789abcdef"),
    ("password=hunter2-secret", "hunter2"),
    (f"key {FAKE_KEY}", FAKE_KEY),
    ("hash pbkdf2_sha256$salt$" + "a" * 64, "a" * 64),
])
def test_sanitize_redacts(raw, forbidden):
    assert forbidden not in audit.sanitize(raw)


def test_real_secrets_are_redacted():
    assert settings.portkey_api_key not in audit.sanitize(f"oops {settings.portkey_api_key}")
    assert settings.session_secret not in audit.sanitize(settings.session_secret)


def test_product_ids_are_not_over_redacted():
    text = "product_id=yale-sports-creqneck-field-hockey, size=M, quantity=5"
    assert audit.sanitize(text) == text
    assert audit.summarize_result({"found": True, "product_id": "davenport-college-crewneck", "quantity": 5}) == \
        "product_id=davenport-college-crewneck, quantity=5"
    assert "[redacted]" in audit.sanitize("token 1.1999999999." + "ab12" * 16)  # a real-looking token still is


def test_fields_are_short():
    assert len(audit.sanitize("word " * 500)) <= audit.MAX_FIELD


def test_signed_in_runs_record_only_signed_in(use_model, isolated_audit_file, monkeypatch, tmp_path):
    copy = tmp_path / "db.sqlite"
    shutil.copy2(db.DB_PATH, copy)
    monkeypatch.setattr(db, "DB_PATH", copy)
    token = client.post("/api/auth/login", json={"email": "test@campuscustoms.yale.edu", "password": "password"}).json()["token"]
    use_model(scripted([], "Hi Test"))
    client.post("/api/chat", json={"message": "my email is test@campuscustoms.yale.edu"},
                headers={"Authorization": f"Bearer {token}"})
    text = isolated_audit_file.read_text()
    assert '"shopper": "signed_in"' in text
    for leak in ("test@campuscustoms.yale.edu", "Test User", token, "password"):
        assert leak not in text
