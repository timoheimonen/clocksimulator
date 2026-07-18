from __future__ import annotations

import pytest
from playwright.sync_api import Page

from tests.helpers import open_page


PAGE_CASES = [
    pytest.param("", "Analog clock", ".clock-container", id="analog"),
    pytest.param("/digital/", "Digital clock", ".digital-container", id="digital"),
]


def open_clock(
    page: Page,
    app_url: str,
    path: str,
    params: dict[str, str] | None = None,
) -> None:
    open_page(page, app_url, params=params, path=path)


def mock_wake_lock(page: Page) -> None:
    page.add_init_script("""
        Object.defineProperty(navigator, 'wakeLock', {
            configurable: true,
            value: {
                request: function () {
                    return Promise.resolve({
                        addEventListener: function () {},
                        release: function () { return Promise.resolve(); }
                    });
                }
            }
        });
    """)


def instrument_intervals(page: Page) -> None:
    page.add_init_script("""
        (function () {
            var originalSetInterval = window.setInterval;
            window.__intervalDelays = [];
            window.setInterval = function () {
                window.__intervalDelays.push(Number(arguments[1]));
                return originalSetInterval.apply(window, arguments);
            };
        })();
    """)


def active_focus_indicator(page: Page) -> dict[str, str]:
    return page.evaluate("""() => {
        var active = document.activeElement;
        var target = active;
        if (active && active.matches('.toggle-label input')) {
            target = active.parentElement.querySelector('.toggle-slider');
        }
        var style = getComputedStyle(target);
        return {
            activeId: active ? active.id : '',
            outlineStyle: style.outlineStyle,
            outlineWidth: style.outlineWidth,
            outlineColor: style.outlineColor,
            boxShadow: style.boxShadow
        };
    }""")


def assert_visible_focus_indicator(page: Page) -> None:
    indicator = active_focus_indicator(page)
    assert indicator["outlineStyle"] != "none"
    assert float(indicator["outlineWidth"].removesuffix("px")) >= 2
    assert indicator["outlineColor"] not in {"transparent", "rgba(0, 0, 0, 0)"}
    assert indicator["boxShadow"] != "none"


def reset_dialog_focus(page: Page) -> None:
    page.keyboard.press("Shift+Tab")
    page.keyboard.press("Tab")


def assert_dialog_tab_order(page: Page, overlay_id: str) -> None:
    count = page.evaluate(
        """overlayId => {
            var overlay = document.getElementById(overlayId);
            return Array.from(overlay.querySelectorAll(
                'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])'
            )).filter(function (el) {
                return !el.disabled && el.getClientRects().length > 0;
            }).length;
        }""",
        overlay_id,
    )
    assert count > 0
    for index in range(count):
        is_expected = page.evaluate(
            """({ overlayId, index }) => {
                var overlay = document.getElementById(overlayId);
                var focusable = Array.from(overlay.querySelectorAll(
                    'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])'
                )).filter(function (el) {
                    return !el.disabled && el.getClientRects().length > 0;
                });
                return document.activeElement === focusable[index];
            }""",
            {"overlayId": overlay_id, "index": index},
        )
        if not is_expected:
            focus_state = page.evaluate(
                """({ overlayId, index }) => {
                    var overlay = document.getElementById(overlayId);
                    var focusable = Array.from(overlay.querySelectorAll(
                        'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])'
                    )).filter(function (el) {
                        return !el.disabled && el.getClientRects().length > 0;
                    });
                    var active = document.activeElement;
                    var expected = focusable[index];
                    return {
                        actual: active.id || active.textContent.trim().slice(0, 40),
                        expected: expected.id || expected.textContent.trim().slice(0, 40),
                        index: index
                    };
                }""",
                {"overlayId": overlay_id, "index": index},
            )
            pytest.fail(str(focus_state))
        assert page.evaluate("() => document.activeElement.matches(':focus-visible')") is True
        assert_visible_focus_indicator(page)
        if index < count - 1:
            page.keyboard.press("Tab")
    page.keyboard.press("Tab")
    assert page.evaluate(
        """overlayId => {
            var focusable = document.getElementById(overlayId).querySelectorAll(
                'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])'
            );
            return document.activeElement === focusable[0];
        }""",
        overlay_id,
    ) is True
    page.keyboard.press("Shift+Tab")
    assert page.evaluate(
        """overlayId => {
            var focusable = document.getElementById(overlayId).querySelectorAll(
                'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])'
            );
            return document.activeElement === focusable[focusable.length - 1];
        }""",
        overlay_id,
    ) is True


@pytest.mark.parametrize(("path", "title", "container_selector"), PAGE_CASES)
@pytest.mark.parametrize("theme", ["light", "dark", "transparent"])
def test_keyboard_focus_ring_visible_on_theme_switch(
    page: Page,
    app_url: str,
    path: str,
    title: str,
    container_selector: str,
    theme: str,
) -> None:
    open_clock(page, app_url, path, {"theme": theme})
    page.keyboard.press("Tab")
    page.wait_for_function("() => !document.querySelector('.toggle-wrapper').hasAttribute('inert')")
    if page.evaluate("() => document.activeElement.id") != "themeToggle":
        page.keyboard.press("Tab")
    assert page.evaluate("() => document.activeElement.id") == "themeToggle"
    assert page.evaluate("() => document.querySelector('.toggle-wrapper').classList.contains('visible')") is True
    assert page.evaluate("() => document.getElementById('themeToggle').matches(':focus-visible')") is True
    assert_visible_focus_indicator(page)


@pytest.mark.parametrize(("path", "title", "container_selector"), PAGE_CASES)
def test_mouse_click_does_not_show_switch_focus_ring(
    page: Page,
    app_url: str,
    path: str,
    title: str,
    container_selector: str,
) -> None:
    open_clock(page, app_url, path)
    page.mouse.move(20, 20)
    page.wait_for_function("() => !document.querySelector('.toggle-wrapper').hasAttribute('inert')")
    page.locator(".theme-toggle").click()
    result = page.evaluate("""() => {
        var input = document.getElementById('themeToggle');
        var slider = input.parentElement.querySelector('.toggle-slider');
        return {
            focusVisible: input.matches(':focus-visible'),
            outlineStyle: getComputedStyle(slider).outlineStyle
        };
    }""")
    assert result == {"focusVisible": False, "outlineStyle": "none"}


@pytest.mark.parametrize(("path", "title", "container_selector"), PAGE_CASES)
def test_all_switches_and_about_button_have_keyboard_focus(
    page: Page,
    app_url: str,
    path: str,
    title: str,
    container_selector: str,
) -> None:
    mock_wake_lock(page)
    open_clock(page, app_url, path)
    expected_ids = ["themeToggle", "wakeLockToggle", "secondModeToggle", "aboutBtn"]
    for expected_id in expected_ids:
        page.keyboard.press("Tab")
        assert page.evaluate("() => document.activeElement.id") == expected_id
        assert_visible_focus_indicator(page)

    page.keyboard.press("Enter")
    assert page.get_attribute("#aboutBtn", "aria-expanded") == "true"
    for _ in range(10):
        page.keyboard.press("Tab")
        assert_visible_focus_indicator(page)
        if page.evaluate("() => document.activeElement.id") == "saveSettingsToggle":
            break
    assert page.evaluate("() => document.activeElement.id") == "saveSettingsToggle"


@pytest.mark.parametrize(("path", "title", "container_selector"), PAGE_CASES)
def test_keyboard_can_open_embed_dialog_from_about_menu(
    page: Page,
    app_url: str,
    path: str,
    title: str,
    container_selector: str,
) -> None:
    mock_wake_lock(page)
    open_clock(page, app_url, path)
    for _ in range(4):
        page.keyboard.press("Tab")
    assert page.evaluate("() => document.activeElement.id") == "aboutBtn"
    page.keyboard.press("Enter")
    page.keyboard.press("Tab")
    assert page.evaluate("() => document.activeElement.id") == "embedLink"
    page.keyboard.press("Enter")
    assert page.get_attribute("#embedOverlay", "aria-hidden") == "false"
    assert page.evaluate("() => document.activeElement.id") == "embedCloseBtn"
    assert_visible_focus_indicator(page)


@pytest.mark.parametrize(("path", "title", "container_selector"), PAGE_CASES)
def test_every_dialog_control_has_keyboard_focus_indicator(
    page: Page,
    app_url: str,
    path: str,
    title: str,
    container_selector: str,
) -> None:
    open_clock(page, app_url, path)
    dialogs = [
        ("embedLink", "embedOverlay"),
        ("dashboardLink", "dashboardOverlay"),
        ("helpLink", "helpOverlay"),
    ]
    for link_id, overlay_id in dialogs:
        page.evaluate("linkId => document.getElementById(linkId).click()", link_id)
        page.wait_for_function(
            "overlayId => document.getElementById(overlayId).classList.contains('visible')",
            arg=overlay_id,
        )
        if overlay_id == "dashboardOverlay":
            page.evaluate("""() => {
                var input = document.getElementById('dashboardTzInput');
                input.value = 'UTC';
                document.getElementById('dashboardAddBtn').click();
            }""")
        reset_dialog_focus(page)
        assert_dialog_tab_order(page, overlay_id)
        page.keyboard.press("Escape")
        assert page.get_attribute("#" + overlay_id, "aria-hidden") == "true"


@pytest.mark.parametrize(("path", "title", "container_selector"), PAGE_CASES)
def test_help_url_examples_are_named_focusable_regions(
    page: Page,
    app_url: str,
    path: str,
    title: str,
    container_selector: str,
) -> None:
    open_clock(page, app_url, path)
    page.evaluate("() => document.getElementById('helpLink').click()")
    regions = page.locator("#helpOverlay pre")
    expected_names = ["Timezone URL examples", "Dashboard URL examples"]
    assert regions.count() == 2
    assert regions.evaluate_all(
        """elements => elements.map(function (element) {
            return {
                tabindex: element.getAttribute('tabindex'),
                role: element.getAttribute('role'),
                name: element.getAttribute('aria-label')
            };
        })"""
    ) == [
        {"tabindex": "0", "role": "region", "name": expected_names[0]},
        {"tabindex": "0", "role": "region", "name": expected_names[1]},
    ]
    for name in expected_names:
        assert page.get_by_role("region", name=name, exact=True).count() == 1


@pytest.mark.parametrize(("path", "title", "container_selector"), PAGE_CASES)
@pytest.mark.parametrize("theme", ["light", "dark", "transparent"])
def test_help_url_examples_scroll_with_keyboard_on_mobile(
    page: Page,
    app_url: str,
    path: str,
    title: str,
    container_selector: str,
    theme: str,
) -> None:
    page.set_viewport_size({"width": 320, "height": 640})
    open_clock(page, app_url, path, {"theme": theme})
    page.evaluate("() => document.getElementById('helpLink').click()")
    expected_names = ["Timezone URL examples", "Dashboard URL examples"]
    focused_names = []
    for expected_name in expected_names:
        for _ in range(20):
            page.keyboard.press("Tab")
            active = page.evaluate("""() => ({
                tagName: document.activeElement.tagName,
                name: document.activeElement.getAttribute('aria-label') || ''
            })""")
            if active["tagName"] == "PRE":
                break
        assert active == {"tagName": "PRE", "name": expected_name}
        focused_names.append(active["name"])
        assert page.evaluate(
            "() => document.activeElement.scrollWidth > document.activeElement.clientWidth"
        ) is True
        assert page.evaluate("() => document.activeElement.matches(':focus-visible')") is True
        assert_visible_focus_indicator(page)
        for _ in range(3):
            page.keyboard.press("ArrowRight")
        page.wait_for_function("() => document.activeElement.scrollLeft > 0")
    assert focused_names == expected_names


@pytest.mark.parametrize(("path", "title", "container_selector"), PAGE_CASES)
def test_preview_iframes_stay_out_of_dialog_tab_order(
    page: Page,
    app_url: str,
    path: str,
    title: str,
    container_selector: str,
) -> None:
    open_clock(page, app_url, path)
    assert page.evaluate("""() => [
        document.getElementById('embedPreview').getAttribute('tabindex'),
        document.getElementById('dashboardPreview').getAttribute('tabindex')
    ]""") == ["-1", "-1"]


@pytest.mark.parametrize(("path", "title", "container_selector"), PAGE_CASES)
def test_dashboard_timezone_has_visible_associated_label_on_mobile(
    page: Page,
    app_url: str,
    path: str,
    title: str,
    container_selector: str,
) -> None:
    page.set_viewport_size({"width": 320, "height": 640})
    open_clock(page, app_url, path)
    page.keyboard.press("Tab")
    page.wait_for_function("() => !document.querySelector('.toggle-wrapper').hasAttribute('inert')")
    page.locator("#aboutBtn").click()
    page.locator("#dashboardLink").click()
    page.wait_for_function("""() => {
        var transform = getComputedStyle(document.querySelector('#dashboardOverlay .modal-panel')).transform;
        return transform === 'none' || transform === 'matrix(1, 0, 0, 1, 0, 0)';
    }""")
    result = page.evaluate("""() => {
        var panel = document.querySelector('#dashboardOverlay .modal-panel');
        var label = document.querySelector('label[for="dashboardTzInput"]');
        var input = document.getElementById('dashboardTzInput');
        var addButton = document.getElementById('dashboardAddBtn');
        var panelRect = panel.getBoundingClientRect();
        var inputRect = input.getBoundingClientRect();
        var addRect = addButton.getBoundingClientRect();
        var panelStyle = getComputedStyle(panel);
        var contentLeft = panelRect.left + parseFloat(panelStyle.paddingLeft);
        var contentRight = panelRect.right - parseFloat(panelStyle.paddingRight);
        return {
            labelCount: document.querySelectorAll('label[for="dashboardTzInput"]').length,
            text: label.textContent.trim(),
            visible: label.getClientRects().length > 0,
            associated: Array.from(input.labels).includes(label),
            rowInsidePanel: inputRect.left >= contentLeft - 1 && addRect.right <= contentRight + 1,
            noHorizontalOverflow: panel.scrollWidth <= panel.clientWidth,
            scrollTop: panel.scrollTop,
            geometry: {
                contentLeft: contentLeft,
                contentRight: contentRight,
                inputLeft: inputRect.left,
                addRight: addRect.right
            }
        };
    }""")
    assert result["labelCount"] == 1
    assert result["text"] == "Timezone"
    assert result["visible"] is True
    assert result["associated"] is True
    assert result["rowInsidePanel"] is True, result["geometry"]
    assert result["noHorizontalOverflow"] is True
    assert result["scrollTop"] == 0


@pytest.mark.parametrize(("path", "title", "container_selector"), PAGE_CASES)
def test_generated_iframe_has_descriptive_title(
    page: Page,
    app_url: str,
    path: str,
    title: str,
    container_selector: str,
) -> None:
    open_clock(page, app_url, path)
    page.evaluate("() => document.getElementById('embedLink').click()")
    page.wait_for_function("() => document.getElementById('embedCode').value !== ''")
    result = page.evaluate("""() => {
        var template = document.createElement('template');
        template.innerHTML = document.getElementById('embedCode').value;
        var frames = template.content.querySelectorAll('iframe');
        return {
            count: frames.length,
            title: frames.length ? frames[0].getAttribute('title') : null
        };
    }""")
    assert result == {"count": 1, "title": title}


@pytest.mark.parametrize(("path", "title", "container_selector"), PAGE_CASES)
def test_reduced_motion_removes_nonessential_transitions(
    page: Page,
    app_url: str,
    path: str,
    title: str,
    container_selector: str,
) -> None:
    page.emulate_media(reduced_motion="reduce")
    open_clock(page, app_url, path)
    result = page.evaluate(
        """containerSelector => {
            var targets = [
                document.body,
                document.querySelector('.toggle-wrapper'),
                document.querySelector('.toggle-label'),
                document.querySelector('.toggle-slider'),
                document.querySelector('.theme-icon'),
                document.querySelector('.about-btn'),
                document.querySelector('.about-bubble'),
                document.querySelector(containerSelector),
                document.querySelector('.overlay'),
                document.querySelector('.modal-panel'),
                document.querySelector('.modal-panel-close'),
                document.querySelector('.embed-copy-btn'),
                document.querySelector('.dashboard-add-btn')
            ];
            var durations = targets.map(function (target) {
                return getComputedStyle(target).transitionDuration;
            });
            durations.push(getComputedStyle(document.querySelector('.toggle-slider'), '::before').transitionDuration);
            return durations;
        }""",
        container_selector,
    )
    assert all(all(float(value.removesuffix("s")) == 0 for value in duration.split(", ")) for duration in result)


@pytest.mark.parametrize(
    ("path", "grid_selector"),
    [
        pytest.param("", ".clock-grid", id="analog"),
        pytest.param("/digital/", ".digital-grid", id="digital"),
    ],
)
def test_reduced_motion_removes_dashboard_transition(
    page: Page,
    app_url: str,
    path: str,
    grid_selector: str,
) -> None:
    page.emulate_media(reduced_motion="reduce")
    open_clock(page, app_url, path, {"tz": "UTC,Europe/Helsinki"})
    duration = page.evaluate(
        "selector => getComputedStyle(document.querySelector(selector)).transitionDuration",
        grid_selector,
    )
    assert all(float(value.strip().removesuffix("s")) == 0 for value in duration.split(","))


@pytest.mark.parametrize(
    ("path", "params", "container_selector"),
    [
        pytest.param("", {"embed": "true"}, ".clock-container", id="analog-single"),
        pytest.param(
            "",
            {"embed": "true", "tz": "UTC,Europe/Helsinki"},
            ".clock-grid",
            id="analog-dashboard",
        ),
        pytest.param("/digital/", {"embed": "true"}, ".digital-container", id="digital-single"),
        pytest.param(
            "/digital/",
            {"embed": "true", "tz": "UTC,Europe/Helsinki"},
            ".digital-grid",
            id="digital-dashboard",
        ),
    ],
)
def test_embed_transition_remains_disabled_without_reduced_motion(
    page: Page,
    app_url: str,
    path: str,
    params: dict[str, str],
    container_selector: str,
) -> None:
    page.emulate_media(reduced_motion="no-preference")
    open_clock(page, app_url, path, params)
    duration = page.evaluate(
        "selector => getComputedStyle(document.querySelector(selector)).transitionDuration",
        container_selector,
    )
    assert all(float(value.strip().removesuffix("s")) == 0 for value in duration.split(","))


@pytest.mark.parametrize(("path", "title", "container_selector"), PAGE_CASES)
def test_normal_motion_keeps_transitions(
    page: Page,
    app_url: str,
    path: str,
    title: str,
    container_selector: str,
) -> None:
    page.emulate_media(reduced_motion="no-preference")
    open_clock(page, app_url, path)
    durations = page.evaluate(
        """containerSelector => ({
            container: getComputedStyle(document.querySelector(containerSelector)).transitionDuration,
            modal: getComputedStyle(document.querySelector('.modal-panel')).transitionDuration
        })""",
        container_selector,
    )
    assert float(durations["container"].split(",")[0].strip().removesuffix("s")) > 0
    assert float(durations["modal"].split(",")[0].strip().removesuffix("s")) > 0


@pytest.mark.parametrize(("path", "title", "container_selector"), PAGE_CASES)
@pytest.mark.parametrize(
    ("params", "reduced_motion", "burnin_timer_expected"),
    [
        pytest.param({}, "no-preference", True, id="normal"),
        pytest.param({"burnin": "false"}, "no-preference", False, id="disabled"),
        pytest.param({"burnin": "true"}, "reduce", False, id="reduced-motion"),
        pytest.param({"embed": "true", "burnin": "true"}, "no-preference", False, id="embed"),
    ],
)
def test_burnin_interval_respects_motion_and_embed_mode(
    page: Page,
    app_url: str,
    path: str,
    title: str,
    container_selector: str,
    params: dict[str, str],
    reduced_motion: str,
    burnin_timer_expected: bool,
) -> None:
    page.emulate_media(reduced_motion=reduced_motion)
    instrument_intervals(page)
    open_clock(page, app_url, path, params)
    has_burnin_timer = page.evaluate("() => window.__intervalDelays.includes(600000)")
    assert has_burnin_timer is burnin_timer_expected


@pytest.mark.parametrize(
    ("path", "clock_kind"),
    [
        pytest.param("", "analog", id="analog"),
        pytest.param("/digital/", "digital", id="digital"),
    ],
)
def test_reduced_motion_keeps_clock_time_updating(
    page: Page,
    app_url: str,
    path: str,
    clock_kind: str,
) -> None:
    page.emulate_media(reduced_motion="reduce")
    open_clock(page, app_url, path)
    initial = page.evaluate("""kind => kind === 'analog'
        ? document.getElementById('minuteHand').style.transform
        : document.getElementById('digitalTime').textContent
    """, clock_kind)
    page.evaluate("() => window.__setMockDate('2026-01-01T12:01:00Z')")
    page.wait_for_function(
        """({ kind, initial }) => {
            var current = kind === 'analog'
                ? document.getElementById('minuteHand').style.transform
                : document.getElementById('digitalTime').textContent;
            return current !== initial;
        }""",
        arg={"kind": clock_kind, "initial": initial},
    )
