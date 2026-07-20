from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page

from tests.helpers import (
    install_timer_probe,
    install_visibility_mock,
    open_page,
    press_tab,
    set_test_time,
)


PAGE_CASES = [
    pytest.param("", "Analog clock", ".clock-container", id="analog"),
    pytest.param("/digital/", "Digital clock", ".digital-container", id="digital"),
]

DIALOG_CASES = [
    pytest.param("embedLink", "embedOverlay", "embedCloseBtn", id="embed"),
    pytest.param(
        "dashboardLink",
        "dashboardOverlay",
        "dashboardCloseBtn",
        id="dashboard",
    ),
    pytest.param("helpLink", "helpOverlay", "helpCloseBtn", id="help"),
]

pytestmark = pytest.mark.accessibility

BURNIN_CASES = [
    pytest.param("", {}, ".clock-container", id="analog-single"),
    pytest.param(
        "",
        {"tz": "UTC,Asia/Tokyo"},
        ".clock-grid",
        id="analog-dashboard",
    ),
    pytest.param("/digital/", {}, ".digital-container", id="digital-single"),
    pytest.param(
        "/digital/",
        {"tz": "UTC,Asia/Tokyo"},
        ".digital-grid",
        id="digital-dashboard",
    ),
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


def suppress_document_css_motion(page: Page) -> None:
    page.add_style_tag(
        content=(
            "*,:before,:after {"
            "transition-duration: 0s !important;"
            "transition-delay: 0s !important;"
            "animation-duration: 0s !important;"
            "animation-delay: 0s !important;"
            "}"
        )
    )


def active_focus_indicator(page: Page) -> dict[str, object]:
    return page.evaluate("""() => {
        var active = document.activeElement;
        var target = active;
        if (active && active.matches('.toggle-label input')) {
            target = active.parentElement.querySelector('.toggle-slider');
        }
        var ancestor = target ? target.parentElement : null;
        var adjacentColor = '';
        while (ancestor) {
            var candidate = getComputedStyle(ancestor).backgroundColor;
            if (candidate && candidate !== 'transparent' &&
                candidate !== 'rgba(0, 0, 0, 0)') {
                adjacentColor = candidate;
                break;
            }
            ancestor = ancestor.parentElement;
        }
        if (!adjacentColor) adjacentColor = getComputedStyle(document.documentElement).backgroundColor;
        var style = getComputedStyle(target);
        return {
            activeId: active ? active.id : '',
            outlineStyle: style.outlineStyle,
            outlineWidth: style.outlineWidth,
            outlineOffset: style.outlineOffset,
            outlineColor: style.outlineColor,
            boxShadow: style.boxShadow,
            width: target ? target.getBoundingClientRect().width : 0,
            height: target ? target.getBoundingClientRect().height : 0,
            adjacentColor: adjacentColor
        };
    }""")


def split_css_layers(value: str) -> list[str]:
    layers = []
    start = 0
    depth = 0
    for index, character in enumerate(value):
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        elif character == "," and depth == 0:
            layers.append(value[start:index].strip())
            start = index + 1
    layers.append(value[start:].strip())
    return [layer for layer in layers if layer]


def rendered_contrast(foreground: str, background: str) -> float:
    foreground_color = parse_css_color(foreground)
    background_color = parse_css_color(background)
    rendered = composite_color(foreground_color, background_color)
    first_luminance = relative_luminance(rendered)
    second_luminance = relative_luminance(background_color)
    lighter = max(first_luminance, second_luminance)
    darker = min(first_luminance, second_luminance)
    return (lighter + 0.05) / (darker + 0.05)


def focus_indicator_results(indicator: dict[str, object]) -> dict[str, bool]:
    width = float(indicator["width"])
    height = float(indicator["height"])
    minimum_area = 4 * (width + height)
    outline_width = float(str(indicator["outlineWidth"]).removesuffix("px"))
    outline_offset = float(str(indicator["outlineOffset"]).removesuffix("px"))
    outline_inner_width = max(0, width + 2 * outline_offset)
    outline_inner_height = max(0, height + 2 * outline_offset)
    outline_area = (
        (outline_inner_width + 2 * outline_width)
        * (outline_inner_height + 2 * outline_width)
        - outline_inner_width * outline_inner_height
    )
    outline_visible = (
        indicator["outlineStyle"] != "none"
        and outline_area >= minimum_area
        and rendered_contrast(
            str(indicator["outlineColor"]), str(indicator["adjacentColor"])
        ) >= 3
    )
    shadow_visible = False
    for layer in split_css_layers(str(indicator["boxShadow"])):
        if layer == "none" or "inset" in layer:
            continue
        color_match = re.search(r"rgba?\([^)]*\)", layer)
        if not color_match:
            continue
        lengths = [
            float(value)
            for value in re.findall(
                r"(-?(?:\d+(?:\.\d*)?|\.\d+))px",
                layer[:color_match.start()] + layer[color_match.end():],
            )
        ]
        spread = lengths[3] if len(lengths) >= 4 else 0
        if spread <= 0:
            continue
        shadow_area = (
            (width + 2 * spread) * (height + 2 * spread) - width * height
        )
        if (
            shadow_area >= minimum_area
            and rendered_contrast(
                color_match.group(0), str(indicator["adjacentColor"])
            ) >= 3
        ):
            shadow_visible = True
            break
    return {"outline": outline_visible, "boxShadow": shadow_visible}


def assert_visible_focus_indicator(page: Page) -> None:
    indicator = active_focus_indicator(page)
    assert any(focus_indicator_results(indicator).values()), indicator


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
            press_tab(page)
    press_tab(page)
    assert page.evaluate(
        """overlayId => {
            var focusable = Array.from(document.getElementById(overlayId).querySelectorAll(
                'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])'
            )).filter(function (el) {
                return !el.disabled && el.getClientRects().length > 0;
            });
            return document.activeElement === focusable[0];
        }""",
        overlay_id,
    ) is True
    press_tab(page, reverse=True)
    assert page.evaluate(
        """overlayId => {
            var focusable = Array.from(document.getElementById(overlayId).querySelectorAll(
                'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])'
            )).filter(function (el) {
                return !el.disabled && el.getClientRects().length > 0;
            });
            return document.activeElement === focusable[focusable.length - 1];
        }""",
        overlay_id,
    ) is True


def install_dialog_listener_probe(page: Page) -> None:
    page.add_init_script("""
        (function () {
          var originalAdd = EventTarget.prototype.addEventListener;
          var originalRemove = EventTarget.prototype.removeEventListener;
          window.__dialogTrapListeners = {};
          EventTarget.prototype.addEventListener = function (type, listener, options) {
            if (type === 'keydown' && this.id && this.id.endsWith('Overlay')) {
              var state = window.__dialogTrapListeners[this.id] || {
                adds: 0,
                removes: 0,
                active: 0
              };
              state.adds += 1;
              state.active += 1;
              window.__dialogTrapListeners[this.id] = state;
            }
            return originalAdd.call(this, type, listener, options);
          };
          EventTarget.prototype.removeEventListener = function (type, listener, options) {
            if (type === 'keydown' && this.id && this.id.endsWith('Overlay')) {
              var state = window.__dialogTrapListeners[this.id];
              if (state) {
                state.removes += 1;
                state.active -= 1;
              }
            }
            return originalRemove.call(this, type, listener, options);
          };
        })();
    """)


def keyboard_open_about(page: Page) -> None:
    for expected_id in ["themeToggle", "wakeLockToggle", "secondModeToggle", "aboutBtn"]:
        press_tab(page)
        assert page.evaluate("() => document.activeElement.id") == expected_id
    page.keyboard.press("Enter")
    about = page.locator("#aboutBubble")
    assert about.get_attribute("role") == "dialog"
    assert about.get_attribute("aria-modal") == "false"
    assert about.get_attribute("aria-label") == "About"
    assert about.get_attribute("aria-hidden") == "false"
    assert about.evaluate("element => element.hasAttribute('inert')") is False


def keyboard_choose_dialog(page: Page, link_id: str) -> None:
    tab_counts = {"embedLink": 1, "dashboardLink": 3, "helpLink": 4}
    assert link_id in tab_counts
    for _ in range(tab_counts[link_id]):
        press_tab(page)
        assert page.locator("#aboutBubble").evaluate(
            "element => element.contains(document.activeElement)"
        ) is True
    assert page.evaluate("() => document.activeElement.id") == link_id
    page.keyboard.press("Enter")


def keyboard_open_dialog(page: Page, link_id: str) -> None:
    keyboard_open_about(page)
    keyboard_choose_dialog(page, link_id)


def keyboard_reopen_dialog(page: Page, link_id: str) -> None:
    page.locator("#aboutBtn").focus()
    page.keyboard.press("Enter")
    keyboard_choose_dialog(page, link_id)


def expected_dialog_name(path: str, overlay_id: str) -> str:
    if overlay_id == "embedOverlay":
        return "Embed this digital clock" if path else "Embed this analog clock"
    if overlay_id == "dashboardOverlay":
        return "Build dashboard"
    return "How to use"


def assert_dialog_open_state(
    page: Page,
    path: str,
    overlay_id: str,
    close_id: str,
) -> None:
    page.clock.run_for(1)
    overlay = page.locator("#" + overlay_id)
    expected_name = expected_dialog_name(path, overlay_id)
    assert page.get_by_role("dialog", name=expected_name, exact=True).count() == 1
    assert overlay.get_attribute("role") == "dialog"
    assert overlay.get_attribute("aria-modal") == "true"
    assert overlay.get_attribute("aria-hidden") == "false"
    assert overlay.evaluate("element => element.hasAttribute('inert')") is False
    assert page.evaluate("() => document.activeElement.id") == close_id
    assert page.locator("main").evaluate("element => element.hasAttribute('inert')") is True
    assert page.locator(".toggle-wrapper").evaluate(
        "element => element.hasAttribute('inert')"
    ) is True
    assert page.locator(".toggle-wrapper").get_attribute("aria-hidden") == "true"


def prepare_dialog_preview(page: Page, overlay_id: str) -> str | None:
    if overlay_id == "embedOverlay":
        page.wait_for_function(
            "() => document.getElementById('embedPreview').getAttribute('src') !== 'about:blank'"
        )
        return "embedPreview"
    if overlay_id == "dashboardOverlay":
        timezone_input = page.get_by_role("textbox", name="Timezone")
        timezone_input.fill("UTC")
        timezone_input.press("Enter")
        timezone_input.fill("Asia/Kathmandu")
        timezone_input.press("Enter")
        page.wait_for_function(
            "() => document.getElementById('dashboardPreview').getAttribute('src') !== 'about:blank'"
        )
        return "dashboardPreview"
    return None


def assert_dialog_closed_state(
    page: Page,
    overlay_id: str,
    preview_id: str | None,
) -> None:
    overlay = page.locator("#" + overlay_id)
    assert overlay.get_attribute("aria-hidden") == "true"
    assert overlay.evaluate("element => element.hasAttribute('inert')") is True
    assert page.locator("main").evaluate("element => element.hasAttribute('inert')") is False
    assert page.locator(".toggle-wrapper").evaluate(
        "element => element.hasAttribute('inert')"
    ) is False
    page.wait_for_function("() => document.activeElement.id === 'aboutBtn'")
    if preview_id:
        assert page.locator("#" + preview_id).get_attribute("src") == "about:blank"


def parse_css_color(value: str) -> tuple[float, float, float, float]:
    value = value.strip().lower()
    if value.startswith("#"):
        raw = value[1:]
        if len(raw) == 3:
            raw = "".join(character * 2 for character in raw)
        assert len(raw) == 6
        return (
            int(raw[0:2], 16),
            int(raw[2:4], 16),
            int(raw[4:6], 16),
            1.0,
        )
    match = re.fullmatch(
        r"rgba?\(\s*([\d.]+)[, ]+\s*([\d.]+)[, ]+\s*([\d.]+)(?:\s*[,/]\s*([\d.]+))?\s*\)",
        value,
    )
    assert match, value
    return (
        float(match.group(1)),
        float(match.group(2)),
        float(match.group(3)),
        float(match.group(4) or 1),
    )


def composite_color(
    foreground: tuple[float, float, float, float],
    background: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    alpha = foreground[3] + background[3] * (1 - foreground[3])
    return tuple(
        (foreground[index] * foreground[3]
        + background[index] * background[3] * (1 - foreground[3]))
        / alpha
        for index in range(3)
    ) + (alpha,)


def relative_luminance(color: tuple[float, float, float, float]) -> float:
    channels = []
    for component in color[:3]:
        normalized = component / 255
        channels.append(
            normalized / 12.92
            if normalized <= 0.04045
            else ((normalized + 0.055) / 1.055) ** 2.4
        )
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(first: str, second: str) -> float:
    first_luminance = relative_luminance(parse_css_color(first))
    second_luminance = relative_luminance(parse_css_color(second))
    lighter = max(first_luminance, second_luminance)
    darker = min(first_luminance, second_luminance)
    return (lighter + 0.05) / (darker + 0.05)


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
    press_tab(page)
    page.wait_for_function("() => !document.querySelector('.toggle-wrapper').hasAttribute('inert')")
    if page.evaluate("() => document.activeElement.id") != "themeToggle":
        press_tab(page)
    assert page.evaluate("() => document.activeElement.id") == "themeToggle"
    assert page.evaluate("() => document.querySelector('.toggle-wrapper').classList.contains('visible')") is True
    assert page.evaluate("() => document.getElementById('themeToggle').matches(':focus-visible')") is True
    assert_visible_focus_indicator(page)


@pytest.mark.parametrize(("path", "title", "container_selector"), PAGE_CASES)
def test_pointer_activation_does_not_force_keyboard_focus_indicator(
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
    assert page.evaluate(
        "() => document.getElementById('themeToggle').matches(':focus-visible')"
    ) is False
    indicator = active_focus_indicator(page)
    assert not any(focus_indicator_results(indicator).values()), indicator


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
        press_tab(page)
        assert page.evaluate("() => document.activeElement.id") == expected_id
        assert_visible_focus_indicator(page)

    page.keyboard.press("Enter")
    assert page.get_attribute("#aboutBtn", "aria-expanded") == "true"
    for _ in range(10):
        press_tab(page)
        assert_visible_focus_indicator(page)
        if page.evaluate("() => document.activeElement.id") == "saveSettingsToggle":
            break
    assert page.evaluate("() => document.activeElement.id") == "saveSettingsToggle"


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
            press_tab(page)
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
    suppress_document_css_motion(page)
    press_tab(page)
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
    assert len(result) == 14
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
def test_ui_normal_motion_retains_transitions(
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


@pytest.mark.parametrize(("path", "params", "container_selector"), BURNIN_CASES)
def test_burnin_interval_respects_motion_and_embed_mode(
    page: Page,
    app_url: str,
    path: str,
    params: dict[str, str],
    container_selector: str,
) -> None:
    page.emulate_media(reduced_motion="no-preference")
    clock = install_timer_probe(page, manual=True)
    install_visibility_mock(page)
    open_clock(page, app_url, path, params)

    burnin_records = [
        record for record in clock.timers()
        if record.kind == "interval" and record.delay == 600000
    ]
    assert len(burnin_records) == 1
    assert burnin_records[0].cleared is False

    clock.run_timer(burnin_records[0].timer_id)
    assert page.locator(container_selector).evaluate(
        "element => element.style.transform"
    ) == "translate(6px, 0px)"

    page.evaluate("() => window.__setTestVisibility('hidden')")
    burnin_records = [
        record for record in clock.timers()
        if record.kind == "interval" and record.delay == 600000
    ]
    assert len(burnin_records) == 1
    assert burnin_records[0].cleared is True

    page.evaluate("() => window.__setTestVisibility('visible')")
    burnin_records = [
        record for record in clock.timers()
        if record.kind == "interval" and record.delay == 600000
    ]
    assert len(burnin_records) == 2
    assert sum(not record.cleared for record in burnin_records) == 1

    page.evaluate("() => window.__setTestVisibility('visible')")
    burnin_records = [
        record for record in clock.timers()
        if record.kind == "interval" and record.delay == 600000
    ]
    assert len(burnin_records) == 2
    assert sum(not record.cleared for record in burnin_records) == 1


@pytest.mark.parametrize(("path", "base_params", "container_selector"), BURNIN_CASES)
@pytest.mark.parametrize(
    ("override_params", "reduced_motion"),
    [
        pytest.param({"burnin": "false"}, "no-preference", id="disabled"),
        pytest.param({"burnin": "true"}, "reduce", id="reduced-motion"),
        pytest.param(
            {"embed": "true", "burnin": "true"},
            "no-preference",
            id="embed",
        ),
    ],
)
def test_burnin_interval_is_not_registered_when_disabled(
    page: Page,
    app_url: str,
    path: str,
    base_params: dict[str, str],
    container_selector: str,
    override_params: dict[str, str],
    reduced_motion: str,
) -> None:
    page.emulate_media(reduced_motion=reduced_motion)
    clock = install_timer_probe(page, manual=True)
    params = {**base_params, **override_params}
    open_clock(page, app_url, path, params)
    burnin_records = [
        record for record in clock.timers()
        if record.kind == "interval" and record.delay == 600000
    ]
    assert burnin_records == []


@pytest.mark.parametrize(
    ("path", "clock_kind"),
    [
        pytest.param("", "analog", id="analog"),
        pytest.param("/digital/", "digital", id="digital"),
    ],
)
@pytest.mark.cross_browser
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
    set_test_time(page, "2026-01-01T12:01:00Z", advance_milliseconds=1000)
    page.wait_for_function(
        """({ kind, initial }) => {
            var current = kind === 'analog'
                ? document.getElementById('minuteHand').style.transform
                : document.getElementById('digitalTime').textContent;
            return current !== initial;
        }""",
        arg={"kind": clock_kind, "initial": initial},
    )


@pytest.mark.cross_browser
@pytest.mark.parametrize(("path", "title", "container_selector"), PAGE_CASES)
@pytest.mark.parametrize(("link_id", "overlay_id", "close_id"), DIALOG_CASES)
def test_dialog_keyboard_lifecycle_focus_trap_and_reopen_listener_balance(
    page: Page,
    app_url: str,
    path: str,
    title: str,
    container_selector: str,
    link_id: str,
    overlay_id: str,
    close_id: str,
) -> None:
    mock_wake_lock(page)
    install_dialog_listener_probe(page)
    open_clock(page, app_url, path)

    keyboard_open_dialog(page, link_id)
    assert_dialog_open_state(page, path, overlay_id, close_id)
    assert page.evaluate(
        "overlayId => window.__dialogTrapListeners[overlayId]", overlay_id
    ) == {"adds": 1, "removes": 0, "active": 1}
    assert_dialog_tab_order(page, overlay_id)
    preview_id = prepare_dialog_preview(page, overlay_id)

    page.keyboard.press("Escape")
    assert_dialog_closed_state(page, overlay_id, preview_id)
    assert page.evaluate(
        "overlayId => window.__dialogTrapListeners[overlayId]", overlay_id
    ) == {"adds": 1, "removes": 1, "active": 0}

    keyboard_reopen_dialog(page, link_id)
    assert_dialog_open_state(page, path, overlay_id, close_id)
    assert page.evaluate(
        "overlayId => window.__dialogTrapListeners[overlayId]", overlay_id
    ) == {"adds": 2, "removes": 1, "active": 1}
    press_tab(page, reverse=True)
    assert page.evaluate(
        """overlayId => {
            var focusable = Array.from(document.getElementById(overlayId).querySelectorAll(
                'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])'
            )).filter(function (element) {
                return !element.disabled && element.getClientRects().length > 0;
            });
            return document.activeElement === focusable[focusable.length - 1];
        }""",
        overlay_id,
    ) is True
    press_tab(page)
    assert page.evaluate("() => document.activeElement.id") == close_id
    page.keyboard.press("Escape")
    assert_dialog_closed_state(page, overlay_id, preview_id)
    assert page.evaluate(
        "overlayId => window.__dialogTrapListeners[overlayId]", overlay_id
    ) == {"adds": 2, "removes": 2, "active": 0}


@pytest.mark.cross_browser
@pytest.mark.parametrize(("path", "title", "container_selector"), PAGE_CASES)
@pytest.mark.parametrize(("link_id", "overlay_id", "close_id"), DIALOG_CASES)
@pytest.mark.parametrize("close_method", ["button", "backdrop"])
def test_dialog_close_methods_restore_inert_focus_and_preview(
    page: Page,
    app_url: str,
    path: str,
    title: str,
    container_selector: str,
    link_id: str,
    overlay_id: str,
    close_id: str,
    close_method: str,
) -> None:
    mock_wake_lock(page)
    open_clock(page, app_url, path)
    keyboard_open_dialog(page, link_id)
    assert_dialog_open_state(page, path, overlay_id, close_id)
    preview_id = prepare_dialog_preview(page, overlay_id)

    if close_method == "button":
        page.locator("#" + close_id).focus()
        page.keyboard.press("Enter")
    else:
        page.mouse.click(2, 2)

    assert_dialog_closed_state(page, overlay_id, preview_id)


@pytest.mark.cross_browser
@pytest.mark.parametrize(("path", "title", "container_selector"), PAGE_CASES)
@pytest.mark.parametrize(
    "switch_key",
    ["theme", "wake-lock", "seconds", "save-settings"],
)
def test_switches_expose_name_state_and_space_activation(
    page: Page,
    app_url: str,
    path: str,
    title: str,
    container_selector: str,
    switch_key: str,
) -> None:
    mock_wake_lock(page)
    open_clock(page, app_url, path)
    definitions = {
        "theme": ("themeToggle", "Toggle dark mode", False),
        "wake-lock": ("wakeLockToggle", "Keep screen on", False),
        "seconds": (
            "secondModeToggle",
            "Show seconds" if path else "Tick seconds",
            True,
        ),
        "save-settings": ("saveSettingsToggle", "Save settings", False),
    }
    switch_id, accessible_name, initially_checked = definitions[switch_key]

    if switch_key == "save-settings":
        keyboard_open_about(page)
    else:
        press_tab(page)

    switch = page.get_by_role("switch", name=accessible_name, exact=True)
    assert switch.count() == 1
    assert switch.get_attribute("id") == switch_id
    assert switch.is_checked() is initially_checked
    switch.focus()
    page.keyboard.press("Space")
    assert switch.is_checked() is (not initially_checked)


@pytest.mark.cross_browser
def test_analog_single_and_dashboard_have_named_image_semantics(
    page: Page,
    app_url: str,
) -> None:
    open_clock(page, app_url, "")
    single = page.get_by_role("img", name="The time is 12:00", exact=True)
    assert single.count() == 1
    assert single.get_attribute("id") == "clock"

    open_clock(page, app_url, "", {"tz": "UTC,Asia/Kathmandu"})
    clocks = page.locator(".clock-grid .clock-cell svg[role='img']")
    assert clocks.count() == 2
    assert clocks.evaluate_all(
        "elements => elements.map(element => element.getAttribute('aria-label'))"
    ) == ["UTC: 12:00", "Kathmandu: 17:45"]
    assert page.get_by_role("img", name="UTC: 12:00", exact=True).count() == 1
    assert page.get_by_role(
        "img", name="Kathmandu: 17:45", exact=True
    ).count() == 1


@pytest.mark.cross_browser
def test_digital_single_and_dashboard_expose_time_and_named_container_semantics(
    page: Page,
    app_url: str,
) -> None:
    open_clock(page, app_url, "/digital/")
    single_time = page.locator("#digitalTime")
    assert single_time.evaluate("element => element.tagName") == "TIME"
    assert single_time.get_attribute("datetime") == "12:00:00"
    assert single_time.text_content() == "12:00:00"
    assert "The time is 12:00:00" in page.locator(
        "#digitalContainer"
    ).aria_snapshot()

    open_clock(
        page,
        app_url,
        "/digital/",
        {"tz": "UTC,Asia/Kathmandu"},
    )
    cells = page.locator(".digital-grid .digital-cell")
    times = page.locator(".digital-grid time.digital-time")
    assert cells.count() == 2
    assert times.count() == 2
    assert times.evaluate_all(
        "elements => elements.map(element => ({ tag: element.tagName, datetime: element.getAttribute('datetime'), text: element.textContent }))"
    ) == [
        {"tag": "TIME", "datetime": "12:00:00", "text": "12:00:00"},
        {"tag": "TIME", "datetime": "17:45:00", "text": "17:45:00"},
    ]
    snapshots = [cells.nth(index).aria_snapshot() for index in range(2)]
    assert "UTC: 12:00:00" in snapshots[0]
    assert "Kathmandu: 17:45:00" in snapshots[1]


@pytest.mark.cross_browser
@pytest.mark.parametrize(
    ("path", "expected_initial", "expected_next"),
    [
        pytest.param("", "The time is 12:00", "The time is 12:01", id="analog"),
        pytest.param(
            "/digital/",
            "The time is 12:00",
            "The time is 12:01",
            id="digital",
        ),
    ],
)
def test_live_region_is_atomic_polite_and_updates_once_per_minute(
    page: Page,
    app_url: str,
    path: str,
    expected_initial: str,
    expected_next: str,
) -> None:
    open_page(
        page,
        app_url,
        path=path,
        fixed_time="2026-01-01T12:00:15Z",
    )
    live = page.locator("#timeAnnounce")
    assert live.get_attribute("aria-live") == "polite"
    assert live.get_attribute("aria-atomic") == "true"
    assert live.text_content() == expected_initial
    page.evaluate("""() => {
        window.__accessibilityLiveChanges = [];
        new MutationObserver(function () {
          window.__accessibilityLiveChanges.push(
            document.getElementById('timeAnnounce').textContent
          );
        }).observe(document.getElementById('timeAnnounce'), {
          childList: true,
          characterData: true,
          subtree: true
        });
    }""")

    set_test_time(page, "2026-01-01T12:00:30Z", advance_milliseconds=1000)
    assert live.text_content() == expected_initial
    assert page.evaluate("() => window.__accessibilityLiveChanges") == []

    set_test_time(page, "2026-01-01T12:01:00Z", advance_milliseconds=1000)
    assert live.text_content() == expected_next
    assert page.evaluate("() => window.__accessibilityLiveChanges") == [expected_next]


@pytest.mark.cross_browser
@pytest.mark.parametrize(
    ("path", "clock_selector", "expected_label"),
    [
        pytest.param("", "#clock", "The time is 12:01", id="analog"),
        pytest.param(
            "/digital/",
            "#digitalContainer",
            "The time is 12:01:00",
            id="digital",
        ),
    ],
)
def test_embed_silences_live_region_but_updates_clock_name(
    page: Page,
    app_url: str,
    path: str,
    clock_selector: str,
    expected_label: str,
) -> None:
    open_page(
        page,
        app_url,
        {"embed": "true"},
        path=path,
        fixed_time="2026-01-01T12:00:00Z",
    )
    assert page.locator("#timeAnnounce").text_content() == ""
    set_test_time(page, "2026-01-01T12:01:00Z", advance_milliseconds=1000)
    assert page.locator(clock_selector).get_attribute("aria-label") == expected_label
    assert page.locator("#timeAnnounce").text_content() == ""


@pytest.mark.cross_browser
@pytest.mark.parametrize(
    ("path", "clock_selector", "icon_selector"),
    [
        pytest.param("", "#clock", "#sunIcon, #moonIcon", id="analog"),
        pytest.param(
            "/digital/",
            "#digitalContainer",
            "#dayNightIcon",
            id="digital",
        ),
    ],
)
def test_daynight_graphics_are_decorative_without_duplicate_names(
    page: Page,
    app_url: str,
    path: str,
    clock_selector: str,
    icon_selector: str,
) -> None:
    open_page(
        page,
        app_url,
        {"daynight": "show"},
        path=path,
        fixed_time="2026-01-01T12:00:00Z",
    )
    assert page.locator(clock_selector).count() == 1
    if path:
        icon = page.locator(icon_selector)
        assert icon.count() == 1
        assert icon.get_attribute("aria-hidden") == "true"
    else:
        assert page.locator(icon_selector).count() == 2
    assert page.get_by_role("img").count() == (0 if path else 1)
    assert page.get_by_role("img", name=re.compile("sun|moon", re.I)).count() == 0


@pytest.mark.cross_browser
@pytest.mark.parametrize(("path", "title", "container_selector"), PAGE_CASES)
def test_dashboard_timezone_native_error_is_tied_to_visibly_labelled_input(
    page: Page,
    app_url: str,
    path: str,
    title: str,
    container_selector: str,
) -> None:
    mock_wake_lock(page)
    open_clock(page, app_url, path)
    suppress_document_css_motion(page)
    keyboard_open_dialog(page, "dashboardLink")
    timezone_input = page.get_by_role("textbox", name="Timezone", exact=True)
    assert timezone_input.count() == 1
    assert page.locator('label[for="dashboardTzInput"]').is_visible() is True
    assert timezone_input.evaluate(
        "element => element.labels.length === 1 && element.labels[0].textContent.trim() === 'Timezone'"
    ) is True

    timezone_input.fill("Invalid/Timezone")
    page.get_by_role("button", name="Add", exact=True).click()
    assert timezone_input.evaluate("element => element.validity.valid") is False
    assert timezone_input.evaluate("element => element.validationMessage") == (
        "Invalid timezone"
    )
    assert page.evaluate("() => document.activeElement.id") == "dashboardTzInput"

    timezone_input.fill("UTC")
    timezone_input.press("Enter")
    assert timezone_input.evaluate("element => element.validity.valid") is True
    assert timezone_input.evaluate("element => element.validationMessage") == ""


@pytest.mark.cross_browser
@pytest.mark.parametrize(
    ("params", "selector", "expected_count"),
    [
        pytest.param({}, ".clock-container", 1, id="single"),
        pytest.param(
            {"tz": "UTC,Asia/Kathmandu", "shadows": "true"},
            ".clock-grid .clock-cell",
            2,
            id="dashboard",
        ),
    ],
)
def test_reduced_motion_hides_analog_seconds_and_removes_all_hand_shadows(
    page: Page,
    app_url: str,
    params: dict[str, str],
    selector: str,
    expected_count: int,
) -> None:
    page.emulate_media(reduced_motion="reduce")
    open_clock(page, app_url, "", params)
    containers = page.locator(selector)
    assert containers.count() == expected_count
    result = containers.evaluate_all("""elements => elements.map(function (container) {
        var second = container.querySelector('.second-hand');
        var shadowTargets = container.querySelectorAll(
          '.hour-hand, .minute-hand, .second-hand, circle[filter]'
        );
        return {
          secondDisplay: getComputedStyle(second).display,
          filteredTargets: Array.from(shadowTargets).filter(function (element) {
            return element.hasAttribute('filter');
          }).length
        };
    })""")
    assert result == [
        {"secondDisplay": "none", "filteredTargets": 0}
        for _ in range(expected_count)
    ]


@pytest.mark.chromium_only
@pytest.mark.parametrize(("path", "title", "container_selector"), PAGE_CASES)
def test_forced_colors_preserve_clock_focus_and_dialog_controls(
    page: Page,
    app_url: str,
    path: str,
    title: str,
    container_selector: str,
) -> None:
    page.emulate_media(forced_colors="active")
    mock_wake_lock(page)
    open_clock(page, app_url, path)
    assert page.evaluate(
        "() => matchMedia('(forced-colors: active)').matches"
    ) is True

    if path:
        assert page.locator("#digitalTime").is_visible() is True
        assert page.locator("#digitalTime").text_content() == "12:00:00"
    else:
        assert page.get_by_role("img", name="The time is 12:00").is_visible() is True
        assert page.locator("#hourHand").is_visible() is True
        assert page.locator("#minuteHand").is_visible() is True

    press_tab(page)
    assert page.evaluate("() => document.activeElement.id") == "themeToggle"
    assert_visible_focus_indicator(page)
    for _ in range(3):
        press_tab(page)
    page.keyboard.press("Enter")
    for _ in range(4):
        press_tab(page)
        assert page.locator("#aboutBubble").evaluate(
            "element => element.contains(document.activeElement)"
        ) is True
    assert page.evaluate("() => document.activeElement.id") == "helpLink"
    page.keyboard.press("Enter")
    assert page.get_by_role("dialog", name="How to use", exact=True).count() == 1
    close = page.get_by_role("button", name="Close", exact=True)
    assert close.count() == 1
    assert close.is_visible() is True
    assert page.evaluate("() => document.activeElement.id") == "helpCloseBtn"
    assert_visible_focus_indicator(page)


@pytest.mark.cross_browser
@pytest.mark.parametrize(("path", "title", "container_selector"), PAGE_CASES)
def test_320_by_256_main_page_has_no_document_horizontal_scroll(
    page: Page,
    app_url: str,
    path: str,
    title: str,
    container_selector: str,
) -> None:
    page.set_viewport_size({"width": 320, "height": 256})
    open_clock(page, app_url, path)
    result = page.evaluate("""containerSelector => ({
      htmlClient: document.documentElement.clientWidth,
      htmlScroll: document.documentElement.scrollWidth,
      bodyClient: document.body.clientWidth,
      bodyScroll: document.body.scrollWidth,
      containerVisible: document.querySelector(containerSelector)
        ? document.querySelector(containerSelector).getClientRects().length > 0
        : false
    })""", container_selector)
    assert result == {
        "htmlClient": 320,
        "htmlScroll": 320,
        "bodyClient": 320,
        "bodyScroll": 320,
        "containerVisible": True,
    }


@pytest.mark.cross_browser
@pytest.mark.parametrize(("path", "title", "container_selector"), PAGE_CASES)
@pytest.mark.parametrize(("link_id", "overlay_id", "close_id"), DIALOG_CASES)
def test_320_by_256_dialog_reflows_without_document_or_panel_overflow(
    page: Page,
    app_url: str,
    path: str,
    title: str,
    container_selector: str,
    link_id: str,
    overlay_id: str,
    close_id: str,
) -> None:
    page.set_viewport_size({"width": 320, "height": 256})
    mock_wake_lock(page)
    open_clock(page, app_url, path)
    suppress_document_css_motion(page)
    keyboard_open_dialog(page, link_id)
    assert_dialog_open_state(page, path, overlay_id, close_id)
    page.wait_for_function("""overlayId => {
      var transform = getComputedStyle(
        document.querySelector('#' + overlayId + ' .modal-panel')
      ).transform;
      return transform === 'none' || transform === 'matrix(1, 0, 0, 1, 0, 0)';
    }""", arg=overlay_id)
    result = page.evaluate("""overlayId => {
      var panel = document.querySelector('#' + overlayId + ' .modal-panel');
      var rect = panel.getBoundingClientRect();
      return {
        documentClient: document.documentElement.clientWidth,
        documentScroll: document.documentElement.scrollWidth,
        bodyScroll: document.body.scrollWidth,
        panelClient: panel.clientWidth,
        panelScroll: panel.scrollWidth,
        left: rect.left,
        right: rect.right,
        top: rect.top,
        bottom: rect.bottom
      };
    }""", overlay_id)
    assert result["documentClient"] == 320
    assert result["documentScroll"] == 320
    assert result["bodyScroll"] == 320
    assert result["panelScroll"] <= result["panelClient"]
    assert result["left"] >= 0
    assert result["right"] <= 320
    assert result["top"] >= 0
    assert result["bottom"] <= 256

    if overlay_id == "helpOverlay":
        regions = page.locator("#helpOverlay pre[role='region']")
        assert regions.count() == 2
        assert regions.evaluate_all(
            "elements => elements.map(element => element.scrollWidth > element.clientWidth)"
        ) == [True, True]


@pytest.mark.cross_browser
@pytest.mark.parametrize(
    ("path", "extra_params", "cell_selector", "label_selector"),
    [
        pytest.param(
            "",
            {},
            ".clock-cell",
            ".clock-label",
            id="analog",
        ),
        pytest.param(
            "/digital/",
            {"format": "12"},
            ".digital-cell",
            ".digital-label",
            id="digital-12-hour",
        ),
    ],
)
def test_small_dashboard_long_labels_daynight_and_borders_are_not_clipped(
    page: Page,
    app_url: str,
    path: str,
    extra_params: dict[str, str],
    cell_selector: str,
    label_selector: str,
) -> None:
    page.set_viewport_size({"width": 320, "height": 256})
    params = {
        "tz": "America/Argentina/Buenos_Aires,America/North_Dakota/New_Salem",
        "daynight": "show",
        "border": "show",
        **extra_params,
    }
    open_clock(page, app_url, path, params)
    cells = page.locator(cell_selector)
    labels = page.locator(label_selector)
    assert cells.count() == 2
    assert labels.count() == 2
    assert labels.all_text_contents() == ["Buenos Aires", "New Salem"]
    assert cells.evaluate_all("""(elements, labelSelector) => elements.map(function (cell) {
      var label = cell.querySelector(labelSelector);
      var cellRect = cell.getBoundingClientRect();
      var labelRect = label.getBoundingClientRect();
      return {
        labelFitsWidth: label.scrollWidth <= label.clientWidth,
        labelInside: labelRect.left >= cellRect.left - 1 &&
          labelRect.right <= cellRect.right + 1 &&
          labelRect.top >= cellRect.top - 1 && labelRect.bottom <= cellRect.bottom + 1
      };
    })""", label_selector) == [
        {"labelFitsWidth": True, "labelInside": True},
        {"labelFitsWidth": True, "labelInside": True},
    ]
    assert page.evaluate(
        "() => document.documentElement.scrollWidth === document.documentElement.clientWidth"
    ) is True

    if path:
        assert cells.evaluate_all(
            "elements => elements.map(element => element.classList.contains('bordered'))"
        ) == [True, True]
        assert page.locator(".digital-cell .daynight-mark.visible").count() == 2
        assert page.locator(".digital-cell time").evaluate_all(
            "elements => elements.map(element => / (AM|PM)$/.test(element.textContent))"
        ) == [True, True]
    else:
        assert page.locator(".clock-cell .clock-border").evaluate_all(
            "elements => elements.map(element => element.getAttribute('stroke') !== 'none')"
        ) == [True, True]
        visible_icons = page.locator(
            ".clock-cell .sun-icon:not([display='none']), .clock-cell .moon-icon:not([display='none'])"
        )
        assert visible_icons.count() == 2


@pytest.mark.cross_browser
@pytest.mark.parametrize(("path", "title", "container_selector"), PAGE_CASES)
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_light_and_dark_text_border_and_focus_colors_meet_contrast_contract(
    page: Page,
    app_url: str,
    path: str,
    title: str,
    container_selector: str,
    theme: str,
) -> None:
    open_clock(page, app_url, path, {"theme": theme})
    variables = page.locator("html").evaluate("""(element, names) => {
      var style = getComputedStyle(element);
      return Object.fromEntries(names.map(function (name) {
        return [name, style.getPropertyValue(name).trim()];
      }));
    }""", [
        "--bg",
        "--focus-ring",
        "--clock-face",
        "--clock-border",
        "--number",
        "--digit",
        "--muted",
    ])
    assert contrast_ratio(variables["--focus-ring"], variables["--bg"]) >= 3
    if path:
        assert contrast_ratio(variables["--digit"], variables["--bg"]) >= 4.5
        assert contrast_ratio(variables["--muted"], variables["--bg"]) >= 4.5
    else:
        assert contrast_ratio(
            variables["--number"], variables["--clock-face"]
        ) >= 4.5
        assert contrast_ratio(
            variables["--clock-border"], variables["--clock-face"]
        ) >= 3


@pytest.mark.cross_browser
@pytest.mark.parametrize(("path", "foreground_variable"), [
    pytest.param("", "--number", id="analog"),
    pytest.param("/digital/", "--digit", id="digital"),
])
def test_transparent_theme_contrast_against_builder_preview_background(
    page: Page,
    app_url: str,
    path: str,
    foreground_variable: str,
) -> None:
    open_clock(page, app_url, path, {"theme": "light"})
    page.evaluate("() => document.getElementById('embedLink').click()")
    page.locator("#embedTheme").select_option("transparent")
    page.wait_for_function("""() => {
      var frame = document.getElementById('embedPreview');
      return frame.contentDocument && frame.contentDocument.documentElement &&
        frame.contentDocument.documentElement.classList.contains('transparent-mode');
    }""")
    colors = page.evaluate("""foregroundVariable => {
      var frame = document.getElementById('embedPreview');
      var frameStyle = getComputedStyle(frame.contentDocument.documentElement);
      return {
        foreground: frameStyle.getPropertyValue(foregroundVariable).trim(),
        wrapper: getComputedStyle(frame.parentElement).backgroundColor,
        panel: getComputedStyle(frame.closest('.modal-panel')).backgroundColor
      };
    }""", foreground_variable)
    preview_background = composite_color(
        parse_css_color(colors["wrapper"]),
        parse_css_color(colors["panel"]),
    )
    preview_rgb = "rgb(%s, %s, %s)" % tuple(
        round(component) for component in preview_background[:3]
    )
    assert contrast_ratio(colors["foreground"], preview_rgb) >= 4.5
