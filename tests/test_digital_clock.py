from __future__ import annotations

import os
import time

import pytest
from playwright.sync_api import Page

from tests.helpers import open_page, assert_screenshot


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


def start_advancing_date(page: Page) -> None:
    page.evaluate("""() => {
        const FixedDate = Date;
        const fixedStart = FixedDate.now();
        const monotonicStart = performance.now();
        window.Date = function () {
            if (arguments.length) return new FixedDate(...arguments);
            return new FixedDate(fixedStart + performance.now() - monotonicStart);
        };
        window.Date.prototype = FixedDate.prototype;
        window.Date.prototype.constructor = window.Date;
        window.Date.now = function () {
            return fixedStart + performance.now() - monotonicStart;
        };
        window.Date.parse = FixedDate.parse.bind(FixedDate);
        window.Date.UTC = FixedDate.UTC.bind(FixedDate);
    }""")


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
    start_advancing_date(page)
    page.wait_for_function(
        "initial => document.getElementById('digitalTime').textContent !== initial",
        arg=initial_visible,
        timeout=3000,
    )

    assert digital_text(page) != initial_visible
    assert page.evaluate("() => document.getElementById('timeAnnounce').textContent") == initial_announcement
    assert page.evaluate("() => window.__timeAnnounceMutationCount") == 0


def test_digital_live_announcement_changes_once_at_next_minute(page: Page, app_url: str) -> None:
    open_digital(page, app_url, fixed_time="2026-01-01T12:00:59.500Z")
    assert page.evaluate("() => document.getElementById('timeAnnounce').textContent") == "The time is 12:00"
    observe_time_announcements(page)
    start_advancing_date(page)

    page.wait_for_function(
        "() => document.getElementById('timeAnnounce').textContent === 'The time is 12:01'",
        timeout=3000,
    )
    visible_at_minute_change = digital_text(page)
    page.wait_for_function(
        "initial => document.getElementById('digitalTime').textContent !== initial",
        arg=visible_at_minute_change,
        timeout=3000,
    )

    assert digital_text(page).startswith("12:01:")
    assert page.evaluate("() => window.__timeAnnounceMutationCount") == 1
    assert page.evaluate("() => window.__timeAnnounceChanges") == ["The time is 12:01"]


def test_digital_seconds_hide(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"seconds": "hide"})
    assert digital_text(page) == "12:00"
    assert page.evaluate("() => getComputedStyle(document.querySelector('.second-mode-toggle')).display") == "none"


def test_digital_seconds_hide_still_announces_minute(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"seconds": "hide"})
    assert page.evaluate("() => document.getElementById('timeAnnounce').textContent") == "The time is 12:00"


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


def test_digital_theme_dark(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"theme": "dark"})
    assert page.evaluate("() => document.documentElement.classList.contains('dark-mode')") is True


def test_digital_theme_light(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"theme": "light"})
    assert page.evaluate("() => document.documentElement.classList.contains('dark-mode')") is False
    assert page.evaluate("() => document.documentElement.classList.contains('transparent-mode')") is False


def test_digital_theme_transparent(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"theme": "transparent"})
    assert page.evaluate("() => document.documentElement.classList.contains('transparent-mode')") is True
    assert page.evaluate("() => getComputedStyle(document.getElementById('digitalTime')).color") == "rgb(250, 250, 250)"


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
    start_advancing_date(page)
    page.wait_for_function(
        """values => document.querySelector(values.selector).textContent !== values.initial""",
        arg={"selector": visible_time_selector, "initial": initial_visible},
        timeout=3000,
    )

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


def test_digital_embed_burnin_disabled(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"embed": "true"})
    time.sleep(0.2)
    transform = page.evaluate("() => document.getElementById('digitalContainer').style.transform")
    assert transform == "" or transform == "none"


def test_digital_daynight_show(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"daynight": "show"})
    state = page.evaluate("() => document.getElementById('dayNightIcon').dataset.state")
    assert state == "day"
    assert page.evaluate("() => document.getElementById('digitalLabel').hidden") is True
    assert page.evaluate("() => document.getElementById('digitalMeta').hidden") is False
    assert page.evaluate("() => !!document.querySelector('#dayNightIcon svg .daynight-sun')") is True
    assert page.evaluate("() => getComputedStyle(document.querySelector('#dayNightIcon .daynight-sun')).display") == "block"
    assert page.evaluate("() => getComputedStyle(document.querySelector('#dayNightIcon .daynight-moon')).display") == "none"


def test_digital_border_show(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"border": "show"})
    assert page.evaluate("() => document.getElementById('digitalContainer').classList.contains('bordered')") is True


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


def test_digital_theme_toggle_changes_class(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"theme": "light"})
    page.evaluate("() => document.getElementById('themeToggle').click()")
    assert page.evaluate("() => document.documentElement.classList.contains('dark-mode')") is True


def test_digital_dashboard_activates_with_multiple_timezones(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"tz": "UTC,Europe/Helsinki"})
    assert page.evaluate("() => !!document.querySelector('.digital-grid')") is True
    assert page.evaluate("() => document.getElementById('digitalContainer').style.display") == "none"


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
    start_advancing_date(page)
    page.wait_for_function(
        """initial => {
            const current = Array.from(document.querySelectorAll('.digital-grid .digital-time'))
                .map(el => el.textContent);
            return JSON.stringify(current) !== JSON.stringify(initial);
        }""",
        arg=initial_visible,
        timeout=3000,
    )

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
            clientWidth: el.clientWidth
        }))
    })""")
    assert result["scrollWidth"] <= result["innerWidth"] + 1
    assert all(t["scrollWidth"] <= t["clientWidth"] + 1 for t in result["times"])


def test_digital_dashboard_daynight_show(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"tz": "UTC,Europe/Helsinki", "daynight": "show"})
    states = page.evaluate("() => Array.from(document.querySelectorAll('.digital-grid .daynight-mark')).map(el => el.dataset.state)")
    assert states == ["day", "day"]


def test_digital_dashboard_invalid_timezone_ignored(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"tz": "UTC,Invalid/Timezone"})
    assert page.evaluate("() => !!document.querySelector('.digital-grid')") is False
    assert digital_text(page) == "12:00:00"


def test_digital_dashboard_all_invalid_timezone_falls_back(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"tz": "Fake/One,Fake/Two"})
    assert page.evaluate("() => !!document.querySelector('.digital-grid')") is False
    assert digital_text(page) == "12:00:00"


def test_digital_embed_panel_generates_digital_iframe(page: Page, app_url: str) -> None:
    open_digital(page, app_url)
    page.evaluate("""() => {
        document.getElementById('embedLink').click();
        document.getElementById('embedTz').value = 'Europe/Helsinki';
        document.getElementById('embedTz').dispatchEvent(new Event('input', { bubbles: true }));
        document.getElementById('embedFormat').value = '12';
        document.getElementById('embedFormat').dispatchEvent(new Event('change', { bubbles: true }));
        document.getElementById('embedSeconds').value = 'hide';
        document.getElementById('embedSeconds').dispatchEvent(new Event('change', { bubbles: true }));
    }""")
    page.wait_for_function("() => document.getElementById('embedCode').value.includes('/digital/')")
    code = page.evaluate("() => document.getElementById('embedCode').value")
    assert 'https://clocksimulator.com/digital/?embed=true' in code
    assert 'tz=Europe%2FHelsinki' in code
    assert 'format=12' in code
    assert 'seconds=hide' in code


def test_digital_copy_button_handles_missing_clipboard(page: Page, app_url: str) -> None:
    page.add_init_script("""
        Object.defineProperty(navigator, 'clipboard', {
            configurable: true,
            value: undefined
        });
    """)
    open_digital(page, app_url)
    page.evaluate("""() => {
        document.getElementById('embedLink').click();
        document.getElementById('embedCopyBtn').click();
    }""")
    page.wait_for_function("() => document.getElementById('embedCopyBtn').textContent === 'Failed'")


def test_digital_dashboard_builder_generates_digital_url(page: Page, app_url: str) -> None:
    open_digital(page, app_url)
    page.evaluate("""() => {
        document.getElementById('dashboardLink').click();
        var input = document.getElementById('dashboardTzInput');
        input.value = 'UTC';
        document.getElementById('dashboardAddBtn').click();
        input.value = 'Europe/Helsinki';
        document.getElementById('dashboardAddBtn').click();
        document.getElementById('dashboardFormat').value = '12';
        document.getElementById('dashboardFormat').dispatchEvent(new Event('change', { bubbles: true }));
    }""")
    page.wait_for_function("() => document.getElementById('dashboardUrl').value.includes('format=12')")
    url = page.evaluate("() => document.getElementById('dashboardUrl').value")
    assert url.startswith("https://clocksimulator.com/digital/?")
    assert "tz=UTC%2CEurope%2FHelsinki" in url
    assert "format=12" in url


def test_digital_service_worker_caches_digital_page() -> None:
    sw_path = os.path.join(os.path.dirname(__file__), "..", "public", "sw.js")
    with open(sw_path, encoding="utf-8") as f:
        body = f.read()
    assert "'/digital/'" in body
    assert "caches.match('/digital/')" in body


def test_analog_index_links_to_digital_clock_under_help() -> None:
    index_path = os.path.join(os.path.dirname(__file__), "..", "public", "index.html")
    with open(index_path, encoding="utf-8") as f:
        body = f.read()
    help_idx = body.index('id="helpLink">How to use')
    digital_idx = body.index('id="digitalClockLink"')
    assert help_idx < digital_idx
    assert '<a href="/digital/" id="digitalClockLink">Digital clock &rarr;</a>' in body


def test_digital_index_links_to_analog_clock_under_help() -> None:
    index_path = os.path.join(os.path.dirname(__file__), "..", "public", "digital", "index.html")
    with open(index_path, encoding="utf-8") as f:
        body = f.read()
    help_idx = body.index('id="helpLink">How to use')
    analog_idx = body.index('id="analogClockLink"')
    assert help_idx < analog_idx
    assert '<a href="/" id="analogClockLink">Analog clock &rarr;</a>' in body


def test_digital_visual_snapshot_dark(page: Page, app_url: str, update_snapshots: bool) -> None:
    open_digital(page, app_url, {"theme": "dark"})
    assert_screenshot(page, "digital-dark.png", update=update_snapshots)


def test_digital_visual_snapshot_light(page: Page, app_url: str, update_snapshots: bool) -> None:
    open_digital(page, app_url, {"theme": "light"})
    assert_screenshot(page, "digital-light.png", update=update_snapshots)


def test_digital_visual_snapshot_embed_transparent(page: Page, app_url: str, update_snapshots: bool) -> None:
    open_digital(page, app_url, {"embed": "true", "theme": "transparent"})
    assert_screenshot(page, "digital-embed-transparent.png", update=update_snapshots)


def test_digital_visual_snapshot_dashboard_dark(page: Page, app_url: str, update_snapshots: bool) -> None:
    open_digital(page, app_url, {"tz": "UTC,Europe/Helsinki,America/New_York", "theme": "dark"})
    assert_screenshot(page, "digital-dashboard-dark-3tz.png", update=update_snapshots)
