from __future__ import annotations

import pytest
from playwright.sync_api import Page

from tests.helpers import assert_screenshot, open_page


TIMEZONES = "UTC,Europe/Helsinki"


def dashboard_counts(page: Page) -> dict[str, int]:
    return page.evaluate(
        """() => ({
            grids: document.querySelectorAll('.clock-grid').length,
            cells: document.querySelectorAll('.clock-grid .clock-cell').length,
            clocks: document.querySelectorAll('.clock-grid .clock-cell svg').length,
            labels: document.querySelectorAll('.clock-grid .clock-label').length,
            hours: document.querySelectorAll('.clock-grid .hour-hand').length,
            minutes: document.querySelectorAll('.clock-grid .minute-hand').length,
            seconds: document.querySelectorAll('.clock-grid .second-hand').length,
            borders: document.querySelectorAll('.clock-grid .clock-border').length,
            numbers: document.querySelectorAll('.clock-grid .numbers').length,
            suns: document.querySelectorAll('.clock-grid .sun-icon').length,
            moons: document.querySelectorAll('.clock-grid .moon-icon').length
        })"""
    )


def grid_dimensions(page: Page) -> tuple[int, int]:
    values = page.locator(".clock-grid").evaluate(
        r"""grid => {
            const style = getComputedStyle(grid);
            return [
                style.gridTemplateColumns.trim().split(/\s+/).filter(Boolean).length,
                style.gridTemplateRows.trim().split(/\s+/).filter(Boolean).length
            ];
        }"""
    )
    return values[0], values[1]


def assert_single_analog_ready(page: Page, aria_label: str | None = None) -> None:
    clock = page.locator("#clock")
    assert clock.is_visible() is True
    assert page.locator(".clock-grid").count() == 0
    assert page.locator("#hourHand").get_attribute("style")
    assert page.locator("#minuteHand").get_attribute("style")
    if aria_label is not None:
        assert clock.get_attribute("aria-label") == aria_label


def test_dashboard_mode_activation_has_exact_structure(
    page: Page,
    app_url: str,
) -> None:
    open_page(page, app_url, {"tz": TIMEZONES})
    assert page.title() == "clocksimulator.com - Dashboard"
    assert dashboard_counts(page) == {
        "grids": 1,
        "cells": 2,
        "clocks": 2,
        "labels": 2,
        "hours": 2,
        "minutes": 2,
        "seconds": 2,
        "borders": 2,
        "numbers": 2,
        "suns": 2,
        "moons": 2,
    }


@pytest.mark.parametrize(
    ("timezones", "rows", "expected_columns", "expected_rows"),
    [
        pytest.param(
            "UTC,Europe/Helsinki,America/New_York,Asia/Tokyo",
            None,
            2,
            2,
            id="auto-4",
        ),
        pytest.param(
            "UTC,Europe/Helsinki,America/New_York,Asia/Tokyo,Australia/Sydney",
            None,
            3,
            2,
            id="auto-5",
        ),
        pytest.param(
            "UTC,Europe/Helsinki,America/New_York,Asia/Tokyo,Australia/Sydney,Pacific/Auckland",
            None,
            3,
            2,
            id="auto-6",
        ),
        pytest.param(
            "UTC,Europe/Helsinki,America/New_York,Asia/Tokyo,Australia/Sydney,Pacific/Auckland,Europe/London,Asia/Kolkata,America/Los_Angeles",
            None,
            3,
            3,
            id="auto-9",
        ),
        pytest.param(
            "UTC,Europe/Helsinki,America/New_York,Asia/Tokyo",
            "1",
            4,
            1,
            id="rows-1",
        ),
        pytest.param(
            "UTC,Europe/Helsinki,America/New_York,Asia/Tokyo",
            "2",
            2,
            2,
            id="rows-2",
        ),
        pytest.param(
            "UTC,Europe/Helsinki,America/New_York,Asia/Tokyo",
            "4",
            1,
            4,
            id="rows-4",
        ),
    ],
)
def test_dashboard_grid_layout(
    page: Page,
    app_url: str,
    timezones: str,
    rows: str | None,
    expected_columns: int,
    expected_rows: int,
) -> None:
    params = {"tz": timezones}
    if rows is not None:
        params["rows"] = rows
    open_page(page, app_url, params)
    expected_count = len(timezones.split(","))
    counts = dashboard_counts(page)
    assert counts["cells"] == expected_count
    assert counts["labels"] == expected_count
    assert grid_dimensions(page) == (expected_columns, expected_rows)


@pytest.mark.parametrize(
    ("theme", "dark", "transparent"),
    [
        pytest.param("dark", True, False, id="dark"),
        pytest.param("light", False, False, id="light"),
        pytest.param("transparent", False, True, id="transparent"),
    ],
)
def test_dashboard_theme_visible_state(
    page: Page,
    app_url: str,
    theme: str,
    dark: bool,
    transparent: bool,
) -> None:
    open_page(page, app_url, {"tz": TIMEZONES, "theme": theme})
    root = page.locator("html")
    assert root.evaluate("element => element.classList.contains('dark-mode')") is dark
    assert root.evaluate(
        "element => element.classList.contains('transparent-mode')"
    ) is transparent
    assert page.locator(".clock-grid").is_visible() is True


def test_dashboard_seconds_hide_and_default_visible(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": TIMEZONES, "seconds": "hide"})
    hands = page.locator(".clock-grid .second-hand")
    assert hands.count() == 2
    assert hands.evaluate_all(
        "elements => elements.map(element => getComputedStyle(element).display)"
    ) == ["none", "none"]

    open_page(page, app_url, {"tz": TIMEZONES})
    hands = page.locator(".clock-grid .second-hand")
    assert hands.count() == 2
    assert hands.evaluate_all(
        "elements => elements.every(element => getComputedStyle(element).display !== 'none')"
    ) is True


def test_dashboard_border_hide_and_default_visible(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": TIMEZONES, "border": "hide"})
    borders = page.locator(".clock-grid .clock-border")
    assert borders.count() == 2
    assert borders.evaluate_all(
        "elements => elements.map(element => element.getAttribute('stroke'))"
    ) == ["none", "none"]

    open_page(page, app_url, {"tz": TIMEZONES})
    borders = page.locator(".clock-grid .clock-border")
    assert borders.count() == 2
    assert borders.evaluate_all(
        "elements => elements.map(element => element.getAttribute('stroke'))"
    ) == ["var(--clock-border)", "var(--clock-border)"]


def test_dashboard_numbers_hide_and_default_visible(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": TIMEZONES, "numbers": "hide"})
    numbers = page.locator(".clock-grid .numbers")
    assert numbers.count() == 2
    assert numbers.evaluate_all(
        "elements => elements.map(element => getComputedStyle(element).display)"
    ) == ["none", "none"]

    open_page(page, app_url, {"tz": TIMEZONES})
    numbers = page.locator(".clock-grid .numbers")
    assert numbers.count() == 2
    assert numbers.evaluate_all(
        "elements => elements.every(element => getComputedStyle(element).display !== 'none')"
    ) is True


@pytest.mark.parametrize("shadows", [None, "false"])
def test_dashboard_shadows_disabled_unless_enabled(
    page: Page,
    app_url: str,
    shadows: str | None,
) -> None:
    params = {"tz": TIMEZONES}
    if shadows is not None:
        params["shadows"] = shadows
    open_page(page, app_url, params)
    assert page.locator(".clock-grid [filter]").count() == 0


def test_dashboard_shadows_true_enables_filters(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": TIMEZONES, "shadows": "true"})
    filtered = page.locator(".clock-grid [filter]")
    assert filtered.count() == 8
    assert filtered.evaluate_all(
        "elements => elements.every(element => element.getAttribute('filter').startsWith('url('))"
    ) is True


def test_dashboard_daynight_uses_each_target_timezone(
    page: Page,
    app_url: str,
) -> None:
    open_page(page, app_url, {"tz": "UTC,Asia/Tokyo", "daynight": "show"})
    cells = page.locator(".clock-grid .clock-cell")
    assert cells.count() == 2
    states = cells.evaluate_all(
        """elements => elements.map(element => ({
            label: element.querySelector('.clock-label').textContent,
            sun: element.querySelector('.sun-icon').getAttribute('display'),
            moon: element.querySelector('.moon-icon').getAttribute('display')
        }))"""
    )
    assert states == [
        {"label": "UTC", "sun": "inline", "moon": "none"},
        {"label": "Tokyo", "sun": "none", "moon": "inline"},
    ]

    open_page(page, app_url, {"tz": "UTC,Asia/Tokyo"})
    cells = page.locator(".clock-grid .clock-cell")
    assert cells.count() == 2
    hidden_states = cells.evaluate_all(
        """elements => elements.map(element => [
            element.querySelector('.sun-icon').getAttribute('display'),
            element.querySelector('.moon-icon').getAttribute('display')
        ])"""
    )
    assert hidden_states == [["none", "none"], ["none", "none"]]


def test_dashboard_mixed_valid_invalid_timezones_keep_order_and_time(
    page: Page,
    app_url: str,
) -> None:
    open_page(page, app_url, {"tz": "UTC,Invalid/Timezone,Asia/Kathmandu"})
    cells = page.locator(".clock-grid .clock-cell")
    assert cells.count() == 2
    assert page.locator(".clock-label").all_text_contents() == ["UTC", "Kathmandu"]
    assert page.locator(".clock-grid svg").evaluate_all(
        "elements => elements.map(element => element.getAttribute('aria-label'))"
    ) == ["UTC: 12:00", "Kathmandu: 17:45"]
    assert page.locator(".clock-grid .hour-hand").evaluate_all(
        "elements => elements.map(element => element.style.transform)"
    ) == ["rotate(0deg)", "rotate(172.5deg)"]


@pytest.mark.parametrize(
    ("timezone_value", "title", "aria_label"),
    [
        pytest.param("UTC", "clocksimulator.com - UTC", "The time is 12:00", id="single"),
        pytest.param(
            "UTC,Invalid/Timezone",
            "clocksimulator.com - UTC",
            "The time is 12:00",
            id="mixed-fallback",
        ),
        pytest.param(
            "Fake/One,Fake/Two",
            "Fullscreen Online Analog Clock | Clocksimulator",
            "The time is 12:00",
            id="all-invalid",
        ),
        pytest.param(
            "",
            "Fullscreen Online Analog Clock | Clocksimulator",
            "The time is 12:00",
            id="empty",
        ),
    ],
)
def test_dashboard_fallbacks_render_initialized_single_clock(
    page: Page,
    app_url: str,
    timezone_value: str,
    title: str,
    aria_label: str,
) -> None:
    open_page(page, app_url, {"tz": timezone_value})
    assert page.title() == title
    assert_single_analog_ready(page, aria_label)


def test_dashboard_embed_combined_hides_ui_and_keeps_labels(
    page: Page,
    app_url: str,
) -> None:
    open_page(page, app_url, {"embed": "true", "tz": TIMEZONES})
    assert page.locator("body").evaluate(
        "element => element.classList.contains('embed-mode')"
    ) is True
    assert page.locator(".clock-grid .clock-cell").count() == 2
    labels = page.locator(".clock-grid .clock-label")
    assert labels.count() == 2
    assert labels.evaluate_all(
        "elements => elements.every(element => element.checkVisibility())"
    ) is True
    assert page.locator(".toggle-wrapper").evaluate(
        "element => element.getBoundingClientRect().width"
    ) == 0


def test_dashboard_all_params_combined(page: Page, app_url: str) -> None:
    open_page(
        page,
        app_url,
        {
            "tz": "UTC,Asia/Kathmandu",
            "theme": "light",
            "seconds": "hide",
            "border": "hide",
            "numbers": "hide",
            "shadows": "false",
            "daynight": "show",
            "rows": "1",
        },
    )
    counts = dashboard_counts(page)
    assert counts["cells"] == 2
    assert counts["labels"] == 2
    assert page.locator(".clock-label").all_text_contents() == ["UTC", "Kathmandu"]
    assert page.locator("html").evaluate(
        "element => !element.classList.contains('dark-mode') && !element.classList.contains('transparent-mode')"
    ) is True
    assert grid_dimensions(page) == (2, 1)
    second_hands = page.locator(".clock-grid .second-hand")
    assert second_hands.count() == 2
    assert second_hands.evaluate_all(
        "elements => elements.every(element => getComputedStyle(element).display === 'none')"
    ) is True
    borders = page.locator(".clock-grid .clock-border")
    assert borders.count() == 2
    assert borders.evaluate_all(
        "elements => elements.every(element => element.getAttribute('stroke') === 'none')"
    ) is True
    numbers = page.locator(".clock-grid .numbers")
    assert numbers.count() == 2
    assert numbers.evaluate_all(
        "elements => elements.every(element => getComputedStyle(element).display === 'none')"
    ) is True
    assert page.locator(".clock-grid [filter]").count() == 0
    assert page.locator(".clock-grid svg").evaluate_all(
        "elements => elements.map(element => element.getAttribute('aria-label'))"
    ) == ["UTC: 12:00", "Kathmandu: 17:45"]
    assert page.locator(".clock-grid .sun-icon").evaluate_all(
        "elements => elements.map(element => element.getAttribute('display'))"
    ) == ["inline", "inline"]
    assert page.locator(".clock-grid .moon-icon").evaluate_all(
        "elements => elements.map(element => element.getAttribute('display'))"
    ) == ["none", "none"]


def test_dashboard_no_duplicate_svg_ids(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": TIMEZONES})
    clocks = page.locator(".clock-grid .clock-cell svg")
    assert clocks.count() == 2
    assert clocks.evaluate_all(
        "elements => elements.every(element => element.querySelectorAll('[id]').length === 0)"
    ) is True


@pytest.mark.visual
def test_dashboard_mode_visual_snapshot_dark_2tz(
    page: Page,
    app_url: str,
    update_snapshots: bool,
) -> None:
    open_page(page, app_url, {"tz": TIMEZONES, "theme": "dark"})
    assert dashboard_counts(page)["cells"] == 2
    assert page.locator("html").evaluate(
        "element => element.classList.contains('dark-mode')"
    ) is True
    assert_screenshot(page, "dashboard-dark-2tz.png", update=update_snapshots)


@pytest.mark.visual
def test_dashboard_mode_visual_snapshot_light_3tz(
    page: Page,
    app_url: str,
    update_snapshots: bool,
) -> None:
    open_page(
        page,
        app_url,
        {"tz": "UTC,Europe/Helsinki,America/New_York", "theme": "light"},
    )
    assert dashboard_counts(page)["cells"] == 3
    assert_screenshot(page, "dashboard-light-3tz.png", update=update_snapshots)


@pytest.mark.visual
def test_dashboard_mode_visual_snapshot_dark_4tz(
    page: Page,
    app_url: str,
    update_snapshots: bool,
) -> None:
    open_page(
        page,
        app_url,
        {
            "tz": "UTC,Europe/Helsinki,America/New_York,Asia/Tokyo",
            "theme": "dark",
        },
    )
    assert dashboard_counts(page)["cells"] == 4
    assert_screenshot(page, "dashboard-dark-4tz.png", update=update_snapshots)


@pytest.mark.visual
def test_dashboard_mode_visual_snapshot_embed_2tz(
    page: Page,
    app_url: str,
    update_snapshots: bool,
) -> None:
    open_page(
        page,
        app_url,
        {"embed": "true", "tz": TIMEZONES, "theme": "dark"},
    )
    assert dashboard_counts(page)["cells"] == 2
    assert page.locator(".toggle-wrapper").evaluate(
        "element => element.getBoundingClientRect().width"
    ) == 0
    assert_screenshot(page, "dashboard-embed-2tz.png", update=update_snapshots)
