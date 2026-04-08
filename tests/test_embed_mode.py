from __future__ import annotations

import time

from playwright.sync_api import Page

from tests.helpers import open_page, assert_screenshot


def test_embed_mode_adds_embed_mode_class(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true"})
    assert page.evaluate("() => document.body.classList.contains('embed-mode')") is True


def test_embed_mode_hides_toggle_wrapper(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true"})
    wrapper_width = page.evaluate("() => document.querySelector('.toggle-wrapper').offsetWidth")
    assert wrapper_width == 0


def test_embed_mode_clock_container_full_size(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true"})
    width = page.evaluate("() => getComputedStyle(document.querySelector('.clock-container')).width")
    assert width != "0px"
    assert width != ""


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
    open_page(page, app_url, {"embed": "true", "tz": "Europe/Helsinki"})
    assert page.evaluate("() => document.body.classList.contains('embed-mode')") is True
    assert page.evaluate("() => !!document.getElementById('clock')") is True


def test_embed_mode_seconds_hide(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true", "seconds": "hide"})
    assert page.evaluate("() => document.getElementById('secondHand').style.display") == "none"


def test_embed_mode_seconds_smooth(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true", "seconds": "smooth"})
    toggle_checked = page.evaluate("() => document.getElementById('secondModeToggle').checked")
    assert toggle_checked is False


def test_embed_mode_border_hide(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true", "border": "hide"})
    assert page.evaluate("() => document.getElementById('clockBorder').getAttribute('stroke')") == "none"


def test_embed_mode_numbers_hide(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true", "numbers": "hide"})
    assert page.evaluate("() => document.getElementById('numbers').style.display") == "none"


def test_embed_mode_shadows_disabled(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true", "shadows": "false"})
    assert page.evaluate("() => document.getElementById('hourHand').hasAttribute('filter')") is False


def test_embed_mode_daynight_show(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true", "daynight": "show"})
    hour = page.evaluate("() => new Date().getHours()")
    is_day = 6 <= hour < 18
    if is_day:
        assert page.evaluate("() => document.getElementById('sunIcon').getAttribute('display')") == "inline"
    else:
        assert page.evaluate("() => document.getElementById('moonIcon').getAttribute('display')") == "inline"


def test_embed_mode_all_params_combined(page: Page, app_url: str) -> None:
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
    assert page.evaluate("() => document.body.classList.contains('embed-mode')") is True
    assert page.evaluate("() => document.documentElement.classList.contains('dark-mode')") is False
    assert page.evaluate("() => document.documentElement.classList.contains('transparent-mode')") is False
    assert page.evaluate("() => document.getElementById('secondHand').style.display") == "none"
    assert page.evaluate("() => document.getElementById('clockBorder').getAttribute('stroke')") == "none"
    assert page.evaluate("() => document.getElementById('numbers').style.display") == "none"
    assert page.evaluate("() => document.getElementById('hourHand').hasAttribute('filter')") is False


def test_embed_mode_wakelock_hidden(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true"})
    wake_lock_hidden = page.evaluate("() => document.getElementById('wakeLockLabel').hasAttribute('hidden')")
    assert wake_lock_hidden is True


def test_embed_mode_overlays_not_visible(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true"})
    result = page.evaluate("""() => {
        var ids = ['embedOverlay', 'dashboardOverlay', 'helpOverlay'];
        var visible = [];
        for (var i = 0; i < ids.length; i++) {
            var el = document.getElementById(ids[i]);
            if (el && el.classList.contains('visible')) visible.push(ids[i]);
        }
        return visible;
    }""")
    assert result == []


def test_embed_mode_about_bubble_hidden(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true"})
    about_visible = page.evaluate("""() => {
        var bubble = document.getElementById('aboutBubble');
        var btn = document.querySelector('.about-btn');
        return {
            bubbleVisible: bubble && bubble.classList.contains('visible'),
            btnWidth: btn ? btn.offsetWidth : 0
        };
    }""")
    assert about_visible["bubbleVisible"] is not True
    assert about_visible["btnWidth"] == 0


def test_embed_mode_burnin_disabled(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true"})
    time.sleep(0.2)
    transform = page.evaluate("() => document.querySelector('.clock-container').style.transform")
    assert transform == "" or transform == "none"


def test_embed_mode_clock_container_no_transition(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true"})
    transition = page.evaluate("() => getComputedStyle(document.querySelector('.clock-container')).transition")
    assert "none" in transition


def test_embed_mode_escape_key_no_effect(page: Page, app_url: str) -> None:
    open_page(page, app_url, {"embed": "true"})
    page.keyboard.press("Escape")
    result = page.evaluate("""() => {
        var overlays = document.querySelectorAll('.overlay');
        for (var i = 0; i < overlays.length; i++) {
            if (overlays[i].classList.contains('visible')) return false;
        }
        var bubble = document.getElementById('aboutBubble');
        if (bubble && bubble.classList.contains('visible')) return false;
        return true;
    }""")
    assert result is True


def test_embed_mode_visual_snapshot_dark(page: Page, app_url: str, update_snapshots: bool) -> None:
    open_page(page, app_url, {"embed": "true", "theme": "dark"})
    assert_screenshot(page, "embed-dark.png", update=update_snapshots)


def test_embed_mode_visual_snapshot_light(page: Page, app_url: str, update_snapshots: bool) -> None:
    open_page(page, app_url, {"embed": "true", "theme": "light"})
    assert_screenshot(page, "embed-light.png", update=update_snapshots)


def test_embed_mode_visual_snapshot_transparent(page: Page, app_url: str, update_snapshots: bool) -> None:
    open_page(page, app_url, {"embed": "true", "theme": "transparent"})
    assert_screenshot(page, "embed-transparent.png", update=update_snapshots)


def test_embed_mode_visual_snapshot_daynight(page: Page, app_url: str, update_snapshots: bool) -> None:
    open_page(page, app_url, {"embed": "true", "theme": "dark", "daynight": "show"})
    assert_screenshot(page, "embed-daynight.png", update=update_snapshots)


def test_embed_mode_visual_snapshot_seconds_hide(page: Page, app_url: str, update_snapshots: bool) -> None:
    open_page(page, app_url, {"embed": "true", "theme": "dark", "seconds": "hide"})
    assert_screenshot(page, "embed-seconds-hide.png", update=update_snapshots)


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
    assert_screenshot(page, "embed-all-params.png", update=update_snapshots)
