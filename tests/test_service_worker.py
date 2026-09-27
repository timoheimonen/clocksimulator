from __future__ import annotations

import pytest
from playwright.sync_api import Page


pytestmark = [pytest.mark.service_worker, pytest.mark.chromium_only]


EXPECTED_PRECACHE_PATHS = {
    "/",
    "/digital/",
    "/privacy",
    "/TOS",
    "/sitemap.xml",
    "/manifest.json",
    "/apple-touch-icon.png",
    "/android-chrome-192x192.png",
    "/android-chrome-512x512.png",
    "/og-image.png",
}


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


def current_cache_name(page: Page) -> str:
    names = page.evaluate(
        """async () => (await caches.keys()).filter(function (name) {
            return name.indexOf('clocksimulator-v') === 0;
        })"""
    )
    assert len(names) == 1
    return names[0]


def test_install_precaches_exact_asset_set_with_successful_nonempty_responses(
    service_worker_page: Page, app_url: str
) -> None:
    prepare_controlled_page(service_worker_page, app_url)
    cache_name = current_cache_name(service_worker_page)

    cached_assets = service_worker_page.evaluate(
        """async (name) => {
            const cache = await caches.open(name);
            const requests = await cache.keys();
            return Promise.all(requests.map(async function (request) {
                const response = await cache.match(request);
                const url = new URL(request.url);
                const body = await response.clone().arrayBuffer();
                return {
                    key: url.pathname + url.search,
                    ok: response.ok,
                    status: response.status,
                    size: body.byteLength
                };
            }));
        }""",
        cache_name,
    )

    assert len(cached_assets) == len(EXPECTED_PRECACHE_PATHS)
    assert {asset["key"] for asset in cached_assets} == EXPECTED_PRECACHE_PATHS
    assert all(asset["ok"] for asset in cached_assets)
    assert all(asset["status"] == 200 for asset in cached_assets)
    assert all(asset["size"] > 0 for asset in cached_assets)

    service_worker_page.context.set_offline(True)
    try:
        service_worker_page.wait_for_function("() => navigator.onLine === false")
        offline = service_worker_page.evaluate(
            """async () => {
                const response = await fetch('/manifest.json');
                return {
                    ok: response.ok,
                    status: response.status,
                    body: await response.text()
                };
            }"""
        )
    finally:
        service_worker_page.context.set_offline(False)

    assert offline["ok"] is True
    assert offline["status"] == 200
    assert '"name"' in offline["body"]


def test_activate_deletes_old_owned_cache_and_preserves_current_and_foreign_caches(
    service_worker_page: Page,
    app_url: str,
) -> None:
    prepare_controlled_page(service_worker_page, app_url)
    cache_name = current_cache_name(service_worker_page)
    seeded = service_worker_page.evaluate(
        """async (currentName) => {
            const oldName = 'clocksimulator-v0.0.0-activation-test';
            const foreignName = 'unrelated-app-activation-test';
            const oldCache = await caches.open(oldName);
            const foreignCache = await caches.open(foreignName);
            await oldCache.put('/old-cache-sentinel', new Response('old'));
            await foreignCache.put('/foreign-cache-sentinel', new Response('foreign'));
            return {
                oldName: oldName,
                currentName: currentName,
                foreignName: foreignName
            };
        }""",
        cache_name,
    )
    workers = service_worker_page.context.service_workers
    assert len(workers) == 1
    workers[0].evaluate(
        "() => self.dispatchEvent(new ExtendableEvent('activate'))"
    )
    service_worker_page.wait_for_function(
        """async (oldName) => !(await caches.keys()).includes(oldName)""",
        arg=seeded["oldName"],
        timeout=10000,
    )

    cache_names = set(service_worker_page.evaluate("async () => caches.keys()"))

    assert seeded["oldName"] not in cache_names
    assert seeded["currentName"] in cache_names
    assert seeded["foreignName"] in cache_names


def test_runtime_cache_miss_returns_clone_caches_response_and_serves_offline_hit(
    service_worker_page: Page,
    app_url: str,
) -> None:
    prepare_controlled_page(service_worker_page, app_url)
    cache_name = current_cache_name(service_worker_page)
    cache_key = "/robots.txt?runtime-cache=miss"
    online = service_worker_page.evaluate(
        """async ([name, key]) => {
            const cache = await caches.open(name);
            await cache.delete(key);
            const cachedBefore = await cache.match(key);
            const response = await fetch(key);
            return {
                cachedBefore: Boolean(cachedBefore),
                ok: response.ok,
                status: response.status,
                body: await response.text()
            };
        }""",
        [cache_name, cache_key],
    )
    assert online.pop("cachedBefore") is False
    service_worker_page.wait_for_function(
        """async ([name, key]) => {
            const cache = await caches.open(name);
            return Boolean(await cache.match(key));
        }""",
        arg=[cache_name, cache_key],
        timeout=10000,
    )
    cached = service_worker_page.evaluate(
        """async ([name, key]) => {
            const response = await (await caches.open(name)).match(key);
            return {
                ok: response.ok,
                status: response.status,
                body: await response.text()
            };
        }""",
        [cache_name, cache_key],
    )

    service_worker_page.context.set_offline(True)
    try:
        service_worker_page.wait_for_function("() => navigator.onLine === false")
        offline = service_worker_page.evaluate(
            """async (key) => {
                const response = await fetch(key);
                return {
                    ok: response.ok,
                    status: response.status,
                    body: await response.text()
                };
            }""",
            cache_key,
        )
    finally:
        service_worker_page.context.set_offline(False)

    assert online["ok"] is True
    assert online["status"] == 200
    assert "User-agent: *" in online["body"]
    assert cached == online
    assert offline == online


def test_non_ok_runtime_network_response_does_not_create_cache_entry(
    service_worker_page: Page,
    app_url: str,
    expected_browser_errors: list[str],
) -> None:
    prepare_controlled_page(service_worker_page, app_url)
    cache_name = current_cache_name(service_worker_page)
    cache_key = "/missing-runtime-resource.txt?runtime-network=not-ok"
    expected_browser_errors.append(
        "console.error: Failed to load resource: the server responded with a status of "
        "404 (File not found) ("
        + app_url.rstrip("/")
        + "/)"
    )
    result = service_worker_page.evaluate(
        """async ([name, key]) => {
            const cache = await caches.open(name);
            await cache.delete(key);
            const response = await fetch(key);
            const body = await response.text();
            const cached = await cache.match(key);
            return {
                ok: response.ok,
                status: response.status,
                bodyLength: body.length,
                cached: Boolean(cached)
            };
        }""",
        [cache_name, cache_key],
    )

    assert result["ok"] is False
    assert result["status"] == 404
    assert result["bodyLength"] > 0
    assert result["cached"] is False


@pytest.mark.parametrize(
    ("path", "title", "selector", "expected_text"),
    [
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
            "/digital",
            "Fullscreen Online Digital Clock | Clocksimulator",
            "#digitalTime",
            None,
            id="digital-without-trailing-slash",
        ),
        pytest.param(
            "/digital/unknown",
            "Fullscreen Online Digital Clock | Clocksimulator",
            "#digitalTime",
            None,
            id="digital-descendant-fallback",
        ),
        pytest.param(
            "/privacy",
            "Privacy Policy - clocksimulator.com",
            "main h1",
            "Privacy Policy",
            id="privacy-policy-public",
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
    ],
)
def test_offline_navigation_returns_expected_document(
    service_worker_page: Page,
    app_url: str,
    path: str,
    title: str,
    selector: str,
    expected_text: str | None,
) -> None:
    prepare_controlled_page(service_worker_page, app_url)
    service_worker_page.context.set_offline(True)
    try:
        service_worker_page.wait_for_function("() => navigator.onLine === false")
        response = service_worker_page.goto(
            app_url.rstrip("/") + path, wait_until="domcontentloaded"
        )

        assert response is not None
        assert response.ok
        assert_document(service_worker_page, title, selector, expected_text)
        assert service_worker_page.evaluate(
            "() => location.pathname + location.search"
        ) == path
        if path == "/?tz=UTC&theme=dark":
            assert service_worker_page.locator("html").evaluate(
                "element => element.classList.contains('dark-mode')"
            )
    finally:
        service_worker_page.context.set_offline(False)


def test_online_navigation_remains_network_first(
    service_worker_page: Page, app_url: str
) -> None:
    prepare_controlled_page(service_worker_page, app_url)
    cached = service_worker_page.evaluate(
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
    response = service_worker_page.goto(
        app_url.rstrip("/") + "/privacy",
        wait_until="domcontentloaded",
    )
    assert response is not None
    assert response.ok
    assert_document(
        service_worker_page,
        "Privacy Policy - clocksimulator.com",
        "main h1",
        "Privacy Policy",
    )
