from __future__ import annotations

import pytest
from playwright.sync_api import Error as PlaywrightError
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
    service_worker_page: Page,
    app_url: str,
    method: str,
    path: str,
    location: str,
) -> None:
    response = service_worker_page.request.fetch(
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
    service_worker_page: Page,
    app_url: str,
    path: str,
    title: str,
    heading: str,
) -> None:
    response = service_worker_page.request.get(app_url.rstrip("/") + path)

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
    service_worker_page: Page,
    app_url: str,
    legacy_path: str,
    public_path: str,
    title: str,
    heading: str,
) -> None:
    response = service_worker_page.goto(
        app_url.rstrip("/") + legacy_path,
        wait_until="domcontentloaded",
    )

    assert response is not None
    assert response.ok
    assert service_worker_page.evaluate(
        "() => location.pathname + location.search"
    ) == public_path
    assert_document(service_worker_page, title, "main h1", heading)


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


def test_precache_hit_returns_cached_asset_while_offline(
    service_worker_page: Page,
    app_url: str,
) -> None:
    prepare_controlled_page(service_worker_page, app_url)
    service_worker_page.context.set_offline(True)
    try:
        service_worker_page.wait_for_function("() => navigator.onLine === false")
        result = service_worker_page.evaluate(
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

    assert result["ok"] is True
    assert result["status"] == 200
    assert '"name"' in result["body"]
    assert len(result["body"]) > 0


def test_runtime_cache_miss_returns_clone_caches_response_and_serves_offline_hit(
    service_worker_page: Page,
    app_url: str,
) -> None:
    prepare_controlled_page(service_worker_page, app_url)
    cache_name = current_cache_name(service_worker_page)
    cache_key = "/robots.txt?runtime-cache=miss"
    workers = service_worker_page.context.service_workers
    assert len(workers) == 1
    workers[0].evaluate(
        """() => {
            self.__runtimeResponseCloneCalls = 0;
            const originalClone = Response.prototype.clone;
            Response.prototype.clone = function () {
                self.__runtimeResponseCloneCalls += 1;
                return originalClone.call(this);
            };
        }"""
    )
    online = service_worker_page.evaluate(
        """async ([name, key]) => {
            const cache = await caches.open(name);
            await cache.delete(key);
            const response = await fetch(key);
            return {
                ok: response.ok,
                status: response.status,
                body: await response.text()
            };
        }""",
        [cache_name, cache_key],
    )
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
    clone_calls = workers[0].evaluate(
        "() => self.__runtimeResponseCloneCalls"
    )

    assert online["ok"] is True
    assert online["status"] == 200
    assert online["body"]
    assert clone_calls == 1
    assert cached == online
    assert offline == online


def test_runtime_cache_write_failure_still_returns_successful_network_response(
    service_worker_page: Page,
    app_url: str,
) -> None:
    prepare_controlled_page(service_worker_page, app_url)
    cache_name = current_cache_name(service_worker_page)
    cache_key = "/__partial-content__?runtime-cache=write-failure"
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
                body: body,
                cached: Boolean(cached)
            };
        }""",
        [cache_name, cache_key],
    )

    assert result == {
        "ok": True,
        "status": 206,
        "body": "partial",
        "cached": False,
    }


def test_runtime_fetch_waits_for_cache_write_before_resolving(
    service_worker_page: Page,
    app_url: str,
) -> None:
    prepare_controlled_page(service_worker_page, app_url)
    cache_name = current_cache_name(service_worker_page)
    cache_key = "/robots.txt?runtime-cache=await-put"
    worker = service_worker_page.context.service_workers[0]
    service_worker_page.evaluate(
        """async ([name, key]) => {
            await (await caches.open(name)).delete(key);
            window.__cachePutStarted = false;
            window.__runtimeFetchSettled = false;
            window.__runtimeFetchResult = null;
            navigator.serviceWorker.addEventListener('message', function (event) {
                if (event.data === 'cache-put-started') window.__cachePutStarted = true;
            });
        }""",
        [cache_name, cache_key],
    )
    worker.evaluate(
        """() => {
            const originalPut = Cache.prototype.put;
            Cache.prototype.put = function (request, response) {
                const cache = this;
                self.clients.matchAll({ type: 'window' }).then(function (clients) {
                    clients.forEach(function (client) {
                        client.postMessage('cache-put-started');
                    });
                });
                return new Promise(function (resolve, reject) {
                    self.__releaseCachePut = function () {
                        originalPut.call(cache, request, response).then(resolve, reject);
                    };
                });
            };
        }"""
    )
    service_worker_page.evaluate(
        """key => {
            fetch(key).then(async function (response) {
                window.__runtimeFetchResult = {
                    ok: response.ok,
                    status: response.status,
                    body: await response.text()
                };
                window.__runtimeFetchSettled = true;
            });
        }""",
        cache_key,
    )
    service_worker_page.wait_for_function("() => window.__cachePutStarted")
    assert service_worker_page.evaluate("() => window.__runtimeFetchSettled") is False

    worker.evaluate("() => self.__releaseCachePut()")
    service_worker_page.wait_for_function("() => window.__runtimeFetchSettled")
    result = service_worker_page.evaluate(
        """async ([name, key]) => ({
            fetch: window.__runtimeFetchResult,
            cached: Boolean(await (await caches.open(name)).match(key))
        })""",
        [cache_name, cache_key],
    )

    assert result["fetch"]["ok"] is True
    assert result["fetch"]["status"] == 200
    assert result["fetch"]["body"]
    assert result["cached"] is True


def test_runtime_cache_keeps_query_keys_separate(
    service_worker_page: Page,
    app_url: str,
    expected_browser_errors: list[str],
) -> None:
    prepare_controlled_page(service_worker_page, app_url)
    cache_name = current_cache_name(service_worker_page)
    cached_key = "/robots.txt?runtime-query=first"
    uncached_key = "/robots.txt?runtime-query=second"
    online = service_worker_page.evaluate(
        """async ([name, cachedKey, uncachedKey]) => {
            const cache = await caches.open(name);
            await Promise.all([cache.delete(cachedKey), cache.delete(uncachedKey)]);
            const response = await fetch(cachedKey);
            return { ok: response.ok, body: await response.text() };
        }""",
        [cache_name, cached_key, uncached_key],
    )
    service_worker_page.wait_for_function(
        """async ([name, key]) => Boolean(
            await (await caches.open(name)).match(key)
        )""",
        arg=[cache_name, cached_key],
        timeout=10000,
    )

    expected_browser_errors.append(
        "console.error: Failed to load resource: net::ERR_FAILED ("
        + app_url.rstrip("/")
        + "/)"
    )
    service_worker_page.context.set_offline(True)
    try:
        service_worker_page.wait_for_function("() => navigator.onLine === false")
        offline = service_worker_page.evaluate(
            """async ([name, cachedKey, uncachedKey]) => {
                const cachedResponse = await fetch(cachedKey);
                let uncachedRejected = false;
                try {
                    await fetch(uncachedKey);
                } catch (error) {
                    uncachedRejected = true;
                }
                const directUncachedMatch = await (
                    await caches.open(name)
                ).match(uncachedKey);
                return {
                    cachedOk: cachedResponse.ok,
                    cachedBody: await cachedResponse.text(),
                    uncachedRejected: uncachedRejected,
                    directUncachedMatch: Boolean(directUncachedMatch)
                };
            }""",
            [cache_name, cached_key, uncached_key],
        )
    finally:
        service_worker_page.context.set_offline(False)

    assert online["ok"] is True
    assert online["body"]
    assert offline["cachedOk"] is True
    assert offline["cachedBody"] == online["body"]
    assert offline["uncachedRejected"] is True
    assert offline["directUncachedMatch"] is False


def test_failed_runtime_network_fetch_does_not_create_cache_entry(
    service_worker_page: Page,
    app_url: str,
    expected_browser_errors: list[str],
) -> None:
    prepare_controlled_page(service_worker_page, app_url)
    cache_name = current_cache_name(service_worker_page)
    cache_key = "/robots.txt?runtime-network=failure"
    service_worker_page.evaluate(
        """async ([name, key]) => (await caches.open(name)).delete(key)""",
        [cache_name, cache_key],
    )

    expected_browser_errors.append(
        "console.error: Failed to load resource: net::ERR_FAILED ("
        + app_url.rstrip("/")
        + "/)"
    )
    service_worker_page.context.set_offline(True)
    try:
        service_worker_page.wait_for_function("() => navigator.onLine === false")
        result = service_worker_page.evaluate(
            """async ([name, key]) => {
                let rejected = false;
                try {
                    await fetch(key);
                } catch (error) {
                    rejected = true;
                }
                const cached = await (await caches.open(name)).match(key);
                return { rejected: rejected, cached: Boolean(cached) };
            }""",
            [cache_name, cache_key],
        )
    finally:
        service_worker_page.context.set_offline(False)

    assert result == {"rejected": True, "cached": False}


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


def test_non_get_request_is_forwarded_without_being_cached(
    service_worker_page: Page,
    app_url: str,
    expected_browser_errors: list[str],
) -> None:
    prepare_controlled_page(service_worker_page, app_url)
    cache_name = current_cache_name(service_worker_page)
    cache_key = "/robots.txt?runtime-method=post"
    expected_browser_errors.append(
        "console.error: Failed to load resource: the server responded with a status of "
        "501 (Unsupported method ('POST')) ("
        + app_url.rstrip("/")
        + "/)"
    )
    result = service_worker_page.evaluate(
        """async ([name, key]) => {
            const cache = await caches.open(name);
            await cache.delete(key);
            const response = await fetch(key, {
                method: 'POST',
                body: 'service-worker-post-body'
            });
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
    assert result["status"] == 501
    assert result["bodyLength"] > 0
    assert result["cached"] is False


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
    service_worker_page: Page,
    app_url: str,
    legacy_path: str,
    public_path: str,
    title: str,
    heading: str,
) -> None:
    prepare_controlled_page(service_worker_page, app_url)
    online_response = service_worker_page.goto(
        app_url.rstrip("/") + legacy_path,
        wait_until="domcontentloaded",
    )

    assert online_response is not None
    assert online_response.ok
    assert service_worker_page.evaluate("() => location.pathname + location.search") == public_path
    assert_document(service_worker_page, title, "main h1", heading)

    service_worker_page.context.set_offline(True)
    try:
        service_worker_page.wait_for_function("() => navigator.onLine === false")
        offline_response = service_worker_page.reload(wait_until="domcontentloaded")

        assert offline_response is not None
        assert offline_response.ok
        assert service_worker_page.evaluate(
            "() => location.pathname + location.search"
        ) == public_path
        assert_document(service_worker_page, title, "main h1", heading)
    finally:
        service_worker_page.context.set_offline(False)


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
        if path == "/digital/?tz=UTC":
            assert service_worker_page.locator("#digitalLabel").inner_text() == "UTC"
    finally:
        service_worker_page.context.set_offline(False)


@pytest.mark.parametrize(
    ("path", "title", "selector"),
    [
        pytest.param(
            "/digital/unknown",
            "Fullscreen Online Digital Clock | Clocksimulator",
            "#digitalTime",
            id="digital-descendant-uses-digital-fallback",
        ),
        pytest.param(
            "/digitalized",
            "Fullscreen Online Analog Clock | Clocksimulator",
            "#clock",
            id="digital-prefix-near-match-uses-root-fallback",
        ),
    ],
)
def test_offline_navigation_fallback_respects_digital_path_boundary(
    service_worker_page: Page,
    app_url: str,
    path: str,
    title: str,
    selector: str,
) -> None:
    prepare_controlled_page(service_worker_page, app_url)
    service_worker_page.context.set_offline(True)
    try:
        service_worker_page.wait_for_function("() => navigator.onLine === false")
        response = service_worker_page.goto(
            app_url.rstrip("/") + path,
            wait_until="domcontentloaded",
        )

        assert response is not None
        assert response.ok
        assert service_worker_page.evaluate("() => location.pathname") == path
        assert_document(service_worker_page, title, selector, None)
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


def test_missing_legal_cache_entry_uses_root_fallback(
    service_worker_page: Page,
    app_url: str,
) -> None:
    prepare_controlled_page(service_worker_page, app_url)
    deleted = service_worker_page.evaluate(
        """async () => {
            const names = await caches.keys();
            const name = names.find(candidate => candidate.indexOf('clocksimulator-v') === 0);
            const cache = await caches.open(name);
            return cache.delete('/privacy');
        }"""
    )

    assert deleted is True
    service_worker_page.context.set_offline(True)
    try:
        service_worker_page.wait_for_function("() => navigator.onLine === false")
        response = service_worker_page.goto(
            app_url.rstrip("/") + "/privacy.html?source=test",
            wait_until="domcontentloaded",
        )

        assert response is not None
        assert response.ok
        assert service_worker_page.evaluate(
            "() => location.pathname + location.search"
        ) == "/privacy.html?source=test"
        assert_document(
            service_worker_page,
            "Fullscreen Online Analog Clock | Clocksimulator",
            "#clock",
            None,
        )
    finally:
        service_worker_page.context.set_offline(False)


@pytest.mark.parametrize(
    ("fallback_key", "path"),
    [
        pytest.param("/", "/missing-root-fallback", id="missing-root-fallback"),
        pytest.param(
            "/digital/",
            "/digital/unknown",
            id="missing-digital-fallback",
        ),
    ],
)
def test_offline_navigation_fails_when_required_fallback_is_missing(
    service_worker_page: Page,
    app_url: str,
    fallback_key: str,
    path: str,
) -> None:
    prepare_controlled_page(service_worker_page, app_url)
    cache_name = current_cache_name(service_worker_page)
    deleted = service_worker_page.evaluate(
        """async ([name, key]) => (await caches.open(name)).delete(key)""",
        [cache_name, fallback_key],
    )
    assert deleted is True

    service_worker_page.context.set_offline(True)
    try:
        service_worker_page.wait_for_function("() => navigator.onLine === false")
        with pytest.raises(PlaywrightError, match="ERR_FAILED"):
            service_worker_page.goto(
                app_url.rstrip("/") + path,
                wait_until="domcontentloaded",
            )
    finally:
        service_worker_page.context.set_offline(False)
