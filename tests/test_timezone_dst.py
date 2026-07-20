from __future__ import annotations

import pytest
from playwright.sync_api import Page

from tests.helpers import open_page, set_test_time


SPRING_DST_TIME = "2026-03-29T01:30:00Z"
FALL_DST_TIME = "2026-10-25T01:30:00Z"
MIDNIGHT_OFFSET_TIME = "2026-03-28T18:30:00Z"
DST_TIMES = [
    pytest.param(SPRING_DST_TIME, id="spring"),
    pytest.param(FALL_DST_TIME, id="fall"),
]


def install_hour_cycle_fallback(page: Page) -> None:
    page.add_init_script("""
        (function() {
            const OriginalDateTimeFormat = Intl.DateTimeFormat;
            const fallbackFormatters = new WeakSet();
            const originalFormatToParts = OriginalDateTimeFormat.prototype.formatToParts;
            window.__hourCycleFallback = {
                optionsRemoved: 0,
                formatToPartsCalls: 0,
                dayPeriodParts: 0
            };

            function prepareArguments(args) {
                const copiedArgs = Array.from(args);
                const options = copiedArgs[1];
                let removed = false;
                if (options && Object.prototype.hasOwnProperty.call(options, 'hourCycle')) {
                    const copiedOptions = Object.assign({}, options);
                    delete copiedOptions.hourCycle;
                    copiedArgs[1] = copiedOptions;
                    window.__hourCycleFallback.optionsRemoved += 1;
                    removed = true;
                }
                return { args: copiedArgs, removed: removed };
            }

            function trackFormatter(formatter, removed) {
                if (removed) fallbackFormatters.add(formatter);
                return formatter;
            }

            OriginalDateTimeFormat.prototype.formatToParts = function() {
                const parts = originalFormatToParts.apply(this, arguments);
                if (fallbackFormatters.has(this)) {
                    window.__hourCycleFallback.formatToPartsCalls += 1;
                    window.__hourCycleFallback.dayPeriodParts += parts.filter(function(part) {
                        return part.type === 'dayPeriod';
                    }).length;
                }
                return parts;
            };

            Intl.DateTimeFormat = new Proxy(OriginalDateTimeFormat, {
                apply: function(target, thisArg, args) {
                    const prepared = prepareArguments(args);
                    const formatter = Reflect.apply(target, thisArg, prepared.args);
                    return trackFormatter(formatter, prepared.removed);
                },
                construct: function(target, args, newTarget) {
                    const prepared = prepareArguments(args);
                    const formatter = Reflect.construct(target, prepared.args, newTarget);
                    return trackFormatter(formatter, prepared.removed);
                }
            });
        })();
    """)


def hour_cycle_fallback_state(page: Page) -> dict[str, int]:
    return page.evaluate("() => ({ ...window.__hourCycleFallback })")


def assert_hour_cycle_fallback_used(page: Page) -> None:
    state = hour_cycle_fallback_state(page)
    assert state["optionsRemoved"] >= 1
    assert state["formatToPartsCalls"] >= 1
    assert state["dayPeriodParts"] >= 1


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


def digital_dashboard_state(page: Page) -> list[dict[str, str]]:
    digital_dashboard_times(page)
    return page.evaluate("""() => Array.from(
        document.querySelectorAll('.digital-grid .digital-cell')
    ).map(cell => ({
        text: cell.querySelector('.digital-time').textContent,
        datetime: cell.querySelector('.digital-time').getAttribute('datetime'),
        label: cell.getAttribute('aria-label')
    }))""")


def single_digital_state(page: Page) -> dict[str, str]:
    page.wait_for_function(
        "() => document.getElementById('digitalTime').textContent !== ''"
    )
    return page.evaluate("""() => ({
        text: document.getElementById('digitalTime').textContent,
        datetime: document.getElementById('digitalTime').getAttribute('datetime'),
        label: document.getElementById('digitalContainer').getAttribute('aria-label')
    })""")


def update_after_time_change(page: Page, path: str, fixed_time: str) -> None:
    page.clock.set_fixed_time(fixed_time)
    if path:
        page.evaluate("() => document.dispatchEvent(new Event('visibilitychange'))")
    else:
        page.clock.run_for(20)


def analog_daynight_state(page: Page, dashboard: bool) -> list[dict[str, object]]:
    selector = ".clock-grid .clock-cell" if dashboard else ".clock-container"
    return page.evaluate(
        """selector => Array.from(document.querySelectorAll(selector)).map(function (container) {
            const svg = container.querySelector('svg');
            const sun = container.querySelector('.sun-icon');
            const moon = container.querySelector('.moon-icon');
            return {
                label: svg.getAttribute('aria-label'),
                sunVisible: getComputedStyle(sun).display !== 'none',
                moonVisible: getComputedStyle(moon).display !== 'none',
                sunAriaHidden: sun.getAttribute('aria-hidden'),
                moonAriaHidden: moon.getAttribute('aria-hidden')
            };
        })""",
        selector,
    )


def digital_daynight_state(page: Page, dashboard: bool) -> list[dict[str, object]]:
    selector = ".digital-grid .digital-cell" if dashboard else ".digital-container"
    return page.evaluate(
        """selector => Array.from(document.querySelectorAll(selector)).map(function (container) {
            const icon = container.querySelector('.daynight-mark');
            const time = container.querySelector('time');
            return {
                label: container.getAttribute('aria-label'),
                time: time.textContent,
                state: icon.getAttribute('data-state'),
                visible: getComputedStyle(icon).display !== 'none' &&
                    icon.classList.contains('visible'),
                ariaHidden: icon.getAttribute('aria-hidden'),
                sunVisible: getComputedStyle(icon.querySelector('.daynight-sun')).display !== 'none',
                moonVisible: getComputedStyle(icon.querySelector('.daynight-moon')).display !== 'none'
            };
        })""",
        selector,
    )


def test_hour_cycle_fallback_analog_single_timezone(
    helsinki_page: Page, app_url: str
) -> None:
    install_hour_cycle_fallback(helsinki_page)
    open_page(
        helsinki_page,
        app_url,
        {"tz": "America/New_York"},
        fixed_time=SPRING_DST_TIME,
    )
    assert single_analog_state(helsinki_page) == {
        "hour": "rotate(285deg)",
        "minute": "rotate(180deg)",
        "label": "The time is 21:30",
    }
    assert_hour_cycle_fallback_used(helsinki_page)


def test_hour_cycle_fallback_digital_single_timezone(
    helsinki_page: Page, app_url: str
) -> None:
    install_hour_cycle_fallback(helsinki_page)
    open_page(
        helsinki_page,
        app_url,
        {"tz": "America/New_York"},
        path="/digital/",
        fixed_time=SPRING_DST_TIME,
    )
    helsinki_page.wait_for_function(
        "() => document.getElementById('digitalTime').textContent !== ''"
    )
    assert helsinki_page.evaluate(
        """() => ({
            text: document.getElementById('digitalTime').textContent,
            datetime: document.getElementById('digitalTime').getAttribute('datetime'),
            label: document.querySelector('.digital-container').getAttribute('aria-label')
        })"""
    ) == {
        "text": "21:30:00",
        "datetime": "21:30:00",
        "label": "The time is 21:30:00",
    }
    assert_hour_cycle_fallback_used(helsinki_page)


def test_hour_cycle_fallback_analog_dashboard(
    helsinki_page: Page, app_url: str
) -> None:
    install_hour_cycle_fallback(helsinki_page)
    open_page(
        helsinki_page,
        app_url,
        {"tz": "UTC,America/New_York"},
        fixed_time=SPRING_DST_TIME,
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
    assert_hour_cycle_fallback_used(helsinki_page)


def test_hour_cycle_fallback_digital_dashboard(
    helsinki_page: Page, app_url: str
) -> None:
    install_hour_cycle_fallback(helsinki_page)
    open_page(
        helsinki_page,
        app_url,
        {"tz": "UTC,America/New_York"},
        path="/digital/",
        fixed_time=SPRING_DST_TIME,
    )
    assert digital_dashboard_state(helsinki_page) == [
        {
            "text": "01:30:00",
            "datetime": "01:30:00",
            "label": "UTC: 01:30:00",
        },
        {
            "text": "21:30:00",
            "datetime": "21:30:00",
            "label": "New York: 21:30:00",
        },
    ]
    assert_hour_cycle_fallback_used(helsinki_page)


@pytest.mark.parametrize(
    ("fixed_time", "expected_time", "expected_hour"),
    [
        pytest.param("2026-01-01T00:30:00Z", "00:30", "rotate(15deg)", id="midnight"),
        pytest.param("2026-01-01T12:30:00Z", "12:30", "rotate(15deg)", id="noon"),
        pytest.param("2026-01-01T23:30:00Z", "23:30", "rotate(345deg)", id="late-pm"),
    ],
)
@pytest.mark.parametrize(
    "path",
    [pytest.param("", id="analog"), pytest.param("/digital/", id="digital")],
)
def test_hour_cycle_fallback_single_time_boundaries(
    helsinki_page: Page,
    app_url: str,
    fixed_time: str,
    expected_time: str,
    expected_hour: str,
    path: str,
) -> None:
    install_hour_cycle_fallback(helsinki_page)
    open_page(
        helsinki_page,
        app_url,
        {"tz": "UTC"},
        path=path,
        fixed_time=fixed_time,
    )
    if path:
        expected = expected_time + ":00"
        helsinki_page.wait_for_function(
            "expected => document.getElementById('digitalTime').textContent === expected",
            arg=expected,
        )
        assert helsinki_page.evaluate(
            "() => document.getElementById('digitalTime').getAttribute('datetime')"
        ) == expected
    else:
        assert single_analog_state(helsinki_page) == {
            "hour": expected_hour,
            "minute": "rotate(180deg)",
            "label": "The time is " + expected_time,
        }
    assert_hour_cycle_fallback_used(helsinki_page)


@pytest.mark.parametrize(
    "path",
    [pytest.param("", id="analog"), pytest.param("/digital/", id="digital")],
)
def test_hour_cycle_fallback_fractional_timezone_offsets(
    helsinki_page: Page, app_url: str, path: str
) -> None:
    install_hour_cycle_fallback(helsinki_page)
    open_page(
        helsinki_page,
        app_url,
        {"tz": "Asia/Kolkata,Asia/Kathmandu"},
        path=path,
        fixed_time=MIDNIGHT_OFFSET_TIME,
    )
    if path:
        assert digital_dashboard_times(helsinki_page) == ["00:00:00", "00:15:00"]
    else:
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
    assert_hour_cycle_fallback_used(helsinki_page)


def test_hour_cycle_fallback_digital_twelve_hour_display(
    helsinki_page: Page, app_url: str
) -> None:
    install_hour_cycle_fallback(helsinki_page)
    open_page(
        helsinki_page,
        app_url,
        {"tz": "America/New_York", "format": "12", "seconds": "show"},
        path="/digital/",
        fixed_time=SPRING_DST_TIME,
    )
    helsinki_page.wait_for_function(
        "() => document.getElementById('digitalTime').textContent !== ''"
    )
    assert helsinki_page.evaluate(
        """() => ({
            text: document.getElementById('digitalTime').textContent,
            datetime: document.getElementById('digitalTime').getAttribute('datetime')
        })"""
    ) == {"text": "09:30:00 PM", "datetime": "21:30:00"}
    assert_hour_cycle_fallback_used(helsinki_page)


@pytest.mark.parametrize(
    "path",
    [pytest.param("", id="analog"), pytest.param("/digital/", id="digital")],
)
def test_hour_cycle_fallback_does_not_change_local_time(
    helsinki_page: Page, app_url: str, path: str
) -> None:
    install_hour_cycle_fallback(helsinki_page)
    open_page(
        helsinki_page,
        app_url,
        path=path,
        fixed_time=SPRING_DST_TIME,
    )
    if path:
        helsinki_page.wait_for_function(
            "() => document.getElementById('digitalTime').textContent === '04:30:00'"
        )
        assert helsinki_page.evaluate(
            "() => document.getElementById('digitalTime').getAttribute('datetime')"
        ) == "04:30:00"
    else:
        assert single_analog_state(helsinki_page) == {
            "hour": "rotate(135deg)",
            "minute": "rotate(180deg)",
            "label": "The time is 04:30",
        }
    assert hour_cycle_fallback_state(helsinki_page) == {
        "optionsRemoved": 0,
        "formatToPartsCalls": 0,
        "dayPeriodParts": 0,
    }


def test_hour_cycle_fallback_formatter_is_not_called_per_animation_frame(
    helsinki_page: Page, app_url: str
) -> None:
    install_hour_cycle_fallback(helsinki_page)
    open_page(
        helsinki_page,
        app_url,
        {"tz": "America/New_York"},
        fixed_time=SPRING_DST_TIME,
    )
    wait_for_single_analog(helsinki_page)
    assert_hour_cycle_fallback_used(helsinki_page)
    initial_calls = hour_cycle_fallback_state(helsinki_page)["formatToPartsCalls"]
    helsinki_page.evaluate("""() => new Promise(resolve => {
        let frames = 0;
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
    assert (
        hour_cycle_fallback_state(helsinki_page)["formatToPartsCalls"]
        == initial_calls
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
    set_test_time(
        helsinki_page,
        "2026-03-29T01:30:01.100Z",
        advance_milliseconds=0,
    )
    helsinki_page.evaluate(
        "() => document.dispatchEvent(new Event('visibilitychange'))"
    )
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
    set_test_time(helsinki_page, "2026-03-29T01:30:01.100Z")
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


NEW_YORK_DST_TRANSITIONS = [
    pytest.param(
        "2026-03-08T06:59:00Z",
        "2026-03-08T07:00:01Z",
        {
            "initialNy": ("01:59:00", "rotate(59.5deg)", "rotate(354deg)"),
            "finalNy": ("03:00:01", "rotate(90deg)", "rotate(0.1deg)"),
            "initialUtc": ("06:59:00", "rotate(209.5deg)", "rotate(354deg)"),
            "finalUtc": ("07:00:01", "rotate(210deg)", "rotate(0.1deg)"),
        },
        id="spring-forward",
    ),
    pytest.param(
        "2026-11-01T05:59:00Z",
        "2026-11-01T06:00:01Z",
        {
            "initialNy": ("01:59:00", "rotate(59.5deg)", "rotate(354deg)"),
            "finalNy": ("01:00:01", "rotate(30deg)", "rotate(0.1deg)"),
            "initialUtc": ("05:59:00", "rotate(179.5deg)", "rotate(354deg)"),
            "finalUtc": ("06:00:01", "rotate(180deg)", "rotate(0.1deg)"),
        },
        id="fall-back",
    ),
]


@pytest.mark.cross_browser
@pytest.mark.parametrize(
    ("path", "dashboard"),
    [
        pytest.param("", False, id="analog-single"),
        pytest.param("", True, id="analog-dashboard"),
        pytest.param("/digital/", False, id="digital-single"),
        pytest.param("/digital/", True, id="digital-dashboard"),
    ],
)
@pytest.mark.parametrize(("initial_time", "final_time", "expected"), NEW_YORK_DST_TRANSITIONS)
def test_target_timezone_dst_changes_without_reload(
    page: Page,
    app_url: str,
    path: str,
    dashboard: bool,
    initial_time: str,
    final_time: str,
    expected: dict[str, tuple[str, str, str]],
) -> None:
    params = {"tz": "UTC,America/New_York"} if dashboard else {"tz": "America/New_York"}
    open_page(page, app_url, params, path=path, fixed_time=initial_time)
    initial_url = page.url

    if path:
        if dashboard:
            initial = digital_dashboard_state(page)
            assert initial == [
                {
                    "text": expected["initialUtc"][0],
                    "datetime": expected["initialUtc"][0],
                    "label": "UTC: " + expected["initialUtc"][0],
                },
                {
                    "text": expected["initialNy"][0],
                    "datetime": expected["initialNy"][0],
                    "label": "New York: " + expected["initialNy"][0],
                },
            ]
            assert page.title() == "clocksimulator.com - Digital Dashboard"
        else:
            assert single_digital_state(page) == {
                "text": expected["initialNy"][0],
                "datetime": expected["initialNy"][0],
                "label": "The time is " + expected["initialNy"][0],
            }
            assert page.title() == "clocksimulator.com - Digital - America/New_York"
    elif dashboard:
        initial = dashboard_analog_state(page)
        assert initial == {
            "UTC": {
                "hour": expected["initialUtc"][1],
                "minute": expected["initialUtc"][2],
                "label": "UTC: " + expected["initialUtc"][0][:5],
            },
            "New York": {
                "hour": expected["initialNy"][1],
                "minute": expected["initialNy"][2],
                "label": "New York: " + expected["initialNy"][0][:5],
            },
        }
        assert page.title() == "clocksimulator.com - Dashboard"
    else:
        assert single_analog_state(page) == {
            "hour": expected["initialNy"][1],
            "minute": expected["initialNy"][2],
            "label": "The time is " + expected["initialNy"][0][:5],
        }
        assert page.title() == "clocksimulator.com - America/New_York"

    update_after_time_change(page, path, final_time)
    assert page.url == initial_url

    if path:
        if dashboard:
            assert digital_dashboard_state(page) == [
                {
                    "text": expected["finalUtc"][0],
                    "datetime": expected["finalUtc"][0],
                    "label": "UTC: " + expected["finalUtc"][0],
                },
                {
                    "text": expected["finalNy"][0],
                    "datetime": expected["finalNy"][0],
                    "label": "New York: " + expected["finalNy"][0],
                },
            ]
        else:
            assert single_digital_state(page) == {
                "text": expected["finalNy"][0],
                "datetime": expected["finalNy"][0],
                "label": "The time is " + expected["finalNy"][0],
            }
    elif dashboard:
        assert dashboard_analog_state(page) == {
            "UTC": {
                "hour": expected["finalUtc"][1],
                "minute": expected["finalUtc"][2],
                "label": "UTC: " + expected["finalUtc"][0][:5],
            },
            "New York": {
                "hour": expected["finalNy"][1],
                "minute": expected["finalNy"][2],
                "label": "New York: " + expected["finalNy"][0][:5],
            },
        }
    else:
        assert single_analog_state(page) == {
            "hour": expected["finalNy"][1],
            "minute": expected["finalNy"][2],
            "label": "The time is " + expected["finalNy"][0][:5],
        }


@pytest.mark.chromium_only
@pytest.mark.parametrize(
    ("path", "dashboard", "expected_sources"),
    [
        pytest.param("", False, 1, id="analog-single"),
        pytest.param("", True, 2, id="analog-dashboard"),
        pytest.param("/digital/", False, 1, id="digital-single"),
        pytest.param("/digital/", True, 2, id="digital-dashboard"),
    ],
)
def test_timezone_offset_recalculated_at_60000ms_sla(
    page: Page,
    app_url: str,
    path: str,
    dashboard: bool,
    expected_sources: int,
) -> None:
    page.add_init_script("""
        window.__offsetFormatToPartsCalls = 0;
        const originalFormatToParts = Intl.DateTimeFormat.prototype.formatToParts;
        Intl.DateTimeFormat.prototype.formatToParts = function () {
            window.__offsetFormatToPartsCalls += 1;
            return originalFormatToParts.apply(this, arguments);
        };
    """)
    params = {"tz": "UTC,America/New_York"} if dashboard else {"tz": "America/New_York"}
    open_page(
        page,
        app_url,
        params,
        path=path,
        fixed_time="2026-02-01T12:00:00Z",
    )
    initial_calls = page.evaluate("() => window.__offsetFormatToPartsCalls")
    assert initial_calls >= expected_sources
    update_after_time_change(page, path, "2026-02-01T12:01:00Z")
    assert page.evaluate("() => window.__offsetFormatToPartsCalls") == (
        initial_calls + expected_sources
    )


@pytest.mark.cross_browser
def test_analog_single_negative_half_hour_offset(page: Page, app_url: str) -> None:
    open_page(
        page,
        app_url,
        {"tz": "America/St_Johns"},
        fixed_time="2026-01-01T12:00:00Z",
    )
    assert single_analog_state(page) == {
        "hour": "rotate(255deg)",
        "minute": "rotate(180deg)",
        "label": "The time is 08:30",
    }
    assert page.title() == "clocksimulator.com - America/St_Johns"


@pytest.mark.cross_browser
def test_digital_dashboard_dateline_and_fractional_offset_matrix(
    page: Page, app_url: str
) -> None:
    open_page(
        page,
        app_url,
        {"tz": "Pacific/Kiritimati,Pacific/Pago_Pago,Australia/Lord_Howe"},
        path="/digital/",
        fixed_time="2026-01-01T12:00:00Z",
    )
    assert digital_dashboard_state(page) == [
        {"text": "02:00:00", "datetime": "02:00:00", "label": "Kiritimati: 02:00:00"},
        {"text": "01:00:00", "datetime": "01:00:00", "label": "Pago Pago: 01:00:00"},
        {"text": "23:00:00", "datetime": "23:00:00", "label": "Lord Howe: 23:00:00"},
    ]


@pytest.mark.cross_browser
def test_lord_howe_thirty_minute_dst_change_without_reload(
    page: Page, app_url: str
) -> None:
    open_page(
        page,
        app_url,
        {"tz": "Australia/Lord_Howe"},
        path="/digital/",
        fixed_time="2026-04-04T14:59:00Z",
    )
    assert single_digital_state(page) == {
        "text": "01:59:00",
        "datetime": "01:59:00",
        "label": "The time is 01:59:00",
    }
    update_after_time_change(page, "/digital/", "2026-04-04T15:00:01Z")
    assert single_digital_state(page) == {
        "text": "01:30:01",
        "datetime": "01:30:01",
        "label": "The time is 01:30:01",
    }


DAYNIGHT_BOUNDARIES = [
    pytest.param(
        "2026-01-01T05:59:00Z",
        "night",
        "Asia/Tokyo",
        "14:59",
        "day",
        id="0559-night",
    ),
    pytest.param(
        "2026-01-01T06:00:00Z",
        "day",
        "Pacific/Honolulu",
        "20:00",
        "night",
        id="0600-day",
    ),
    pytest.param(
        "2026-01-01T17:59:00Z",
        "day",
        "Asia/Tokyo",
        "02:59",
        "night",
        id="1759-day",
    ),
    pytest.param(
        "2026-01-01T18:00:00Z",
        "night",
        "Pacific/Honolulu",
        "08:00",
        "day",
        id="1800-night",
    ),
]


def assert_icon_pair(entry: dict[str, object], expected_state: str) -> None:
    assert entry["sunVisible"] is (expected_state == "day")
    assert entry["moonVisible"] is (expected_state == "night")
    assert int(bool(entry["sunVisible"])) + int(bool(entry["moonVisible"])) == 1


@pytest.mark.cross_browser
@pytest.mark.parametrize(
    ("path", "dashboard"),
    [
        pytest.param("", False, id="analog-single"),
        pytest.param("", True, id="analog-dashboard"),
        pytest.param("/digital/", False, id="digital-single"),
        pytest.param("/digital/", True, id="digital-dashboard"),
    ],
)
@pytest.mark.parametrize(
    ("fixed_time", "utc_state", "other_tz", "other_time", "other_state"),
    DAYNIGHT_BOUNDARIES,
)
def test_daynight_boundaries_for_every_render_path(
    page: Page,
    app_url: str,
    path: str,
    dashboard: bool,
    fixed_time: str,
    utc_state: str,
    other_tz: str,
    other_time: str,
    other_state: str,
) -> None:
    utc_time = fixed_time[11:16]
    params = {
        "tz": "UTC," + other_tz if dashboard else "UTC",
        "daynight": "show",
    }
    open_page(page, app_url, params, path=path, fixed_time=fixed_time)
    if path:
        entries = digital_daynight_state(page, dashboard)
        assert len(entries) == (2 if dashboard else 1)
        assert entries[0]["time"] == utc_time + ":00"
        assert entries[0]["state"] == utc_state
        assert entries[0]["visible"] is True
        assert entries[0]["ariaHidden"] == "true"
        assert_icon_pair(entries[0], utc_state)
        if dashboard:
            assert entries[1]["time"] == other_time + ":00"
            assert entries[1]["state"] == other_state
            assert entries[1]["visible"] is True
            assert entries[1]["ariaHidden"] == "true"
            assert_icon_pair(entries[1], other_state)
    else:
        entries = analog_daynight_state(page, dashboard)
        assert len(entries) == (2 if dashboard else 1)
        expected_prefix = "UTC: " if dashboard else "The time is "
        assert entries[0]["label"] == expected_prefix + utc_time
        assert_icon_pair(entries[0], utc_state)
        if dashboard:
            other_name = other_tz.split("/")[-1].replace("_", " ")
            assert entries[1]["label"] == other_name + ": " + other_time
            assert_icon_pair(entries[1], other_state)


DAYNIGHT_LIVE_TRANSITIONS = [
    pytest.param(
        "2026-01-01T05:59:59Z",
        "2026-01-01T06:00:00Z",
        ("night", "day"),
        ("05:59", "06:00"),
        ("14:59", "15:00", "day"),
        id="dawn",
    ),
    pytest.param(
        "2026-01-01T17:59:59Z",
        "2026-01-01T18:00:00Z",
        ("day", "night"),
        ("17:59", "18:00"),
        ("02:59", "03:00", "night"),
        id="dusk",
    ),
]


@pytest.mark.cross_browser
@pytest.mark.parametrize(
    ("path", "dashboard"),
    [
        pytest.param("", False, id="analog-single"),
        pytest.param("", True, id="analog-dashboard"),
        pytest.param("/digital/", False, id="digital-single"),
        pytest.param("/digital/", True, id="digital-dashboard"),
    ],
)
@pytest.mark.parametrize(
    ("initial_time", "final_time", "utc_states", "utc_times", "tokyo"),
    DAYNIGHT_LIVE_TRANSITIONS,
)
def test_daynight_boundary_changes_without_reload(
    page: Page,
    app_url: str,
    path: str,
    dashboard: bool,
    initial_time: str,
    final_time: str,
    utc_states: tuple[str, str],
    utc_times: tuple[str, str],
    tokyo: tuple[str, str, str],
) -> None:
    params = {
        "tz": "UTC,Asia/Tokyo" if dashboard else "UTC",
        "daynight": "show",
    }
    open_page(page, app_url, params, path=path, fixed_time=initial_time)
    initial_url = page.url

    if path:
        initial_entries = digital_daynight_state(page, dashboard)
        assert initial_entries[0]["time"] == utc_times[0] + ":59"
        assert initial_entries[0]["state"] == utc_states[0]
        assert_icon_pair(initial_entries[0], utc_states[0])
        if dashboard:
            assert initial_entries[1]["time"] == tokyo[0] + ":59"
            assert initial_entries[1]["state"] == tokyo[2]
            assert_icon_pair(initial_entries[1], tokyo[2])
    else:
        initial_entries = analog_daynight_state(page, dashboard)
        assert initial_entries[0]["label"].endswith(utc_times[0])
        assert_icon_pair(initial_entries[0], utc_states[0])
        if dashboard:
            assert initial_entries[1]["label"] == "Tokyo: " + tokyo[0]
            assert_icon_pair(initial_entries[1], tokyo[2])

    update_after_time_change(page, path, final_time)
    assert page.url == initial_url

    if path:
        final_entries = digital_daynight_state(page, dashboard)
        assert final_entries[0]["time"] == utc_times[1] + ":00"
        assert final_entries[0]["state"] == utc_states[1]
        assert_icon_pair(final_entries[0], utc_states[1])
        if dashboard:
            assert final_entries[1]["time"] == tokyo[1] + ":00"
            assert final_entries[1]["state"] == tokyo[2]
            assert_icon_pair(final_entries[1], tokyo[2])
    else:
        final_entries = analog_daynight_state(page, dashboard)
        assert final_entries[0]["label"].endswith(utc_times[1])
        assert_icon_pair(final_entries[0], utc_states[1])
        if dashboard:
            assert final_entries[1]["label"] == "Tokyo: " + tokyo[1]
            assert_icon_pair(final_entries[1], tokyo[2])


@pytest.mark.cross_browser
@pytest.mark.parametrize(
    ("path", "dashboard"),
    [
        pytest.param("", False, id="analog-single"),
        pytest.param("", True, id="analog-dashboard"),
        pytest.param("/digital/", False, id="digital-single"),
        pytest.param("/digital/", True, id="digital-dashboard"),
    ],
)
def test_daynight_absent_has_no_visible_indicator(
    page: Page, app_url: str, path: str, dashboard: bool
) -> None:
    params = {"tz": "UTC,Asia/Tokyo" if dashboard else "UTC"}
    open_page(
        page,
        app_url,
        params,
        path=path,
        fixed_time="2026-01-01T12:00:00Z",
    )
    if path:
        entries = digital_daynight_state(page, dashboard)
        assert len(entries) == (2 if dashboard else 1)
        assert all(entry["visible"] is False for entry in entries)
        assert all(entry["state"] is None for entry in entries)
    else:
        entries = analog_daynight_state(page, dashboard)
        assert len(entries) == (2 if dashboard else 1)
        assert all(entry["sunVisible"] is False for entry in entries)
        assert all(entry["moonVisible"] is False for entry in entries)


@pytest.mark.accessibility
@pytest.mark.parametrize(
    ("path", "dashboard"),
    [
        pytest.param("", False, id="analog-single"),
        pytest.param("", True, id="analog-dashboard"),
        pytest.param("/digital/", False, id="digital-single"),
        pytest.param("/digital/", True, id="digital-dashboard"),
    ],
)
def test_daynight_indicators_are_hidden_from_accessibility_tree(
    page: Page, app_url: str, path: str, dashboard: bool
) -> None:
    params = {
        "tz": "UTC,Asia/Tokyo" if dashboard else "UTC",
        "daynight": "show",
    }
    open_page(
        page,
        app_url,
        params,
        path=path,
        fixed_time="2026-01-01T05:59:00Z",
    )
    if path:
        entries = digital_daynight_state(page, dashboard)
        assert len(entries) == (2 if dashboard else 1)
        assert all(entry["ariaHidden"] == "true" for entry in entries)
    else:
        entries = analog_daynight_state(page, dashboard)
        assert len(entries) == (2 if dashboard else 1)
        assert all(entry["sunAriaHidden"] == "true" for entry in entries)
        assert all(entry["moonAriaHidden"] == "true" for entry in entries)
