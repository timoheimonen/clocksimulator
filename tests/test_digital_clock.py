from __future__ import annotations

import os
import time

from playwright.sync_api import Page

from tests.helpers import open_page, assert_screenshot


def open_digital(
    page: Page,
    app_url: str,
    params: dict[str, str] | None = None,
    localStorage_items: dict[str, str] | None = None,
) -> None:
    open_page(page, app_url, params, localStorage_items, path="/digital/")


def digital_text(page: Page) -> str:
    return page.evaluate("() => document.getElementById('digitalTime').textContent")


def test_digital_page_renders_local_time(page: Page, app_url: str) -> None:
    open_digital(page, app_url)
    assert digital_text(page) == "12:00:00"
    assert page.evaluate("() => document.getElementById('digitalLabel').textContent") == ""
    assert page.evaluate("() => document.getElementById('digitalMeta').hidden") is True


def test_digital_seconds_hide(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"seconds": "hide"})
    assert digital_text(page) == "12:00"
    assert page.evaluate("() => getComputedStyle(document.querySelector('.second-mode-toggle')).display") == "none"


def test_digital_seconds_toggle_hides_seconds(page: Page, app_url: str) -> None:
    open_digital(page, app_url)
    page.evaluate("() => document.getElementById('secondModeToggle').click()")
    assert digital_text(page) == "12:00"


def test_digital_format_12_hour(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"format": "12"})
    assert digital_text(page) == "12:00:00 PM"


def test_digital_timezone(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"tz": "Europe/Helsinki"})
    assert digital_text(page) == "14:00:00"
    assert page.evaluate("() => document.getElementById('digitalLabel').textContent") == "Helsinki"


def test_digital_title_changes_for_timezone(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"tz": "Europe/Helsinki"})
    assert page.evaluate("() => document.title") == "clocksimulator.com - Digital - Europe/Helsinki"


def test_digital_theme_dark(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"theme": "dark"})
    assert page.evaluate("() => document.documentElement.classList.contains('dark-mode')") is True


def test_digital_theme_light(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"theme": "light"})
    assert page.evaluate("() => document.documentElement.classList.contains('dark-mode')") is False
    assert page.evaluate("() => document.documentElement.classList.contains('transparent-mode')") is False


def test_digital_theme_transparent(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"theme": "transparent"})
    assert page.evaluate("() => document.documentElement.classList.contains('transparent-mode')") is True
    assert page.evaluate("() => getComputedStyle(document.getElementById('digitalTime')).color") == "rgb(250, 250, 250)"


def test_digital_embed_mode_defaults_dark_and_hides_controls(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"embed": "true"})
    assert page.evaluate("() => document.body.classList.contains('embed-mode')") is True
    assert page.evaluate("() => document.documentElement.classList.contains('dark-mode')") is True
    assert page.evaluate("() => document.querySelector('.toggle-wrapper').offsetWidth") == 0


def test_digital_embed_time_is_viewport_centered_without_meta(page: Page, app_url: str) -> None:
    page.set_viewport_size({"width": 800, "height": 300})
    open_digital(page, app_url, {"embed": "true", "seconds": "hide"})
    result = page.evaluate("""() => {
        const rect = document.getElementById('digitalTime').getBoundingClientRect();
        return {
            centerX: rect.left + rect.width / 2,
            centerY: rect.top + rect.height / 2,
            viewportX: window.innerWidth / 2,
            viewportY: window.innerHeight / 2,
            metaHidden: document.getElementById('digitalMeta').hidden
        };
    }""")
    assert result["metaHidden"] is True
    assert abs(result["centerX"] - result["viewportX"]) <= 1
    assert abs(result["centerY"] - result["viewportY"]) <= 1


def test_digital_embed_with_meta_keeps_time_centered(page: Page, app_url: str) -> None:
    page.set_viewport_size({"width": 900, "height": 320})
    open_digital(page, app_url, {"embed": "true", "tz": "Europe/Helsinki", "daynight": "show"})
    result = page.evaluate("""() => {
        const timeRect = document.getElementById('digitalTime').getBoundingClientRect();
        const metaRect = document.getElementById('digitalMeta').getBoundingClientRect();
        return {
            centerX: timeRect.left + timeRect.width / 2,
            centerY: timeRect.top + timeRect.height / 2,
            viewportX: window.innerWidth / 2,
            viewportY: window.innerHeight / 2,
            metaHidden: document.getElementById('digitalMeta').hidden,
            label: document.getElementById('digitalLabel').textContent,
            metaTop: metaRect.top,
            timeBottom: timeRect.bottom
        };
    }""")
    assert result["metaHidden"] is False
    assert result["label"] == "Helsinki"
    assert abs(result["centerX"] - result["viewportX"]) <= 1
    assert abs(result["centerY"] - result["viewportY"]) <= 1
    assert result["metaTop"] > result["timeBottom"]


def test_digital_embed_theme_transparent(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"embed": "true", "theme": "transparent"})
    assert page.evaluate("() => document.documentElement.classList.contains('transparent-mode')") is True
    assert page.evaluate("() => document.documentElement.classList.contains('dark-mode')") is False
    assert page.evaluate("() => getComputedStyle(document.getElementById('digitalTime')).color") == "rgb(250, 250, 250)"


def test_digital_embed_removes_favicon(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"embed": "true"})
    assert page.evaluate("() => document.getElementById('favicon')") is None


def test_digital_embed_burnin_disabled(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"embed": "true"})
    time.sleep(0.2)
    transform = page.evaluate("() => document.getElementById('digitalContainer').style.transform")
    assert transform == "" or transform == "none"


def test_digital_daynight_show(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"daynight": "show"})
    state = page.evaluate("() => document.getElementById('dayNightIcon').dataset.state")
    assert state == "day"
    assert page.evaluate("() => document.getElementById('digitalLabel').hidden") is True
    assert page.evaluate("() => document.getElementById('digitalMeta').hidden") is False
    assert page.evaluate("() => !!document.querySelector('#dayNightIcon svg .daynight-sun')") is True
    assert page.evaluate("() => getComputedStyle(document.querySelector('#dayNightIcon .daynight-sun')).display") == "block"
    assert page.evaluate("() => getComputedStyle(document.querySelector('#dayNightIcon .daynight-moon')).display") == "none"


def test_digital_border_show(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"border": "show"})
    assert page.evaluate("() => document.getElementById('digitalContainer').classList.contains('bordered')") is True


def test_digital_saved_settings_seconds_hidden(page: Page, app_url: str) -> None:
    open_digital(
        page,
        app_url,
        localStorage_items={
            "clocksimulator-user-settings": '{"theme":"light","wakeLock":false,"secondModeTick":true,"digitalShowSeconds":false}'
        },
    )
    assert digital_text(page) == "12:00"
    assert page.evaluate("() => document.getElementById('secondModeToggle').checked") is False


def test_digital_theme_toggle_changes_class(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"theme": "light"})
    page.evaluate("() => document.getElementById('themeToggle').click()")
    assert page.evaluate("() => document.documentElement.classList.contains('dark-mode')") is True


def test_digital_dashboard_activates_with_multiple_timezones(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"tz": "UTC,Europe/Helsinki"})
    assert page.evaluate("() => !!document.querySelector('.digital-grid')") is True
    assert page.evaluate("() => document.getElementById('digitalContainer').style.display") == "none"


def test_digital_dashboard_labels_and_times(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"tz": "UTC,Europe/Helsinki,America/New_York"})
    result = page.evaluate("""() => ({
        labels: Array.from(document.querySelectorAll('.digital-grid .digital-label')).map(el => el.textContent),
        times: Array.from(document.querySelectorAll('.digital-grid .digital-time')).map(el => el.textContent)
    })""")
    assert result["labels"] == ["UTC", "Helsinki", "New York"]
    assert result["times"] == ["12:00:00", "14:00:00", "07:00:00"]


def test_digital_dashboard_rows_parameter(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"tz": "UTC,Europe/Helsinki,America/New_York,Asia/Tokyo", "rows": "2"})
    rows = page.evaluate(
        "() => getComputedStyle(document.querySelector('.digital-grid')).gridTemplateRows.trim().split(/\\s+/).filter(Boolean).length"
    )
    assert rows == 2


def test_digital_dashboard_seconds_hide(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"tz": "UTC,Europe/Helsinki", "seconds": "hide"})
    times = page.evaluate("() => Array.from(document.querySelectorAll('.digital-grid .digital-time')).map(el => el.textContent)")
    assert times == ["12:00", "14:00"]


def test_digital_dashboard_format_12_hour(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"tz": "UTC,Asia/Tokyo", "format": "12"})
    times = page.evaluate("() => Array.from(document.querySelectorAll('.digital-grid .digital-time')).map(el => el.textContent)")
    assert times == ["12:00:00 PM", "09:00:00 PM"]


def test_digital_dashboard_12_hour_text_fits_viewport(page: Page, app_url: str) -> None:
    page.set_viewport_size({"width": 840, "height": 734})
    open_digital(
        page,
        app_url,
        {
            "tz": "UTC,Europe/Helsinki,America/New_York",
            "rows": "1",
            "seconds": "hide",
            "format": "12",
            "border": "show",
            "daynight": "show",
        },
    )
    result = page.evaluate("""() => ({
        scrollWidth: document.documentElement.scrollWidth,
        innerWidth: window.innerWidth,
        times: Array.from(document.querySelectorAll('.digital-grid .digital-time')).map(el => ({
            scrollWidth: el.scrollWidth,
            clientWidth: el.clientWidth
        }))
    })""")
    assert result["scrollWidth"] <= result["innerWidth"] + 1
    assert all(t["scrollWidth"] <= t["clientWidth"] + 1 for t in result["times"])


def test_digital_dashboard_daynight_show(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"tz": "UTC,Europe/Helsinki", "daynight": "show"})
    states = page.evaluate("() => Array.from(document.querySelectorAll('.digital-grid .daynight-mark')).map(el => el.dataset.state)")
    assert states == ["day", "day"]


def test_digital_dashboard_invalid_timezone_ignored(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"tz": "UTC,Invalid/Timezone"})
    assert page.evaluate("() => !!document.querySelector('.digital-grid')") is False
    assert digital_text(page) == "12:00:00"


def test_digital_dashboard_all_invalid_timezone_falls_back(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"tz": "Fake/One,Fake/Two"})
    assert page.evaluate("() => !!document.querySelector('.digital-grid')") is False
    assert digital_text(page) == "12:00:00"


def test_digital_embed_panel_generates_digital_iframe(page: Page, app_url: str) -> None:
    open_digital(page, app_url)
    page.evaluate("""() => {
        document.getElementById('embedLink').click();
        document.getElementById('embedTz').value = 'Europe/Helsinki';
        document.getElementById('embedTz').dispatchEvent(new Event('input', { bubbles: true }));
        document.getElementById('embedFormat').value = '12';
        document.getElementById('embedFormat').dispatchEvent(new Event('change', { bubbles: true }));
        document.getElementById('embedSeconds').value = 'hide';
        document.getElementById('embedSeconds').dispatchEvent(new Event('change', { bubbles: true }));
    }""")
    page.wait_for_function("() => document.getElementById('embedCode').value.includes('/digital/')")
    code = page.evaluate("() => document.getElementById('embedCode').value")
    assert 'https://clocksimulator.com/digital/?embed=true' in code
    assert 'tz=Europe%2FHelsinki' in code
    assert 'format=12' in code
    assert 'seconds=hide' in code


def test_digital_copy_button_handles_missing_clipboard(page: Page, app_url: str) -> None:
    page.add_init_script("""
        Object.defineProperty(navigator, 'clipboard', {
            configurable: true,
            value: undefined
        });
    """)
    open_digital(page, app_url)
    page.evaluate("""() => {
        document.getElementById('embedLink').click();
        document.getElementById('embedCopyBtn').click();
    }""")
    page.wait_for_function("() => document.getElementById('embedCopyBtn').textContent === 'Failed'")


def test_digital_dashboard_builder_generates_digital_url(page: Page, app_url: str) -> None:
    open_digital(page, app_url)
    page.evaluate("""() => {
        document.getElementById('dashboardLink').click();
        var input = document.getElementById('dashboardTzInput');
        input.value = 'UTC';
        document.getElementById('dashboardAddBtn').click();
        input.value = 'Europe/Helsinki';
        document.getElementById('dashboardAddBtn').click();
        document.getElementById('dashboardFormat').value = '12';
        document.getElementById('dashboardFormat').dispatchEvent(new Event('change', { bubbles: true }));
    }""")
    page.wait_for_function("() => document.getElementById('dashboardUrl').value.includes('format=12')")
    url = page.evaluate("() => document.getElementById('dashboardUrl').value")
    assert url.startswith("https://clocksimulator.com/digital/?")
    assert "tz=UTC%2CEurope%2FHelsinki" in url
    assert "format=12" in url


def test_digital_service_worker_caches_digital_page() -> None:
    sw_path = os.path.join(os.path.dirname(__file__), "..", "public", "sw.js")
    with open(sw_path, encoding="utf-8") as f:
        body = f.read()
    assert "'/digital/'" in body
    assert "caches.match('/digital/')" in body


def test_analog_index_links_to_digital_clock_under_help() -> None:
    index_path = os.path.join(os.path.dirname(__file__), "..", "public", "index.html")
    with open(index_path, encoding="utf-8") as f:
        body = f.read()
    help_idx = body.index('id="helpLink">How to use')
    digital_idx = body.index('id="digitalClockLink"')
    assert help_idx < digital_idx
    assert '<a href="/digital/" id="digitalClockLink">Digital clock &rarr;</a>' in body


def test_digital_index_links_to_analog_clock_under_help() -> None:
    index_path = os.path.join(os.path.dirname(__file__), "..", "public", "digital", "index.html")
    with open(index_path, encoding="utf-8") as f:
        body = f.read()
    help_idx = body.index('id="helpLink">How to use')
    analog_idx = body.index('id="analogClockLink"')
    assert help_idx < analog_idx
    assert '<a href="/" id="analogClockLink">Analog clock &rarr;</a>' in body


def test_digital_visual_snapshot_dark(page: Page, app_url: str, update_snapshots: bool) -> None:
    open_digital(page, app_url, {"theme": "dark"})
    assert_screenshot(page, "digital-dark.png", update=update_snapshots)


def test_digital_visual_snapshot_light(page: Page, app_url: str, update_snapshots: bool) -> None:
    open_digital(page, app_url, {"theme": "light"})
    assert_screenshot(page, "digital-light.png", update=update_snapshots)


def test_digital_visual_snapshot_embed_transparent(page: Page, app_url: str, update_snapshots: bool) -> None:
    open_digital(page, app_url, {"embed": "true", "theme": "transparent"})
    assert_screenshot(page, "digital-embed-transparent.png", update=update_snapshots)


def test_digital_visual_snapshot_dashboard_dark(page: Page, app_url: str, update_snapshots: bool) -> None:
    open_digital(page, app_url, {"tz": "UTC,Europe/Helsinki,America/New_York", "theme": "dark"})
    assert_screenshot(page, "digital-dashboard-dark-3tz.png", update=update_snapshots)
