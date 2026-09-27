from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page

from tests.helpers import (
    build_clock_url,
    navigate_clock_page,
    open_page,
    reload_clock_page,
    wait_for_clock_ready,
)


SETTINGS_KEY = "clocksimulator-user-settings"
SENTINEL_KEY = "unrelated-application-state"
KNOWN_FIELDS = {"theme", "wakeLock", "secondModeTick", "digitalShowSeconds"}


def full_settings(
    *,
    theme: str = "light",
    wake_lock: bool = False,
    analog_seconds: bool = True,
    digital_seconds: bool = True,
) -> dict[str, object]:
    return {
        "theme": theme,
        "wakeLock": wake_lock,
        "secondModeTick": analog_seconds,
        "digitalShowSeconds": digital_seconds,
    }


def open_clock(
    page: Page,
    app_url: str,
    path: str = "",
    params: dict[str, str] | None = None,
    storage_value: str | None = None,
    extra_storage: dict[str, str] | None = None,
) -> None:
    items = dict(extra_storage or {})
    if storage_value is not None:
        items[SETTINGS_KEY] = storage_value
    open_page(
        page,
        app_url,
        params=params,
        localStorage_items=items or None,
        path=path,
    )


def click_control(page: Page, selector: str) -> None:
    page.mouse.move(20, 20)
    page.wait_for_function(
        "() => !document.querySelector('.toggle-wrapper').hasAttribute('inert')"
    )
    page.locator(selector).click()


def open_about(page: Page) -> None:
    if page.locator("#aboutBtn").get_attribute("aria-expanded") != "true":
        click_control(page, "#aboutBtn")


def enable_saved_settings(page: Page) -> None:
    if not page.locator("#saveSettingsToggle").is_checked():
        open_about(page)
        click_control(page, "#saveSettingsLabel")


def read_raw_storage(page: Page, key: str = SETTINGS_KEY) -> str | None:
    return page.evaluate("key => localStorage.getItem(key)", key)


def read_saved_settings(page: Page) -> dict[str, object] | None:
    raw = read_raw_storage(page)
    return json.loads(raw) if raw is not None else None


def replace_saved_settings(page: Page, settings: dict[str, object]) -> None:
    page.evaluate(
        "([key, value]) => localStorage.setItem(key, value)",
        [SETTINGS_KEY, json.dumps(settings, separators=(",", ":"))],
    )


def install_resolved_wake_lock_mock(page: Page) -> None:
    page.add_init_script("""
        Object.defineProperty(navigator, 'wakeLock', {
            configurable: true,
            value: {
                request: function(type) {
                    window.__resolvedWakeLockRequests =
                        (window.__resolvedWakeLockRequests || []).concat(type);
                    return Promise.resolve({
                        addEventListener: function() {},
                        release: function() { return Promise.resolve(); }
                    });
                }
            }
        });
    """)


def install_missing_wake_lock_api(page: Page) -> None:
    page.add_init_script("""
        try { delete navigator.wakeLock; } catch (e) {}
        try { delete Navigator.prototype.wakeLock; } catch (e) {}
        window.__wakeLockApiIsAbsent = !('wakeLock' in navigator);
    """)


def assert_theme(page: Page, expected: str) -> None:
    state = page.evaluate("""() => ({
        dark: document.documentElement.classList.contains('dark-mode'),
        transparent: document.documentElement.classList.contains('transparent-mode'),
        toggle: document.getElementById('themeToggle').checked
    })""")
    if expected == "dark":
        assert state == {"dark": True, "transparent": False, "toggle": True}
    elif expected == "light":
        assert state == {"dark": False, "transparent": False, "toggle": False}
    else:
        assert state == {"dark": False, "transparent": True, "toggle": False}


def assert_common_controls(
    page: Page,
    *,
    theme: str,
    wake_lock: bool,
    seconds: bool,
) -> None:
    assert_theme(page, theme)
    if wake_lock:
        page.wait_for_function("() => document.getElementById('wakeLockToggle').checked")
    assert page.locator("#wakeLockToggle").is_checked() is wake_lock
    assert page.locator("#secondModeToggle").is_checked() is seconds
    assert page.locator("#saveSettingsToggle").is_checked() is True


@pytest.mark.cross_browser
@pytest.mark.parametrize(
    ("path", "expected_settings"),
    [
        (
            "",
            full_settings(
                theme="dark",
                wake_lock=True,
                analog_seconds=False,
                digital_seconds=True,
            ),
        ),
        (
            "/digital/",
            full_settings(
                theme="dark",
                wake_lock=True,
                analog_seconds=True,
                digital_seconds=False,
            ),
        ),
    ],
    ids=("analog", "digital"),
)
def test_user_changes_survive_real_reload(
    page: Page,
    app_url: str,
    path: str,
    expected_settings: dict[str, object],
) -> None:
    install_resolved_wake_lock_mock(page)
    open_clock(page, app_url, path=path)
    enable_saved_settings(page)

    click_control(page, "label.theme-toggle")
    click_control(page, "label.wake-lock-toggle")
    click_control(page, "label.second-mode-toggle")

    assert read_saved_settings(page) == expected_settings
    reload_clock_page(page)
    assert_common_controls(
        page,
        theme="dark",
        wake_lock=True,
        seconds=False,
    )
    assert read_saved_settings(page) == expected_settings


@pytest.mark.cross_browser
def test_navigation_round_trip_preserves_shared_and_independent_fields(
    page: Page, app_url: str
) -> None:
    install_resolved_wake_lock_mock(page)
    open_clock(page, app_url, storage_value=json.dumps(full_settings()))

    click_control(page, "label.theme-toggle")
    click_control(page, "label.wake-lock-toggle")
    click_control(page, "label.second-mode-toggle")
    after_analog = full_settings(
        theme="dark",
        wake_lock=True,
        analog_seconds=False,
        digital_seconds=True,
    )
    assert read_saved_settings(page) == after_analog

    open_about(page)
    page.locator("#digitalClockLink").click()
    page.wait_for_url("**/digital/")
    wait_for_clock_ready(page)

    assert page.locator("#digitalTime").text_content() == "12:00:00"
    assert_common_controls(
        page,
        theme="dark",
        wake_lock=True,
        seconds=True,
    )
    assert read_saved_settings(page) == after_analog

    click_control(page, "label.theme-toggle")
    click_control(page, "label.second-mode-toggle")
    after_digital = full_settings(
        theme="light",
        wake_lock=True,
        analog_seconds=False,
        digital_seconds=False,
    )
    assert read_saved_settings(page) == after_digital

    open_about(page)
    page.locator("#analogClockLink").click()
    page.wait_for_url(app_url + "/")
    wait_for_clock_ready(page)

    assert page.locator("#clock").get_attribute("aria-label") == "The time is 12:00"
    assert_common_controls(
        page,
        theme="light",
        wake_lock=True,
        seconds=False,
    )
    assert read_saved_settings(page) == after_digital


@pytest.mark.parametrize("path", [pytest.param("", id="analog")])
def test_disabling_saved_settings_then_reloading_restores_defaults(
    page: Page, app_url: str, path: str
) -> None:
    install_resolved_wake_lock_mock(page)
    initial = full_settings(
        theme="dark",
        wake_lock=True,
        analog_seconds=False,
        digital_seconds=False,
    )
    open_clock(page, app_url, path=path, storage_value=json.dumps(initial))

    open_about(page)
    click_control(page, "#saveSettingsLabel")
    assert read_raw_storage(page) is None

    reload_clock_page(page)
    assert_theme(page, "light")
    assert page.locator("#wakeLockToggle").is_checked() is False
    assert page.locator("#secondModeToggle").is_checked() is True
    assert page.locator("#saveSettingsToggle").is_checked() is False


@pytest.mark.parametrize(
    ("path", "url_theme"),
    [
        pytest.param("", "light", id="analog"),
        pytest.param("/digital/", "transparent", id="digital"),
    ],
)
def test_url_visit_is_byte_preserving_temporary_override(
    page: Page, app_url: str, path: str, url_theme: str
) -> None:
    install_resolved_wake_lock_mock(page)
    raw_settings = (
        '{ "theme": "dark", "wakeLock": true, "secondModeTick": false, '
        '"digitalShowSeconds": false, "future": {"revision": 7, "name": "å"} }'
    )
    raw_sentinel = '  {"owner":"another-app","bytes":"unchanged"}  '
    open_clock(
        page,
        app_url,
        path=path,
        params={"theme": url_theme, "seconds": "smooth"},
        storage_value=raw_settings,
        extra_storage={SENTINEL_KEY: raw_sentinel},
    )

    assert_theme(page, url_theme)
    assert page.locator("#saveSettingsToggle").is_disabled() is True
    click_control(page, "label.theme-toggle")
    click_control(page, "label.second-mode-toggle")
    assert read_raw_storage(page) == raw_settings
    assert read_raw_storage(page, SENTINEL_KEY) == raw_sentinel
    assert page.evaluate("() => window.__resolvedWakeLockRequests || []") == []

    navigate_clock_page(page, build_clock_url(app_url, path))
    assert_common_controls(
        page,
        theme="dark",
        wake_lock=True,
        seconds=False,
    )
    assert read_raw_storage(page) == raw_settings
    assert read_raw_storage(page, SENTINEL_KEY) == raw_sentinel


@pytest.mark.parametrize("path", ["", "/digital/"], ids=("analog", "digital"))
def test_write_time_reread_preserves_other_page_field_and_unknown_fields(
    page: Page, app_url: str, path: str
) -> None:
    raw_sentinel = "another-owner:do-not-touch\n"
    open_clock(
        page,
        app_url,
        path=path,
        storage_value=json.dumps(full_settings()),
        extra_storage={SENTINEL_KEY: raw_sentinel},
    )
    if path:
        externally_updated = full_settings(
            analog_seconds=False,
            digital_seconds=True,
        )
    else:
        externally_updated = full_settings(
            analog_seconds=True,
            digital_seconds=False,
        )
    externally_updated["futureVersion"] = {"source": "newer-tab", "enabled": True}
    replace_saved_settings(page, externally_updated)

    click_control(page, "label.theme-toggle")

    saved = read_saved_settings(page)
    assert saved is not None
    assert saved["theme"] == "dark"
    assert saved["secondModeTick"] is externally_updated["secondModeTick"]
    assert saved["digitalShowSeconds"] is externally_updated["digitalShowSeconds"]
    assert saved["futureVersion"] == externally_updated["futureVersion"]
    assert read_raw_storage(page, SENTINEL_KEY) == raw_sentinel


@pytest.mark.parametrize(
    ("path", "storage_value"),
    [
        pytest.param("", "[]", id="analog-array"),
        pytest.param(
            "",
            '{"theme":"light","wakeLock":"yes","secondModeTick":"smooth",'
            '"digitalShowSeconds":"hidden"}',
            id="analog-wrong_field_types",
        ),
        pytest.param("/digital/", '{"digitalShowSeconds":false}', id="digital-partial"),
    ],
)
def test_invalid_saved_data_is_safely_normalized_on_next_write(
    page: Page,
    app_url: str,
    path: str,
    storage_value: str,
) -> None:
    install_missing_wake_lock_api(page)
    open_clock(page, app_url, path=path, storage_value=storage_value)
    assert page.evaluate("() => window.__wakeLockApiIsAbsent") is True

    enable_saved_settings(page)
    click_control(page, "label.theme-toggle")

    saved = read_saved_settings(page)
    assert saved is not None, storage_value
    assert set(saved) == KNOWN_FIELDS
    assert saved["theme"] == "dark"
    assert saved["wakeLock"] is False
    assert isinstance(saved["secondModeTick"], bool)
    assert isinstance(saved["digitalShowSeconds"], bool)


@pytest.mark.parametrize(
    ("path", "mutation_selector"),
    [pytest.param("", "label.theme-toggle", id="analog-theme")],
)
def test_missing_wake_lock_api_does_not_overwrite_saved_true_intent(
    page: Page,
    app_url: str,
    path: str,
    mutation_selector: str,
) -> None:
    install_missing_wake_lock_api(page)
    initial = full_settings(wake_lock=True)
    open_clock(page, app_url, path=path, storage_value=json.dumps(initial))
    assert page.evaluate("() => window.__wakeLockApiIsAbsent") is True
    assert page.locator("#wakeLockLabel").is_hidden() is True

    click_control(page, mutation_selector)

    saved = read_saved_settings(page)
    assert saved is not None
    assert saved["wakeLock"] is True


@pytest.mark.parametrize("path", [pytest.param("", id="analog")])
def test_stored_transparent_theme_is_not_a_top_level_persistent_theme(
    page: Page, app_url: str, path: str
) -> None:
    initial = full_settings(theme="transparent")
    open_clock(page, app_url, path=path, storage_value=json.dumps(initial))

    assert_theme(page, "light")
    click_control(page, "label.second-mode-toggle")
    saved = read_saved_settings(page)
    assert saved is not None
    assert saved["theme"] == "light"


@pytest.mark.parametrize(
    ("path", "blocked_method"),
    [pytest.param("", "setItem", id="analog-setItem")],
)
def test_individual_storage_api_exceptions_are_silent_and_ui_remains_operable(
    page: Page,
    app_url: str,
    path: str,
    blocked_method: str,
) -> None:
    page.add_init_script(
        """(function (blockedMethod) {
            const original = Storage.prototype[blockedMethod];
            Object.defineProperty(Storage.prototype, blockedMethod, {
                configurable: true,
                value: function() {
                    window.__blockedStorageCalls = (window.__blockedStorageCalls || 0) + 1;
                    throw new DOMException('Blocked ' + blockedMethod, 'SecurityError');
                }
            });
            window.__originalBlockedStorageMethod = original;
        })(%s);""" % json.dumps(blocked_method)
    )
    open_clock(page, app_url, path=path)

    open_about(page)
    click_control(page, "#saveSettingsLabel")
    click_control(page, "label.theme-toggle")
    open_about(page)
    click_control(page, "#saveSettingsLabel")

    assert page.locator("#saveSettingsToggle").is_checked() is False
    assert page.evaluate("() => window.__blockedStorageCalls || 0") >= 1
    assert_theme(page, "dark")


@pytest.mark.parametrize("path", [pytest.param("/digital/", id="digital")])
def test_all_blocked_storage_operations_are_handled_silently(
    page: Page, app_url: str, path: str
) -> None:
    page.add_init_script("""
        ['getItem', 'setItem', 'removeItem'].forEach(function(method) {
            Object.defineProperty(Storage.prototype, method, {
                configurable: true,
                value: function() {
                    window.__blockedStorageCalls = (window.__blockedStorageCalls || 0) + 1;
                    throw new DOMException('Blocked ' + method, 'SecurityError');
                }
            });
        });
    """)
    open_clock(page, app_url, path=path)

    open_about(page)
    click_control(page, "#saveSettingsLabel")
    click_control(page, "label.theme-toggle")
    open_about(page)
    click_control(page, "#saveSettingsLabel")

    assert page.locator("#saveSettingsToggle").is_checked() is False
    assert page.evaluate("() => window.__blockedStorageCalls || 0") >= 3
    assert_theme(page, "dark")
