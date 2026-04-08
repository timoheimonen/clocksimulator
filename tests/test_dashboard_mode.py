from __future__ import annotations

import time

from playwright.sync_api import Page

from tests.helpers import open_page, assert_screenshot


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
    columns = page.evaluate(
        "() => getComputedStyle(document.querySelector('.clock-grid')).gridTemplateColumns.trim().split(/\\s+/).filter(Boolean).length"
    )
    assert columns == 2


def test_dashboard_mode_clock_labels_show(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": "UTC,Europe/Helsinki"})
    labels = page.evaluate("() => document.querySelectorAll('.clock-label').length")
    assert labels == 2


def test_dashboard_mode_rows_parameter(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": "UTC,Europe/Helsinki,America/New_York,Asia/Tokyo", "rows": "2"})
    rows = page.evaluate(
        "() => getComputedStyle(document.querySelector('.clock-grid')).gridTemplateRows.trim().split(/\\s+/).filter(Boolean).length"
    )
    assert rows == 2


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
    icon_states = page.evaluate(
        """() => Array.from(document.querySelectorAll('.clock-grid .clock-cell')).map(cell => {
            const sun = cell.querySelector('.sun-icon');
            const moon = cell.querySelector('.moon-icon');
            return {
                sun: sun ? sun.getAttribute('display') : null,
                moon: moon ? moon.getAttribute('display') : null,
            };
        })"""
    )
    assert len(icon_states) == 2
    assert all(
        (state["sun"] == "inline" and state["moon"] == "none")
        or (state["sun"] == "none" and state["moon"] == "inline")
        for state in icon_states
    )


def test_dashboard_mode_filters_removed(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": "UTC,Europe/Helsinki"})
    has_filters = page.evaluate("() => document.querySelectorAll('.clock-grid [filter]').length")
    assert has_filters == 0


def test_dashboard_mode_invalid_timezone_ignored(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": "UTC,Invalid/Timezone"})
    title = page.evaluate("() => document.title")
    assert title == "clocksimulator.com - UTC"
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
    rows = page.evaluate(
        "() => getComputedStyle(document.querySelector('.clock-grid')).gridTemplateRows.trim().split(/\\s+/).filter(Boolean).length"
    )
    assert labels == 4
    assert rows == 2


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
    rows = page.evaluate(
        "() => getComputedStyle(document.querySelector('.clock-grid')).gridTemplateRows.trim().split(/\\s+/).filter(Boolean).length"
    )
    assert rows == 1


def test_dashboard_auto_grid_4tz(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": "UTC,Europe/Helsinki,America/New_York,Asia/Tokyo"})
    layout = page.evaluate("""() => {
        var grid = document.querySelector('.clock-grid');
        var style = getComputedStyle(grid);
        return {
            cols: style.gridTemplateColumns.trim().split(/\\s+/).filter(Boolean).length,
            rows: style.gridTemplateRows.trim().split(/\\s+/).filter(Boolean).length
        };
    }""")
    assert layout["cols"] == 2
    assert layout["rows"] == 2


def test_dashboard_auto_grid_5tz(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": "UTC,Europe/Helsinki,America/New_York,Asia/Tokyo,Australia/Sydney"})
    layout = page.evaluate("""() => {
        var grid = document.querySelector('.clock-grid');
        var style = getComputedStyle(grid);
        return {
            cols: style.gridTemplateColumns.trim().split(/\\s+/).filter(Boolean).length,
            rows: style.gridTemplateRows.trim().split(/\\s+/).filter(Boolean).length
        };
    }""")
    assert layout["cols"] == 3
    assert layout["rows"] == 2


def test_dashboard_auto_grid_6tz(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": "UTC,Europe/Helsinki,America/New_York,Asia/Tokyo,Australia/Sydney,Pacific/Auckland"})
    layout = page.evaluate("""() => {
        var grid = document.querySelector('.clock-grid');
        var style = getComputedStyle(grid);
        return {
            cols: style.gridTemplateColumns.trim().split(/\\s+/).filter(Boolean).length,
            rows: style.gridTemplateRows.trim().split(/\\s+/).filter(Boolean).length
        };
    }""")
    assert layout["cols"] == 3
    assert layout["rows"] == 2


def test_dashboard_auto_grid_9tz(page: Page, app_url: str) -> None:
    open_page(page, app_url, {
        "tz": "UTC,Europe/Helsinki,America/New_York,Asia/Tokyo,Australia/Sydney,Pacific/Auckland,Europe/London,Asia/Kolkata,America/Los_Angeles"
    })
    layout = page.evaluate("""() => {
        var grid = document.querySelector('.clock-grid');
        var style = getComputedStyle(grid);
        return {
            cols: style.gridTemplateColumns.trim().split(/\\s+/).filter(Boolean).length,
            rows: style.gridTemplateRows.trim().split(/\\s+/).filter(Boolean).length
        };
    }""")
    assert layout["cols"] == 3
    assert layout["rows"] == 3


def test_dashboard_single_tz_no_grid(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": "UTC"})
    assert page.evaluate("() => !!document.querySelector('.clock-grid')") is False
    assert page.evaluate("() => !!document.getElementById('clock')") is True
    title = page.evaluate("() => document.title")
    assert title == "clocksimulator.com - UTC"


def test_dashboard_all_invalid_tz_fallback(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": "Fake/One,Fake/Two"})
    assert page.evaluate("() => !!document.querySelector('.clock-grid')") is False
    assert page.evaluate("() => !!document.getElementById('clock')") is True


def test_dashboard_empty_tz_param(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": ""})
    assert page.evaluate("() => !!document.querySelector('.clock-grid')") is False
    assert page.evaluate("() => !!document.getElementById('clock')") is True


def test_dashboard_original_container_hidden(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": "UTC,Europe/Helsinki"})
    display = page.evaluate("() => document.querySelector('.clock-container').style.display")
    assert display == "none"


def test_dashboard_label_text_matches_tz(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": "UTC,Europe/Helsinki,America/New_York"})
    labels = page.evaluate(
        "() => Array.from(document.querySelectorAll('.clock-label')).map(el => el.textContent)"
    )
    assert labels == ["UTC", "Helsinki", "New York"]


def test_dashboard_clocks_different_hand_angles(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": "UTC,Asia/Tokyo"})
    angles = page.evaluate("""() => {
        var hands = document.querySelectorAll('.clock-grid .hour-hand');
        return Array.from(hands).map(h => h.style.transform);
    }""")
    assert len(angles) == 2
    assert angles[0] != ""
    assert angles[1] != ""
    assert angles[0] != angles[1]


def test_dashboard_no_duplicate_svg_ids(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": "UTC,Europe/Helsinki"})
    ids_in_clones = page.evaluate("""() => {
        var svgs = document.querySelectorAll('.clock-grid .clock-cell svg');
        var count = 0;
        for (var i = 0; i < svgs.length; i++) {
            count += svgs[i].querySelectorAll('[id]').length;
        }
        return count;
    }""")
    assert ids_in_clones == 0


def test_dashboard_embed_labels_visible(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true", "tz": "UTC,Europe/Helsinki"})
    labels = page.evaluate("""() => {
        var els = document.querySelectorAll('.clock-label');
        return Array.from(els).map(el => el.offsetHeight > 0);
    }""")
    assert len(labels) == 2
    assert all(labels)


def test_dashboard_embed_burnin_disabled(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true", "tz": "UTC,Europe/Helsinki"})
    time.sleep(0.2)
    transform = page.evaluate("() => document.querySelector('.clock-grid').style.transform")
    assert transform == "" or transform == "none"


def test_dashboard_mode_visual_snapshot_dark_2tz(page: Page, app_url: str, update_snapshots: bool) -> None:
    open_page(page, app_url, {"tz": "UTC,Europe/Helsinki", "theme": "dark"})
    assert_screenshot(page, "dashboard-dark-2tz.png", update=update_snapshots)


def test_dashboard_mode_visual_snapshot_light_3tz(page: Page, app_url: str, update_snapshots: bool) -> None:
    open_page(page, app_url, {"tz": "UTC,Europe/Helsinki,America/New_York", "theme": "light"})
    assert_screenshot(page, "dashboard-light-3tz.png", update=update_snapshots)


def test_dashboard_mode_visual_snapshot_dark_4tz(page: Page, app_url: str, update_snapshots: bool) -> None:
    open_page(page, app_url, {"tz": "UTC,Europe/Helsinki,America/New_York,Asia/Tokyo", "theme": "dark"})
    assert_screenshot(page, "dashboard-dark-4tz.png", update=update_snapshots)


def test_dashboard_mode_visual_snapshot_embed_2tz(page: Page, app_url: str, update_snapshots: bool) -> None:
    open_page(page, app_url, {"embed": "true", "tz": "UTC,Europe/Helsinki", "theme": "dark"})
    assert_screenshot(page, "dashboard-embed-2tz.png", update=update_snapshots)
