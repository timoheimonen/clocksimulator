from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page, Route

from tests.helpers import open_page, assert_screenshot


def _has_class(page: Page, cls: str) -> bool:
    return page.evaluate(f"() => document.documentElement.classList.contains('{cls}')")


def _open_with_theme_environment(
    page: Page,
    app_url: str,
    params: dict[str, str] | None = None,
    local_storage_items: dict[str, str] | None = None,
    os_dark: bool = False,
    os_dark_after_head: bool | None = None,
    storage_get_error: bool = False,
    bare_query: bool = False,
) -> dict[str, dict[str, bool | int]]:
    page.goto(app_url.rstrip("/") + "/robots.txt")
    page.evaluate(
        """async () => {
            var registrations = await navigator.serviceWorker.getRegistrations();
            await Promise.all(registrations.map(function (registration) {
                return registration.unregister();
            }));
        }"""
    )
    page.goto("about:blank")

    override = """<script>
        (function () {
          window.__settingsReadCount = 0;
          var originalGetItem = Storage.prototype.getItem;
          Storage.prototype.getItem = function (key) {
            if (key === 'clocksimulator-user-settings') {
              window.__settingsReadCount += 1;
              if (%s) {
                throw new DOMException('Storage access blocked', 'SecurityError');
              }
            }
            return originalGetItem.call(this, key);
          };
          window.__colorSchemeReadCount = 0;
          Object.defineProperty(window, 'matchMedia', {
            writable: true,
            value: function (query) {
              var matches = false;
              if (query === '(prefers-color-scheme: dark)') {
                window.__colorSchemeReadCount += 1;
                matches = window.__colorSchemeReadCount === 1 ? %s : %s;
              }
              return {
                matches: matches,
                media: query,
                onchange: null,
                addEventListener: function () {},
                removeEventListener: function () {}
              };
            }
          });
          window.__themeAtDOMContentLoaded = null;
          document.addEventListener('DOMContentLoaded', function () {
            window.__themeAtDOMContentLoaded = {
              dark: document.documentElement.classList.contains('dark-mode'),
              transparent: document.documentElement.classList.contains('transparent-mode'),
              checked: document.getElementById('themeToggle').checked,
              settingsReads: window.__settingsReadCount
            };
          });
        })();
      </script>""" % (
        json.dumps(storage_get_error),
        json.dumps(os_dark),
        json.dumps(os_dark if os_dark_after_head is None else os_dark_after_head),
    )
    head_probe = """<script>
        window.__themeAfterHead = {
          dark: document.documentElement.classList.contains('dark-mode'),
          transparent: document.documentElement.classList.contains('transparent-mode'),
          settingsReads: window.__settingsReadCount
        };
      </script>"""

    def route_handler(route: Route) -> None:
        if route.request.resource_type != "document":
            route.continue_()
            return
        response = route.fetch()
        body = response.text().replace("<head>", "<head>" + override, 1)
        body = body.replace("</head>", head_probe + "</head>", 1)
        route.fulfill(response=response, body=body.encode())

    page.route("**/*", route_handler)
    try:
        target_url = app_url.rstrip("/") + "/?" if bare_query else app_url
        open_page(
            page,
            target_url,
            params=params,
            localStorage_items=local_storage_items,
        )
        return page.evaluate(
            """() => ({
                head: window.__themeAfterHead,
                domcontentloaded: window.__themeAtDOMContentLoaded
            })"""
        )
    finally:
        page.unroute("**/*", route_handler)


def _assert_theme_probe(
    result: dict[str, dict[str, bool | int]],
    head_theme: str,
    final_theme: str,
    head_settings_reads: int,
    final_settings_reads: int,
) -> None:
    assert result == {
        "head": {
            "dark": head_theme == "dark",
            "transparent": head_theme == "transparent",
            "settingsReads": head_settings_reads,
        },
        "domcontentloaded": {
            "dark": final_theme == "dark",
            "transparent": final_theme == "transparent",
            "checked": final_theme == "dark",
            "settingsReads": final_settings_reads,
        },
    }


def test_theme_dark_param(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"theme": "dark"})
    assert _has_class(page, "dark-mode") is True


def test_theme_light_param(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"theme": "light"})
    assert _has_class(page, "dark-mode") is False
    assert _has_class(page, "transparent-mode") is False


def test_theme_transparent_param(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"theme": "transparent"})
    assert _has_class(page, "transparent-mode") is True


def test_theme_dark_css_variables(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"theme": "dark"})
    bg = page.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()")
    assert bg == "#000000"


def test_theme_light_css_variables(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"theme": "light"})
    bg = page.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()")
    assert bg == "#f0f0f0"


def test_theme_transparent_css_variables(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"theme": "transparent"})
    bg = page.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()")
    assert bg == "transparent"


def test_embed_mode_default_dark(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true"})
    assert _has_class(page, "dark-mode") is True


def test_embed_mode_theme_light_override(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true", "theme": "light"})
    assert _has_class(page, "dark-mode") is False
    assert _has_class(page, "transparent-mode") is False


def test_embed_mode_theme_transparent_override(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true", "theme": "transparent"})
    assert _has_class(page, "transparent-mode") is True


def test_saved_settings_theme_dark(page: Page, app_url: str) -> None:
    open_page(
        page,
        app_url,
        localStorage_items={"clocksimulator-user-settings": '{"theme":"dark","wakeLock":false,"secondModeTick":true}'},
    )
    assert _has_class(page, "dark-mode") is True


def test_saved_settings_theme_light(page: Page, app_url: str) -> None:
    open_page(
        page,
        app_url,
        localStorage_items={"clocksimulator-user-settings": '{"theme":"light","wakeLock":false,"secondModeTick":true}'},
    )
    assert _has_class(page, "dark-mode") is False


def test_os_dark_preference_applied(page: Page, app_url: str) -> None:
    page.add_init_script("""
        Object.defineProperty(window, 'matchMedia', {
            writable: true,
            value: function(query) {
                return {
                    matches: query === '(prefers-color-scheme: dark)',
                    media: query,
                    onchange: null,
                    addEventListener: function() {},
                    removeEventListener: function() {},
                };
            },
        });
    """)
    open_page(page, app_url)
    assert _has_class(page, "dark-mode") is True


def test_os_light_preference_applied(page: Page, app_url: str) -> None:
    """When OS prefers light mode and no theme is set, dark-mode should not be applied.
    Intercept HTML to inject matchMedia mock before inline scripts execute."""

    def handle_route(route):
        resp = route.fetch()
        body = resp.text()
        override = "<script>Object.defineProperty(window,'matchMedia',{writable:true,value:function(q){return{matches:q.includes('light'),media:q,onchange:null,addEventListener:function(){},removeEventListener:function(){}}}})</script>"
        body = body.replace("<head>", "<head>" + override, 1)
        route.fulfill(response=resp, body=body.encode())

    def route_handler(route):
        if route.request.resource_type == "document":
            handle_route(route)
        else:
            route.continue_()

    page.add_init_script("localStorage.clear();")
    page.route("**/*", route_handler)
    page.goto(app_url)
    page.wait_for_load_state("domcontentloaded")
    assert _has_class(page, "dark-mode") is False
    page.unroute("**/*", route_handler)


def test_theme_param_overrides_saved_settings(page: Page, app_url: str) -> None:
    open_page(
        page,
        app_url,
        params={"theme": "light"},
        localStorage_items={"clocksimulator-user-settings": '{"theme":"dark","wakeLock":false,"secondModeTick":true}'},
    )
    assert _has_class(page, "dark-mode") is False


def test_theme_param_overrides_os_preference(page: Page, app_url: str) -> None:
    page.add_init_script("""
        Object.defineProperty(window, 'matchMedia', {
            writable: true,
            value: function(query) {
                return {
                    matches: query === '(prefers-color-scheme: dark)',
                    media: query,
                    onchange: null,
                    addEventListener: function() {},
                    removeEventListener: function() {},
                };
            },
        });
    """)
    open_page(page, app_url, {"theme": "light"})
    assert _has_class(page, "dark-mode") is False


@pytest.mark.parametrize(
    ("params", "stored_theme", "os_dark", "expected_dark"),
    [
        pytest.param({"tz": "UTC"}, "dark", False, False, id="single-os-light"),
        pytest.param({"tz": "UTC"}, "light", True, True, id="single-os-dark"),
        pytest.param(
            {"tz": "UTC,Europe/Helsinki"},
            "dark",
            False,
            False,
            id="dashboard-os-light",
        ),
        pytest.param(
            {"tz": "UTC,Europe/Helsinki"},
            "light",
            True,
            True,
            id="dashboard-os-dark",
        ),
    ],
)
def test_parameterized_url_uses_os_theme_without_fouc_or_settings_read(
    page: Page,
    app_url: str,
    params: dict[str, str],
    stored_theme: str,
    os_dark: bool,
    expected_dark: bool,
) -> None:
    state = _open_with_theme_environment(
        page,
        app_url,
        params=params,
        local_storage_items={
            "clocksimulator-user-settings": json.dumps({"theme": stored_theme})
        },
        os_dark=os_dark,
    )
    expected_theme = "dark" if expected_dark else "light"
    _assert_theme_probe(state, expected_theme, expected_theme, 0, 0)


def test_main_script_resynchronizes_theme_if_os_preference_changes(
    page: Page, app_url: str
) -> None:
    state = _open_with_theme_environment(
        page,
        app_url,
        params={"tz": "UTC"},
        os_dark=True,
        os_dark_after_head=False,
    )
    _assert_theme_probe(state, "dark", "light", 0, 0)


@pytest.mark.parametrize(
    ("theme", "stored_theme", "os_dark"),
    [
        pytest.param("dark", "light", False, id="dark"),
        pytest.param("light", "dark", True, id="light"),
        pytest.param("transparent", "dark", True, id="transparent"),
    ],
)
def test_explicit_theme_has_priority_without_fouc_or_settings_read(
    page: Page,
    app_url: str,
    theme: str,
    stored_theme: str,
    os_dark: bool,
) -> None:
    state = _open_with_theme_environment(
        page,
        app_url,
        params={"theme": theme},
        local_storage_items={
            "clocksimulator-user-settings": json.dumps({"theme": stored_theme})
        },
        os_dark=os_dark,
    )
    _assert_theme_probe(state, theme, theme, 0, 0)


def test_embed_default_has_priority_without_fouc_or_settings_read(
    page: Page, app_url: str
) -> None:
    state = _open_with_theme_environment(
        page,
        app_url,
        params={"embed": "true"},
        local_storage_items={
            "clocksimulator-user-settings": json.dumps({"theme": "light"})
        },
        os_dark=False,
    )
    _assert_theme_probe(state, "dark", "dark", 0, 0)


@pytest.mark.parametrize(
    ("stored_theme", "os_dark", "expected_dark"),
    [
        pytest.param("dark", False, True, id="stored-dark"),
        pytest.param("light", True, False, id="stored-light"),
    ],
)
def test_parameterless_url_uses_saved_theme_before_os_without_fouc(
    page: Page,
    app_url: str,
    stored_theme: str,
    os_dark: bool,
    expected_dark: bool,
) -> None:
    state = _open_with_theme_environment(
        page,
        app_url,
        local_storage_items={
            "clocksimulator-user-settings": json.dumps({"theme": stored_theme})
        },
        os_dark=os_dark,
    )
    expected_theme = "dark" if expected_dark else "light"
    _assert_theme_probe(state, expected_theme, expected_theme, 1, 2)


def test_bare_query_uses_saved_theme_without_fouc(page: Page, app_url: str) -> None:
    state = _open_with_theme_environment(
        page,
        app_url,
        local_storage_items={
            "clocksimulator-user-settings": json.dumps({"theme": "dark"})
        },
        os_dark=False,
        bare_query=True,
    )
    _assert_theme_probe(state, "dark", "dark", 1, 2)


@pytest.mark.parametrize("os_dark", [False, True], ids=["os-light", "os-dark"])
def test_invalid_saved_json_falls_back_to_os_without_fouc(
    page: Page, app_url: str, os_dark: bool
) -> None:
    state = _open_with_theme_environment(
        page,
        app_url,
        local_storage_items={"clocksimulator-user-settings": "{invalid-json"},
        os_dark=os_dark,
    )
    expected_theme = "dark" if os_dark else "light"
    _assert_theme_probe(state, expected_theme, expected_theme, 1, 2)


@pytest.mark.parametrize("os_dark", [False, True], ids=["os-light", "os-dark"])
def test_storage_exception_falls_back_to_os_without_fouc(
    page: Page, app_url: str, os_dark: bool
) -> None:
    state = _open_with_theme_environment(
        page,
        app_url,
        os_dark=os_dark,
        storage_get_error=True,
    )
    expected_theme = "dark" if os_dark else "light"
    _assert_theme_probe(state, expected_theme, expected_theme, 1, 2)


@pytest.mark.parametrize(
    ("stored_theme", "os_dark"),
    [
        pytest.param("dark", False, id="os-light"),
        pytest.param("light", True, id="os-dark"),
    ],
)
def test_invalid_theme_param_uses_os_without_fouc_or_settings_read(
    page: Page,
    app_url: str,
    stored_theme: str,
    os_dark: bool,
) -> None:
    state = _open_with_theme_environment(
        page,
        app_url,
        params={"theme": "invalid"},
        local_storage_items={
            "clocksimulator-user-settings": json.dumps({"theme": stored_theme})
        },
        os_dark=os_dark,
    )
    expected_theme = "dark" if os_dark else "light"
    _assert_theme_probe(state, expected_theme, expected_theme, 0, 0)


def test_invalid_theme_param_uses_embed_default_without_settings_read(
    page: Page, app_url: str
) -> None:
    state = _open_with_theme_environment(
        page,
        app_url,
        params={"embed": "true", "theme": "invalid"},
        local_storage_items={
            "clocksimulator-user-settings": json.dumps({"theme": "light"})
        },
        os_dark=False,
    )
    _assert_theme_probe(state, "dark", "dark", 0, 0)


def test_theme_toggle_changes_class(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"theme": "light"})
    assert _has_class(page, "dark-mode") is False
    page.evaluate("() => document.getElementById('themeToggle').click()")
    assert _has_class(page, "dark-mode") is True


def test_theme_toggle_removes_transparent_mode(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"theme": "transparent"})
    assert _has_class(page, "transparent-mode") is True
    page.evaluate("() => document.getElementById('themeToggle').click()")
    assert _has_class(page, "transparent-mode") is False
    assert _has_class(page, "dark-mode") is True


def test_theme_transparent_in_embed_mode(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true", "theme": "transparent"})
    assert _has_class(page, "transparent-mode") is True
    assert _has_class(page, "dark-mode") is False


def test_theme_dashboard_dark(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": "UTC,Europe/Helsinki", "theme": "dark"})
    assert _has_class(page, "dark-mode") is True
    assert page.evaluate("() => !!document.querySelector('.clock-grid')") is True


def test_theme_no_fouc_dark_mode(page: Page, app_url: str) -> None:
    """Theme class must exist at DOMContentLoaded, before full load."""
    page.add_init_script("""
        window.__themeAtDOMContentLoaded = null;
        document.addEventListener('DOMContentLoaded', () => {
            window.__themeAtDOMContentLoaded = document.documentElement.classList.contains('dark-mode');
        });
    """)
    open_page(page, app_url, {"theme": "dark"})
    theme_at_domcp = page.evaluate("() => window.__themeAtDOMContentLoaded")
    assert theme_at_domcp is True


def test_theme_no_fouc_embed_mode(page: Page, app_url: str) -> None:
    """Embed dark mode must be applied at DOMContentLoaded."""
    page.add_init_script("""
        window.__embedDarkAtDOMContentLoaded = null;
        document.addEventListener('DOMContentLoaded', () => {
            window.__embedDarkAtDOMContentLoaded = document.documentElement.classList.contains('dark-mode');
        });
    """)
    open_page(page, app_url, {"embed": "true"})
    embed_dark_at_domcp = page.evaluate("() => window.__embedDarkAtDOMContentLoaded")
    assert embed_dark_at_domcp is True


def test_theme_visual_snapshot_dark(page: Page, app_url: str, update_snapshots: bool) -> None:
    open_page(page, app_url, {"theme": "dark"})
    assert_screenshot(page, "theme-dark.png", update=update_snapshots)


def test_theme_visual_snapshot_light(page: Page, app_url: str, update_snapshots: bool) -> None:
    open_page(page, app_url, {"theme": "light"})
    assert_screenshot(page, "theme-light.png", update=update_snapshots)


def test_theme_visual_snapshot_transparent(page: Page, app_url: str, update_snapshots: bool) -> None:
    open_page(page, app_url, {"theme": "transparent"})
    assert_screenshot(page, "theme-transparent.png", update=update_snapshots)
