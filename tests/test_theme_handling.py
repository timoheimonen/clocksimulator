from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page, Route

from tests.helpers import (
    assert_screenshot,
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
            "params": {"theme": "dark"},
            "stored": "light",
            "os_dark": False,
            "expected": "dark",
            "head_reads": 0,
            "final_reads": 0,
            "head_media": 0,
            "final_media": 0,
        },
        id="explicit-dark",
    ),
    pytest.param(
        {
            "params": {"theme": "light"},
            "stored": "dark",
            "os_dark": True,
            "expected": "light",
            "head_reads": 0,
            "final_reads": 0,
            "head_media": 0,
            "final_media": 0,
        },
        id="explicit-light",
    ),
    pytest.param(
        {
            "params": {"theme": "transparent"},
            "stored": "dark",
            "os_dark": True,
            "expected": "transparent",
            "head_reads": 0,
            "final_reads": 0,
            "head_media": 0,
            "final_media": 0,
        },
        id="explicit-transparent",
    ),
    pytest.param(
        {
            "params": {"embed": "true", "theme": "light"},
            "stored": "dark",
            "os_dark": True,
            "expected": "light",
            "head_reads": 0,
            "final_reads": 0,
            "head_media": 0,
            "final_media": 0,
        },
        id="explicit-light-over-embed-default",
    ),
    pytest.param(
        {
            "params": {"embed": "true", "theme": "transparent"},
            "stored": "dark",
            "os_dark": True,
            "expected": "transparent",
            "head_reads": 0,
            "final_reads": 0,
            "head_media": 0,
            "final_media": 0,
        },
        id="explicit-transparent-over-embed-default",
    ),
    pytest.param(
        {
            "params": {"embed": "true"},
            "stored": "light",
            "os_dark": False,
            "expected": "dark",
            "head_reads": 0,
            "final_reads": 0,
            "head_media": 0,
            "final_media": 0,
        },
        id="embed-default",
    ),
    pytest.param(
        {
            "stored": "dark",
            "os_dark": False,
            "expected": "dark",
            "head_reads": 1,
            "final_reads": 2,
            "head_media": 0,
            "final_media": 0,
        },
        id="stored-dark",
    ),
    pytest.param(
        {
            "stored": "light",
            "os_dark": True,
            "expected": "light",
            "head_reads": 1,
            "final_reads": 2,
            "head_media": 0,
            "final_media": 0,
        },
        id="stored-light",
    ),
    pytest.param(
        {
            "stored": "transparent",
            "os_dark": False,
            "expected": "light",
            "head_reads": 1,
            "final_reads": 2,
            "head_media": 1,
            "final_media": 2,
        },
        id="stored-transparent-falls-back-to-os",
    ),
    pytest.param(
        {
            "stored": "dark",
            "os_dark": False,
            "expected": "dark",
            "head_reads": 1,
            "final_reads": 2,
            "head_media": 0,
            "final_media": 0,
            "bare_query": True,
        },
        id="bare-query-uses-storage",
    ),
    pytest.param(
        {
            "params": {"tz": "UTC"},
            "stored": "dark",
            "os_dark": False,
            "expected": "light",
            "head_reads": 0,
            "final_reads": 0,
            "head_media": 1,
            "final_media": 2,
        },
        id="unrelated-param-skips-storage",
    ),
    pytest.param(
        {
            "params": {"theme": "sepia"},
            "stored": "light",
            "os_dark": True,
            "expected": "dark",
            "head_reads": 0,
            "final_reads": 0,
            "head_media": 1,
            "final_media": 2,
        },
        id="invalid-theme-skips-storage",
    ),
    pytest.param(
        {
            "params": {"embed": "true", "theme": "sepia"},
            "stored": "light",
            "os_dark": False,
            "expected": "dark",
            "head_reads": 0,
            "final_reads": 0,
            "head_media": 0,
            "final_media": 0,
        },
        id="invalid-theme-keeps-embed-default",
    ),
    pytest.param(
        {
            "storage_value": "{invalid-json",
            "os_dark": True,
            "expected": "dark",
            "head_reads": 1,
            "final_reads": 2,
            "head_media": 1,
            "final_media": 2,
        },
        id="invalid-json-falls-back-to-os",
    ),
    pytest.param(
        {
            "storage_error": True,
            "os_dark": False,
            "expected": "light",
            "head_reads": 1,
            "final_reads": 2,
            "head_media": 1,
            "final_media": 2,
        },
        id="storage-exception-falls-back-to-os",
    ),
]

OS_RESYNC_CASES = [
    pytest.param(
        {
            "os_dark": True,
            "os_dark_after_head": False,
            "head": "dark",
            "final": "light",
            "head_reads": 1,
            "final_reads": 2,
            "head_media": 1,
            "final_media": 2,
        },
        id="os-only-resynchronizes",
    ),
    pytest.param(
        {
            "params": {"theme": "light"},
            "os_dark": False,
            "os_dark_after_head": True,
            "head": "light",
            "final": "light",
            "head_reads": 0,
            "final_reads": 0,
            "head_media": 0,
            "final_media": 0,
        },
        id="explicit-theme-does-not-resynchronize",
    ),
    pytest.param(
        {
            "params": {"embed": "true"},
            "os_dark": False,
            "os_dark_after_head": True,
            "head": "dark",
            "final": "dark",
            "head_reads": 0,
            "final_reads": 0,
            "head_media": 0,
            "final_media": 0,
        },
        id="embed-default-does-not-resynchronize",
    ),
    pytest.param(
        {
            "stored": "light",
            "os_dark": False,
            "os_dark_after_head": True,
            "head": "light",
            "final": "light",
            "head_reads": 1,
            "final_reads": 2,
            "head_media": 0,
            "final_media": 0,
        },
        id="stored-theme-does-not-resynchronize",
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
    os_dark_after_head = bool(case.get("os_dark_after_head", os_dark))
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
              matches = window.__themeProbe.mediaReads === 1 ? %s : %s;
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
        json.dumps(os_dark_after_head),
    )
    head_probe = """<script>
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
          domcontentloaded: window.__themeAtDOMContentLoaded,
          finalTheme: window.__recordTheme(),
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
    assert result["head"] == {
        "theme": head_theme,
        "reads": case["head_reads"],
        "writes": 0,
        "mediaReads": case["head_media"],
    }
    assert result["domcontentloaded"] == {
        "theme": final_theme,
        "checked": final_theme == "dark",
        "reads": case["final_reads"],
        "writes": 0,
        "mediaReads": case["final_media"],
        "transitions": [head_theme]
        if head_theme == final_theme
        else [head_theme, final_theme],
    }
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
@pytest.mark.parametrize("path", PAGE_PATHS)
@pytest.mark.parametrize("case", OS_RESYNC_CASES)
def test_os_theme_resynchronizes_only_without_stronger_source(
    page: Page,
    app_url: str,
    path: str,
    case: dict[str, object],
) -> None:
    result = open_with_theme_probe(page, app_url, path, case)
    assert_theme_probe(result, case, str(case["head"]), str(case["final"]))


@pytest.mark.cross_browser
@pytest.mark.parametrize("path", PAGE_PATHS)
@pytest.mark.parametrize(
    ("theme", "expected_bg"),
    [
        pytest.param("light", "#f0f0f0", id="light"),
        pytest.param("dark", "#000000", id="dark"),
        pytest.param("transparent", "transparent", id="transparent"),
    ],
)
def test_theme_classes_and_base_rendering(
    page: Page,
    app_url: str,
    path: str,
    theme: str,
    expected_bg: str,
) -> None:
    install_test_clock(page)
    seed_local_storage(page, app_url)
    navigate_clock_page(page, build_clock_url(app_url, path, {"theme": theme}))
    assert theme_name(page) == theme
    assert page.locator("html").evaluate(
        "element => getComputedStyle(element).getPropertyValue('--bg').trim()"
    ) == expected_bg
    assert page.locator("#themeToggle").is_checked() is (theme == "dark")


@pytest.mark.cross_browser
@pytest.mark.parametrize("path", PAGE_PATHS)
@pytest.mark.parametrize(
    ("initial_theme", "expected_theme"),
    [
        pytest.param("light", "dark", id="light-to-dark"),
        pytest.param("transparent", "dark", id="transparent-to-dark"),
    ],
)
def test_theme_switch_updates_class_and_checked_state(
    page: Page,
    app_url: str,
    path: str,
    initial_theme: str,
    expected_theme: str,
) -> None:
    install_test_clock(page)
    seed_local_storage(page, app_url)
    navigate_clock_page(page, build_clock_url(app_url, path, {"theme": initial_theme}))
    switch = page.locator("#themeToggle")
    page.evaluate("() => document.getElementById('themeToggle').click()")
    assert theme_name(page) == expected_theme
    assert switch.is_checked() is True


@pytest.mark.visual
@pytest.mark.chromium_only
@pytest.mark.parametrize(
    ("theme", "name", "transparent"),
    [
        pytest.param("dark", "theme-dark.png", False, id="dark"),
        pytest.param("light", "theme-light.png", False, id="light"),
        pytest.param("transparent", "theme-transparent.png", True, id="transparent"),
    ],
)
def test_theme_visual_snapshot(
    page: Page,
    app_url: str,
    update_snapshots: bool,
    theme: str,
    name: str,
    transparent: bool,
) -> None:
    install_test_clock(page)
    seed_local_storage(page, app_url)
    navigate_clock_page(page, build_clock_url(app_url, "", {"theme": theme}))
    assert theme_name(page) == theme
    assert page.get_by_role("img", name="The time is 12:00").count() == 1
    assert_screenshot(
        page,
        name,
        update=update_snapshots,
        transparent=transparent,
    )
