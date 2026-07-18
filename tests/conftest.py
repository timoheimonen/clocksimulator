from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import os
from pathlib import Path
import re
import threading
from typing import Iterator
from urllib.request import urlopen

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

CONTEXT_OPTIONS = {
    "locale": "en-US",
    "viewport": {"width": 1280, "height": 720},
    "color_scheme": "light",
    "reduced_motion": "no-preference",
    "device_scale_factor": 1,
}


@dataclass(frozen=True)
class BrowserError:
    kind: str
    message: str
    url: str

    def describe(self) -> str:
        location = self.url or "about:blank"
        return f"{self.kind}: {self.message} ({location})"


def pytest_addoption(parser) -> None:
    parser.addoption(
        "--update-snapshots",
        action="store_true",
        default=False,
        help="Regenerate baseline screenshots",
    )
    parser.addoption(
        "--browser-engine",
        action="store",
        choices=("chromium", "firefox", "webkit"),
        default=os.environ.get("CLOCKSIMULATOR_BROWSER", "chromium"),
        help="Browser engine used by clocksimulator tests",
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    setattr(item, "rep_" + report.when, report)


@pytest.fixture(scope="session")
def update_snapshots(request) -> bool:
    return request.config.getoption("--update-snapshots")


@pytest.fixture(scope="session")
def browser_engine(request) -> str:
    return request.config.getoption("--browser-engine")


@pytest.fixture(scope="session")
def http_server() -> Iterator[str]:
    public_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "public"))

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=public_dir, **kwargs)

        def send_head(self):
            request_path, separator, query = self.path.partition("?")
            if request_path == "/__partial-content__":
                payload = b"partial"
                self.send_response(HTTPStatus.PARTIAL_CONTENT)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Range", "bytes 0-6/7")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                return BytesIO(payload)
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

        def log_message(self, format, *args) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    server.block_on_close = False
    port = server.server_address[1]
    ready = threading.Event()

    def serve() -> None:
        ready.set()
        server.serve_forever()

    thread = threading.Thread(target=serve, name="clocksimulator-test-server")
    thread.start()
    if not ready.wait(timeout=5):
        server.server_close()
        thread.join(timeout=5)
        pytest.fail("Local clocksimulator test server did not become ready")

    try:
        with urlopen(f"http://127.0.0.1:{port}/robots.txt", timeout=5) as response:
            if response.status != HTTPStatus.OK:
                pytest.fail(
                    f"Local clocksimulator test server readiness returned {response.status}"
                )
    except Exception as error:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        pytest.fail(f"Local clocksimulator test server readiness failed: {error}")

    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        if thread.is_alive():
            pytest.fail("Local clocksimulator test server did not stop cleanly")


@pytest.fixture(scope="session")
def app_url(http_server: str) -> str:
    return http_server


def browser_fixture_scope(fixture_name: str, config: pytest.Config) -> str:
    return "module" if config.getoption("--browser-engine") == "webkit" else "session"


@pytest.fixture(scope=browser_fixture_scope)
def browser(browser_engine: str) -> Iterator[Browser]:
    playwright = sync_playwright().start()
    browser_type = getattr(playwright, browser_engine)
    launched_browser = browser_type.launch()
    try:
        yield launched_browser
    finally:
        launched_browser.close()
        playwright.stop()


@pytest.fixture
def browser_errors() -> list[BrowserError]:
    return []


@pytest.fixture
def expected_browser_errors() -> list[str]:
    return []


def attach_browser_error_gate(page: Page, errors: list[BrowserError]) -> None:
    page.on(
        "pageerror",
        lambda error: errors.append(BrowserError("pageerror", str(error), page.url)),
    )

    def record_console(message) -> None:
        if message.type == "error":
            errors.append(BrowserError("console.error", message.text, page.url))

    page.on("console", record_console)


def assert_expected_browser_errors(
    errors: list[BrowserError], expected: list[str]
) -> None:
    actual = [error.describe() for error in errors]
    unmatched = actual.copy()
    for expected_message in expected:
        matching = next(
            (message for message in unmatched if expected_message == message),
            None,
        )
        if matching is None:
            pytest.fail(
                "Expected browser error was not observed:\n"
                + expected_message
                + "\nObserved errors:\n"
                + ("\n".join(actual) if actual else "<none>")
            )
        unmatched.remove(matching)

    if unmatched:
        pytest.fail("Unexpected browser errors:\n" + "\n".join(unmatched))


def create_test_context(
    browser: Browser,
    browser_errors: list[BrowserError],
    timezone_id: str,
    service_workers: str,
) -> BrowserContext:
    context = browser.new_context(
        timezone_id=timezone_id,
        service_workers=service_workers,
        **CONTEXT_OPTIONS,
    )
    def attach_page(created_page: Page) -> None:
        attach_browser_error_gate(created_page, browser_errors)

    context.on("page", attach_page)
    return context


def start_tracing(context: BrowserContext, request) -> str:
    tracing_mode = request.config.getoption("--tracing")
    if tracing_mode != "off":
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
    return tracing_mode


def stop_tracing(
    context: BrowserContext,
    request,
    tracing_mode: str,
    force_retain: bool = False,
) -> None:
    if tracing_mode == "off":
        return
    failed = any(
        getattr(request.node, "rep_" + phase, None)
        and getattr(request.node, "rep_" + phase).failed
        for phase in ("setup", "call", "teardown")
    )
    retain = force_retain or tracing_mode == "on" or (
        tracing_mode == "retain-on-failure" and failed
    )
    if retain:
        output = Path(request.config.getoption("--output"))
        if not output.is_absolute():
            output = Path(str(request.config.rootpath)) / output
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", request.node.nodeid).strip("-")
        trace_path = output / safe_name / "trace.zip"
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        context.tracing.stop(path=trace_path)
    else:
        context.tracing.stop()


def finalize_test_context(
    context: BrowserContext,
    request,
    tracing_mode: str,
    browser_errors: list[BrowserError],
    expected_browser_errors: list[str],
) -> None:
    force_retain = False
    try:
        assert_expected_browser_errors(browser_errors, expected_browser_errors)
    except BaseException:
        force_retain = True
        raise
    finally:
        try:
            stop_tracing(
                context,
                request,
                tracing_mode,
                force_retain=force_retain,
            )
        finally:
            context.close()


@pytest.fixture
def context(
    browser: Browser,
    browser_errors: list[BrowserError],
    expected_browser_errors: list[str],
    request,
) -> Iterator[BrowserContext]:
    ctx = create_test_context(browser, browser_errors, "UTC", "block")
    tracing_mode = start_tracing(ctx, request)
    try:
        yield ctx
    finally:
        finalize_test_context(
            ctx,
            request,
            tracing_mode,
            browser_errors,
            expected_browser_errors,
        )


@pytest.fixture
def page(context: BrowserContext) -> Page:
    return context.new_page()


@pytest.fixture
def helsinki_context(
    browser: Browser,
    browser_errors: list[BrowserError],
    expected_browser_errors: list[str],
    request,
) -> Iterator[BrowserContext]:
    ctx = create_test_context(browser, browser_errors, "Europe/Helsinki", "block")
    tracing_mode = start_tracing(ctx, request)
    try:
        yield ctx
    finally:
        finalize_test_context(
            ctx,
            request,
            tracing_mode,
            browser_errors,
            expected_browser_errors,
        )


@pytest.fixture
def helsinki_page(helsinki_context: BrowserContext) -> Page:
    return helsinki_context.new_page()


@pytest.fixture
def service_worker_context(
    browser: Browser,
    browser_errors: list[BrowserError],
    expected_browser_errors: list[str],
    request,
) -> Iterator[BrowserContext]:
    ctx = create_test_context(browser, browser_errors, "UTC", "allow")
    tracing_mode = start_tracing(ctx, request)
    try:
        yield ctx
    finally:
        finalize_test_context(
            ctx,
            request,
            tracing_mode,
            browser_errors,
            expected_browser_errors,
        )


@pytest.fixture
def service_worker_page(service_worker_context: BrowserContext) -> Page:
    return service_worker_context.new_page()
