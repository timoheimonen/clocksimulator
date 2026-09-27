from __future__ import annotations

import pytest
from playwright.sync_api import Page

from tests.helpers import (
    open_page,
    set_test_time,
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


def test_digital_page_renders_local_time(page: Page, app_url: str) -> None:
    open_digital(page, app_url)
    assert digital_text(page) == "12:00:00"
    assert page.locator("#digitalTime").get_attribute("datetime") == "12:00:00"
    assert page.locator("#secondModeToggle").is_checked() is True
    assert page.evaluate(
        "() => getComputedStyle(document.querySelector('.second-mode-toggle')).display"
    ) == "flex"
    assert page.evaluate("() => document.getElementById('digitalLabel').textContent") == ""
    assert page.evaluate("() => document.getElementById('digitalMeta').hidden") is True


def test_digital_seconds_hide(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"seconds": "hide"})
    assert digital_text(page) == "12:00"
    assert page.evaluate("() => getComputedStyle(document.querySelector('.second-mode-toggle')).display") == "none"
    assert page.evaluate("() => document.getElementById('timeAnnounce').textContent") == "The time is 12:00"


def test_digital_seconds_hidden_updates_once_at_next_minute_boundary(
    page: Page,
    app_url: str,
) -> None:
    open_digital(
        page,
        app_url,
        {"seconds": "hide"},
        fixed_time="2026-01-01T12:00:59.500Z",
    )
    time = page.locator("#digitalTime")
    assert time.text_content() == "12:00"
    assert time.get_attribute("datetime") == "12:00:59"
    assert page.locator("#timeAnnounce").text_content() == "The time is 12:00"

    set_test_time(page, "2026-01-01T12:01:00.000Z", advance_milliseconds=500)

    assert time.text_content() == "12:01"
    assert time.get_attribute("datetime") == "12:01:00"
    assert page.locator("#timeAnnounce").text_content() == "The time is 12:01"


def test_digital_seconds_toggle_hides_seconds(page: Page, app_url: str) -> None:
    open_digital(page, app_url)
    page.evaluate("() => document.getElementById('secondModeToggle').click()")
    assert digital_text(page) == "12:00"


@pytest.mark.parametrize(
    ("fixed_time", "expected_text", "expected_announcement"),
    [
        pytest.param("2026-01-01T00:00:00Z", "12:00:00 AM", "The time is 12:00 AM", id="midnight"),
        pytest.param("2026-01-01T12:00:00Z", "12:00:00 PM", "The time is 12:00 PM", id="noon"),
    ],
)
def test_digital_format_12_hour(
    page: Page,
    app_url: str,
    fixed_time: str,
    expected_text: str,
    expected_announcement: str,
) -> None:
    open_digital(page, app_url, {"format": "12"}, fixed_time=fixed_time)
    assert digital_text(page) == expected_text
    assert page.evaluate("() => document.getElementById('timeAnnounce').textContent") == expected_announcement


def test_digital_timezone(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"tz": "Europe/Helsinki"})
    assert digital_text(page) == "14:00:00"
    assert page.evaluate("() => document.getElementById('digitalLabel').textContent") == "Helsinki"
    assert page.evaluate("() => document.title") == "clocksimulator.com - Digital - Europe/Helsinki"


def test_digital_embed_mode_defaults_dark_and_hides_controls(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"embed": "true"})
    assert page.evaluate("() => document.body.classList.contains('embed-mode')") is True
    assert page.evaluate("() => document.documentElement.classList.contains('dark-mode')") is True
    assert page.evaluate("() => document.querySelector('.toggle-wrapper').offsetWidth") == 0


def test_digital_daynight_show(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"daynight": "show"})
    state = page.evaluate("() => document.getElementById('dayNightIcon').dataset.state")
    assert state == "day"
    assert page.evaluate("() => document.getElementById('digitalLabel').hidden") is True
    assert page.evaluate("() => document.getElementById('digitalMeta').hidden") is False
    assert page.evaluate("() => !!document.querySelector('#dayNightIcon svg .daynight-sun')") is True
    assert page.evaluate("() => getComputedStyle(document.querySelector('#dayNightIcon .daynight-sun')).display") == "block"
    assert page.evaluate("() => getComputedStyle(document.querySelector('#dayNightIcon .daynight-moon')).display") == "none"


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


def test_digital_dashboard_live_region_remains_accessible(page: Page, app_url: str) -> None:
    open_digital(
        page,
        app_url,
        {"tz": "UTC,Asia/Kathmandu"},
        fixed_time="2026-01-01T12:00:15.250Z",
    )
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
    assert ":00:15" not in result["announcement"]

    initial_visible = page.locator(".digital-grid .digital-time").all_text_contents()
    observe_time_announcements(page)
    set_test_time(page, "2026-01-01T12:00:16.250Z", advance_milliseconds=1000)

    assert page.locator(".digital-grid .digital-time").all_text_contents() != initial_visible
    assert page.evaluate("() => document.getElementById('timeAnnounce').textContent") == result["announcement"]
    assert page.evaluate("() => window.__timeAnnounceMutationCount") == 0


def test_digital_dashboard_labels_and_times(page: Page, app_url: str) -> None:
    open_digital(page, app_url, {"tz": "UTC,Europe/Helsinki,America/New_York"})
    result = page.evaluate("""() => ({
        labels: Array.from(document.querySelectorAll('.digital-grid .digital-label')).map(el => el.textContent),
        times: Array.from(document.querySelectorAll('.digital-grid .digital-time')).map(el => el.textContent)
    })""")
    assert result["labels"] == ["UTC", "Helsinki", "New York"]
    assert result["times"] == ["12:00:00", "14:00:00", "07:00:00"]
    assert page.locator(".digital-grid").count() == 1
    assert page.locator(".digital-grid .digital-cell").count() == 3
    assert page.locator("#digitalContainer").is_hidden() is True


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
            text: el.textContent,
            scrollWidth: el.scrollWidth,
            clientWidth: el.clientWidth,
            fontSize: parseFloat(getComputedStyle(el).fontSize)
        }))
    })""")
    assert [t["text"] for t in result["times"]] == ["12:00 PM", "02:00 PM", "07:00 AM"]
    assert result["scrollWidth"] <= result["innerWidth"] + 1
    assert len(result["times"]) == 3
    assert all(t["scrollWidth"] <= t["clientWidth"] + 1 for t in result["times"])
    assert all(t["fontSize"] >= 24 for t in result["times"])


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
