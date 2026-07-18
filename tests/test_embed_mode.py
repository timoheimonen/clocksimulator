from __future__ import annotations

import pytest
from playwright.sync_api import Page

from tests.helpers import open_page, assert_screenshot


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


def test_embed_mode_adds_embed_mode_class(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true"})
    assert page.evaluate("() => document.body.classList.contains('embed-mode')") is True


def test_embed_mode_hides_toggle_wrapper(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true"})
    wrapper_width = page.evaluate("() => document.querySelector('.toggle-wrapper').offsetWidth")
    assert wrapper_width == 0


@pytest.mark.parametrize(
    "viewport",
    [
        pytest.param({"width": 1280, "height": 720}, id="landscape"),
        pytest.param({"width": 720, "height": 1280}, id="portrait"),
        pytest.param({"width": 240, "height": 320}, id="small"),
    ],
)
def test_embed_mode_clock_container_full_size(
    page: Page,
    app_url: str,
    viewport: dict[str, int],
) -> None:
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


def test_embed_mode_defaults_to_dark_theme(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true"})
    assert page.evaluate("() => document.documentElement.classList.contains('dark-mode')") is True


def test_embed_mode_theme_light_override(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true", "theme": "light"})
    assert page.evaluate("() => document.documentElement.classList.contains('dark-mode')") is False
    assert page.evaluate("() => document.documentElement.classList.contains('transparent-mode')") is False


def test_embed_mode_theme_transparent(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true", "theme": "transparent"})
    assert page.evaluate("() => document.documentElement.classList.contains('transparent-mode')") is True


def test_embed_mode_removes_favicon(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true"})
    assert page.evaluate("() => document.getElementById('favicon')") is None


def test_embed_mode_disables_save_settings(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true"})
    assert page.evaluate("() => document.getElementById('saveSettingsToggle').disabled") is True


def test_embed_mode_no_time_announcements(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true"})
    page.wait_for_function("() => getComputedStyle(document.documentElement).getPropertyValue('--second-angle').trim() !== ''")
    announce_text = page.evaluate("() => document.getElementById('timeAnnounce').textContent")
    assert announce_text == ""


def test_embed_mode_with_single_timezone(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true", "tz": "Asia/Kathmandu"})
    assert page.evaluate("() => document.body.classList.contains('embed-mode')") is True
    assert page.title() == "clocksimulator.com - Asia/Kathmandu"
    assert hand_angle(page, "#hourHand") == pytest.approx(172.5)
    assert hand_angle(page, "#minuteHand") == pytest.approx(270)
    assert page.locator("#clock").get_attribute("aria-label") == "The time is 17:45"


def test_embed_mode_seconds_tick_visible_by_default(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true"})
    assert page.locator("#secondHand").evaluate(
        "element => getComputedStyle(element).display"
    ) != "none"
    assert page.locator("#secondModeToggle").is_checked() is True


def test_embed_mode_seconds_hide(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true", "seconds": "hide"})
    second_hand = page.locator("#secondHand")
    assert second_hand.evaluate("element => getComputedStyle(element).display") == "none"
    assert second_hand.is_hidden() is True


def test_embed_mode_seconds_smooth(page: Page, app_url: str) -> None:
    open_page(
        page,
        app_url,
        {"embed": "true", "seconds": "smooth"},
        fixed_time="2026-01-01T12:00:00.500Z",
    )
    assert page.locator("#secondModeToggle").is_checked() is False
    second_angle = page.evaluate(
        "() => parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--second-angle'))"
    )
    assert second_angle == pytest.approx(3)


def test_embed_mode_border_hide(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true", "border": "hide"})
    assert page.evaluate("() => document.getElementById('clockBorder').getAttribute('stroke')") == "none"


def test_embed_mode_border_visible_by_default(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true"})
    assert page.locator("#clockBorder").get_attribute("stroke") == "var(--clock-border)"


def test_embed_mode_numbers_hide(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true", "numbers": "hide"})
    numbers = page.locator("#numbers")
    assert numbers.evaluate("element => getComputedStyle(element).display") == "none"
    assert numbers.is_hidden() is True


def test_embed_mode_numbers_visible_by_default(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true"})
    assert page.locator("#numbers").evaluate(
        "element => getComputedStyle(element).display"
    ) != "none"


def test_embed_mode_shadows_disabled(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true", "shadows": "false"})
    filtered = page.evaluate(
        "() => ['hourHand', 'minuteHand', 'secondHand', 'centerDot'].filter(id => document.getElementById(id).hasAttribute('filter'))"
    )
    assert filtered == []


def test_embed_mode_shadows_enabled_by_default(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true"})
    filters = page.evaluate(
        "() => ['hourHand', 'minuteHand', 'secondHand', 'centerDot'].map(id => document.getElementById(id).getAttribute('filter'))"
    )
    assert filters == [
        "url(#hourShadow)",
        "url(#minuteShadow)",
        "url(#secondShadow)",
        "url(#dotShadow)",
    ]


def test_embed_mode_daynight_show(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true", "daynight": "show"})
    assert icon_displays(page) == {"sun": "inline", "moon": "none"}


def test_embed_mode_daynight_hidden_by_default(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true"})
    assert icon_displays(page) == {"sun": "none", "moon": "none"}


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
    assert page.evaluate("() => document.documentElement.classList.contains('dark-mode')") is False
    assert page.evaluate("() => document.documentElement.classList.contains('transparent-mode')") is False
    assert page.locator("#secondHand").evaluate(
        "element => getComputedStyle(element).display"
    ) == "none"
    assert page.evaluate("() => document.getElementById('clockBorder').getAttribute('stroke')") == "none"
    assert page.locator("#numbers").evaluate(
        "element => getComputedStyle(element).display"
    ) == "none"
    assert page.title() == "clocksimulator.com - Asia/Kathmandu"
    assert hand_angle(page, "#hourHand") == pytest.approx(172.5)
    assert hand_angle(page, "#minuteHand") == pytest.approx(270)
    assert page.locator("#clock").get_attribute("aria-label") == "The time is 17:45"
    assert page.locator("#clock [filter]").count() == 0
    assert icon_displays(page) == {"sun": "inline", "moon": "none"}


def test_embed_mode_wakelock_hidden(page: Page, app_url: str) -> None:
    page.add_init_script(
        """Object.defineProperty(navigator, 'wakeLock', {
            configurable: true,
            value: { request: function () { return Promise.resolve({
                addEventListener: function () {},
                release: function () { return Promise.resolve(); }
            }); } }
        });"""
    )
    open_page(page, app_url, {"embed": "true"})
    hidden_state = page.locator("#wakeLockLabel").evaluate(
        """element => ({
            visible: element.checkVisibility({
                checkOpacity: true,
                checkVisibilityCSS: true
            }),
            width: element.getBoundingClientRect().width,
            height: element.getBoundingClientRect().height
        })"""
    )
    assert hidden_state == {"visible": False, "width": 0, "height": 0}
    assert page.get_by_role("switch", name="Keep screen on").count() == 0


@pytest.mark.visual
def test_embed_mode_visual_snapshot_dark(page: Page, app_url: str, update_snapshots: bool) -> None:
    open_page(page, app_url, {"embed": "true", "theme": "dark"})
    assert page.locator("html").get_attribute("class") == "dark-mode"
    assert_screenshot(page, "embed-dark.png", update=update_snapshots)


@pytest.mark.visual
def test_embed_mode_visual_snapshot_light(page: Page, app_url: str, update_snapshots: bool) -> None:
    open_page(page, app_url, {"embed": "true", "theme": "light"})
    assert page.locator("html").get_attribute("class") in {None, ""}
    assert_screenshot(page, "embed-light.png", update=update_snapshots)


@pytest.mark.visual
def test_embed_mode_visual_snapshot_transparent(page: Page, app_url: str, update_snapshots: bool) -> None:
    open_page(page, app_url, {"embed": "true", "theme": "transparent"})
    assert page.locator("body").evaluate(
        "element => getComputedStyle(element).backgroundColor"
    ) == "rgba(0, 0, 0, 0)"
    assert_screenshot(
        page,
        "embed-transparent.png",
        update=update_snapshots,
        transparent=True,
    )


@pytest.mark.visual
def test_embed_mode_visual_snapshot_daynight(page: Page, app_url: str, update_snapshots: bool) -> None:
    open_page(page, app_url, {"embed": "true", "theme": "dark", "daynight": "show"})
    assert icon_displays(page) == {"sun": "inline", "moon": "none"}
    assert_screenshot(
        page,
        "embed-daynight-icon.png",
        update=update_snapshots,
        selector="#sunIcon",
    )


@pytest.mark.visual
def test_embed_mode_visual_snapshot_second_hand_detail(
    page: Page, app_url: str, update_snapshots: bool
) -> None:
    open_page(page, app_url, {"embed": "true", "theme": "dark", "seconds": "tick"})
    assert page.locator("#secondHand").evaluate(
        "element => getComputedStyle(element).display"
    ) != "none"
    clock_box = page.locator("#clock").bounding_box()
    assert clock_box is not None
    assert_screenshot(
        page,
        "embed-second-hand-detail.png",
        update=update_snapshots,
        clip={
            "x": clock_box["x"] + clock_box["width"] * 0.49,
            "y": clock_box["y"] + clock_box["height"] * 0.08,
            "width": clock_box["width"] * 0.02,
            "height": clock_box["height"] * 0.52,
        },
    )


@pytest.mark.visual
def test_embed_mode_visual_snapshot_seconds_hide(page: Page, app_url: str, update_snapshots: bool) -> None:
    open_page(page, app_url, {"embed": "true", "theme": "dark", "seconds": "hide"})
    assert page.locator("#secondHand").evaluate(
        "element => getComputedStyle(element).display"
    ) == "none"
    assert_screenshot(page, "embed-seconds-hide.png", update=update_snapshots)


@pytest.mark.visual
def test_embed_mode_visual_snapshot_all_params(page: Page, app_url: str, update_snapshots: bool) -> None:
    open_page(page, app_url, {
        "embed": "true",
        "tz": "America/New_York",
        "theme": "light",
        "seconds": "hide",
        "border": "hide",
        "numbers": "hide",
        "shadows": "false",
        "daynight": "show",
    })
    assert page.locator("#secondHand").evaluate(
        "element => getComputedStyle(element).display"
    ) == "none"
    assert icon_displays(page) == {"sun": "inline", "moon": "none"}
    assert_screenshot(page, "embed-all-params.png", update=update_snapshots)
