from __future__ import annotations

import pytest
from playwright.sync_api import Page

from tests.helpers import (
    assert_screenshot,
    install_timer_probe,
    open_page,
    press_tab,
    set_test_time,
    wait_for_clock_ready,
)


def open_digital(
    page: Page,
    app_url: str,
    params: dict[str, str] | None = None,
    localStorage_items: dict[str, str] | None = None,
    fixed_time: str = "2026-01-01T12:00:00Z",
) -> None:
    open_page(page, app_url, params, localStorage_items, path="/digital/", fixed_time=fixed_time)


def digital_text(page: Page) -> str:
    return page.evaluate("() => document.getElementById('digitalTime').textContent")


def observe_time_announcements(page: Page) -> None:
    page.evaluate("""() => {
        const announce = document.getElementById('timeAnnounce');
        window.__timeAnnounceMutationCount = 0;
        window.__timeAnnounceChanges = [];
        window.__timeAnnounceObserver = new MutationObserver(function (records) {
            window.__timeAnnounceMutationCount += records.length;
            for (let i = 0; i < records.length; i++) {
                window.__timeAnnounceChanges.push(announce.textContent);
            }
        });
        window.__timeAnnounceObserver.observe(announce, {
            childList: true,
            characterData: true,
            subtree: true
        });
    }""")


def observe_digital_updates(page: Page) -> None:
    page.evaluate(
        """() => {
            const times = Array.from(document.querySelectorAll('time.digital-time'));
            const announce = document.getElementById('timeAnnounce');
            window.__digitalTimeMutationCount = 0;
            window.__digitalAnnounceMutationCount = 0;
            window.__digitalTimeObserver = new MutationObserver(function (records) {
                window.__digitalTimeMutationCount += records.length;
            });
            window.__digitalAnnounceObserver = new MutationObserver(function (records) {
                window.__digitalAnnounceMutationCount += records.length;
            });
            times.forEach(function (time) {
                window.__digitalTimeObserver.observe(time, {
                    childList: true,
                    characterData: true,
                    subtree: true
                });
            });
            window.__digitalAnnounceObserver.observe(announce, {
                childList: true,
                characterData: true,
                subtree: true
            });
        }"""
    )


def test_digital_page_renders_local_time(page: Page, app_url: str) -> None:
    open_digital(page, app_url)
    assert digital_text(page) == "12:00:00"
    assert page.evaluate("() => document.getElementById('digitalLabel').textContent") == ""
    assert page.evaluate("() => document.getElementById('digitalMeta').hidden") is True


def test_digital_live_announcement_stays_stable_within_minute(page: Page, app_url: str) -> None:
    open_digital(page, app_url, fixed_time="2026-01-01T12:00:15.250Z")
    initial_visible = digital_text(page)
    initial_announcement = page.evaluate("() => document.getElementById('timeAnnounce').textContent")
    assert initial_announcement == "The time is 12:00"

    observe_time_announcements(page)
    set_test_time(page, "2026-01-01T12:00:16.250Z", advance_milliseconds=1000)

    assert digital_text(page) != initial_visible
    assert page.evaluate("() => document.getElementById('timeAnnounce').textContent") == initial_announcement
    assert page.evaluate("() => window.__timeAnnounceMutationCount") == 0


def test_digital_live_announcement_changes_once_at_next_minute(page: Page, app_url: str) -> None:
    open_digital(page, app_url, fixed_time="2026-01-01T12:00:59.500Z")
    assert page.evaluate("() => document.getElementById('timeAnnounce').textContent") == "The time is 12:00"
    observe_time_announcements(page)
    set_test_time(page, "2026-01-01T12:01:00.000Z", advance_milliseconds=500)
    assert page.locator("#timeAnnounce").text_content() == "The time is 12:01"
    visible_at_minute_change = digital_text(page)
    set_test_time(page, "2026-01-01T12:01:01.000Z", advance_milliseconds=1000)

    assert digital_text(page) != visible_at_minute_change
    assert digital_text(page).startswith("12:01:")
    assert page.evaluate("() => window.__timeAnnounceMutationCount") == 1
    assert page.evaluate("() => window.__timeAnnounceChanges") == ["The time is 12:01"]


def test_digital_seconds_hide(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"seconds": "hide"})
    assert digital_text(page) == "12:00"
    assert page.evaluate("() => getComputedStyle(document.querySelector('.second-mode-toggle')).display") == "none"


def test_digital_seconds_visible_by_default(page: Page, app_url: str) -> None:
    open_digital(page, app_url)
    assert digital_text(page) == "12:00:00"
    assert page.locator("#digitalTime").get_attribute("datetime") == "12:00:00"
    assert page.locator("#secondModeToggle").is_checked() is True
    assert page.evaluate(
        "() => getComputedStyle(document.querySelector('.second-mode-toggle')).display"
    ) == "flex"


def test_digital_seconds_hide_still_announces_minute(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"seconds": "hide"})
    assert page.evaluate("() => document.getElementById('timeAnnounce').textContent") == "The time is 12:00"


@pytest.mark.parametrize(
    "timezones",
    [
        pytest.param(None, id="single"),
        pytest.param("UTC,Asia/Kathmandu", id="dashboard"),
    ],
)
def test_digital_seconds_hidden_updates_once_at_next_minute_boundary(
    page: Page,
    app_url: str,
    timezones: str | None,
) -> None:
    clock = install_timer_probe(
        page,
        "2026-01-01T12:00:59.500Z",
        manual=True,
    )
    params = {"seconds": "hide"}
    if timezones is not None:
        params["tz"] = timezones
    open_digital(
        page,
        app_url,
        params,
        fixed_time="2026-01-01T12:00:59.500Z",
    )
    times = (
        page.locator("#digitalTime")
        if timezones is None
        else page.locator(".digital-grid time.digital-time")
    )
    expected_before = ["12:00"] if timezones is None else ["12:00", "17:45"]
    expected_after = ["12:01"] if timezones is None else ["12:01", "17:46"]
    expected_datetime_before = (
        ["12:00:59"]
        if timezones is None
        else ["12:00:59", "17:45:59"]
    )
    expected_datetime_after = (
        ["12:01:00"]
        if timezones is None
        else ["12:01:00", "17:46:00"]
    )
    assert times.all_text_contents() == expected_before
    assert times.evaluate_all(
        "elements => elements.map(element => element.getAttribute('datetime'))"
    ) == expected_datetime_before
    initial_announcement = page.locator("#timeAnnounce").text_content()
    observe_digital_updates(page)
    minute_timer_candidates = [
        record
        for record in clock.timers()
        if record.kind == "timeout" and record.delay == 500 and not record.cleared
    ]
    assert len(minute_timer_candidates) == 2
    assert times.all_text_contents() == expected_before
    assert page.locator("#timeAnnounce").text_content() == initial_announcement
    assert page.evaluate("() => window.__digitalTimeMutationCount") == 0
    assert page.evaluate("() => window.__digitalAnnounceMutationCount") == 0

    clock.set_time("2026-01-01T12:01:00.000Z")
    effectful_timers = 0
    for record in minute_timer_candidates:
        before = times.all_text_contents()
        clock.run_timer(record.timer_id)
        if times.all_text_contents() != before:
            effectful_timers += 1
    assert effectful_timers == 1
    assert times.all_text_contents() == expected_after
    assert times.evaluate_all(
        "elements => elements.map(element => element.getAttribute('datetime'))"
    ) == expected_datetime_after
    assert page.evaluate("() => window.__digitalTimeMutationCount") == len(expected_after)
    assert page.evaluate("() => window.__digitalAnnounceMutationCount") == 1


def test_digital_seconds_toggle_targets_real_minute_and_second_boundaries(
    page: Page,
    app_url: str,
) -> None:
    clock = install_timer_probe(
        page,
        "2026-01-01T12:00:30.250Z",
        manual=True,
    )
    open_digital(
        page,
        app_url,
        fixed_time="2026-01-01T12:00:30.250Z",
    )
    press_tab(page)
    page.locator("label.second-mode-toggle").click()
    assert digital_text(page) == "12:00"
    observe_digital_updates(page)
    minute_timer_candidates = [
        record
        for record in clock.timers()
        if record.kind == "timeout" and record.delay == 29750 and not record.cleared
    ]
    assert len(minute_timer_candidates) == 2
    assert digital_text(page) == "12:00"
    assert page.evaluate("() => window.__digitalTimeMutationCount") == 0

    clock.set_time("2026-01-01T12:01:00.000Z")
    effectful_timers = 0
    for record in minute_timer_candidates:
        before = digital_text(page)
        clock.run_timer(record.timer_id)
        if digital_text(page) != before:
            effectful_timers += 1
    assert effectful_timers == 1
    assert digital_text(page) == "12:01"
    assert page.evaluate("() => window.__digitalTimeMutationCount") == 1

    clock.set_time("2026-01-01T12:01:00.999Z")
    page.locator("label.second-mode-toggle").click()
    assert digital_text(page) == "12:01:00"
    page.wait_for_function("() => window.__digitalTimeMutationCount >= 2")
    page.evaluate("() => window.__digitalTimeObserver.disconnect()")
    observe_digital_updates(page)
    second_timer_candidates = [
        record
        for record in clock.timers()
        if record.kind == "timeout" and record.delay == 1 and not record.cleared
    ]
    assert len(second_timer_candidates) == 1
    assert digital_text(page) == "12:01:00"
    assert page.evaluate("() => window.__digitalTimeMutationCount") == 0

    clock.set_time("2026-01-01T12:01:01.000Z")
    clock.run_timer(second_timer_candidates[0].timer_id)
    assert digital_text(page) == "12:01:01"
    assert page.evaluate("() => window.__digitalTimeMutationCount") == 1


def test_digital_seconds_toggle_hides_seconds(page: Page, app_url: str) -> None:
    open_digital(page, app_url)
    page.evaluate("() => document.getElementById('secondModeToggle').click()")
    assert digital_text(page) == "12:00"


def test_digital_format_12_hour(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"format": "12"})
    assert digital_text(page) == "12:00:00 PM"


@pytest.mark.parametrize(
    ("fixed_time", "expected_announcement"),
    [
        ("2026-01-01T00:00:00Z", "The time is 12:00 AM"),
        ("2026-01-01T12:00:00Z", "The time is 12:00 PM"),
    ],
)
def test_digital_12_hour_live_announcement_excludes_seconds(
    page: Page,
    app_url: str,
    fixed_time: str,
    expected_announcement: str,
) -> None:
    open_digital(page, app_url, {"format": "12"}, fixed_time=fixed_time)
    assert page.evaluate("() => document.getElementById('timeAnnounce').textContent") == expected_announcement


def test_digital_timezone(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"tz": "Europe/Helsinki"})
    assert digital_text(page) == "14:00:00"
    assert page.evaluate("() => document.getElementById('digitalLabel').textContent") == "Helsinki"


def test_digital_title_changes_for_timezone(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"tz": "Europe/Helsinki"})
    assert page.evaluate("() => document.title") == "clocksimulator.com - Digital - Europe/Helsinki"


def test_digital_embed_mode_defaults_dark_and_hides_controls(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"embed": "true"})
    assert page.evaluate("() => document.body.classList.contains('embed-mode')") is True
    assert page.evaluate("() => document.documentElement.classList.contains('dark-mode')") is True
    assert page.evaluate("() => document.querySelector('.toggle-wrapper').offsetWidth") == 0


@pytest.mark.parametrize(
    ("params", "visible_time_selector"),
    [
        ({"embed": "true"}, "#digitalTime"),
        ({"embed": "true", "tz": "UTC,Europe/Helsinki"}, ".digital-grid .digital-time"),
    ],
    ids=["single", "dashboard"],
)
def test_digital_embed_live_announcement_stays_empty(
    page: Page,
    app_url: str,
    params: dict[str, str],
    visible_time_selector: str,
) -> None:
    open_digital(page, app_url, params, fixed_time="2026-01-01T12:00:15.250Z")
    initial_visible = page.evaluate(
        "selector => document.querySelector(selector).textContent",
        visible_time_selector,
    )
    assert page.evaluate("() => document.getElementById('timeAnnounce').textContent") == ""

    observe_time_announcements(page)
    set_test_time(page, "2026-01-01T12:00:16.250Z", advance_milliseconds=1000)

    assert page.evaluate(
        "selector => document.querySelector(selector).textContent",
        visible_time_selector,
    ) != initial_visible
    assert page.evaluate("() => document.getElementById('timeAnnounce').textContent") == ""
    assert page.evaluate("() => window.__timeAnnounceMutationCount") == 0


def test_digital_embed_time_is_viewport_centered_without_meta(page: Page, app_url: str) -> None:
    page.set_viewport_size({"width": 800, "height": 300})
    open_digital(page, app_url, {"embed": "true", "seconds": "hide"})
    result = page.evaluate("""() => {
        const rect = document.getElementById('digitalTime').getBoundingClientRect();
        return {
            centerX: rect.left + rect.width / 2,
            centerY: rect.top + rect.height / 2,
            viewportX: window.innerWidth / 2,
            viewportY: window.innerHeight / 2,
            metaHidden: document.getElementById('digitalMeta').hidden
        };
    }""")
    assert result["metaHidden"] is True
    assert abs(result["centerX"] - result["viewportX"]) <= 1
    assert abs(result["centerY"] - result["viewportY"]) <= 1


def test_digital_embed_with_meta_keeps_time_centered(page: Page, app_url: str) -> None:
    page.set_viewport_size({"width": 900, "height": 320})
    open_digital(page, app_url, {"embed": "true", "tz": "Europe/Helsinki", "daynight": "show"})
    result = page.evaluate("""() => {
        const timeRect = document.getElementById('digitalTime').getBoundingClientRect();
        const metaRect = document.getElementById('digitalMeta').getBoundingClientRect();
        return {
            centerX: timeRect.left + timeRect.width / 2,
            centerY: timeRect.top + timeRect.height / 2,
            viewportX: window.innerWidth / 2,
            viewportY: window.innerHeight / 2,
            metaHidden: document.getElementById('digitalMeta').hidden,
            label: document.getElementById('digitalLabel').textContent,
            metaTop: metaRect.top,
            timeBottom: timeRect.bottom
        };
    }""")
    assert result["metaHidden"] is False
    assert result["label"] == "Helsinki"
    assert abs(result["centerX"] - result["viewportX"]) <= 1
    assert abs(result["centerY"] - result["viewportY"]) <= 1
    assert result["metaTop"] > result["timeBottom"]


def test_digital_embed_theme_transparent(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"embed": "true", "theme": "transparent"})
    assert page.evaluate("() => document.documentElement.classList.contains('transparent-mode')") is True
    assert page.evaluate("() => document.documentElement.classList.contains('dark-mode')") is False
    assert page.evaluate("() => getComputedStyle(document.getElementById('digitalTime')).color") == "rgb(250, 250, 250)"


def test_digital_embed_removes_favicon(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"embed": "true"})
    assert page.evaluate("() => document.getElementById('favicon')") is None


def test_digital_daynight_show(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"daynight": "show"})
    state = page.evaluate("() => document.getElementById('dayNightIcon').dataset.state")
    assert state == "day"
    assert page.evaluate("() => document.getElementById('digitalLabel').hidden") is True
    assert page.evaluate("() => document.getElementById('digitalMeta').hidden") is False
    assert page.evaluate("() => !!document.querySelector('#dayNightIcon svg .daynight-sun')") is True
    assert page.evaluate("() => getComputedStyle(document.querySelector('#dayNightIcon .daynight-sun')).display") == "block"
    assert page.evaluate("() => getComputedStyle(document.querySelector('#dayNightIcon .daynight-moon')).display") == "none"


def test_digital_daynight_hidden_by_default(page: Page, app_url: str) -> None:
    open_digital(page, app_url)
    icon = page.locator("#dayNightIcon")
    assert icon.evaluate("element => element.classList.contains('visible')") is False
    assert icon.get_attribute("data-state") is None
    assert page.locator("#digitalMeta").get_attribute("hidden") == ""


def test_digital_border_show(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"border": "show"})
    assert page.evaluate("() => document.getElementById('digitalContainer').classList.contains('bordered')") is True


def test_digital_border_hidden_by_default(page: Page, app_url: str) -> None:
    open_digital(page, app_url)
    assert page.locator("#digitalContainer").evaluate(
        "element => element.classList.contains('bordered')"
    ) is False


def test_digital_saved_settings_seconds_hidden(page: Page, app_url: str) -> None:
    open_digital(
        page,
        app_url,
        localStorage_items={
            "clocksimulator-user-settings": '{"theme":"light","wakeLock":false,"secondModeTick":true,"digitalShowSeconds":false}'
        },
    )
    assert digital_text(page) == "12:00"
    assert page.evaluate("() => document.getElementById('secondModeToggle').checked") is False


def test_digital_dashboard_activation_has_exact_structure(
    page: Page, app_url: str
) -> None:
    open_digital(page, app_url, {"tz": "UTC,Europe/Helsinki"})
    assert page.locator(".digital-grid").count() == 1
    assert page.locator(".digital-grid .digital-cell").count() == 2
    assert page.locator(".digital-grid .digital-time").count() == 2
    assert page.locator(".digital-grid .digital-label").all_text_contents() == [
        "UTC",
        "Helsinki",
    ]
    assert page.locator("#digitalContainer").is_hidden() is True


def test_digital_dashboard_live_region_remains_accessible(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"tz": "UTC,Asia/Kathmandu"})
    result = page.evaluate("""() => {
        const main = document.querySelector('main');
        const announce = document.getElementById('timeAnnounce');
        let excludedAncestor = null;
        let node = announce;
        while (node) {
            const style = getComputedStyle(node);
            if (node.hidden || style.display === 'none' || style.visibility === 'hidden' ||
                node.getAttribute('aria-hidden') === 'true') {
                excludedAncestor = node.id || node.tagName.toLowerCase();
                break;
            }
            node = node.parentElement;
        }
        return {
            mainDisplay: getComputedStyle(main).display,
            excludedAncestor: excludedAncestor,
            announcement: announce.textContent
        };
    }""")
    assert result["mainDisplay"] != "none"
    assert result["excludedAncestor"] is None
    assert "UTC 12:00" in result["announcement"]
    assert "Kathmandu 17:45" in result["announcement"]
    assert ":00:00" not in result["announcement"]


def test_digital_dashboard_labels_and_times(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"tz": "UTC,Europe/Helsinki,America/New_York"})
    result = page.evaluate("""() => ({
        labels: Array.from(document.querySelectorAll('.digital-grid .digital-label')).map(el => el.textContent),
        times: Array.from(document.querySelectorAll('.digital-grid .digital-time')).map(el => el.textContent)
    })""")
    assert result["labels"] == ["UTC", "Helsinki", "New York"]
    assert result["times"] == ["12:00:00", "14:00:00", "07:00:00"]


def test_digital_dashboard_live_announcement_stays_stable_within_minute(page: Page, app_url: str) -> None:
    open_digital(
        page,
        app_url,
        {"tz": "UTC,Europe/Helsinki"},
        fixed_time="2026-01-01T12:00:15.250Z",
    )
    initial_visible = page.evaluate(
        "() => Array.from(document.querySelectorAll('.digital-grid .digital-time')).map(el => el.textContent)"
    )
    initial_announcement = page.evaluate("() => document.getElementById('timeAnnounce').textContent")
    assert "UTC 12:00" in initial_announcement
    assert "Helsinki 14:00" in initial_announcement
    assert ":00:15" not in initial_announcement

    observe_time_announcements(page)
    set_test_time(page, "2026-01-01T12:00:16.250Z", advance_milliseconds=1000)

    current_visible = page.evaluate(
        "() => Array.from(document.querySelectorAll('.digital-grid .digital-time')).map(el => el.textContent)"
    )
    assert current_visible != initial_visible
    assert page.evaluate("() => document.getElementById('timeAnnounce').textContent") == initial_announcement
    assert page.evaluate("() => window.__timeAnnounceMutationCount") == 0


def test_digital_dashboard_rows_parameter(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"tz": "UTC,Europe/Helsinki,America/New_York,Asia/Tokyo", "rows": "2"})
    rows = page.evaluate(
        "() => getComputedStyle(document.querySelector('.digital-grid')).gridTemplateRows.trim().split(/\\s+/).filter(Boolean).length"
    )
    assert rows == 2


def test_digital_dashboard_seconds_hide(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"tz": "UTC,Europe/Helsinki", "seconds": "hide"})
    times = page.evaluate("() => Array.from(document.querySelectorAll('.digital-grid .digital-time')).map(el => el.textContent)")
    assert times == ["12:00", "14:00"]


def test_digital_dashboard_format_12_hour(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"tz": "UTC,Asia/Tokyo", "format": "12"})
    times = page.evaluate("() => Array.from(document.querySelectorAll('.digital-grid .digital-time')).map(el => el.textContent)")
    assert times == ["12:00:00 PM", "09:00:00 PM"]


def test_digital_dashboard_12_hour_text_fits_viewport(page: Page, app_url: str) -> None:
    page.set_viewport_size({"width": 840, "height": 734})
    open_digital(
        page,
        app_url,
        {
            "tz": "UTC,Europe/Helsinki,America/New_York",
            "rows": "1",
            "seconds": "hide",
            "format": "12",
            "border": "show",
            "daynight": "show",
        },
    )
    result = page.evaluate("""() => ({
        scrollWidth: document.documentElement.scrollWidth,
        innerWidth: window.innerWidth,
        times: Array.from(document.querySelectorAll('.digital-grid .digital-time')).map(el => ({
            scrollWidth: el.scrollWidth,
            clientWidth: el.clientWidth,
            fontSize: parseFloat(getComputedStyle(el).fontSize)
        }))
    })""")
    assert result["scrollWidth"] <= result["innerWidth"] + 1
    assert len(result["times"]) == 3
    assert all(t["scrollWidth"] <= t["clientWidth"] + 1 for t in result["times"])
    assert all(t["fontSize"] >= 24 for t in result["times"])


def test_digital_dashboard_daynight_show(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"tz": "UTC,Europe/Helsinki", "daynight": "show"})
    states = page.evaluate("() => Array.from(document.querySelectorAll('.digital-grid .daynight-mark')).map(el => el.dataset.state)")
    assert states == ["day", "day"]


def test_digital_dashboard_invalid_timezone_ignored(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"tz": "UTC,Invalid/Timezone,Asia/Kathmandu"})
    cells = page.locator(".digital-grid .digital-cell")
    assert cells.count() == 2
    assert page.locator(".digital-grid .digital-label").all_text_contents() == [
        "UTC",
        "Kathmandu",
    ]
    assert page.locator(".digital-grid .digital-time").all_text_contents() == [
        "12:00:00",
        "17:45:00",
    ]
    assert page.locator(".digital-grid .digital-time").evaluate_all(
        "elements => elements.map(element => element.getAttribute('datetime'))"
    ) == ["12:00:00", "17:45:00"]
    assert cells.evaluate_all(
        "elements => elements.map(element => element.getAttribute('aria-label'))"
    ) == ["UTC: 12:00:00", "Kathmandu: 17:45:00"]
    assert page.title() == "clocksimulator.com - Digital Dashboard"


def test_digital_dashboard_all_invalid_timezone_falls_back(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"tz": "Fake/One,Fake/Two"})
    assert page.evaluate("() => !!document.querySelector('.digital-grid')") is False
    assert page.locator("#digitalTime").is_visible() is True
    assert digital_text(page) == "12:00:00"
    assert page.locator("#digitalTime").get_attribute("datetime") == "12:00:00"
    assert page.locator("#digitalContainer").get_attribute("aria-label") == (
        "The time is 12:00:00"
    )


def test_analog_page_link_navigates_to_digital_clock(
    page: Page,
    app_url: str,
) -> None:
    open_page(page, app_url)
    press_tab(page)
    page.locator("#aboutBtn").focus()
    page.keyboard.press("Enter")
    link = page.get_by_role("link", name="Digital clock")
    assert link.is_visible() is True
    assert link.get_attribute("href") == "/digital/"
    link.click()
    page.wait_for_url(app_url.rstrip("/") + "/digital/")
    wait_for_clock_ready(page)
    assert digital_text(page) == "12:00:00"


def test_digital_page_link_navigates_to_analog_clock(
    page: Page,
    app_url: str,
) -> None:
    open_digital(page, app_url)
    press_tab(page)
    page.locator("#aboutBtn").focus()
    page.keyboard.press("Enter")
    link = page.get_by_role("link", name="Analog clock")
    assert link.is_visible() is True
    assert link.get_attribute("href") == "/"
    link.click()
    page.wait_for_url(app_url.rstrip("/") + "/")
    wait_for_clock_ready(page)
    assert page.locator("#clock").get_attribute("aria-label") == "The time is 12:00"


@pytest.mark.visual
def test_digital_visual_snapshot_dark(page: Page, app_url: str, update_snapshots: bool) -> None:
    open_digital(page, app_url, {"theme": "dark"})
    assert digital_text(page) == "12:00:00"
    assert page.locator("html").evaluate(
        "element => element.classList.contains('dark-mode')"
    ) is True
    assert_screenshot(page, "digital-dark.png", update=update_snapshots)


@pytest.mark.visual
def test_digital_visual_snapshot_light(page: Page, app_url: str, update_snapshots: bool) -> None:
    open_digital(page, app_url, {"theme": "light"})
    assert digital_text(page) == "12:00:00"
    assert_screenshot(page, "digital-light.png", update=update_snapshots)


@pytest.mark.visual
def test_digital_visual_snapshot_embed_transparent(page: Page, app_url: str, update_snapshots: bool) -> None:
    open_digital(page, app_url, {"embed": "true", "theme": "transparent"})
    assert page.locator("body").evaluate(
        "element => getComputedStyle(element).backgroundColor"
    ) == "rgba(0, 0, 0, 0)"
    assert_screenshot(
        page,
        "digital-embed-transparent.png",
        update=update_snapshots,
        transparent=True,
    )


@pytest.mark.visual
def test_digital_visual_snapshot_dashboard_dark(page: Page, app_url: str, update_snapshots: bool) -> None:
    open_digital(page, app_url, {"tz": "UTC,Europe/Helsinki,America/New_York", "theme": "dark"})
    assert page.locator(".digital-grid .digital-cell").count() == 3
    assert_screenshot(page, "digital-dashboard-dark-3tz.png", update=update_snapshots)
