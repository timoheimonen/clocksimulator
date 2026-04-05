from __future__ import annotations

from playwright.sync_api import Page

from conftest import open_page, assert_screenshot


def test_dashboard_mode_activates_with_multiple_tz(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": "UTC,Europe/Helsinki"})
    grid_exists = page.evaluate("() => !!document.querySelector('.clock-grid')")
    assert grid_exists is True


def test_dashboard_mode_title_changes(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": "UTC,Europe/Helsinki"})
    title = page.evaluate("() => document.title")
    assert "Dashboard" in title


def test_dashboard_mode_clock_grid_created(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": "UTC,Europe/Helsinki"})
    grid = page.evaluate("() => document.querySelector('.clock-grid')")
    assert grid is not None


def test_dashboard_mode_grid_columns_correct(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": "UTC,Europe/Helsinki"})
    columns = page.evaluate("() => getComputedStyle(document.querySelector('.clock-grid')).gridTemplateColumns")
    assert "2" in columns


def test_dashboard_mode_clock_labels_show(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": "UTC,Europe/Helsinki"})
    labels = page.evaluate("() => document.querySelectorAll('.clock-label').length")
    assert labels == 2


def test_dashboard_mode_rows_parameter(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": "UTC,Europe/Helsinki,America/New_York,Asia/Tokyo", "rows": "2"})
    rows = page.evaluate("() => getComputedStyle(document.querySelector('.clock-grid')).gridTemplateRows")
    assert "2" in rows


def test_dashboard_mode_theme_dark(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": "UTC,Europe/Helsinki", "theme": "dark"})
    assert page.evaluate("() => document.documentElement.classList.contains('dark-mode')") is True


def test_dashboard_mode_theme_light(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": "UTC,Europe/Helsinki", "theme": "light"})
    assert page.evaluate("() => document.documentElement.classList.contains('dark-mode')") is False


def test_dashboard_mode_seconds_hide(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": "UTC,Europe/Helsinki", "seconds": "hide"})
    visible_hands = page.evaluate("() => Array.from(document.querySelectorAll('.second-hand')).filter(el => el.style.display !== 'none').length")
    assert visible_hands == 0


def test_dashboard_mode_border_hide(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": "UTC,Europe/Helsinki", "border": "hide"})
    borders_stroke = page.evaluate("() => Array.from(document.querySelectorAll('.clock-border')).every(el => el.getAttribute('stroke') === 'none')")
    assert borders_stroke is True


def test_dashboard_mode_numbers_hide(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": "UTC,Europe/Helsinki", "numbers": "hide"})
    numbers_hidden = page.evaluate("() => Array.from(document.querySelectorAll('.numbers')).every(el => el.style.display === 'none')")
    assert numbers_hidden is True


def test_dashboard_mode_daynight_show(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": "UTC,Europe/Helsinki", "daynight": "show"})
    icons = page.evaluate("() => { const suns = document.querySelectorAll('.sun-icon'); const moons = document.querySelectorAll('.moon-icon'); return suns.length + moons.length; }")
    assert icons >= 2


def test_dashboard_mode_shadows_disabled(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": "UTC,Europe/Helsinki", "shadows": "false"})
    has_filters = page.evaluate("() => document.querySelectorAll('[filter]').length")
    assert has_filters == 0


def test_dashboard_mode_invalid_timezone_ignored(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": "UTC,Invalid/Timezone"})
    title = page.evaluate("() => document.title")
    assert "UTC" in title or "clocksimulator" in title
    assert page.evaluate("() => !!document.querySelector('.clock-grid')") is False


def test_dashboard_mode_mixed_valid_invalid_tz(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": "UTC,Invalid/Timezone,Europe/Helsinki"})
    labels = page.evaluate("() => document.querySelectorAll('.clock-label').length")
    assert labels == 2


def test_dashboard_mode_embed_combined(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true", "tz": "UTC,Europe/Helsinki"})
    assert page.evaluate("() => document.body.classList.contains('embed-mode')") is True
    assert page.evaluate("() => !!document.querySelector('.clock-grid')") is True
    assert page.evaluate("() => document.querySelector('.toggle-wrapper').offsetWidth") == 0


def test_dashboard_mode_embed_grid_no_transition(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true", "tz": "UTC,Europe/Helsinki"})
    transition = page.evaluate("() => getComputedStyle(document.querySelector('.clock-grid')).transition")
    assert "none" in transition


def test_dashboard_mode_three_timezones(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": "UTC,Europe/Helsinki,America/New_York"})
    labels = page.evaluate("() => document.querySelectorAll('.clock-label').length")
    assert labels == 3


def test_dashboard_mode_four_tz_with_rows(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": "UTC,Europe/Helsinki,America/New_York,Asia/Tokyo", "rows": "2"})
    labels = page.evaluate("() => document.querySelectorAll('.clock-label').length")
    rows = page.evaluate("() => getComputedStyle(document.querySelector('.clock-grid')).gridTemplateRows")
    assert labels == 4
    assert "2" in rows


def test_dashboard_mode_all_params_combined(page: Page, app_url: str) -> None:
    open_page(page, app_url, {
        "tz": "UTC,Europe/Helsinki",
        "theme": "light",
        "seconds": "hide",
        "border": "hide",
        "numbers": "hide",
        "shadows": "false",
        "daynight": "show",
        "rows": "1",
    })
    assert page.evaluate("() => document.documentElement.classList.contains('dark-mode')") is False
    assert page.evaluate("() => document.querySelectorAll('.clock-label').length") == 2
    rows = page.evaluate("() => getComputedStyle(document.querySelector('.clock-grid')).gridTemplateRows")
    assert "1" in rows


def test_dashboard_mode_visual_snapshot_dark_2tz(page: Page, app_url: str, update_snapshots: bool) -> None:
    open_page(page, app_url, {"tz": "UTC,Europe/Helsinki", "theme": "dark"})
    assert_screenshot(page, "dashboard-dark-2tz.png", update=update_snapshots)


def test_dashboard_mode_visual_snapshot_light_3tz(page: Page, app_url: str, update_snapshots: bool) -> None:
    open_page(page, app_url, {"tz": "UTC,Europe/Helsinki,America/New_York", "theme": "light"})
    assert_screenshot(page, "dashboard-light-3tz.png", update=update_snapshots)
