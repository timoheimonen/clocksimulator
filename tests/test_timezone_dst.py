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
                moonVisible: getComputedStyle(moon).display !== 'none'
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


@pytest.mark.parametrize(
    ("path", "fixed_time", "expected_time", "expected_hour"),
    [
        pytest.param("", "2026-01-01T00:30:00Z", "00:30", "rotate(15deg)", id="analog-midnight"),
        pytest.param(
            "/digital/", "2026-01-01T00:30:00Z", "00:30", "rotate(15deg)", id="digital-midnight"
        ),
        pytest.param("", "2026-01-01T12:30:00Z", "12:30", "rotate(15deg)", id="analog-noon"),
    ],
)
def test_hour_cycle_fallback_single_time_boundaries(
    helsinki_page: Page,
    app_url: str,
    path: str,
    fixed_time: str,
    expected_time: str,
    expected_hour: str,
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


def test_digital_fractional_timezone_offsets(helsinki_page: Page, app_url: str) -> None:
    open_page(
        helsinki_page,
        app_url,
        {"tz": "Asia/Kolkata,Asia/Kathmandu"},
        path="/digital/",
        fixed_time=MIDNIGHT_OFFSET_TIME,
    )
    assert digital_dashboard_times(helsinki_page) == ["00:00:00", "00:15:00"]


def test_local_time_still_uses_browser_timezone(
    helsinki_page: Page, app_url: str
) -> None:
    open_page(helsinki_page, app_url, fixed_time=SPRING_DST_TIME)
    assert single_analog_state(helsinki_page) == {
        "hour": "rotate(135deg)",
        "minute": "rotate(180deg)",
        "label": "The time is 04:30",
    }
    open_page(helsinki_page, app_url, path="/digital/", fixed_time=SPRING_DST_TIME)
    helsinki_page.wait_for_function(
        "() => document.getElementById('digitalTime').textContent === '04:30:00'"
    )
    assert helsinki_page.evaluate(
        "() => document.getElementById('digitalTime').getAttribute('datetime')"
    ) == "04:30:00"


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


def test_analog_timezone_preserves_second_hand_mode_and_milliseconds(
    helsinki_page: Page, app_url: str
) -> None:
    open_page(
        helsinki_page,
        app_url,
        {"tz": "America/New_York", "seconds": "smooth"},
        fixed_time="2026-03-29T01:30:00.900Z",
    )
    state = single_analog_state(helsinki_page)
    initial_angle = helsinki_page.evaluate(
        "() => parseFloat(getComputedStyle(document.getElementById('secondHand')).getPropertyValue('--second-angle'))"
    )
    assert state["minute"] == "rotate(180deg)"
    assert initial_angle == pytest.approx(5.4)
    set_test_time(helsinki_page, "2026-03-29T01:30:01.100Z")
    helsinki_page.wait_for_function(
        "() => document.getElementById('minuteHand').style.transform === 'rotate(180.1deg)'"
    )
    advanced_angle = helsinki_page.evaluate(
        "() => parseFloat(getComputedStyle(document.getElementById('secondHand')).getPropertyValue('--second-angle'))"
    )
    assert advanced_angle == pytest.approx(6.6)


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
    "path",
    [
        pytest.param("", id="analog-single"),
        pytest.param("/digital/", id="digital-dashboard"),
    ],
)
@pytest.mark.parametrize(("initial_time", "final_time", "expected"), NEW_YORK_DST_TRANSITIONS)
def test_target_timezone_dst_changes_without_reload(
    page: Page,
    app_url: str,
    path: str,
    initial_time: str,
    final_time: str,
    expected: dict[str, tuple[str, str, str]],
) -> None:
    params = {"tz": "UTC,America/New_York"} if path else {"tz": "America/New_York"}
    open_page(page, app_url, params, path=path, fixed_time=initial_time)
    initial_url = page.url

    if path:
        assert digital_dashboard_state(page) == [
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
        assert single_analog_state(page) == {
            "hour": expected["initialNy"][1],
            "minute": expected["initialNy"][2],
            "label": "The time is " + expected["initialNy"][0][:5],
        }
        assert page.title() == "clocksimulator.com - America/New_York"

    update_after_time_change(page, path, final_time)
    assert page.url == initial_url

    if path:
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
        assert single_analog_state(page) == {
            "hour": expected["finalNy"][1],
            "minute": expected["finalNy"][2],
            "label": "The time is " + expected["finalNy"][0][:5],
        }


@pytest.mark.chromium_only
def test_timezone_offset_recalculated_at_60000ms_sla(page: Page, app_url: str) -> None:
    page.add_init_script("""
        window.__offsetFormatToPartsCalls = 0;
        const originalFormatToParts = Intl.DateTimeFormat.prototype.formatToParts;
        Intl.DateTimeFormat.prototype.formatToParts = function () {
            window.__offsetFormatToPartsCalls += 1;
            return originalFormatToParts.apply(this, arguments);
        };
    """)
    open_page(
        page,
        app_url,
        {"tz": "UTC,America/New_York"},
        fixed_time="2026-02-01T12:00:00Z",
    )
    initial_calls = page.evaluate("() => window.__offsetFormatToPartsCalls")
    assert initial_calls >= 2
    page.evaluate("""() => new Promise(resolve => {
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
    assert page.evaluate("() => window.__offsetFormatToPartsCalls") == initial_calls
    update_after_time_change(page, "", "2026-02-01T12:01:00Z")
    page.wait_for_function(
        "expected => window.__offsetFormatToPartsCalls >= expected",
        arg=initial_calls + 2,
    )
    assert page.evaluate("() => window.__offsetFormatToPartsCalls") == initial_calls + 2


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


def assert_icon_pair(entry: dict[str, object], expected_state: str) -> None:
    assert entry["sunVisible"] is (expected_state == "day")
    assert entry["moonVisible"] is (expected_state == "night")
    assert int(bool(entry["sunVisible"])) + int(bool(entry["moonVisible"])) == 1


@pytest.mark.cross_browser
@pytest.mark.parametrize(
    ("path", "fixed_time", "utc_state", "other_tz", "other_time", "other_state"),
    [
        pytest.param(
            "", "2026-01-01T05:59:00Z", "night", "Asia/Tokyo", "14:59", "day",
            id="analog-dashboard-0559-night",
        ),
        pytest.param(
            "", "2026-01-01T06:00:00Z", "day", "Pacific/Honolulu", "20:00", "night",
            id="analog-dashboard-0600-day",
        ),
        pytest.param(
            "", "2026-01-01T17:59:00Z", "day", "Asia/Tokyo", "02:59", "night",
            id="analog-dashboard-1759-day",
        ),
        pytest.param(
            "", "2026-01-01T18:00:00Z", "night", "Pacific/Honolulu", "08:00", "day",
            id="analog-dashboard-1800-night",
        ),
        pytest.param(
            "/digital/", "2026-01-01T06:00:00Z", "day", "Pacific/Honolulu", "20:00", "night",
            id="digital-dashboard-0600-day",
        ),
        pytest.param(
            "/digital/", "2026-01-01T18:00:00Z", "night", "Pacific/Honolulu", "08:00", "day",
            id="digital-dashboard-1800-night",
        ),
    ],
)
def test_daynight_boundaries_for_every_render_path(
    page: Page,
    app_url: str,
    path: str,
    fixed_time: str,
    utc_state: str,
    other_tz: str,
    other_time: str,
    other_state: str,
) -> None:
    utc_time = fixed_time[11:16]
    params = {"tz": "UTC," + other_tz, "daynight": "show"}
    open_page(page, app_url, params, path=path, fixed_time=fixed_time)
    if path:
        entries = digital_daynight_state(page, True)
        assert len(entries) == 2
        assert entries[0]["time"] == utc_time + ":00"
        assert entries[0]["state"] == utc_state
        assert entries[0]["visible"] is True
        assert entries[0]["ariaHidden"] == "true"
        assert_icon_pair(entries[0], utc_state)
        assert entries[1]["time"] == other_time + ":00"
        assert entries[1]["state"] == other_state
        assert entries[1]["visible"] is True
        assert entries[1]["ariaHidden"] == "true"
        assert_icon_pair(entries[1], other_state)
    else:
        entries = analog_daynight_state(page, True)
        assert len(entries) == 2
        assert entries[0]["label"] == "UTC: " + utc_time
        assert_icon_pair(entries[0], utc_state)
        other_name = other_tz.split("/")[-1].replace("_", " ")
        assert entries[1]["label"] == other_name + ": " + other_time
        assert_icon_pair(entries[1], other_state)


@pytest.mark.cross_browser
@pytest.mark.parametrize(
    ("path", "initial_time", "final_time", "utc_states", "utc_times"),
    [
        pytest.param(
            "",
            "2026-01-01T05:59:59Z",
            "2026-01-01T06:00:00Z",
            ("night", "day"),
            ("05:59", "06:00"),
            id="analog-single-dawn",
        ),
        pytest.param(
            "/digital/",
            "2026-01-01T17:59:59Z",
            "2026-01-01T18:00:00Z",
            ("day", "night"),
            ("17:59", "18:00"),
            id="digital-dashboard-dusk",
        ),
    ],
)
def test_daynight_boundary_changes_without_reload(
    page: Page,
    app_url: str,
    path: str,
    initial_time: str,
    final_time: str,
    utc_states: tuple[str, str],
    utc_times: tuple[str, str],
) -> None:
    params = {"tz": "UTC,Asia/Tokyo" if path else "UTC", "daynight": "show"}
    open_page(page, app_url, params, path=path, fixed_time=initial_time)
    initial_url = page.url

    if path:
        initial_entries = digital_daynight_state(page, True)
        assert initial_entries[0]["time"] == utc_times[0] + ":59"
        assert initial_entries[0]["state"] == utc_states[0]
        assert_icon_pair(initial_entries[0], utc_states[0])
        assert initial_entries[1]["time"] == "02:59:59"
        assert initial_entries[1]["state"] == "night"
        assert_icon_pair(initial_entries[1], "night")
    else:
        initial_entries = analog_daynight_state(page, False)
        assert initial_entries[0]["label"].endswith(utc_times[0])
        assert_icon_pair(initial_entries[0], utc_states[0])

    update_after_time_change(page, path, final_time)
    assert page.url == initial_url

    if path:
        final_entries = digital_daynight_state(page, True)
        assert final_entries[0]["time"] == utc_times[1] + ":00"
        assert final_entries[0]["state"] == utc_states[1]
        assert_icon_pair(final_entries[0], utc_states[1])
        assert final_entries[1]["time"] == "03:00:00"
        assert final_entries[1]["state"] == "night"
        assert_icon_pair(final_entries[1], "night")
    else:
        final_entries = analog_daynight_state(page, False)
        assert final_entries[0]["label"].endswith(utc_times[1])
        assert_icon_pair(final_entries[0], utc_states[1])


@pytest.mark.cross_browser
@pytest.mark.parametrize(
    ("path", "dashboard"),
    [
        pytest.param("", True, id="analog-dashboard"),
        pytest.param("/digital/", False, id="digital-single"),
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
