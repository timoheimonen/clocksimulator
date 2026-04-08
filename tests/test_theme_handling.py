from __future__ import annotations

from playwright.sync_api import Page

from tests.helpers import open_page, assert_screenshot


def _has_class(page: Page, cls: str) -> bool:
    return page.evaluate(f"() => document.documentElement.classList.contains('{cls}')")


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
