"""Start the backend and frontend once per test session, drive them with Microsoft Edge.

Uses ports 8001/5174 so it never collides with dev servers already running on 8000/5173.
Both process trees are always torn down at the end.
"""

import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page, sync_playwright

HW4 = Path(__file__).resolve().parents[1]
API_PORT, WEB_PORT = 8001, 5174
API_URL = f"http://localhost:{API_PORT}"
WEB_URL = f"http://localhost:{WEB_PORT}"


def wait_for_port(port: int, timeout: float = 30) -> None:
    # "localhost" so both IPv4 (uvicorn) and IPv6 (Vite on Node) listeners are found.
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            socket.create_connection(("localhost", port), timeout=1).close()
            return
        except OSError:
            time.sleep(0.3)
    raise RuntimeError(f"Nothing listening on port {port} after {timeout}s")


def listener_pids(port: int) -> set[str]:
    out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True).stdout
    out += subprocess.run(["netstat", "-ano", "-p", "TCPv6"], capture_output=True, text=True).stdout
    return {
        cols[-1]
        for cols in (line.split() for line in out.splitlines())
        if len(cols) >= 5 and cols[1].endswith(f":{port}") and cols[3] == "LISTENING"
    }


def kill_tree(proc: subprocess.Popen, port: int) -> None:
    """Kill the launched process tree, then anything still holding the test port."""
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    for pid in listener_pids(port):
        subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], capture_output=True)


@pytest.fixture(scope="session")
def test_db(tmp_path_factory) -> Path:
    """Throwaway copy of the database: accounts created by tests never touch the real one."""
    copy = tmp_path_factory.mktemp("db") / "campus_customs.db"
    shutil.copy2(HW4 / "backend" / "data" / "campus_customs.db", copy)
    return copy


@pytest.fixture(scope="session")
def servers(test_db):
    env = os.environ.copy()
    env["CORS_ORIGINS"] = WEB_URL
    env["VITE_API_BASE_URL"] = API_URL
    env["DATABASE_PATH"] = str(test_db)
    node_dir = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "nodejs"
    env["PATH"] = str(node_dir) + os.pathsep + env["PATH"]
    npm = shutil.which("npm.cmd", path=env["PATH"]) or "npm.cmd"

    api = subprocess.Popen(
        [str(HW4 / "backend" / ".venv" / "Scripts" / "python.exe"), "-m", "uvicorn", "main:app", "--port", str(API_PORT)],
        cwd=HW4 / "backend", env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    web = subprocess.Popen(
        [npm, "run", "dev", "--", "--port", str(WEB_PORT), "--strictPort"],
        cwd=HW4 / "frontend", env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        wait_for_port(API_PORT)
        wait_for_port(WEB_PORT)
        yield
    finally:
        kill_tree(web, WEB_PORT)
        kill_tree(api, API_PORT)


@pytest.fixture(scope="session")
def browser(servers) -> Browser:
    with sync_playwright() as p:
        # --no-proxy-server: Edge's proxy auto-detection otherwise adds ~20s to every new context.
        b = p.chromium.launch(channel="msedge", headless=True, args=["--no-proxy-server"])
        # Warm up: Vite pre-bundles dependencies on the first request, which can take ~20s.
        warm = b.new_page()
        warm.goto(WEB_URL, timeout=90_000)
        warm.close()
        yield b
        b.close()


@pytest.fixture
def page(browser: Browser) -> Page:
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    pg = context.new_page()
    pg.set_default_timeout(10_000)
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" and "net::ERR_FAILED" not in m.text else None)
    yield pg
    context.close()
    assert not errors, f"Browser errors: {errors}"


@pytest.fixture
def page_allow_errors(browser: Browser) -> Page:
    """For tests that deliberately break requests (e.g. aborted images)."""
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    pg = context.new_page()
    pg.set_default_timeout(10_000)
    yield pg
    context.close()
