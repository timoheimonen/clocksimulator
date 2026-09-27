from __future__ import annotations

import pytest
from playwright.sync_api import Page

from tests.helpers import open_page


def hand_angle(page: Page, selector: str) -> float:
    value = page.locator(selector).evaluate(
        "element => parseFloat(element.style.transform.replace(/[^0-9.-]/g, ''))"
    )
    return float(value)


def icon_displays(page: Page) -> dict[str, str]:
    return page.evaluate(
        """() => ({
            sun: document.getElementById('sunIcon').getAttribute('display'),
            moon: document.getElementById('moonIcon').getAttribute('display')
        })"""
    )


def second_hand_colors(page: Page) -> dict[str, str]:
    return page.evaluate(
        """() => ({
            hour: getComputedStyle(document.getElementById('hourHand')).fill,
            second: getComputedStyle(document.getElementById('secondHand')).stroke,
            dot: getComputedStyle(document.getElementById('centerDot')).fill
        })"""
    )


@pytest.mark.cross_browser
@pytest.mark.parametrize(
    ("params", "expected"),
    [
        pytest.param(
            {},
            {"hour": "rgb(34, 34, 34)", "second": "rgb(214, 48, 49)", "dot": "rgb(214, 48, 49)"},
            id="missing-default-dark",
        ),
        pytest.param(
            {"color": "0066ff"},
            {"hour": "rgb(0, 102, 255)", "second": "rgb(0, 102, 255)", "dot": "rgb(0, 102, 255)"},
            id="missing-custom-clock-color",
        ),
        pytest.param(
            {"color": "0066ff", "secondcolor": "ff3b30"},
            {"hour": "rgb(0, 102, 255)", "second": "rgb(255, 59, 48)", "dot": "rgb(255, 59, 48)"},
            id="custom-both",
        ),
        pytest.param(
            {"color": "0066ff", "secondcolor": "#ff3b30"},
            {"hour": "rgb(0, 102, 255)", "second": "rgb(0, 102, 255)", "dot": "rgb(0, 102, 255)"},
            id="invalid-falls-back-to-clock-color",
        ),
    ],
)
def test_transparent_secondcolor_sets_second_hand_and_center_dot(
    page: Page,
    app_url: str,
    params: dict[str, str],
    expected: dict[str, str],
) -> None:
    open_page(page, app_url, {"embed": "true", "theme": "transparent", **params})
    assert second_hand_colors(page) == expected


@pytest.mark.cross_browser
def test_secondcolor_is_ignored_outside_transparent_theme_and_cleared_by_theme_switch(
    page: Page,
    app_url: str,
) -> None:
    open_page(page, app_url, {"theme": "light", "secondcolor": "00ff00"})
    assert page.locator("html").get_attribute("data-second-color") is None
    assert second_hand_colors(page)["second"] == "rgb(214, 48, 49)"

    open_page(page, app_url, {"theme": "transparent", "secondcolor": "00ff00"})
    assert page.locator("html").get_attribute("data-second-color") == "custom"
    page.mouse.move(20, 20)
    page.wait_for_function(
        "() => !document.querySelector('.toggle-wrapper').hasAttribute('inert')"
    )
    page.locator(".theme-toggle").click()
    assert page.locator("html").get_attribute("data-second-color") is None
    assert page.locator("html").evaluate(
        "element => element.style.getPropertyValue('--custom-second-color')"
    ) == ""
    assert second_hand_colors(page)["second"] == "rgb(239, 68, 68)"


def test_embed_mode_clock_container_full_size(page: Page, app_url: str) -> None:
    viewport = {"width": 720, "height": 1280}
    page.set_viewport_size(viewport)
    open_page(page, app_url, {"embed": "true"})
    geometry = page.locator(".clock-container").evaluate(
        """element => {
            const rect = element.getBoundingClientRect();
            return {
                x: rect.x,
                y: rect.y,
                width: rect.width,
                height: rect.height,
                scrollWidth: document.documentElement.scrollWidth,
                scrollHeight: document.documentElement.scrollHeight,
                overflow: getComputedStyle(document.body).overflow
            };
        }"""
    )
    expected_size = min(viewport.values())
    assert geometry["width"] == pytest.approx(expected_size, abs=1)
    assert geometry["height"] == pytest.approx(expected_size, abs=1)
    assert geometry["x"] == pytest.approx((viewport["width"] - expected_size) / 2, abs=1)
    assert geometry["y"] == pytest.approx((viewport["height"] - expected_size) / 2, abs=1)
    assert geometry["scrollWidth"] <= viewport["width"]
    assert geometry["scrollHeight"] <= viewport["height"]
    assert geometry["overflow"] == "hidden"


def test_embed_mode_all_params_combined(page: Page, app_url: str) -> None:
    open_page(page, app_url, {
        "embed": "true",
        "tz": "Asia/Kathmandu",
        "theme": "light",
        "seconds": "hide",
        "border": "hide",
        "numbers": "hide",
        "shadows": "false",
        "daynight": "show",
    })
    assert page.evaluate("() => document.body.classList.contains('embed-mode')") is True
    assert page.evaluate("() => document.querySelector('.toggle-wrapper').offsetWidth") == 0
    assert page.evaluate("() => document.documentElement.classList.contains('dark-mode')") is False
    assert page.evaluate("() => document.documentElement.classList.contains('transparent-mode')") is False
    assert page.locator("#secondHand").evaluate(
        "element => getComputedStyle(element).display"
    ) == "none"
    assert page.locator("#secondHand").is_hidden() is True
    assert page.evaluate("() => document.getElementById('clockBorder').getAttribute('stroke')") == "none"
    assert page.locator("#numbers").evaluate(
        "element => getComputedStyle(element).display"
    ) == "none"
    assert page.locator("#numbers").is_hidden() is True
    assert page.title() == "clocksimulator.com - Asia/Kathmandu"
    assert hand_angle(page, "#hourHand") == pytest.approx(172.5)
    assert hand_angle(page, "#minuteHand") == pytest.approx(270)
    assert page.locator("#clock").get_attribute("aria-label") == "The time is 17:45"
    assert page.locator("#clock [filter]").count() == 0
    assert page.evaluate(
        "() => ['hourHand', 'minuteHand', 'secondHand', 'centerDot'].filter(id => document.getElementById(id).hasAttribute('filter'))"
    ) == []
    assert icon_displays(page) == {"sun": "inline", "moon": "none"}
