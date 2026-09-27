from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page, Route

from tests.helpers import (
    build_clock_url,
    expected_clock_count,
    install_test_clock,
    navigate_clock_page,
    seed_local_storage,
)


PAGE_PATHS = [
    pytest.param("", id="analog"),
    pytest.param("/digital/", id="digital"),
]

THEME_PRIORITY_CASES = [
    pytest.param(
        {
            "params": {"theme": "light"},
            "stored": "dark",
            "os_dark": True,
            "expected": "light",
        },
        id="explicit-light",
    ),
    pytest.param(
        {
            "params": {"embed": "true", "theme": "transparent"},
            "stored": "dark",
            "os_dark": True,
            "expected": "transparent",
        },
        id="explicit-transparent-over-embed-default",
    ),
    pytest.param(
        {
            "params": {"embed": "true"},
            "stored": "light",
            "os_dark": False,
            "expected": "dark",
        },
        id="embed-default",
    ),
    pytest.param(
        {
            "stored": "light",
            "os_dark": True,
            "expected": "light",
            "reads_storage": True,
        },
        id="stored-light",
    ),
    pytest.param(
        {
            "params": {"tz": "UTC"},
            "stored": "dark",
            "os_dark": False,
            "expected": "light",
            "reads_media": True,
        },
        id="unrelated-param-skips-storage",
    ),
    pytest.param(
        {
            "params": {"theme": "sepia"},
            "stored": "light",
            "os_dark": True,
            "expected": "dark",
            "reads_media": True,
        },
        id="invalid-theme-skips-storage",
    ),
    pytest.param(
        {
            "storage_error": True,
            "os_dark": False,
            "expected": "light",
            "reads_storage": True,
            "reads_media": True,
        },
        id="storage-exception-falls-back-to-os",
    ),
]


def theme_name(page: Page) -> str:
    return page.evaluate("""() => document.documentElement.classList.contains('dark-mode')
        ? 'dark'
        : document.documentElement.classList.contains('transparent-mode')
            ? 'transparent'
            : 'light'
    """)


def open_with_theme_probe(
    page: Page,
    app_url: str,
    path: str,
    case: dict[str, object],
) -> dict[str, object]:
    os_dark = bool(case.get("os_dark", False))
    storage_error = bool(case.get("storage_error", False))
    override = """<script>
      (function () {
        window.__themeProbe = {
          reads: 0,
          writes: 0,
          mediaReads: 0,
          transitions: []
        };
        window.__recordTheme = function () {
          var value = document.documentElement.classList.contains('dark-mode')
            ? 'dark'
            : document.documentElement.classList.contains('transparent-mode')
              ? 'transparent'
              : 'light';
          var values = window.__themeProbe.transitions;
          if (!values.length || values[values.length - 1] !== value) values.push(value);
          return value;
        };
        window.__recordClockColor = function () {
          var root = document.documentElement;
          var style = getComputedStyle(root);
          return {
            color: root.getAttribute('data-clock-color'),
            foreground: (style.getPropertyValue('--number') || style.getPropertyValue('--digit')).trim(),
            background: style.getPropertyValue('--bg').trim()
          };
        };
        new MutationObserver(window.__recordTheme).observe(document.documentElement, {
          attributes: true,
          attributeFilter: ['class']
        });
        var originalGetItem = Storage.prototype.getItem;
        var originalSetItem = Storage.prototype.setItem;
        var originalRemoveItem = Storage.prototype.removeItem;
        Storage.prototype.getItem = function (key) {
          if (key === 'clocksimulator-user-settings') {
            window.__themeProbe.reads += 1;
            if (%s) throw new DOMException('Storage access blocked', 'SecurityError');
          }
          return originalGetItem.call(this, key);
        };
        Storage.prototype.setItem = function (key, value) {
          if (key === 'clocksimulator-user-settings') window.__themeProbe.writes += 1;
          return originalSetItem.call(this, key, value);
        };
        Storage.prototype.removeItem = function (key) {
          if (key === 'clocksimulator-user-settings') window.__themeProbe.writes += 1;
          return originalRemoveItem.call(this, key);
        };
        Object.defineProperty(window, 'matchMedia', {
          configurable: true,
          value: function (query) {
            var matches = false;
            if (query === '(prefers-color-scheme: dark)') {
              window.__themeProbe.mediaReads += 1;
              matches = %s;
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
            theme: window.__recordTheme(),
            checked: document.getElementById('themeToggle').checked,
            reads: window.__themeProbe.reads,
            writes: window.__themeProbe.writes,
            mediaReads: window.__themeProbe.mediaReads,
            transitions: window.__themeProbe.transitions.slice()
          };
        });
      })();
    </script>""" % (
        json.dumps(storage_error),
        json.dumps(os_dark),
    )
    head_probe = """<script>
      window.__clockColorAfterHead = window.__recordClockColor();
      window.__themeAfterHead = {
        theme: window.__recordTheme(),
        reads: window.__themeProbe.reads,
        writes: window.__themeProbe.writes,
        mediaReads: window.__themeProbe.mediaReads
      };
    </script>"""

    def route_handler(route: Route) -> None:
        if route.request.resource_type != "document":
            route.continue_()
            return
        response = route.fetch()
        body = response.text()
        if "<head>" in body:
            body = body.replace("<head>", "<head>" + override, 1)
            body = body.replace("</head>", head_probe + "</head>", 1)
        route.fulfill(response=response, body=body.encode())

    stored_items: dict[str, str] = {}
    if "storage_value" in case:
        stored_items["clocksimulator-user-settings"] = str(case["storage_value"])
    elif "stored" in case:
        stored_items["clocksimulator-user-settings"] = json.dumps(
            {"theme": case["stored"], "unrelated": "preserved"}
        )

    install_test_clock(page)
    seed_local_storage(page, app_url, stored_items)
    params = case.get("params")
    assert params is None or isinstance(params, dict)
    target = build_clock_url(app_url, path, params)
    if case.get("bare_query"):
        target += "?"

    page.route("**/*", route_handler)
    try:
        navigate_clock_page(page, target, expected_clock_count(params))
        return page.evaluate("""() => ({
          head: window.__themeAfterHead,
          headClockColor: window.__clockColorAfterHead,
          domcontentloaded: window.__themeAtDOMContentLoaded,
          finalTheme: window.__recordTheme(),
          finalClockColor: window.__recordClockColor(),
          finalWrites: window.__themeProbe.writes
        })""")
    finally:
        page.unroute("**/*", route_handler)


def assert_theme_probe(
    result: dict[str, object],
    case: dict[str, object],
    head_theme: str,
    final_theme: str,
) -> None:
    reads_storage = bool(case.get("reads_storage", False))
    reads_media = bool(case.get("reads_media", False))
    head = result["head"]
    loaded = result["domcontentloaded"]
    assert isinstance(head, dict) and isinstance(loaded, dict)
    assert head["theme"] == head_theme
    assert loaded["theme"] == final_theme
    assert loaded["checked"] is (final_theme == "dark")
    assert loaded["transitions"] == (
        [head_theme] if head_theme == final_theme else [head_theme, final_theme]
    )
    for snapshot in (head, loaded):
        assert snapshot["writes"] == 0
        assert (snapshot["reads"] > 0) is reads_storage
        assert (snapshot["mediaReads"] > 0) is reads_media
    assert result["finalTheme"] == final_theme
    assert result["finalWrites"] == 0


@pytest.mark.cross_browser
@pytest.mark.parametrize("path", PAGE_PATHS)
@pytest.mark.parametrize("case", THEME_PRIORITY_CASES)
def test_theme_priority_and_fouc_matrix(
    page: Page,
    app_url: str,
    path: str,
    case: dict[str, object],
) -> None:
    result = open_with_theme_probe(page, app_url, path, case)
    expected = str(case["expected"])
    assert_theme_probe(result, case, expected, expected)


@pytest.mark.cross_browser
@pytest.mark.parametrize(
    ("path", "color", "dashboard"),
    [
        pytest.param("", None, False, id="analog-legacy-default"),
        pytest.param("", "abcdef12", False, id="analog-invalid-hex-eight-digits"),
        pytest.param("", "#abc", False, id="analog-invalid-hex-leading-hash"),
        pytest.param("", "0aF", False, id="analog-hex-short-single"),
        pytest.param("", "FF8800", True, id="analog-hex-long-dashboard"),
        pytest.param("", "light", False, id="analog-light-single"),
        pytest.param("/digital/", None, False, id="digital-legacy-default"),
        pytest.param("/digital/", "FF8800", True, id="digital-hex-long-dashboard"),
        pytest.param("/digital/", "dark", False, id="digital-dark-single"),
    ],
)
def test_transparent_clock_color_before_first_paint_and_rendered_without_storage_changes(
    page: Page,
    app_url: str,
    path: str,
    color: str | None,
    dashboard: bool,
) -> None:
    params = {"embed": "true", "theme": "transparent", "daynight": "show"}
    if color is not None:
        params["color"] = color
    if dashboard:
        params["tz"] = "UTC,Asia/Kathmandu"
    raw_settings = '{"theme":"dark","unrelated":"preserved","digitalShowSeconds":false}'
    case = {
        "params": params,
        "storage_value": raw_settings,
        "os_dark": True,
    }
    result = open_with_theme_probe(page, app_url, path, case)
    assert_theme_probe(result, case, "transparent", "transparent")
    expected_color = color if color in ("dark", "light") else ("dark" if path == "" else "light")
    foreground = "#222222" if expected_color == "dark" else "#fafafa"
    custom_hex = color if color in ("0aF", "FF8800") else None
    if custom_hex:
        expected_color = "custom"
        foreground = "#" + custom_hex
    expected_state = {
        "color": expected_color,
        "foreground": foreground,
        "background": "transparent",
    }
    assert result["headClockColor"] == expected_state
    assert result["finalClockColor"] == expected_state
    assert page.evaluate(
        "() => localStorage.getItem('clocksimulator-user-settings')"
    ) == raw_settings
    assert page.locator("#saveSettingsToggle").is_disabled() is True
    assert page.locator("html, body").evaluate_all(
        "elements => elements.map(element => getComputedStyle(element).backgroundColor)"
    ) == ["rgba(0, 0, 0, 0)", "rgba(0, 0, 0, 0)"]
    expected_rgb = "rgb(34, 34, 34)" if expected_color == "dark" else "rgb(250, 250, 250)"
    if custom_hex:
        expected_rgb = "rgb(0, 170, 255)" if custom_hex == "0aF" else "rgb(255, 136, 0)"
    expected_count = 2 if dashboard else 1
    if path == "":
        scope = ".clock-grid" if dashboard else ".clock-container"
        assert page.locator(scope + " .hour-hand").evaluate_all(
            "elements => elements.map(element => getComputedStyle(element).fill)"
        ) == [expected_rgb] * expected_count
        assert page.locator(scope + " .sun-icon circle").evaluate_all(
            "elements => elements.map(element => getComputedStyle(element).stroke)"
        ) == [expected_rgb] * expected_count
        assert page.locator(scope + " .clock-border").evaluate_all(
            "elements => elements.map(element => getComputedStyle(element).fill)"
        ) == ["rgba(0, 0, 0, 0)"] * expected_count
        if dashboard:
            assert page.locator(".clock-grid .clock-label").evaluate_all(
                "elements => elements.map(element => getComputedStyle(element).color)"
            ) == [expected_rgb] * expected_count
    else:
        scope = ".digital-grid" if dashboard else ".digital-container"
        assert page.locator(scope + " .digital-time").evaluate_all(
            "elements => elements.map(element => getComputedStyle(element).color)"
        ) == [expected_rgb] * expected_count
        assert page.locator(scope + " .daynight-mark").evaluate_all(
            "elements => elements.map(element => getComputedStyle(element).color)"
        ) == [expected_rgb] * expected_count
        expected_muted = "rgb(85, 85, 85)" if expected_color == "dark" else "rgb(212, 212, 212)"
        if custom_hex:
            expected_muted = expected_rgb
        assert page.locator(scope + " .digital-meta").evaluate_all(
            "elements => elements.map(element => getComputedStyle(element).color)"
        ) == [expected_muted] * expected_count
        shadows = page.locator(scope + " .digital-time").evaluate_all(
            "elements => elements.map(element => getComputedStyle(element).textShadow)"
        )
        assert all((shadow == "none") is (expected_color == "dark") for shadow in shadows)


@pytest.mark.cross_browser
@pytest.mark.parametrize(
    ("path", "theme", "color", "expected_theme"),
    [
        pytest.param("", None, "0af", "dark", id="analog-embed-default-hex"),
        pytest.param("/digital/", "light", "FF8800", "light", id="digital-light-hex"),
    ],
)
def test_clock_color_is_ignored_without_transparent_theme(
    page: Page,
    app_url: str,
    path: str,
    theme: str | None,
    color: str,
    expected_theme: str,
) -> None:
    params = {"embed": "true", "color": color}
    if theme is not None:
        params["theme"] = theme
    case = {
        "params": params,
        "stored": "light",
    }
    result = open_with_theme_probe(page, app_url, path, case)
    assert_theme_probe(result, case, expected_theme, expected_theme)
    expected_state = {
        "color": None,
        "foreground": "#fafafa" if expected_theme == "dark" else "#222222",
        "background": "#000000" if expected_theme == "dark" else "#f0f0f0",
    }
    assert result["headClockColor"] == expected_state
    assert result["finalClockColor"] == expected_state


@pytest.mark.cross_browser
@pytest.mark.parametrize("path", PAGE_PATHS)
def test_theme_switch_updates_class_and_checked_state(
    page: Page,
    app_url: str,
    path: str,
) -> None:
    install_test_clock(page)
    seed_local_storage(page, app_url)
    navigate_clock_page(
        page, build_clock_url(app_url, path, {"theme": "transparent", "color": "0af"})
    )
    switch = page.locator("#themeToggle")
    page.evaluate("() => document.getElementById('themeToggle').click()")
    assert theme_name(page) == "dark"
    assert switch.is_checked() is True
    assert page.locator("html").get_attribute("data-clock-color") is None
