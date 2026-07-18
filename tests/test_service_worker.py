from __future__ import annotations

import pytest
from playwright.sync_api import Page


def prepare_controlled_page(page: Page, app_url: str) -> None:
    page.goto(app_url, wait_until="domcontentloaded")
    page.evaluate(
        """() => {
            window.__serviceWorkerReady = false;
            navigator.serviceWorker.ready.then(function () {
                window.__serviceWorkerReady = true;
            });
        }"""
    )
    page.wait_for_function("() => window.__serviceWorkerReady", timeout=10000)
    page.reload(wait_until="domcontentloaded")
    page.wait_for_function("() => navigator.serviceWorker.controller !== null", timeout=10000)


@pytest.mark.parametrize(
    ("path", "title", "selector", "expected_text"),
    [
        pytest.param(
            "/",
            "Fullscreen Online Analog Clock | Clocksimulator",
            "#clock",
            None,
            id="analog-root",
        ),
        pytest.param(
            "/?tz=UTC&theme=dark",
            "clocksimulator.com - UTC",
            "#clock",
            None,
            id="analog-query",
        ),
        pytest.param(
            "/digital/",
            "Fullscreen Online Digital Clock | Clocksimulator",
            "#digitalTime",
            None,
            id="digital-root",
        ),
        pytest.param(
            "/digital/?tz=UTC",
            "clocksimulator.com - Digital - UTC",
            "#digitalTime",
            None,
            id="digital-query",
        ),
        pytest.param(
            "/digital",
            "Fullscreen Online Digital Clock | Clocksimulator",
            "#digitalTime",
            None,
            id="digital-without-trailing-slash",
        ),
        pytest.param(
            "/privacy.html",
            "Privacy Policy - clocksimulator.com",
            "main h1",
            "Privacy Policy",
            id="privacy-policy",
        ),
        pytest.param(
            "/TOS.html",
            "Terms of Service - clocksimulator.com",
            "main h1",
            "Terms of Service",
            id="terms-of-service",
        ),
        pytest.param(
            "/privacy.html?source=test",
            "Privacy Policy - clocksimulator.com",
            "main h1",
            "Privacy Policy",
            id="privacy-policy-query",
        ),
        pytest.param(
            "/unknown-offline-route",
            "Fullscreen Online Analog Clock | Clocksimulator",
            "#clock",
            None,
            id="unknown-route-root-fallback",
        ),
    ],
)
def test_offline_navigation_returns_expected_document(
    page: Page,
    app_url: str,
    path: str,
    title: str,
    selector: str,
    expected_text: str | None,
) -> None:
    prepare_controlled_page(page, app_url)
    page.context.set_offline(True)
    try:
        page.wait_for_function("() => navigator.onLine === false")
        response = page.goto(app_url.rstrip("/") + path, wait_until="domcontentloaded")
        assert response is not None
        assert response.ok
        locator = page.locator(selector)
        locator.wait_for(state="visible")
        assert page.title() == title
        if expected_text is not None:
            assert locator.inner_text() == expected_text
        if selector == "#digitalTime":
            assert locator.inner_text()
        assert page.evaluate("() => location.pathname + location.search") == path
        if path == "/?tz=UTC&theme=dark":
            assert page.locator("html").evaluate("element => element.classList.contains('dark-mode')")
        if path == "/digital/?tz=UTC":
            assert page.locator("#digitalLabel").inner_text() == "UTC"
    finally:
        page.context.set_offline(False)
