from __future__ import annotations

from http.server import HTTPServer, SimpleHTTPRequestHandler
import os
import threading
import datetime

import pytest
from playwright.sync_api import sync_playwright, Page, BrowserContext


SCREENSHOTS_DIR = os.path.join(os.path.dirname(__file__), "screenshots")


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


def open_page(
    page: Page,
    app_url: str,
    params: dict[str, str] | None = None,
    localStorage_items: dict[str, str] | None = None,
) -> None:
    """Navigate to the app with optional query params and localStorage."""
    page.add_init_script("localStorage.clear();")
    page.add_init_script("""
        (function() {
            var fixed = Date.UTC(2026, 0, 1, 12, 0, 0, 0);
            var OrigDate = Date;
            window.Date = function() {
                if (arguments.length) return new OrigDate(...arguments);
                return new OrigDate(fixed);
            };
            window.Date.now = function() { return fixed; };
            window.Date.parse = OrigDate.parse.bind(OrigDate);
            window.Date.UTC = OrigDate.UTC.bind(OrigDate);
        })();
    """)

    if localStorage_items:
        for key, value in localStorage_items.items():
            page.add_init_script(f"localStorage.setItem('{key}', {value!r});")

    url = app_url
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url += f"?{qs}"

    page.goto(url)
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(500)


def is_daytime() -> bool:
    """Return True if the current UTC hour is daytime (6-18)."""
    hour = datetime.datetime.now(datetime.timezone.utc).hour
    return 6 <= hour < 18


def assert_screenshot(page: Page, name: str, update: bool = False, threshold: float = 0.01) -> None:
    """Compare a page screenshot against a baseline image.

    Args:
        page: Playwright page instance
        name: Screenshot filename (e.g. "embed-dark.png")
        update: If True, regenerate the baseline
        threshold: Maximum fraction of differing pixels (0.01 = 1%)
    """
    from PIL import Image
    import io

    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    baseline_path = os.path.join(SCREENSHOTS_DIR, name)

    screenshot_bytes = page.screenshot()
    actual_img = Image.open(io.BytesIO(screenshot_bytes))

    if update or not os.path.exists(baseline_path):
        actual_img.save(baseline_path)
        pytest.skip(f"Baseline screenshot created: {name}")
        return

    baseline_img = Image.open(baseline_path)

    if actual_img.size != baseline_img.size:
        actual_img.save(baseline_path)
        pytest.fail(
            f"Screenshot size mismatch for {name}: "
            f"expected {baseline_img.size}, got {actual_img.size}. Baseline updated."
        )

    actual_pixels = actual_img.load()
    baseline_pixels = baseline_img.load()
    width, height = actual_img.size
    total_pixels = width * height
    diff_count = 0

    for y in range(height):
        for x in range(width):
            if actual_pixels[x, y] != baseline_pixels[x, y]:
                diff_count += 1

    diff_ratio = diff_count / total_pixels

    if diff_ratio > threshold:
        diff_img = actual_img.copy()
        diff_pixels = diff_img.load()
        for y in range(height):
            for x in range(width):
                if actual_pixels[x, y] != baseline_pixels[x, y]:
                    diff_pixels[x, y] = (255, 0, 0, 255)
                else:
                    diff_pixels[x, y] = (128, 128, 128, 255)

        diff_name = name.replace(".png", "_diff.png")
        diff_path = os.path.join(SCREENSHOTS_DIR, diff_name)
        diff_img.save(diff_path)

        pytest.fail(
            f"Screenshot mismatch for {name}: {diff_count}/{total_pixels} pixels differ "
            f"({diff_ratio:.2%}). Diff saved to {diff_name}. "
            f"Run with --update-snapshots to regenerate baselines."
        )
