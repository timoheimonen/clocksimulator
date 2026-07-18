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
