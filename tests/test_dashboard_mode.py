from __future__ import annotations

import pytest
from playwright.sync_api import Page

from tests.helpers import open_page


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


def grid_dimensions(page: Page, selector: str = ".clock-grid") -> tuple[int, int]:
    values = page.locator(selector).evaluate(
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


@pytest.mark.parametrize(
    ("timezones", "rows", "expected_columns", "expected_rows"),
    [
        pytest.param(
            "UTC,Europe/Helsinki,America/New_York,Asia/Tokyo,Australia/Sydney",
            None,
            3,
            2,
            id="auto-5",
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
    assert page.title() == "clocksimulator.com - Dashboard"
    assert dashboard_counts(page) == {
        "grids": 1,
        **{
            key: expected_count
            for key in (
                "cells", "clocks", "labels", "hours", "minutes", "seconds",
                "borders", "numbers", "suns", "moons",
            )
        },
    }
    assert grid_dimensions(page) == (expected_columns, expected_rows)


FOUR_ZONES = "UTC,Europe/Helsinki,America/New_York,Asia/Tokyo"
FIVE_ZONES = FOUR_ZONES + ",Australia/Sydney"


@pytest.mark.parametrize(
    ("path", "timezones", "rows", "expected_columns", "expected_rows"),
    [
        pytest.param("", FIVE_ZONES, "0", 3, 2, id="analog-zero-is-auto"),
        pytest.param("", FIVE_ZONES, "abc", 3, 2, id="analog-non-numeric-is-auto"),
        pytest.param("", FIVE_ZONES, "-2", 3, 2, id="analog-negative-is-auto"),
        pytest.param("", FOUR_ZONES, "9", 1, 4, id="analog-clamped-to-zone-count"),
        pytest.param(
            "/digital/",
            "UTC,Europe/Helsinki,Asia/Tokyo",
            "9",
            1,
            3,
            id="digital-clamped-to-zone-count",
        ),
    ],
)
def test_dashboard_rows_parameter_edge_values(
    page: Page,
    app_url: str,
    path: str,
    timezones: str,
    rows: str,
    expected_columns: int,
    expected_rows: int,
) -> None:
    open_page(page, app_url, {"tz": timezones, "rows": rows}, path=path)
    expected_count = len(timezones.split(","))
    if path:
        grid = ".digital-grid"
        cells = page.locator(".digital-grid .digital-cell")
        rendered = page.locator(".digital-grid .digital-time").evaluate_all(
            "elements => elements.map(element => element.textContent !== '')"
        )
    else:
        grid = ".clock-grid"
        cells = page.locator(".clock-grid .clock-cell")
        rendered = page.locator(".clock-grid .hour-hand").evaluate_all(
            "elements => elements.map(element => element.style.transform !== '')"
        )
    assert cells.count() == expected_count
    assert rendered == [True] * expected_count
    assert grid_dimensions(page, grid) == (expected_columns, expected_rows)


def test_dashboard_shadows_disabled_unless_enabled(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"tz": TIMEZONES})
    assert page.locator(".clock-grid [filter]").count() == 0

    open_page(page, app_url, {"tz": TIMEZONES, "shadows": "true"})
    filtered = page.locator(".clock-grid [filter]")
    assert filtered.count() == 8
    assert filtered.evaluate_all(
        "elements => elements.every(element => element.getAttribute('filter').startsWith('url('))"
    ) is True


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

    open_page(page, app_url, {"tz": TIMEZONES})
    assert page.locator(".clock-grid .second-hand").evaluate_all(
        "elements => elements.map(element => getComputedStyle(element).display !== 'none')"
    ) == [True, True]
    assert page.locator(".clock-grid .clock-border").evaluate_all(
        "elements => elements.map(element => element.getAttribute('stroke'))"
    ) == ["var(--clock-border)", "var(--clock-border)"]
    assert page.locator(".clock-grid .numbers").evaluate_all(
        "elements => elements.map(element => getComputedStyle(element).display !== 'none')"
    ) == [True, True]
