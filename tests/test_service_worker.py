from __future__ import annotations

import pytest
from playwright.sync_api import Browser, BrowserContext, Page


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


def create_isolated_context(browser: Browser) -> BrowserContext:
    return browser.new_context(
        timezone_id="UTC",
        locale="en-US",
        viewport={"width": 1280, "height": 720},
    )


def assert_document(
    page: Page,
    title: str,
    selector: str,
    expected_text: str | None,
) -> None:
    locator = page.locator(selector)
    locator.wait_for(state="visible")
    assert page.title() == title
    if expected_text is not None:
        assert locator.inner_text() == expected_text
    if selector == "#digitalTime":
        assert locator.inner_text()


@pytest.mark.parametrize("method", ["GET", "HEAD"])
@pytest.mark.parametrize(
    ("path", "location"),
    [
        pytest.param("/privacy.html", "/privacy", id="privacy-policy"),
        pytest.param("/TOS.html", "/TOS", id="terms-of-service"),
        pytest.param(
            "/privacy.html?second=2&encoded=a%2Fb&empty=&first=1",
            "/privacy?second=2&encoded=a%2Fb&empty=&first=1",
            id="privacy-policy-query",
        ),
        pytest.param(
            "/TOS.html?second=2&encoded=a%2Fb&empty=&first=1",
            "/TOS?second=2&encoded=a%2Fb&empty=&first=1",
            id="terms-of-service-query",
        ),
    ],
)
def test_legacy_legal_route_redirect_contract(
    page: Page,
    app_url: str,
    method: str,
    path: str,
    location: str,
) -> None:
    response = page.request.fetch(
        app_url.rstrip("/") + path,
        method=method,
        max_redirects=0,
    )

    assert response.status == 307
    assert response.headers["location"] == location


@pytest.mark.parametrize(
    ("path", "title", "heading"),
    [
        pytest.param(
            "/privacy",
            "Privacy Policy - clocksimulator.com",
            "Privacy Policy",
            id="privacy-policy",
        ),
        pytest.param(
            "/TOS",
            "Terms of Service - clocksimulator.com",
            "Terms of Service",
            id="terms-of-service",
        ),
    ],
)
def test_public_legal_route_rewrite_contract(
    page: Page,
    app_url: str,
    path: str,
    title: str,
    heading: str,
) -> None:
    response = page.request.get(app_url.rstrip("/") + path)

    assert response.status == 200
    body = response.text()
    assert "<title>" + title + "</title>" in body
    assert "<h1>" + heading + "</h1>" in body


@pytest.mark.parametrize(
    ("legacy_path", "public_path", "title", "heading"),
    [
        pytest.param(
            "/privacy.html",
            "/privacy",
            "Privacy Policy - clocksimulator.com",
            "Privacy Policy",
            id="privacy-policy",
        ),
        pytest.param(
            "/TOS.html",
            "/TOS",
            "Terms of Service - clocksimulator.com",
            "Terms of Service",
            id="terms-of-service",
        ),
        pytest.param(
            "/privacy.html?source=test",
            "/privacy?source=test",
            "Privacy Policy - clocksimulator.com",
            "Privacy Policy",
            id="privacy-policy-query",
        ),
        pytest.param(
            "/TOS.html?source=test",
            "/TOS?source=test",
            "Terms of Service - clocksimulator.com",
            "Terms of Service",
            id="terms-of-service-query",
        ),
    ],
)
def test_browser_legacy_navigation_uses_public_route(
    browser: Browser,
    app_url: str,
    legacy_path: str,
    public_path: str,
    title: str,
    heading: str,
) -> None:
    context = create_isolated_context(browser)
    redirect_page = context.new_page()
    try:
        response = redirect_page.goto(
            app_url.rstrip("/") + legacy_path,
            wait_until="domcontentloaded",
        )

        assert response is not None
        assert response.ok
        assert redirect_page.evaluate("() => location.pathname + location.search") == public_path
        assert_document(redirect_page, title, "main h1", heading)
    finally:
        context.close()


def test_legal_pages_are_precached_under_public_routes(page: Page, app_url: str) -> None:
    prepare_controlled_page(page, app_url)

    cached_paths = page.evaluate(
        """async () => {
            const names = await caches.keys();
            const name = names.find(candidate => candidate.indexOf('clocksimulator-v') === 0);
            const cache = await caches.open(name);
            const requests = await cache.keys();
            return requests.map(request => new URL(request.url).pathname);
        }"""
    )

    assert "/privacy" in cached_paths
    assert "/TOS" in cached_paths
    assert "/privacy.html" not in cached_paths
    assert "/TOS.html" not in cached_paths


@pytest.mark.parametrize(
    ("legacy_path", "public_path", "title", "heading"),
    [
        pytest.param(
            "/privacy.html",
            "/privacy",
            "Privacy Policy - clocksimulator.com",
            "Privacy Policy",
            id="privacy-policy",
        ),
        pytest.param(
            "/TOS.html",
            "/TOS",
            "Terms of Service - clocksimulator.com",
            "Terms of Service",
            id="terms-of-service",
        ),
        pytest.param(
            "/privacy.html?source=test",
            "/privacy?source=test",
            "Privacy Policy - clocksimulator.com",
            "Privacy Policy",
            id="privacy-policy-query",
        ),
        pytest.param(
            "/TOS.html?source=test",
            "/TOS?source=test",
            "Terms of Service - clocksimulator.com",
            "Terms of Service",
            id="terms-of-service-query",
        ),
    ],
)
def test_online_redirect_then_offline_reload_returns_legal_document(
    page: Page,
    app_url: str,
    legacy_path: str,
    public_path: str,
    title: str,
    heading: str,
) -> None:
    prepare_controlled_page(page, app_url)
    online_response = page.goto(
        app_url.rstrip("/") + legacy_path,
        wait_until="domcontentloaded",
    )

    assert online_response is not None
    assert online_response.ok
    assert page.evaluate("() => location.pathname + location.search") == public_path
    assert_document(page, title, "main h1", heading)

    page.context.set_offline(True)
    try:
        page.wait_for_function("() => navigator.onLine === false")
        offline_response = page.reload(wait_until="domcontentloaded")

        assert offline_response is not None
        assert offline_response.ok
        assert page.evaluate("() => location.pathname + location.search") == public_path
        assert_document(page, title, "main h1", heading)
    finally:
        page.context.set_offline(False)


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
            "/privacy",
            "Privacy Policy - clocksimulator.com",
            "main h1",
            "Privacy Policy",
            id="privacy-policy-public",
        ),
        pytest.param(
            "/TOS",
            "Terms of Service - clocksimulator.com",
            "main h1",
            "Terms of Service",
            id="terms-of-service-public",
        ),
        pytest.param(
            "/privacy?source=test",
            "Privacy Policy - clocksimulator.com",
            "main h1",
            "Privacy Policy",
            id="privacy-policy-public-query",
        ),
        pytest.param(
            "/TOS?source=test",
            "Terms of Service - clocksimulator.com",
            "main h1",
            "Terms of Service",
            id="terms-of-service-public-query",
        ),
        pytest.param(
            "/privacy.html",
            "Privacy Policy - clocksimulator.com",
            "main h1",
            "Privacy Policy",
            id="privacy-policy-legacy",
        ),
        pytest.param(
            "/TOS.html",
            "Terms of Service - clocksimulator.com",
            "main h1",
            "Terms of Service",
            id="terms-of-service-legacy",
        ),
        pytest.param(
            "/privacy.html?source=test",
            "Privacy Policy - clocksimulator.com",
            "main h1",
            "Privacy Policy",
            id="privacy-policy-legacy-query",
        ),
        pytest.param(
            "/TOS.html?source=test",
            "Terms of Service - clocksimulator.com",
            "main h1",
            "Terms of Service",
            id="terms-of-service-legacy-query",
        ),
        pytest.param(
            "/unknown-offline-route",
            "Fullscreen Online Analog Clock | Clocksimulator",
            "#clock",
            None,
            id="unknown-route-root-fallback",
        ),
        pytest.param(
            "/privacy-policy",
            "Fullscreen Online Analog Clock | Clocksimulator",
            "#clock",
            None,
            id="privacy-near-match-root-fallback",
        ),
        pytest.param(
            "/privacy.html-extra",
            "Fullscreen Online Analog Clock | Clocksimulator",
            "#clock",
            None,
            id="privacy-legacy-near-match-root-fallback",
        ),
        pytest.param(
            "/tos",
            "Fullscreen Online Analog Clock | Clocksimulator",
            "#clock",
            None,
            id="terms-near-match-root-fallback",
        ),
        pytest.param(
            "/TOS.html-extra",
            "Fullscreen Online Analog Clock | Clocksimulator",
            "#clock",
            None,
            id="terms-legacy-near-match-root-fallback",
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
        assert_document(page, title, selector, expected_text)
        assert page.evaluate("() => location.pathname + location.search") == path
        if path == "/?tz=UTC&theme=dark":
            assert page.locator("html").evaluate(
                "element => element.classList.contains('dark-mode')"
            )
        if path == "/digital/?tz=UTC":
            assert page.locator("#digitalLabel").inner_text() == "UTC"
    finally:
        page.context.set_offline(False)


def test_online_navigation_remains_network_first(browser: Browser, app_url: str) -> None:
    context = create_isolated_context(browser)
    network_page = context.new_page()
    try:
        prepare_controlled_page(network_page, app_url)
        cached = network_page.evaluate(
            """async () => {
                const names = await caches.keys();
                const name = names.find(candidate => candidate.indexOf('clocksimulator-v') === 0);
                const cache = await caches.open(name);
                await cache.put('/privacy', new Response(
                    '<!doctype html><title>Cached sentinel</title><main><h1>Cached sentinel</h1></main>',
                    { headers: { 'Content-Type': 'text/html' } }
                ));
                return true;
            }"""
        )

        assert cached is True
        response = network_page.goto(
            app_url.rstrip("/") + "/privacy",
            wait_until="domcontentloaded",
        )
        assert response is not None
        assert response.ok
        assert_document(
            network_page,
            "Privacy Policy - clocksimulator.com",
            "main h1",
            "Privacy Policy",
        )
    finally:
        context.close()


def test_missing_legal_cache_entry_uses_root_fallback(
    browser: Browser,
    app_url: str,
) -> None:
    context = create_isolated_context(browser)
    fallback_page = context.new_page()
    try:
        prepare_controlled_page(fallback_page, app_url)
        deleted = fallback_page.evaluate(
            """async () => {
                const names = await caches.keys();
                const name = names.find(candidate => candidate.indexOf('clocksimulator-v') === 0);
                const cache = await caches.open(name);
                return cache.delete('/privacy');
            }"""
        )

        assert deleted is True
        context.set_offline(True)
        fallback_page.wait_for_function("() => navigator.onLine === false")
        response = fallback_page.goto(
            app_url.rstrip("/") + "/privacy.html?source=test",
            wait_until="domcontentloaded",
        )

        assert response is not None
        assert response.ok
        assert fallback_page.evaluate(
            "() => location.pathname + location.search"
        ) == "/privacy.html?source=test"
        assert_document(
            fallback_page,
            "Fullscreen Online Analog Clock | Clocksimulator",
            "#clock",
            None,
        )
    finally:
        context.set_offline(False)
        context.close()
