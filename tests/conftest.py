from __future__ import annotations

from http import HTTPStatus
from http.server import HTTPServer, SimpleHTTPRequestHandler
import os
import threading

import pytest
from playwright.sync_api import sync_playwright, Page, BrowserContext


def pytest_addoption(parser):
    parser.addoption(
        "--update-snapshots",
        action="store_true",
        default=False,
        help="Regenerate baseline screenshots",
    )


@pytest.fixture(scope="session")
def update_snapshots(request):
    return request.config.getoption("--update-snapshots")


@pytest.fixture(scope="session")
def http_server() -> str:
    """Start a local HTTP server serving the public/ directory and return base URL."""
    public_dir = os.path.join(os.path.dirname(__file__), "..", "public")

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=public_dir, **kwargs)

        def send_head(self):
            request_path, separator, query = self.path.partition("?")
            redirect_paths = {
                "/privacy.html": "/privacy",
                "/TOS.html": "/TOS",
            }
            rewrite_paths = {
                "/privacy": "/privacy.html",
                "/TOS": "/TOS.html",
            }
            query_suffix = separator + query if separator else ""

            if request_path in redirect_paths:
                self.send_response(HTTPStatus.TEMPORARY_REDIRECT)
                self.send_header("Location", redirect_paths[request_path] + query_suffix)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return None

            if request_path in rewrite_paths:
                original_path = self.path
                self.path = rewrite_paths[request_path] + query_suffix
                try:
                    return super().send_head()
                finally:
                    self.path = original_path

            return super().send_head()

        def log_message(self, format, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.fixture(scope="session")
def app_url(http_server: str) -> str:
    return http_server


@pytest.fixture(scope="session")
def browser():
    """Launch a Chromium browser for the session."""
    pw = sync_playwright().start()
    b = pw.chromium.launch()
    yield b
    b.close()
    pw.stop()


@pytest.fixture(scope="session")
def context(browser) -> BrowserContext:
    """Create a browser context locked to UTC timezone and en-US locale."""
    ctx = browser.new_context(
        timezone_id="UTC",
        locale="en-US",
        viewport={"width": 1280, "height": 720},
    )
    yield ctx
    ctx.close()


@pytest.fixture
def page(context: BrowserContext) -> Page:
    """Return a fresh page for each test."""
    p = context.new_page()
    yield p
    p.close()


@pytest.fixture(scope="session")
def helsinki_context(browser) -> BrowserContext:
    """Create a separate browser context using a DST-observing timezone."""
    ctx = browser.new_context(
        timezone_id="Europe/Helsinki",
        locale="en-US",
        viewport={"width": 1280, "height": 720},
    )
    yield ctx
    ctx.close()


@pytest.fixture
def helsinki_page(helsinki_context: BrowserContext) -> Page:
    """Return a fresh Helsinki-timezone page for each DST regression test."""
    p = helsinki_context.new_page()
    yield p
    p.close()
