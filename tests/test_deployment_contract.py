from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from typing import Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import pytest
from playwright.sync_api import Page


pytestmark = [pytest.mark.deployment, pytest.mark.chromium_only]

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WRANGLER_VERSION = "4.28.0"


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: bytes


class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def fetch(url: str, follow_redirects: bool = False) -> HttpResponse:
    opener = build_opener() if follow_redirects else build_opener(NoRedirectHandler())
    request = Request(url, headers={"User-Agent": "clocksimulator-contract-test"})
    try:
        with opener.open(request, timeout=5) as response:
            return HttpResponse(
                status=response.status,
                headers={key.lower(): value for key, value in response.headers.items()},
                body=response.read(),
            )
    except HTTPError as error:
        return HttpResponse(
            status=error.code,
            headers={key.lower(): value for key, value in error.headers.items()},
            body=error.read(),
        )


@contextmanager
def wrangler_process() -> Iterator[str]:
    executable = shutil.which("wrangler")
    if executable is None:
        pytest.fail(
            "Wrangler is required for deployment tests; install pinned wrangler@"
            + WRANGLER_VERSION
        )
    version = subprocess.run(
        [executable, "--version"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()
    assert version == WRANGLER_VERSION

    with tempfile.TemporaryDirectory(prefix="clocksimulator-wrangler-") as temp_directory:
        runtime_root = Path(temp_directory)
        shutil.copy2(REPOSITORY_ROOT / "wrangler.jsonc", runtime_root / "wrangler.jsonc")
        shutil.copytree(REPOSITORY_ROOT / "public", runtime_root / "public")
        port = free_port()
        inspector_port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        environment = os.environ.copy()
        environment["WRANGLER_SEND_METRICS"] = "false"
        environment["WRANGLER_LOG_PATH"] = str(runtime_root / "wrangler.log")
        process = subprocess.Popen(
            [
                executable,
                "dev",
                "--ip",
                "127.0.0.1",
                "--port",
                str(port),
                "--inspector-port",
                str(inspector_port),
                "--persist-to",
                str(runtime_root / "state"),
                "--log-level",
                "error",
                "--show-interactive-dev-session",
                "false",
            ],
            cwd=runtime_root,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        deadline = time.monotonic() + 20
        startup_error: Exception | None = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            try:
                response = fetch(base_url + "/robots.txt", follow_redirects=True)
                if response.status == 200:
                    startup_error = None
                    break
            except (URLError, TimeoutError, ConnectionError) as error:
                startup_error = error
            threading.Event().wait(0.05)
        else:
            startup_error = TimeoutError("Wrangler did not become ready within 20 seconds")

        if process.poll() is not None or startup_error is not None:
            process.terminate()
            output, _ = process.communicate(timeout=5)
            pytest.fail(
                "Pinned Wrangler runtime failed to start: "
                + str(startup_error or "process exited")
                + "\n"
                + output
            )

        try:
            yield base_url
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


@pytest.fixture(scope="module")
def deployment_url() -> Iterator[str]:
    with wrangler_process() as base_url:
        yield base_url


@pytest.mark.parametrize(
    ("path", "expected_title_fragment"),
    [
        pytest.param("/", "Online Analog Clock", id="analog-root"),
        pytest.param("/digital/", "Online Digital Clock", id="digital-directory"),
    ],
)
def test_primary_routes_serve_html(
    deployment_url: str, path: str, expected_title_fragment: str
) -> None:
    response = fetch(deployment_url + path)
    assert response.status == 200
    assert response.headers["content-type"].startswith("text/html")
    assert expected_title_fragment.encode() in response.body


@pytest.mark.parametrize(
    ("source", "destination"),
    [
        pytest.param("/digital?mode=test", "/digital/?mode=test", id="digital-trailing-slash"),
        pytest.param("/privacy.html?source=legacy", "/privacy?source=legacy", id="privacy-legacy"),
        pytest.param("/TOS.html?source=legacy", "/TOS?source=legacy", id="tos-legacy"),
    ],
)
def test_auto_trailing_slash_redirects_preserve_query(
    deployment_url: str, source: str, destination: str
) -> None:
    response = fetch(deployment_url + source)
    assert response.status in {301, 302, 307, 308}
    location = urlsplit(response.headers["location"])
    assert location.path + ("?" + location.query if location.query else "") == destination


@pytest.mark.parametrize(
    "path",
    [pytest.param("/privacy", id="privacy"), pytest.param("/TOS", id="tos")],
)
def test_extensionless_legal_routes_serve_html(deployment_url: str, path: str) -> None:
    response = fetch(deployment_url + path)
    assert response.status == 200
    assert response.headers["content-type"].startswith("text/html")
    assert b'<link rel="canonical"' in response.body


def test_deployment_headers_allow_embedding_and_cors(deployment_url: str) -> None:
    response = fetch(deployment_url + "/")
    assert response.status == 200
    csp = response.headers["content-security-policy"]
    directives = [part.strip() for part in csp.split(";") if part.strip()]
    assert "frame-ancestors *" in directives
    assert response.headers["access-control-allow-origin"] == "*"


@pytest.mark.parametrize(
    ("path", "mime_prefix"),
    [
        pytest.param("/sw.js", "application/javascript", id="service-worker"),
        pytest.param("/manifest.json", "application/json", id="manifest"),
        pytest.param("/apple-touch-icon.png", "image/png", id="png"),
        pytest.param("/robots.txt", "text/plain", id="robots"),
    ],
)
def test_static_asset_status_and_mime(
    deployment_url: str, path: str, mime_prefix: str
) -> None:
    response = fetch(deployment_url + path)
    assert response.status == 200
    assert response.headers["content-type"].startswith(mime_prefix)
    assert response.body
    if path == "/sw.js":
        assert response.headers.get("location") is None


def test_cross_origin_analog_and_digital_iframes(
    page: Page, app_url: str, deployment_url: str
) -> None:
    page.goto(app_url + "/robots.txt")
    page.set_content(
        """<!doctype html>
        <html><body style="margin:0;background:rgb(12,34,56)">
          <iframe id="analog" width="320" height="256"></iframe>
          <iframe id="digital" width="320" height="256"></iframe>
        </body></html>"""
    )
    page.locator("#analog").evaluate(
        "(frame, source) => frame.src = source",
        deployment_url + "/?embed=true&theme=transparent",
    )
    page.locator("#digital").evaluate(
        "(frame, source) => frame.src = source",
        deployment_url + "/digital/?embed=true&theme=transparent",
    )

    analog = page.frame_locator("#analog")
    digital = page.frame_locator("#digital")
    analog.locator("#clock").wait_for(state="visible")
    digital.locator("#digitalTime").wait_for(state="visible")
    frames = [frame for frame in page.frames if frame.parent_frame is page.main_frame]
    assert len(frames) == 2
    for child in frames:
        assert child.evaluate("() => location.origin") == urlsplit(deployment_url).scheme + "://" + urlsplit(deployment_url).netloc
        assert child.evaluate(
            "() => getComputedStyle(document.documentElement).backgroundColor"
        ) == "rgba(0, 0, 0, 0)"
        assert child.evaluate("() => getComputedStyle(document.body).backgroundColor") == "rgba(0, 0, 0, 0)"
        assert child.evaluate("() => document.documentElement.scrollWidth <= innerWidth") is True
        assert child.evaluate("() => document.documentElement.scrollHeight <= innerHeight") is True
        assert child.evaluate("() => document.body.scrollWidth <= innerWidth") is True
        assert child.evaluate("() => document.body.scrollHeight <= innerHeight") is True
