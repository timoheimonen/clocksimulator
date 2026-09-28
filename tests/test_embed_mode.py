from __future__ import annotations

import pytest
from playwright.sync_api import Page

from tests.helpers import install_test_clock, install_timer_probe, open_page, set_test_time


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


def install_shadow_mutation_probe(page: Page) -> None:
    page.evaluate(
        """() => {
            window.__shadowMutations = [];
            const observer = new MutationObserver(records => {
                records.forEach(record => window.__shadowMutations.push(record.target.id));
            });
            ['hourDS', 'minuteDS', 'secondDS', 'dotDS'].forEach(id => {
                observer.observe(document.getElementById(id), { attributes: true });
            });
        }"""
    )


def mutated_shadows(page: Page) -> list[str]:
    return page.evaluate(
        "() => Array.from(new Set(window.__shadowMutations.splice(0))).sort()"
    )


def test_second_angle_is_scoped_to_second_hand(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"seconds": "smooth"}, fixed_time="2026-01-01T12:00:07.500Z")
    state = page.evaluate(
        """() => ({
            root: document.documentElement.style.getPropertyValue('--second-angle'),
            hand: document.getElementById('secondHand').style.getPropertyValue('--second-angle'),
            transform: getComputedStyle(document.getElementById('secondHand')).transform
        })"""
    )
    assert state["root"] == ""
    assert state["hand"] == "45deg"
    assert state["transform"] != "none"


def test_hand_shadows_are_rewritten_only_when_their_angle_changes(
    page: Page, app_url: str
) -> None:
    open_page(page, app_url, fixed_time="2026-01-01T12:00:00.000Z")
    assert page.evaluate(
        "() => ['hourDS', 'minuteDS', 'secondDS', 'dotDS'].every(id => document.getElementById(id).getAttribute('dx') !== '0')"
    ) is True
    install_shadow_mutation_probe(page)

    set_test_time(page, "2026-01-01T12:00:00.500Z")
    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => resolve()))")
    assert mutated_shadows(page) == []

    set_test_time(page, "2026-01-01T12:00:01.000Z")
    page.wait_for_function("() => window.__shadowMutations.length > 0")
    assert mutated_shadows(page) == ["minuteDS", "secondDS"]


def install_animation_frame_counter(page: Page, fixed_time: str) -> None:
    install_test_clock(page, fixed_time)
    page.add_init_script("""
        window.__animationFrameRequests = 0;
        const originalRequestAnimationFrame = window.requestAnimationFrame.bind(window);
        window.requestAnimationFrame = function (callback) {
            window.__animationFrameRequests += 1;
            return originalRequestAnimationFrame(callback);
        };
    """)


def animation_frame_requests_during(page: Page, milliseconds: int) -> int:
    before = page.evaluate("() => window.__animationFrameRequests")
    page.wait_for_timeout(milliseconds)
    return page.evaluate("() => window.__animationFrameRequests") - before


def pending_timeout_delays(clock) -> list[float]:
    return [
        timer.delay for timer in clock.timers()
        if timer.kind == "timeout" and timer.calls == 0 and not timer.cleared
    ]


@pytest.mark.parametrize(
    ("params", "fixed_time", "expected_delay"),
    [
        pytest.param({}, "2026-01-01T12:00:00.500Z", 500, id="tick-after-bounce"),
        pytest.param({"seconds": "hide"}, "2026-01-01T12:00:00.000Z", 1000, id="seconds-hidden"),
        pytest.param({"tz": "UTC,Europe/Helsinki"}, "2026-01-01T12:00:00.000Z", 1000, id="dashboard-tick"),
    ],
)
def test_clock_waits_for_next_second_when_nothing_moves_between_seconds(
    page: Page, app_url: str, params: dict[str, str], fixed_time: str, expected_delay: int
) -> None:
    clock = install_timer_probe(page, fixed_time)
    install_animation_frame_counter(page, fixed_time)
    open_page(page, app_url, params, fixed_time=fixed_time)
    assert animation_frame_requests_during(page, 300) <= 1
    assert expected_delay in pending_timeout_delays(clock)


def test_clock_updates_every_frame_in_smooth_mode_and_tick_bounce(page: Page, app_url: str) -> None:
    install_animation_frame_counter(page, "2026-01-01T12:00:00.500Z")
    open_page(page, app_url, {"seconds": "smooth"}, fixed_time="2026-01-01T12:00:00.500Z")
    assert animation_frame_requests_during(page, 300) > 5

    open_page(page, app_url, fixed_time="2026-01-01T12:00:00.050Z")
    assert animation_frame_requests_during(page, 300) > 5


def test_switching_to_smooth_mode_cancels_wait_for_next_second(page: Page, app_url: str) -> None:
    clock = install_timer_probe(page, "2026-01-01T12:00:00.500Z")
    open_page(page, app_url, fixed_time="2026-01-01T12:00:00.500Z")
    assert 500 in pending_timeout_delays(clock)
    page.evaluate(
        """() => {
            const toggle = document.getElementById('secondModeToggle');
            toggle.checked = false;
            toggle.dispatchEvent(new Event('change'));
        }"""
    )
    assert 500 not in pending_timeout_delays(clock)
    page.wait_for_function(
        "() => document.getElementById('secondHand').style.getPropertyValue('--second-angle') === '3deg'"
    )
