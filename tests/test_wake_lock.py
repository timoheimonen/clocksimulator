from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page

from tests.helpers import (
    install_css_motion_suppression,
    install_visibility_mock,
    open_page,
)


SETTINGS_KEY = "clocksimulator-user-settings"
pytestmark = pytest.mark.cross_browser


@pytest.fixture(autouse=True)
def suppress_wake_lock_css_motion(page: Page) -> None:
    install_css_motion_suppression(page)


def settings_with_wake_lock(enabled: bool) -> str:
    return json.dumps(
        {
            "theme": "light",
            "wakeLock": enabled,
            "secondModeTick": True,
            "digitalShowSeconds": True,
        },
        separators=(",", ":"),
    )


def install_missing_wake_lock_api(page: Page) -> None:
    page.add_init_script("""
        try { delete navigator.wakeLock; } catch (e) {}
        try { delete Navigator.prototype.wakeLock; } catch (e) {}
        window.__wakeLockApiIsAbsent = !('wakeLock' in navigator);
    """)


def install_wake_lock_mock(page: Page) -> None:
    page.add_init_script("""
        (function () {
            let nextRequestId = 1;
            const requests = [];
            const sentinels = [];
            const unhandled = [];

            window.addEventListener('unhandledrejection', function (event) {
                unhandled.push(String(event.reason));
            });

            function pendingRequest(requestId) {
                return requests.find(function (request) {
                    return request.id === requestId && request.status === 'pending';
                });
            }

            function nextPendingRequest() {
                return requests.find(function (request) {
                    return request.status === 'pending';
                });
            }

            function findSentinel(sentinelId) {
                return sentinels.find(function (sentinel) {
                    return sentinel.id === sentinelId;
                });
            }

            function dispatchRelease(sentinel) {
                sentinel.listeners.slice().forEach(function (listener) {
                    listener.call(sentinel.publicValue, new Event('release'));
                });
            }

            function createSentinel(requestId) {
                const sentinel = {
                    id: 'sentinel-' + requestId,
                    requestId: requestId,
                    released: false,
                    releaseCalls: 0,
                    listeners: [],
                    publicValue: null
                };
                sentinel.publicValue = {
                    __testId: sentinel.id,
                    get released() { return sentinel.released; },
                    addEventListener: function (type, listener) {
                        if (type === 'release') sentinel.listeners.push(listener);
                    },
                    release: function () {
                        sentinel.releaseCalls += 1;
                        if (!sentinel.released) {
                            sentinel.released = true;
                            dispatchRelease(sentinel);
                        }
                        return Promise.resolve();
                    }
                };
                sentinels.push(sentinel);
                return sentinel;
            }

            const wakeLock = {
                request: function (type) {
                    const request = {
                        id: nextRequestId++,
                        type: type,
                        status: 'pending',
                        sentinelId: null,
                        resolve: null,
                        reject: null
                    };
                    requests.push(request);
                    return new Promise(function (resolve, reject) {
                        request.resolve = resolve;
                        request.reject = reject;
                    });
                }
            };

            Object.defineProperty(navigator, 'wakeLock', {
                configurable: true,
                value: wakeLock
            });

            window.__wakeLockTest = {
                resolve: function (requestId) {
                    const request = pendingRequest(requestId);
                    if (!request) throw new Error('Pending Wake Lock request not found: ' + requestId);
                    const sentinel = createSentinel(request.id);
                    request.status = 'resolved';
                    request.sentinelId = sentinel.id;
                    request.resolve(sentinel.publicValue);
                    return sentinel.id;
                },
                resolveNext: function () {
                    const request = nextPendingRequest();
                    if (!request) throw new Error('No pending Wake Lock request');
                    return this.resolve(request.id);
                },
                reject: function (requestId, message) {
                    const request = pendingRequest(requestId);
                    if (!request) throw new Error('Pending Wake Lock request not found: ' + requestId);
                    request.status = 'rejected';
                    request.reject(new DOMException(message || 'Wake Lock rejected', 'NotAllowedError'));
                },
                rejectNext: function (message) {
                    const request = nextPendingRequest();
                    if (!request) throw new Error('No pending Wake Lock request');
                    this.reject(request.id, message);
                },
                systemRelease: function (sentinelId) {
                    const sentinel = findSentinel(sentinelId);
                    if (!sentinel) throw new Error('Wake Lock sentinel not found: ' + sentinelId);
                    if (!sentinel.released) {
                        sentinel.released = true;
                        dispatchRelease(sentinel);
                    }
                },
                snapshot: function () {
                    return {
                        requests: requests.map(function (request) {
                            return {
                                id: request.id,
                                type: request.type,
                                status: request.status,
                                sentinelId: request.sentinelId
                            };
                        }),
                        pendingIds: requests.filter(function (request) {
                            return request.status === 'pending';
                        }).map(function (request) { return request.id; }),
                        activeSentinelIds: sentinels.filter(function (sentinel) {
                            return !sentinel.released;
                        }).map(function (sentinel) { return sentinel.id; }),
                        sentinels: sentinels.map(function (sentinel) {
                            return {
                                id: sentinel.id,
                                requestId: sentinel.requestId,
                                released: sentinel.released,
                                releaseCalls: sentinel.releaseCalls
                            };
                        }),
                        unhandled: unhandled.slice()
                    };
                }
            };
        })();
    """)


def install_synchronous_request_failure(page: Page) -> None:
    page.add_init_script("""
        window.__wakeLockSyncRequests = 0;
        Object.defineProperty(navigator, 'wakeLock', {
            configurable: true,
            value: {
                request: function () {
                    window.__wakeLockSyncRequests += 1;
                    throw new DOMException('request failed synchronously', 'NotAllowedError');
                }
            }
        });
    """)


def install_synchronous_release_failure(page: Page) -> None:
    page.add_init_script("""
        window.__wakeLockSyncReleases = 0;
        Object.defineProperty(navigator, 'wakeLock', {
            configurable: true,
            value: {
                request: function () {
                    return Promise.resolve({
                        addEventListener: function () {},
                        release: function () {
                            window.__wakeLockSyncReleases += 1;
                            throw new Error('release failed synchronously');
                        }
                    });
                }
            }
        });
    """)


def open_wake_page(
    page: Page,
    app_url: str,
    path: str,
    *,
    saved_intent: bool | None = None,
    params: dict[str, str] | None = None,
) -> None:
    items = None
    if saved_intent is not None:
        items = {SETTINGS_KEY: settings_with_wake_lock(saved_intent)}
    open_page(
        page,
        app_url,
        path=path,
        params=params,
        localStorage_items=items,
    )


def reveal_controls(page: Page) -> None:
    page.mouse.move(20, 20)
    page.wait_for_function(
        "() => !document.querySelector('.toggle-wrapper').hasAttribute('inert')"
    )


def click_control(page: Page, selector: str) -> None:
    reveal_controls(page)
    page.locator(selector).click()


def flush_promises(page: Page) -> None:
    page.evaluate("""async () => {
        await Promise.resolve();
        await Promise.resolve();
        await Promise.resolve();
    }""")


def wake_snapshot(page: Page) -> dict[str, object]:
    return page.evaluate("() => window.__wakeLockTest.snapshot()")


def resolve_next(page: Page) -> str:
    sentinel_id = page.evaluate("() => window.__wakeLockTest.resolveNext()")
    flush_promises(page)
    return sentinel_id


def reject_next(page: Page) -> None:
    page.evaluate("() => window.__wakeLockTest.rejectNext('permission denied')")
    flush_promises(page)


def set_visibility(page: Page, state: str) -> None:
    page.evaluate("state => window.__setTestVisibility(state)", state)
    flush_promises(page)


def read_saved_intent(page: Page) -> bool:
    return page.evaluate(
        "key => JSON.parse(localStorage.getItem(key)).wakeLock",
        SETTINGS_KEY,
    )


@pytest.mark.parametrize("path", ["", "/digital/"], ids=("analog", "digital"))
def test_missing_api_keeps_control_unavailable_without_errors(
    page: Page, app_url: str, path: str
) -> None:
    install_missing_wake_lock_api(page)
    open_wake_page(page, app_url, path)
    reveal_controls(page)

    assert page.evaluate("() => window.__wakeLockApiIsAbsent") is True
    state = page.locator("#wakeLockLabel").evaluate("""element => {
        const rect = element.getBoundingClientRect();
        return {
            display: getComputedStyle(element).display,
            width: rect.width,
            height: rect.height,
            hidden: element.checkVisibility ? !element.checkVisibility() : rect.width === 0
        };
    }""")
    assert state == {"display": "none", "width": 0, "height": 0, "hidden": True}
    assert page.locator("#wakeLockToggle").is_checked() is False


@pytest.mark.parametrize("path", ["", "/digital/"], ids=("analog", "digital"))
def test_supported_api_defaults_off_without_request(
    page: Page, app_url: str, path: str
) -> None:
    install_wake_lock_mock(page)
    open_wake_page(page, app_url, path)
    reveal_controls(page)

    assert page.locator("#wakeLockLabel").is_visible() is True
    assert page.locator("#wakeLockToggle").is_checked() is False
    assert wake_snapshot(page) == {
        "requests": [],
        "pendingIds": [],
        "activeSentinelIds": [],
        "sentinels": [],
        "unhandled": [],
    }


@pytest.mark.parametrize("path", ["", "/digital/"], ids=("analog", "digital"))
def test_toggle_on_requests_exactly_one_screen_lock(
    page: Page, app_url: str, path: str
) -> None:
    install_wake_lock_mock(page)
    open_wake_page(page, app_url, path)

    click_control(page, "label.wake-lock-toggle")

    state = wake_snapshot(page)
    assert state["requests"] == [
        {"id": 1, "type": "screen", "status": "pending", "sentinelId": None}
    ]
    assert state["pendingIds"] == [1]
    assert state["activeSentinelIds"] == []
    resolve_next(page)
    assert page.locator("#wakeLockToggle").is_checked() is True
    assert wake_snapshot(page)["activeSentinelIds"] == ["sentinel-1"]


@pytest.mark.parametrize("path", ["", "/digital/"], ids=("analog", "digital"))
def test_toggle_off_releases_active_sentinel_once(
    page: Page, app_url: str, path: str
) -> None:
    install_wake_lock_mock(page)
    open_wake_page(page, app_url, path)
    click_control(page, "label.wake-lock-toggle")
    resolve_next(page)

    click_control(page, "label.wake-lock-toggle")
    flush_promises(page)
    state = wake_snapshot(page)

    assert page.locator("#wakeLockToggle").is_checked() is False
    assert state["pendingIds"] == []
    assert state["activeSentinelIds"] == []
    assert state["sentinels"] == [
        {
            "id": "sentinel-1",
            "requestId": 1,
            "released": True,
            "releaseCalls": 1,
        }
    ]
    assert state["unhandled"] == []


@pytest.mark.parametrize("path", ["", "/digital/"], ids=("analog", "digital"))
def test_saved_true_requests_lock_on_parameterless_load(
    page: Page, app_url: str, path: str
) -> None:
    install_wake_lock_mock(page)
    open_wake_page(page, app_url, path, saved_intent=True)

    assert wake_snapshot(page)["requests"] == [
        {"id": 1, "type": "screen", "status": "pending", "sentinelId": None}
    ]
    resolve_next(page)
    assert page.locator("#wakeLockToggle").is_checked() is True
    assert read_saved_intent(page) is True


@pytest.mark.parametrize("path", ["", "/digital/"], ids=("analog", "digital"))
def test_rejected_request_preserves_saved_intent_and_coherent_ui(
    page: Page, app_url: str, path: str
) -> None:
    install_visibility_mock(page)
    install_wake_lock_mock(page)
    open_wake_page(page, app_url, path, saved_intent=False)
    click_control(page, "label.wake-lock-toggle")
    assert read_saved_intent(page) is True

    reject_next(page)
    state = wake_snapshot(page)

    assert state["unhandled"] == []
    assert page.locator("#wakeLockToggle").is_checked() is True
    assert read_saved_intent(page) is True
    assert state["pendingIds"] == []
    assert state["activeSentinelIds"] == []


@pytest.mark.parametrize("path", ["", "/digital/"], ids=("analog", "digital"))
def test_rejected_request_retries_once_after_hidden_to_visible_transition(
    page: Page, app_url: str, path: str
) -> None:
    install_visibility_mock(page)
    install_wake_lock_mock(page)
    open_wake_page(page, app_url, path, saved_intent=False)
    click_control(page, "label.wake-lock-toggle")
    reject_next(page)

    set_visibility(page, "hidden")
    set_visibility(page, "visible")
    state = wake_snapshot(page)

    assert len(state["requests"]) == 2
    assert state["pendingIds"] == [2]
    assert read_saved_intent(page) is True
    assert state["unhandled"] == []


@pytest.mark.parametrize("path", ["", "/digital/"], ids=("analog", "digital"))
def test_system_release_preserves_intent_and_reacquires_when_visible(
    page: Page, app_url: str, path: str
) -> None:
    install_visibility_mock(page)
    install_wake_lock_mock(page)
    open_wake_page(page, app_url, path, saved_intent=False)
    click_control(page, "label.wake-lock-toggle")
    sentinel_id = resolve_next(page)

    page.evaluate(
        "sentinelId => window.__wakeLockTest.systemRelease(sentinelId)",
        sentinel_id,
    )
    flush_promises(page)
    assert page.locator("#wakeLockToggle").is_checked() is True
    assert read_saved_intent(page) is True
    assert wake_snapshot(page)["activeSentinelIds"] == []

    set_visibility(page, "hidden")
    set_visibility(page, "visible")
    state = wake_snapshot(page)
    assert len(state["requests"]) == 2
    assert state["pendingIds"] == [2]
    resolve_next(page)
    assert wake_snapshot(page)["activeSentinelIds"] == ["sentinel-2"]


@pytest.mark.parametrize("path", ["", "/digital/"], ids=("analog", "digital"))
def test_repeated_visible_events_do_not_duplicate_pending_request(
    page: Page, app_url: str, path: str
) -> None:
    install_visibility_mock(page)
    install_wake_lock_mock(page)
    open_wake_page(page, app_url, path)
    click_control(page, "label.wake-lock-toggle")

    set_visibility(page, "visible")
    set_visibility(page, "visible")
    set_visibility(page, "visible")
    state = wake_snapshot(page)

    assert len(state["requests"]) == 1
    assert state["pendingIds"] == [1]
    assert state["activeSentinelIds"] == []


@pytest.mark.parametrize("path", ["", "/digital/"], ids=("analog", "digital"))
def test_repeated_visible_events_do_not_request_while_sentinel_is_active(
    page: Page, app_url: str, path: str
) -> None:
    install_visibility_mock(page)
    install_wake_lock_mock(page)
    open_wake_page(page, app_url, path)
    click_control(page, "label.wake-lock-toggle")
    resolve_next(page)

    set_visibility(page, "visible")
    set_visibility(page, "visible")
    state = wake_snapshot(page)

    assert len(state["requests"]) == 1
    assert state["pendingIds"] == []
    assert state["activeSentinelIds"] == ["sentinel-1"]


@pytest.mark.parametrize("path", ["", "/digital/"], ids=("analog", "digital"))
def test_hidden_to_visible_does_not_request_without_active_intent(
    page: Page, app_url: str, path: str
) -> None:
    install_visibility_mock(page)
    install_wake_lock_mock(page)
    open_wake_page(page, app_url, path)

    set_visibility(page, "hidden")
    set_visibility(page, "visible")

    assert wake_snapshot(page)["requests"] == []


@pytest.mark.parametrize("path", ["", "/digital/"], ids=("analog", "digital"))
def test_rapid_on_then_off_releases_late_sentinel_without_reactivating_ui(
    page: Page, app_url: str, path: str
) -> None:
    install_visibility_mock(page)
    install_wake_lock_mock(page)
    open_wake_page(page, app_url, path, saved_intent=False)

    click_control(page, "label.wake-lock-toggle")
    click_control(page, "label.wake-lock-toggle")
    assert page.locator("#wakeLockToggle").is_checked() is False
    assert read_saved_intent(page) is False
    resolve_next(page)
    state = wake_snapshot(page)

    assert state["sentinels"] == [
        {
            "id": "sentinel-1",
            "requestId": 1,
            "released": True,
            "releaseCalls": 1,
        }
    ]
    assert state["activeSentinelIds"] == []
    assert page.locator("#wakeLockToggle").is_checked() is False
    assert read_saved_intent(page) is False
    assert state["unhandled"] == []


@pytest.mark.parametrize("path", ["", "/digital/"], ids=("analog", "digital"))
def test_embed_hides_control_and_never_requests_lock(
    page: Page, app_url: str, path: str
) -> None:
    install_visibility_mock(page)
    install_wake_lock_mock(page)
    open_wake_page(
        page,
        app_url,
        path,
        saved_intent=True,
        params={"embed": "true"},
    )

    label_state = page.locator("#wakeLockLabel").evaluate("""element => {
        const rect = element.getBoundingClientRect();
        return {
            visible: element.checkVisibility ? element.checkVisibility() : rect.width > 0,
            width: rect.width,
            height: rect.height
        };
    }""")
    assert label_state == {"visible": False, "width": 0, "height": 0}
    assert page.locator("#wakeLockToggle").is_checked() is False
    assert wake_snapshot(page)["requests"] == []

    set_visibility(page, "visible")
    assert wake_snapshot(page)["requests"] == []


@pytest.mark.parametrize("path", ["", "/digital/"], ids=("analog", "digital"))
def test_synchronous_request_failure_preserves_intent_without_page_error(
    page: Page, app_url: str, path: str
) -> None:
    install_synchronous_request_failure(page)
    open_wake_page(page, app_url, path, saved_intent=False)

    click_control(page, "label.wake-lock-toggle")

    assert page.evaluate("() => window.__wakeLockSyncRequests") == 1
    assert page.locator("#wakeLockToggle").is_checked() is True
    assert read_saved_intent(page) is True


@pytest.mark.parametrize("path", ["", "/digital/"], ids=("analog", "digital"))
def test_synchronous_release_failure_keeps_off_state_without_page_error(
    page: Page, app_url: str, path: str
) -> None:
    install_synchronous_release_failure(page)
    open_wake_page(page, app_url, path, saved_intent=False)
    click_control(page, "label.wake-lock-toggle")
    flush_promises(page)

    click_control(page, "label.wake-lock-toggle")

    assert page.evaluate("() => window.__wakeLockSyncReleases") == 1
    assert page.locator("#wakeLockToggle").is_checked() is False
    assert read_saved_intent(page) is False
