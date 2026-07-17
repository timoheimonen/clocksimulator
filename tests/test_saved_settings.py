from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page

from tests.helpers import open_page


SETTINGS_KEY = "clocksimulator-user-settings"
KNOWN_FIELDS = {"theme", "wakeLock", "secondModeTick", "digitalShowSeconds"}


def open_clock(
    page: Page,
    app_url: str,
    path: str = "",
    params: dict[str, str] | None = None,
    storage_value: str | None = None,
) -> None:
    local_storage_items = None if storage_value is None else {SETTINGS_KEY: storage_value}
    open_page(
        page,
        app_url,
        params=params,
        localStorage_items=local_storage_items,
        path=path,
    )


def click_control(page: Page, selector: str) -> None:
    page.keyboard.press("Tab")
    page.wait_for_function(
        "() => !document.querySelector('.toggle-wrapper').hasAttribute('inert')"
    )
    page.locator(selector).click()


def open_about(page: Page) -> None:
    if page.locator("#aboutBtn").get_attribute("aria-expanded") != "true":
        click_control(page, "#aboutBtn")


def enable_saved_settings(page: Page) -> None:
    if page.locator("#saveSettingsToggle").is_checked():
        click_control(page, "label.theme-toggle")
    else:
        open_about(page)
        click_control(page, "#saveSettingsLabel")


def read_saved_settings(page: Page) -> dict[str, object] | None:
    raw = page.evaluate("key => localStorage.getItem(key)", SETTINGS_KEY)
    return json.loads(raw) if raw is not None else None


def replace_saved_settings(page: Page, settings: dict[str, object]) -> None:
    page.evaluate(
        "([key, value]) => localStorage.setItem(key, value)",
        [SETTINGS_KEY, json.dumps(settings)],
    )


def install_wake_lock_mock(page: Page) -> None:
    page.add_init_script("""
        Object.defineProperty(navigator, 'wakeLock', {
            configurable: true,
            value: {
                request: function() {
                    return Promise.resolve({
                        addEventListener: function() {},
                        release: function() { return Promise.resolve(); }
                    });
                }
            }
        });
    """)


def test_analog_save_preserves_digital_seconds_and_updates_shared_fields(
    page: Page, app_url: str
) -> None:
    install_wake_lock_mock(page)
    initial = {
        "theme": "light",
        "wakeLock": False,
        "secondModeTick": True,
        "digitalShowSeconds": False,
    }
    open_clock(page, app_url, storage_value=json.dumps(initial))

    click_control(page, "label.wake-lock-toggle")
    click_control(page, "label.theme-toggle")
    click_control(page, "label.second-mode-toggle")

    assert read_saved_settings(page) == {
        "theme": "dark",
        "wakeLock": True,
        "secondModeTick": False,
        "digitalShowSeconds": False,
    }


def test_digital_save_preserves_analog_seconds_and_updates_shared_fields(
    page: Page, app_url: str
) -> None:
    install_wake_lock_mock(page)
    initial = {
        "theme": "light",
        "wakeLock": False,
        "secondModeTick": False,
        "digitalShowSeconds": False,
    }
    open_clock(page, app_url, path="/digital/", storage_value=json.dumps(initial))

    click_control(page, "label.wake-lock-toggle")
    click_control(page, "label.theme-toggle")
    click_control(page, "label.second-mode-toggle")

    assert read_saved_settings(page) == {
        "theme": "dark",
        "wakeLock": True,
        "secondModeTick": False,
        "digitalShowSeconds": True,
    }


def test_analog_save_rereads_digital_seconds_at_write_time(
    page: Page, app_url: str
) -> None:
    initial = {
        "theme": "light",
        "wakeLock": False,
        "secondModeTick": True,
        "digitalShowSeconds": True,
    }
    open_clock(page, app_url, storage_value=json.dumps(initial))
    replace_saved_settings(
        page,
        {
            "theme": "light",
            "wakeLock": False,
            "secondModeTick": True,
            "digitalShowSeconds": False,
            "unknown": "removed",
        },
    )

    click_control(page, "label.second-mode-toggle")

    assert read_saved_settings(page) == {
        "theme": "light",
        "wakeLock": False,
        "secondModeTick": False,
        "digitalShowSeconds": False,
    }


def test_digital_save_rereads_analog_seconds_at_write_time(
    page: Page, app_url: str
) -> None:
    initial = {
        "theme": "light",
        "wakeLock": False,
        "secondModeTick": True,
        "digitalShowSeconds": True,
    }
    open_clock(page, app_url, path="/digital/", storage_value=json.dumps(initial))
    replace_saved_settings(
        page,
        {
            "theme": "light",
            "wakeLock": False,
            "secondModeTick": False,
            "digitalShowSeconds": True,
            "unknown": "removed",
        },
    )

    click_control(page, "label.second-mode-toggle")

    assert read_saved_settings(page) == {
        "theme": "light",
        "wakeLock": False,
        "secondModeTick": False,
        "digitalShowSeconds": False,
    }


@pytest.mark.parametrize("path", ["", "/digital/"])
@pytest.mark.parametrize(
    ("storage_value", "case_name"),
    [
        (None, "missing"),
        ('{"theme":"dark","wakeLock":false}', "partial"),
        ("{", "malformed"),
        ("null", "null"),
        ("[]", "array"),
        (
            '{"theme":"light","wakeLock":false,"secondModeTick":"smooth",'
            '"digitalShowSeconds":"hidden","unknown":true}',
            "wrong_field_types",
        ),
    ],
    ids=lambda value: value if isinstance(value, str) and value in {
        "missing",
        "partial",
        "malformed",
        "null",
        "array",
        "wrong_field_types",
    } else None,
)
def test_invalid_saved_data_is_normalized_without_page_errors(
    page: Page,
    app_url: str,
    path: str,
    storage_value: str | None,
    case_name: str,
) -> None:
    page_errors: list[str] = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    open_clock(page, app_url, path=path, storage_value=storage_value)

    enable_saved_settings(page)

    saved = read_saved_settings(page)
    assert saved is not None, case_name
    assert set(saved) == KNOWN_FIELDS
    assert saved["theme"] in {"dark", "light"}
    assert isinstance(saved["wakeLock"], bool)
    assert saved["secondModeTick"] is True
    assert saved["digitalShowSeconds"] is True
    assert page_errors == []


@pytest.mark.parametrize("path", ["", "/digital/"])
def test_disabling_saved_settings_removes_the_shared_key(
    page: Page, app_url: str, path: str
) -> None:
    initial = {
        "theme": "light",
        "wakeLock": False,
        "secondModeTick": False,
        "digitalShowSeconds": False,
    }
    open_clock(page, app_url, path=path, storage_value=json.dumps(initial))

    open_about(page)
    click_control(page, "#saveSettingsLabel")

    assert page.locator("#saveSettingsToggle").is_checked() is False
    assert read_saved_settings(page) is None


@pytest.mark.parametrize("path", ["", "/digital/"])
def test_url_parameters_disable_saved_settings_writes(
    page: Page, app_url: str, path: str
) -> None:
    open_clock(page, app_url, path=path, params={"theme": "light"})

    assert page.locator("#saveSettingsToggle").is_disabled() is True
    click_control(page, "label.theme-toggle")

    assert page.evaluate(
        "() => document.documentElement.classList.contains('dark-mode')"
    ) is True
    assert read_saved_settings(page) is None


@pytest.mark.parametrize("path", ["", "/digital/"])
def test_blocked_local_storage_is_handled_silently(
    page: Page, app_url: str, path: str
) -> None:
    page_errors: list[str] = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.add_init_script("""
        ['getItem', 'setItem', 'removeItem'].forEach(function(method) {
            Object.defineProperty(Storage.prototype, method, {
                configurable: true,
                value: function() { throw new DOMException('Blocked', 'SecurityError'); }
            });
        });
    """)
    open_clock(page, app_url, path=path)

    open_about(page)
    click_control(page, "#saveSettingsLabel")
    click_control(page, "#saveSettingsLabel")

    assert page.locator("#saveSettingsToggle").is_checked() is False
    assert page_errors == []
