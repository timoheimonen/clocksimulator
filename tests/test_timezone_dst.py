from __future__ import annotations

import pytest
from playwright.sync_api import Page

from tests.helpers import open_page


SPRING_DST_TIME = "2026-03-29T01:30:00Z"
FALL_DST_TIME = "2026-10-25T01:30:00Z"
MIDNIGHT_OFFSET_TIME = "2026-03-28T18:30:00Z"
DST_TIMES = [
    pytest.param(SPRING_DST_TIME, id="spring"),
    pytest.param(FALL_DST_TIME, id="fall"),
]


def wait_for_single_analog(page: Page) -> None:
    page.wait_for_function("""() => {
        const hour = document.getElementById('hourHand');
        const minute = document.getElementById('minuteHand');
        return hour && minute && hour.style.transform !== '' && minute.style.transform !== '';
    }""")


def single_analog_state(page: Page) -> dict[str, str]:
    wait_for_single_analog(page)
    return page.evaluate("""() => ({
        hour: document.getElementById('hourHand').style.transform,
        minute: document.getElementById('minuteHand').style.transform,
        label: document.getElementById('clock').getAttribute('aria-label')
    })""")


def dashboard_analog_state(page: Page) -> dict[str, dict[str, str]]:
    page.wait_for_function("""() => {
        const hands = Array.from(document.querySelectorAll('.clock-grid .hour-hand'));
        return hands.length > 0 && hands.every(hand => hand.style.transform !== '');
    }""")
    return page.evaluate("""() => Object.fromEntries(
        Array.from(document.querySelectorAll('.clock-grid .clock-cell')).map(cell => [
            cell.querySelector('.clock-label').textContent,
            {
                hour: cell.querySelector('.hour-hand').style.transform,
                minute: cell.querySelector('.minute-hand').style.transform,
                label: cell.querySelector('svg').getAttribute('aria-label')
            }
        ])
    )""")


def digital_dashboard_times(page: Page) -> list[str]:
    page.wait_for_function("""() => {
        const times = Array.from(document.querySelectorAll('.digital-grid .digital-time'));
        return times.length > 0 && times.every(time => time.textContent !== '');
    }""")
    return page.evaluate(
        "() => Array.from(document.querySelectorAll('.digital-grid .digital-time')).map(time => time.textContent)"
    )


@pytest.mark.parametrize("fixed_time", DST_TIMES)
def test_analog_single_timezone_across_helsinki_dst(
    helsinki_page: Page, app_url: str, fixed_time: str
) -> None:
    open_page(
        helsinki_page,
        app_url,
        {"tz": "America/New_York"},
        fixed_time=fixed_time,
    )
    assert single_analog_state(helsinki_page) == {
        "hour": "rotate(285deg)",
        "minute": "rotate(180deg)",
        "label": "The time is 21:30",
    }


@pytest.mark.parametrize("fixed_time", DST_TIMES)
def test_analog_dashboard_across_helsinki_dst(
    helsinki_page: Page, app_url: str, fixed_time: str
) -> None:
    open_page(
        helsinki_page,
        app_url,
        {"tz": "UTC,America/New_York"},
        fixed_time=fixed_time,
    )
    assert dashboard_analog_state(helsinki_page) == {
        "UTC": {
            "hour": "rotate(45deg)",
            "minute": "rotate(180deg)",
            "label": "UTC: 01:30",
        },
        "New York": {
            "hour": "rotate(285deg)",
            "minute": "rotate(180deg)",
            "label": "New York: 21:30",
        },
    }


@pytest.mark.parametrize("fixed_time", DST_TIMES)
def test_digital_single_timezone_across_helsinki_dst(
    helsinki_page: Page, app_url: str, fixed_time: str
) -> None:
    open_page(
        helsinki_page,
        app_url,
        {"tz": "America/New_York"},
        path="/digital/",
        fixed_time=fixed_time,
    )
    helsinki_page.wait_for_function(
        "() => document.getElementById('digitalTime').textContent === '21:30:00'"
    )
    assert helsinki_page.evaluate(
        "() => document.getElementById('digitalTime').getAttribute('datetime')"
    ) == "21:30:00"


@pytest.mark.parametrize("fixed_time", DST_TIMES)
def test_digital_dashboard_across_helsinki_dst(
    helsinki_page: Page, app_url: str, fixed_time: str
) -> None:
    open_page(
        helsinki_page,
        app_url,
        {"tz": "UTC,America/New_York"},
        path="/digital/",
        fixed_time=fixed_time,
    )
    assert digital_dashboard_times(helsinki_page) == ["01:30:00", "21:30:00"]


def test_analog_fractional_timezone_offsets(helsinki_page: Page, app_url: str) -> None:
    open_page(
        helsinki_page,
        app_url,
        {"tz": "Asia/Kolkata,Asia/Kathmandu"},
        fixed_time=MIDNIGHT_OFFSET_TIME,
    )
    assert dashboard_analog_state(helsinki_page) == {
        "Kolkata": {
            "hour": "rotate(0deg)",
            "minute": "rotate(0deg)",
            "label": "Kolkata: 00:00",
        },
        "Kathmandu": {
            "hour": "rotate(7.5deg)",
            "minute": "rotate(90deg)",
            "label": "Kathmandu: 00:15",
        },
    }


def test_digital_fractional_timezone_offsets(helsinki_page: Page, app_url: str) -> None:
    open_page(
        helsinki_page,
        app_url,
        {"tz": "Asia/Kolkata,Asia/Kathmandu"},
        path="/digital/",
        fixed_time=MIDNIGHT_OFFSET_TIME,
    )
    assert digital_dashboard_times(helsinki_page) == ["00:00:00", "00:15:00"]


@pytest.mark.parametrize(
    ("fixed_time", "hour", "label"),
    [
        pytest.param(SPRING_DST_TIME, "rotate(135deg)", "The time is 04:30", id="spring"),
        pytest.param(FALL_DST_TIME, "rotate(105deg)", "The time is 03:30", id="fall"),
    ],
)
def test_analog_local_time_still_uses_browser_timezone(
    helsinki_page: Page,
    app_url: str,
    fixed_time: str,
    hour: str,
    label: str,
) -> None:
    open_page(helsinki_page, app_url, fixed_time=fixed_time)
    assert single_analog_state(helsinki_page) == {
        "hour": hour,
        "minute": "rotate(180deg)",
        "label": label,
    }


@pytest.mark.parametrize(
    ("fixed_time", "expected"),
    [
        pytest.param(SPRING_DST_TIME, "04:30:00", id="spring"),
        pytest.param(FALL_DST_TIME, "03:30:00", id="fall"),
    ],
)
def test_digital_local_time_still_uses_browser_timezone(
    helsinki_page: Page, app_url: str, fixed_time: str, expected: str
) -> None:
    open_page(
        helsinki_page,
        app_url,
        path="/digital/",
        fixed_time=fixed_time,
    )
    helsinki_page.wait_for_function(
        "expected => document.getElementById('digitalTime').textContent === expected",
        arg=expected,
    )
    assert helsinki_page.evaluate(
        "() => document.getElementById('digitalTime').getAttribute('datetime')"
    ) == expected


def test_timezone_offset_ignores_epoch_milliseconds(helsinki_page: Page, app_url: str) -> None:
    open_page(
        helsinki_page,
        app_url,
        {"tz": "America/New_York"},
        path="/digital/",
        fixed_time="2026-03-29T01:30:00.900Z",
    )
    helsinki_page.wait_for_function(
        "() => document.getElementById('digitalTime').textContent === '21:30:00'"
    )
    assert helsinki_page.evaluate(
        "() => document.getElementById('digitalTime').getAttribute('datetime')"
    ) == "21:30:00"
    helsinki_page.evaluate("""() => {
        window.__setMockDate('2026-03-29T01:30:01.100Z');
        document.dispatchEvent(new Event('visibilitychange'));
    }""")
    helsinki_page.wait_for_function(
        "() => document.getElementById('digitalTime').textContent === '21:30:01'"
    )
    assert helsinki_page.evaluate(
        "() => document.getElementById('digitalTime').getAttribute('datetime')"
    ) == "21:30:01"


@pytest.mark.parametrize(
    ("seconds_mode", "expected_angle"),
    [
        pytest.param("smooth", 5.4, id="smooth"),
        pytest.param("tick", 0.0, id="tick"),
    ],
)
def test_analog_timezone_preserves_second_hand_mode_and_milliseconds(
    helsinki_page: Page,
    app_url: str,
    seconds_mode: str,
    expected_angle: float,
) -> None:
    open_page(
        helsinki_page,
        app_url,
        {"tz": "America/New_York", "seconds": seconds_mode},
        fixed_time="2026-03-29T01:30:00.900Z",
    )
    state = single_analog_state(helsinki_page)
    initial_angle = helsinki_page.evaluate(
        "() => parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--second-angle'))"
    )
    assert state["minute"] == "rotate(180deg)"
    assert initial_angle == pytest.approx(expected_angle)
    helsinki_page.evaluate(
        "() => window.__setMockDate('2026-03-29T01:30:01.100Z')"
    )
    helsinki_page.wait_for_function(
        "() => document.getElementById('minuteHand').style.transform === 'rotate(180.1deg)'"
    )
    advanced_angle = helsinki_page.evaluate(
        "() => parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--second-angle'))"
    )
    expected_advanced_angle = 6.6 if seconds_mode == "smooth" else 6.0
    assert advanced_angle == pytest.approx(expected_advanced_angle)


def test_timezone_formatter_is_not_called_per_animation_frame(
    helsinki_page: Page, app_url: str
) -> None:
    helsinki_page.add_init_script("""
        window.__formatToPartsCalls = 0;
        var originalFormatToParts = Intl.DateTimeFormat.prototype.formatToParts;
        Intl.DateTimeFormat.prototype.formatToParts = function() {
            window.__formatToPartsCalls += 1;
            return originalFormatToParts.apply(this, arguments);
        };
    """)
    open_page(
        helsinki_page,
        app_url,
        {"tz": "America/New_York"},
        fixed_time=SPRING_DST_TIME,
    )
    wait_for_single_analog(helsinki_page)
    initial_calls = helsinki_page.evaluate("() => window.__formatToPartsCalls")
    helsinki_page.evaluate("""() => new Promise(resolve => {
        var frames = 0;
        function nextFrame() {
            frames += 1;
            if (frames === 12) {
                resolve();
                return;
            }
            requestAnimationFrame(nextFrame);
        }
        requestAnimationFrame(nextFrame);
    })""")
    assert initial_calls >= 1
    assert helsinki_page.evaluate("() => window.__formatToPartsCalls") == initial_calls
