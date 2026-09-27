from __future__ import annotations

from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import threading
from typing import Iterator
from urllib.parse import parse_qs, quote, urlencode, urlsplit
from urllib.request import urlopen

from PIL import Image
import pytest
from playwright.sync_api import FrameLocator, Page

from tests.helpers import (
    install_css_motion_suppression,
    install_test_clock,
    install_timer_probe,
    open_page,
)


pytestmark = pytest.mark.cross_browser


BUILDER_CASES = [
    pytest.param(
        "/",
        "Analog clock",
        "https://clocksimulator.com/",
        200,
        200,
        120,
        120,
        50,
        1000,
        50,
        1000,
        "light",
        id="analog-light",
    ),
    pytest.param(
        "/digital/",
        "Digital clock",
        "https://clocksimulator.com/digital/",
        360,
        160,
        240,
        110,
        120,
        1600,
        80,
        1000,
        "dark",
        id="digital-dark",
    ),
]


ANALOG_DASHBOARD_CASE = pytest.param(
    "/", "https://clocksimulator.com/", id="analog"
)
DIGITAL_DASHBOARD_CASE = pytest.param(
    "/digital/",
    "https://clocksimulator.com/digital/",
    id="digital",
)


REAL_IFRAME_CASES = [
    pytest.param(
        "/",
        {
            "embed": "true",
            "theme": "{theme}",
            "tz": "Asia/Kathmandu",
            "seconds": "hide",
            "border": "hide",
            "numbers": "hide",
            "shadows": "false",
            "daynight": "show",
        },
        120,
        120,
        "analog-single",
        "transparent",
        id="analog-single-small-transparent",
    ),
    pytest.param(
        "/",
        {
            "embed": "true",
            "theme": "{theme}",
            "tz": "UTC,Asia/Kathmandu",
            "rows": "1",
            "seconds": "hide",
            "border": "hide",
            "numbers": "hide",
            "daynight": "show",
        },
        280,
        160,
        "analog-dashboard",
        "dark",
        id="analog-dashboard-landscape-dark",
    ),
    pytest.param(
        "/digital/",
        {
            "embed": "true",
            "theme": "{theme}",
            "tz": "Asia/Kathmandu",
            "seconds": "hide",
            "format": "12",
            "border": "hide",
            "daynight": "show",
        },
        160,
        240,
        "digital-single",
        "light",
        id="digital-single-portrait-light",
    ),
    pytest.param(
        "/digital/",
        {
            "embed": "true",
            "theme": "{theme}",
            "tz": "UTC,Asia/Kathmandu",
            "rows": "1",
            "seconds": "hide",
            "format": "12",
            "border": "hide",
            "daynight": "show",
        },
        280,
        160,
        "digital-dashboard",
        "transparent",
        id="digital-dashboard-small-transparent",
    ),
]


@pytest.fixture(autouse=True)
def suppress_builder_css_motion(page: Page) -> None:
    install_css_motion_suppression(page)


def open_builder(page: Page, app_url: str, path: str, panel: str) -> None:
    open_page(page, app_url, path=path)
    link_id = "embedLink" if panel == "embed" else "dashboardLink"
    overlay_id = "embedOverlay" if panel == "embed" else "dashboardOverlay"
    page.evaluate("linkId => document.getElementById(linkId).click()", link_id)
    page.wait_for_function(
        "overlayId => document.getElementById(overlayId).classList.contains('visible')",
        arg=overlay_id,
    )


def parsed_generated_iframe(page: Page) -> dict[str, object]:
    return page.evaluate(
        """() => {
            const template = document.createElement('template');
            template.innerHTML = document.getElementById('embedCode').value;
            const frames = template.content.querySelectorAll('iframe');
            const frame = frames[0] || null;
            return {
                count: frames.length,
                src: frame ? frame.getAttribute('src') : null,
                title: frame ? frame.getAttribute('title') : null,
                width: frame ? frame.getAttribute('width') : null,
                height: frame ? frame.getAttribute('height') : null,
                style: frame ? frame.getAttribute('style') : null,
                allowtransparency: frame ? frame.getAttribute('allowtransparency') : null,
                elementChildren: template.content.children.length
            };
        }"""
    )


def query_values(url: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(url).query, keep_blank_values=True)


def wait_for_preview(page: Page, selector: str, expected_selector: str) -> FrameLocator:
    frame = page.frame_locator(selector)
    frame.locator("body.embed-mode").wait_for()
    frame.locator(expected_selector).first.wait_for()
    return frame


def select_and_dispatch(page: Page, selector: str, value: str) -> None:
    page.locator(selector).select_option(value)


def add_dashboard_timezone(
    page: Page,
    timezone: str,
    method: str = "button",
) -> None:
    field = page.locator("#dashboardTzInput")
    field.fill(timezone)
    if method == "enter":
        field.press("Enter")
    else:
        page.locator("#dashboardAddBtn").click()


def dashboard_chip_names(page: Page) -> list[str]:
    return page.locator("#tzChips .tz-chip").evaluate_all(
        "elements => elements.map(element => element.firstChild.textContent)"
    )


def resolved_timezone(page: Page, timezone: str) -> str:
    return page.evaluate(
        """timezone => new Intl.DateTimeFormat(undefined, {
            timeZone: timezone
        }).resolvedOptions().timeZone""",
        timezone,
    )


def install_clipboard_mock(page: Page, mode: str) -> None:
    page.add_init_script(
        """(() => {
            const mode = %s;
            window.__clipboardWrites = [];
            if (mode === 'missing') {
                Object.defineProperty(navigator, 'clipboard', {
                    configurable: true,
                    value: undefined
                });
                return;
            }
            Object.defineProperty(navigator, 'clipboard', {
                configurable: true,
                value: {
                    writeText: function (value) {
                        window.__clipboardWrites.push(value);
                        return mode === 'reject'
                            ? Promise.reject(new Error('clipboard denied'))
                            : Promise.resolve();
                    }
                }
            });
        })();""" % json.dumps(mode)
    )


@pytest.fixture(scope="session")
def iframe_harness_url() -> Iterator[str]:
    public_dir = Path(__file__).resolve().parents[1] / "public"
    harness = """<!doctype html>
<html><head><meta charset="utf-8"><title>Iframe harness</title>
<style>
:root { --bg: rgb(255, 0, 255); }
html, body { margin: 0; min-height: 100%; background: rgb(21, 72, 94); font-family: Papyrus, serif; }
.clock-container, .digital-container { display: none !important; }
time { color: rgb(0, 255, 0) !important; }
#parentSentinel { color: rgb(1, 2, 3); }
#clockFrame { display: block; margin: 20px; border: 0; background: transparent; }
</style></head>
<body><span id="parentSentinel">parent</span><iframe id="clockFrame" title="Embedded clock"></iframe></body></html>"""

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(public_dir), **kwargs)

        def do_GET(self) -> None:
            if self.path.partition("?")[0] == "/__iframe_harness__":
                encoded = harness.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
                return
            super().do_GET()

        def log_message(self, format, *args) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(
        target=server.serve_forever,
        name="clocksimulator-iframe-harness",
    )
    thread.start()
    base_url = "http://127.0.0.1:" + str(server.server_address[1])
    try:
        with urlopen(base_url + "/__iframe_harness__", timeout=5) as response:
            assert response.status == HTTPStatus.OK
        yield base_url
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        if thread.is_alive():
            pytest.fail("Iframe harness server did not stop cleanly")


@pytest.mark.parametrize(
    (
        "path",
        "title",
        "production_base",
        "default_width",
        "default_height",
        "preview_width",
        "preview_height",
        "min_width",
        "max_width",
        "min_height",
        "max_height",
        "page_theme",
    ),
    BUILDER_CASES,
)
def test_embed_builder_default_is_one_exact_parseable_iframe_and_loaded_preview(
    page: Page,
    app_url: str,
    path: str,
    title: str,
    production_base: str,
    default_width: int,
    default_height: int,
    preview_width: int,
    preview_height: int,
    min_width: int,
    max_width: int,
    min_height: int,
    max_height: int,
    page_theme: str,
) -> None:
    page.emulate_media(color_scheme=page_theme)
    open_builder(page, app_url, path, "embed")
    expected_src = production_base + "?embed=true&theme=" + page_theme
    expected_style = (
        "border:none; border-radius:50%; overflow:hidden;"
        if path == "/"
        else "border:none; overflow:hidden;"
    )
    assert parsed_generated_iframe(page) == {
        "count": 1,
        "src": expected_src,
        "title": title,
        "width": str(default_width),
        "height": str(default_height),
        "style": expected_style,
        "allowtransparency": None,
        "elementChildren": 1,
    }
    preview = page.locator("#embedPreview")
    assert preview.get_attribute("width") == str(preview_width)
    assert preview.get_attribute("height") == str(preview_height)
    if path == "/":
        assert preview.evaluate("element => element.style.borderRadius") == "50%"
    frame = wait_for_preview(
        page,
        "#embedPreview",
        "#clock" if path == "/" else "#digitalTime",
    )
    assert frame.locator("html").evaluate(
        "element => element.classList.contains('dark-mode')"
    ) is (page_theme == "dark")
    assert frame.locator("body").evaluate(
        "element => element.classList.contains('embed-mode')"
    ) is True


@pytest.mark.parametrize("path", [pytest.param("/digital/", id="digital")])
def test_embed_clock_color_updates_preview_and_code_and_survives_theme_switches(
    page: Page,
    app_url: str,
    path: str,
) -> None:
    open_builder(page, app_url, path, "embed")
    color_field = page.locator("#embedClockColorField")
    color_select = page.get_by_label("Clock color", exact=True)
    default_color = "dark" if path == "/" else "light"
    other_color = "light" if default_color == "dark" else "dark"
    production_base = "https://clocksimulator.com" + path
    assert color_field.is_visible() is False
    assert color_select.input_value() == default_color
    assert "color" not in query_values(str(parsed_generated_iframe(page)["src"]))

    def assert_transparent_preview(color: str) -> None:
        expected_query = "?embed=true&theme=transparent&color=" + color
        generated = parsed_generated_iframe(page)
        assert generated["src"] == production_base + expected_query
        assert generated["allowtransparency"] == "true"
        assert page.locator("#embedPreview").get_attribute("src").endswith(expected_query)
        frame = wait_for_preview(
            page, "#embedPreview", "#clock" if path == "/" else "#digitalTime"
        )
        frame.locator('html.transparent-mode[data-clock-color="' + color + '"]').wait_for()
        foreground = frame.locator("#hourHand" if path == "/" else "#digitalTime")
        assert foreground.evaluate(
            "(element, property) => getComputedStyle(element)[property]",
            "fill" if path == "/" else "color",
        ) == ("rgb(34, 34, 34)" if color == "dark" else "rgb(250, 250, 250)")
        assert frame.locator("body").evaluate(
            "element => getComputedStyle(element).backgroundColor"
        ) == "rgba(0, 0, 0, 0)"

    select_and_dispatch(page, "#embedTheme", "transparent")
    assert color_field.is_visible() is True
    assert_transparent_preview(default_color)
    select_and_dispatch(page, "#embedClockColor", other_color)
    assert_transparent_preview(other_color)

    for theme in ("light", "dark"):
        select_and_dispatch(page, "#embedTheme", theme)
        assert color_field.is_visible() is False
        assert color_select.input_value() == other_color
        generated = parsed_generated_iframe(page)
        assert generated["src"] == production_base + "?embed=true&theme=" + theme
        assert generated["allowtransparency"] is None
        frame = wait_for_preview(
            page, "#embedPreview", "#clock" if path == "/" else "#digitalTime"
        )
        frame.locator("html:not(.transparent-mode):not([data-clock-color])").wait_for()

    select_and_dispatch(page, "#embedTheme", "transparent")
    assert color_field.is_visible() is True
    assert color_select.input_value() == other_color
    assert_transparent_preview(other_color)


@pytest.mark.parametrize("path", [pytest.param("/", id="analog")])
def test_embed_custom_clock_color_reaches_code_and_preview(
    page: Page,
    app_url: str,
    path: str,
) -> None:
    open_builder(page, app_url, path, "embed")
    analog = path == "/"
    custom_field = page.locator("#embedCustomColorField")
    clock_color = page.get_by_label("Custom clock color" if analog else "Custom color", exact=True)
    production_base = "https://clocksimulator.com" + path
    assert custom_field.is_visible() is False
    assert page.locator("#embedSecondColor").count() == (1 if analog else 0)

    def expected_query(color: str, second_color: str) -> str:
        query = "?embed=true&theme=transparent&color=" + color
        return query + ("&secondcolor=" + second_color if analog else "")

    select_and_dispatch(page, "#embedTheme", "transparent")
    assert custom_field.is_visible() is False
    select_and_dispatch(page, "#embedClockColor", "custom")
    assert custom_field.is_visible() is True
    assert clock_color.input_value() == "#ff8800"
    assert parsed_generated_iframe(page)["src"] == production_base + expected_query("ff8800", "d63031")

    clock_color.fill("#1a2b8c")
    if analog:
        second_color = page.get_by_label("Custom second hand color", exact=True)
        assert second_color.input_value() == "#d63031"
        second_color.fill("#00ff66")
    page.clock.run_for(400)
    query = expected_query("1a2b8c", "00ff66")
    assert parsed_generated_iframe(page)["src"] == production_base + query
    assert page.locator("#embedPreview").get_attribute("src").endswith(query)
    frame = wait_for_preview(page, "#embedPreview", "#clock" if analog else "#digitalTime")
    frame.locator('html.transparent-mode[data-clock-color="custom"]').wait_for()
    foreground = frame.locator("#hourHand" if analog else "#digitalTime")
    assert foreground.evaluate(
        "(element, property) => getComputedStyle(element)[property]",
        "fill" if analog else "color",
    ) == "rgb(26, 43, 140)"
    if analog:
        frame.locator('html[data-second-color="custom"]').wait_for(state="attached")
        assert frame.locator("#secondHand").evaluate(
            "element => getComputedStyle(element).stroke"
        ) == "rgb(0, 255, 102)"
        assert frame.locator("#centerDot").evaluate(
            "element => getComputedStyle(element).fill"
        ) == "rgb(0, 255, 102)"
    assert page.locator("#embedOverlay .embed-preview-wrap").evaluate(
        "element => element.classList.contains('light-clock-preview')"
    ) is False

    clock_color.fill("#f0f0f0")
    page.clock.run_for(400)
    assert page.locator("#embedOverlay .embed-preview-wrap").evaluate(
        "element => element.classList.contains('light-clock-preview')"
    ) is True

    select_and_dispatch(page, "#embedClockColor", "light")
    assert custom_field.is_visible() is False
    assert parsed_generated_iframe(page)["src"] == (
        production_base + "?embed=true&theme=transparent&color=light"
    )

    select_and_dispatch(page, "#embedTheme", "dark")
    assert custom_field.is_visible() is False
    assert parsed_generated_iframe(page)["src"] == production_base + "?embed=true&theme=dark"


@pytest.mark.parametrize("path", ["/", "/digital/"])
def test_every_embed_builder_control_reaches_code_and_preview_dom(
    page: Page,
    app_url: str,
    path: str,
) -> None:
    open_builder(page, app_url, path, "embed")
    page.locator("#embedTz").fill("  Asia/Kathmandu  ")
    select_and_dispatch(page, "#embedTheme", "transparent")
    select_and_dispatch(page, "#embedClockColor", "light" if path == "/" else "dark")
    select_and_dispatch(page, "#embedSeconds", "smooth" if path == "/" else "hide")
    select_and_dispatch(page, "#embedBorder", "hide" if path == "/" else "show")
    select_and_dispatch(page, "#embedDayNight", "show")
    if path == "/":
        select_and_dispatch(page, "#embedShape", "square")
        select_and_dispatch(page, "#embedNumbers", "hide")
        select_and_dispatch(page, "#embedShadows", "false")
        page.locator("#embedWidth").fill("321")
        page.locator("#embedHeight").fill("234")
        production_base = "https://clocksimulator.com/"
        expected_query = (
            "?embed=true&tz=Asia%2FKathmandu&theme=transparent&seconds=smooth"
            "&border=hide&daynight=show&numbers=hide&shadows=false&color=light"
        )
        expected_width = "321"
        expected_height = "234"
        expected_style = "border:none; overflow:hidden;"
    else:
        select_and_dispatch(page, "#embedFormat", "12")
        page.locator("#embedWidth").fill("421")
        page.locator("#embedHeight").fill("187")
        production_base = "https://clocksimulator.com/digital/"
        expected_query = (
            "?embed=true&tz=Asia%2FKathmandu&theme=transparent&seconds=hide"
            "&format=12&border=show&daynight=show&color=dark"
        )
        expected_width = "421"
        expected_height = "187"
        expected_style = "border:none; overflow:hidden;"

    page.clock.run_for(400)
    generated = parsed_generated_iframe(page)
    assert generated == {
        "count": 1,
        "src": production_base + expected_query,
        "title": "Analog clock" if path == "/" else "Digital clock",
        "width": expected_width,
        "height": expected_height,
        "style": expected_style,
        "allowtransparency": "true",
        "elementChildren": 1,
    }
    assert page.locator("#embedPreview").get_attribute("src").endswith(expected_query)
    assert page.locator("#embedPreview").get_attribute("width") == (
        "120" if path == "/" else "240"
    )
    assert page.locator("#embedPreview").get_attribute("height") == (
        "120" if path == "/" else "110"
    )
    frame = wait_for_preview(
        page,
        "#embedPreview",
        "#clock" if path == "/" else "#digitalTime",
    )
    assert frame.locator("html").evaluate(
        "element => element.classList.contains('transparent-mode')"
    ) is True
    assert frame.locator(".toggle-wrapper").evaluate(
        "element => getComputedStyle(element).display"
    ) == "none"

    if path == "/":
        assert page.locator("#embedPreview").evaluate(
            "element => element.style.borderRadius"
        ) == "0px"
        assert frame.locator("#secondModeToggle").is_checked() is False
        assert frame.locator("#secondHand").evaluate(
            "element => getComputedStyle(element).display"
        ) != "none"
        assert frame.locator("#clockBorder").get_attribute("stroke") == "none"
        assert frame.locator("#numbers").evaluate(
            "element => getComputedStyle(element).display"
        ) == "none"
        assert frame.locator("#clock [filter]").count() == 0
        assert frame.locator("#sunIcon").evaluate(
            "element => getComputedStyle(element).display"
        ) == "inline"
    else:
        assert frame.locator("#digitalTime").text_content() == "05:45 PM"
        assert frame.locator("#digitalContainer").evaluate(
            "element => element.classList.contains('bordered')"
        ) is True
        assert frame.locator("#dayNightIcon").get_attribute("data-state") == "day"


@pytest.mark.parametrize(
    ("path", "timezone_input", "expected_timezones", "is_valid"),
    [
        pytest.param(
            "/",
            " UTC, Asia/Kathmandu , Europe/Helsinki ",
            ["UTC", "Asia/Kathmandu", "Europe/Helsinki"],
            True,
            id="analog-multiple-trimmed-ordered",
        ),
        pytest.param(
            "/digital/",
            "UTC,Mars/Olympus",
            [],
            False,
            id="digital-mixed-valid-invalid",
        ),
        pytest.param(
            "/digital/",
            "America/Argentina/Buenos_Aires,Asia/Kathmandu",
            ["America/Argentina/Buenos_Aires", "Asia/Kathmandu"],
            True,
            id="digital-url-encoding-order",
        ),
    ],
)
def test_embed_builder_timezone_validation_encoding_and_order(
    page: Page,
    app_url: str,
    path: str,
    timezone_input: str,
    expected_timezones: list[str],
    is_valid: bool,
) -> None:
    open_builder(page, app_url, path, "embed")
    page.locator("#embedTz").fill(timezone_input)
    page.clock.run_for(400)
    field_state = page.locator("#embedTz").evaluate(
        """element => ({
            valid: element.checkValidity(),
            message: element.validationMessage
        })"""
    )
    generated_src = str(parsed_generated_iframe(page)["src"])
    parsed = query_values(generated_src)
    preview_src = str(page.locator("#embedPreview").get_attribute("src"))
    preview_query = query_values(preview_src)
    if is_valid:
        assert field_state == {"valid": True, "message": ""}
        expected_joined = ",".join(expected_timezones)
        if expected_timezones:
            assert parsed["tz"] == [expected_joined]
            assert preview_query["tz"] == [expected_joined]
            encoded_timezone = expected_joined.replace("/", "%2F").replace(",", "%2C")
            assert "tz=" + encoded_timezone in generated_src
        else:
            assert "tz" not in parsed
            assert "tz" not in preview_query
    else:
        assert field_state["valid"] is False
        assert field_state["message"] == "Invalid timezone(s)"
        assert "tz" not in parsed
        assert "tz" not in preview_query
        assert timezone_input not in generated_src

    expected_rendered_count = len(expected_timezones) if len(expected_timezones) > 1 else 1
    rendered_selector = (
        ".clock-grid .clock-cell" if path == "/" else ".digital-grid .digital-cell"
    )
    single_selector = "#clock" if path == "/" else "#digitalTime"
    frame = wait_for_preview(
        page,
        "#embedPreview",
        rendered_selector if expected_rendered_count > 1 else single_selector,
    )
    if expected_rendered_count > 1:
        assert frame.locator(rendered_selector).count() == expected_rendered_count
        label_selector = ".clock-label" if path == "/" else ".digital-label"
        assert frame.locator(label_selector).all_text_contents() == [
            timezone.split("/")[-1].replace("_", " ")
            for timezone in expected_timezones
        ]
    else:
        grid_selector = ".clock-grid" if path == "/" else ".digital-grid"
        assert frame.locator(grid_selector).count() == 0
        if len(expected_timezones) == 1:
            if path == "/":
                assert frame.locator("#clock").get_attribute("aria-label")
            else:
                assert frame.locator("#digitalLabel").text_content() == (
                    expected_timezones[0].split("/")[-1].replace("_", " ")
                )


@pytest.mark.parametrize(
    ("path", "default_width", "default_height", "width_cap", "height_cap", "bounds"),
    [
        pytest.param("/", 200, 200, 120, 120, {"width": (50, 1000), "height": (50, 1000)}, id="analog"),
        pytest.param("/digital/", 360, 160, 240, 110, {"width": (120, 1600), "height": (80, 1000)}, id="digital"),
    ],
)
def test_embed_builder_accepts_dimension_boundaries_exponents_and_caps_preview(
    page: Page,
    app_url: str,
    path: str,
    default_width: int,
    default_height: int,
    width_cap: int,
    height_cap: int,
    bounds: dict[str, tuple[int, int]],
) -> None:
    open_builder(page, app_url, path, "embed")
    for dimension in ("width", "height"):
        for boundary, value in zip(("minimum", "maximum"), bounds[dimension]):
            page.locator("#embedWidth").fill(str(default_width))
            page.locator("#embedHeight").fill(str(default_height))
            selector = "#embedWidth" if dimension == "width" else "#embedHeight"
            page.locator(selector).fill(str(value))
            page.clock.run_for(400)
            state = page.locator(selector).evaluate(
                "element => ({ valid: element.checkValidity(), message: element.validationMessage })"
            )
            assert state == {"valid": True, "message": ""}, (dimension, boundary)
            generated = parsed_generated_iframe(page)
            expected_width = value if dimension == "width" else default_width
            expected_height = value if dimension == "height" else default_height
            assert generated["width"] == str(expected_width), (dimension, boundary)
            assert generated["height"] == str(expected_height), (dimension, boundary)
            assert page.locator("#embedPreview").get_attribute("width") == str(
                min(expected_width, width_cap)
            ), (dimension, boundary)
            assert page.locator("#embedPreview").get_attribute("height") == str(
                min(expected_height, height_cap)
            ), (dimension, boundary)
    width = page.locator("#embedWidth")
    width.fill("1e3")
    assert width.evaluate(
        "element => ({ valid: element.checkValidity(), value: element.valueAsNumber })"
    ) == {"valid": True, "value": 1000}
    page.clock.run_for(400)
    assert parsed_generated_iframe(page)["width"] == "1000"
    assert page.locator("#embedPreview").get_attribute("width") == str(width_cap)


@pytest.mark.parametrize(
    ("path", "valid_width", "valid_height", "over_width", "over_height"),
    [
        pytest.param("/digital/", 444, 222, 1601, 1001, id="digital"),
    ],
)
def test_embed_builder_rejects_invalid_dimensions_without_replacing_preview(
    page: Page,
    app_url: str,
    path: str,
    valid_width: int,
    valid_height: int,
    over_width: int,
    over_height: int,
) -> None:
    open_builder(page, app_url, path, "embed")
    page.locator("#embedWidth").fill(str(valid_width))
    page.locator("#embedHeight").fill(str(valid_height))
    page.clock.run_for(400)
    for dimension in ("width", "height"):
        if dimension == "height":
            page.locator("#embedWidth").fill(str(valid_width))
            assert page.locator("#embedWidth").evaluate(
                "element => element.checkValidity()"
            ) is True
        previous_code = page.locator("#embedCode").input_value()
        previous_src = page.locator("#embedPreview").get_attribute("src")
        selector = "#embedWidth" if dimension == "width" else "#embedHeight"
        field = page.locator(selector)
        invalid_values = [
            ("empty", ""),
            ("non-numeric", None),
            ("zero", "0"),
            ("negative", "-1"),
            (
                "above-maximum",
                str(over_width if dimension == "width" else over_height),
            ),
        ]
        for invalid_kind, invalid_value in invalid_values:
            case = (dimension, invalid_kind)
            field.fill("")
            if invalid_value is None:
                field.press_sequentially("not-a-number")
            elif invalid_value:
                field.fill(invalid_value)

            assert page.locator("#embedCode").input_value() == previous_code, case
            assert (
                page.locator("#embedPreview").get_attribute("src") == previous_src
            ), case
            page.clock.run_for(400)
            validation = field.evaluate(
                "element => ({ valid: element.checkValidity(), message: element.validationMessage })"
            )
            assert validation["valid"] is False, case
            assert validation["message"], case
            assert page.locator("#embedCode").input_value() == previous_code, case
            assert (
                page.locator("#embedPreview").get_attribute("src") == previous_src
            ), case


@pytest.mark.parametrize("path", [pytest.param("/", id="analog")])
@pytest.mark.parametrize(
    ("clipboard_mode", "expected_feedback", "expected_write_count"),
    [
        pytest.param("success", "Copied!", 1, id="success"),
        pytest.param("reject", "Failed", 1, id="rejected-promise"),
        pytest.param("missing", "Failed", 0, id="missing-api"),
    ],
)
def test_embed_builder_clipboard_flow_and_timed_feedback(
    page: Page,
    app_url: str,
    path: str,
    clipboard_mode: str,
    expected_feedback: str,
    expected_write_count: int,
) -> None:
    install_clipboard_mock(page, clipboard_mode)
    clock = install_timer_probe(page, manual=True)
    open_builder(page, app_url, path, "embed")
    generated_code = page.locator("#embedCode").input_value()
    page.locator("#embedCopyBtn").click()
    page.wait_for_function(
        "expected => document.getElementById('embedCopyBtn').textContent === expected",
        arg=expected_feedback,
        timeout=1000,
    )
    writes = page.evaluate("() => window.__clipboardWrites")
    assert len(writes) == expected_write_count
    if writes:
        assert writes == [generated_code]
    assert page.locator("#embedCopyBtn").text_content() == expected_feedback
    feedback_timers = [
        timer
        for timer in clock.timers()
        if timer.kind == "timeout" and timer.delay == 1500 and not timer.cleared
    ]
    assert len(feedback_timers) == 1
    clock.run_timer(feedback_timers[0].timer_id)
    assert page.locator("#embedCopyBtn").text_content() == "Copy code"


@pytest.mark.parametrize(
    ("path", "production_base"), [ANALOG_DASHBOARD_CASE]
)
def test_dashboard_builder_empty_one_zone_canonicalization_duplicates_and_removal(
    page: Page,
    app_url: str,
    path: str,
    production_base: str,
) -> None:
    open_builder(page, app_url, path, "dashboard")
    canonical_new_york = resolved_timezone(page, "US/Eastern")
    canonical_utc = resolved_timezone(page, "UTC")
    canonical_helsinki = resolved_timezone(page, "Europe/Helsinki")
    canonical_kathmandu = resolved_timezone(page, "Asia/Kathmandu")
    assert page.locator("#dashboardUrl").input_value() == ""
    assert page.locator("#dashboardPreview").get_attribute("src") == "about:blank"
    assert page.locator("#tzChips").text_content() == "Add at least two timezones"

    add_dashboard_timezone(page, "US/Eastern", "button")
    assert dashboard_chip_names(page) == [canonical_new_york]
    assert page.locator("#tzChips .tz-chips-empty").text_content() == "Add one more timezone"
    assert page.locator("#dashboardUrl").input_value() == ""
    assert page.locator("#dashboardPreview").get_attribute("src") == "about:blank"

    add_dashboard_timezone(page, canonical_new_york, "enter")
    assert dashboard_chip_names(page) == [canonical_new_york]
    assert page.locator("#dashboardTzInput").input_value() == ""

    add_dashboard_timezone(page, "UTC", "enter")
    add_dashboard_timezone(page, "Europe/Helsinki", "button")
    add_dashboard_timezone(page, "Asia/Kathmandu", "enter")
    assert dashboard_chip_names(page) == [
        canonical_new_york,
        canonical_utc,
        canonical_helsinki,
        canonical_kathmandu,
    ]

    page.locator("#tzChips .tz-chip-remove").nth(1).click()
    assert dashboard_chip_names(page) == [
        canonical_new_york,
        canonical_helsinki,
        canonical_kathmandu,
    ]
    assert page.locator("#tzChips .tz-chip-remove").evaluate_all(
        "elements => elements.map(element => element.dataset.idx)"
    ) == ["0", "1", "2"]
    ordered_url = page.locator("#dashboardUrl").input_value()
    assert ordered_url.startswith(production_base + "?")
    assert query_values(ordered_url)["tz"] == [
        ",".join([canonical_new_york, canonical_helsinki, canonical_kathmandu])
    ]

    page.locator("#tzChips .tz-chip-remove").nth(2).click()
    page.locator("#tzChips .tz-chip-remove").nth(1).click()
    assert dashboard_chip_names(page) == [canonical_new_york]
    assert page.locator("#dashboardUrl").input_value() == ""
    assert page.locator("#dashboardPreview").get_attribute("src") == "about:blank"


@pytest.mark.parametrize(
    ("path", "panel", "page_theme"),
    [
        pytest.param("/", "embed", "light", id="analog-embed-light"),
        pytest.param("/digital/", "dashboard", "dark", id="digital-dashboard-dark"),
    ],
)
def test_builder_theme_follows_page_theme_until_user_chooses(
    page: Page,
    app_url: str,
    path: str,
    panel: str,
    page_theme: str,
) -> None:
    other_theme = "dark" if page_theme == "light" else "light"
    page.emulate_media(color_scheme=page_theme)
    open_page(page, app_url, path=path)
    theme_select = page.locator("#" + panel + "Theme")
    overlay = "#" + panel + "Overlay"

    def open_builder_panel() -> None:
        page.evaluate("linkId => document.getElementById(linkId).click()", panel + "Link")
        page.locator(overlay + ".visible").wait_for()

    def close_builder_and_toggle_page_theme() -> None:
        page.locator("#" + panel + "CloseBtn").click()
        page.locator("#themeToggle").evaluate("element => element.click()")

    def generated_theme() -> list[str]:
        if panel == "embed":
            return query_values(str(parsed_generated_iframe(page)["src"]))["theme"]
        return query_values(page.locator("#dashboardUrl").input_value())["theme"]

    open_builder_panel()
    assert theme_select.input_value() == page_theme
    if panel == "dashboard":
        add_dashboard_timezone(page, "UTC")
        add_dashboard_timezone(page, "Asia/Tokyo")
    assert generated_theme() == [page_theme]

    close_builder_and_toggle_page_theme()
    open_builder_panel()
    assert theme_select.input_value() == other_theme
    assert generated_theme() == [other_theme]

    select_and_dispatch(page, "#" + panel + "Theme", page_theme)
    close_builder_and_toggle_page_theme()
    open_builder_panel()
    assert theme_select.input_value() == page_theme


@pytest.mark.parametrize(
    ("path", "production_base"), [DIGITAL_DASHBOARD_CASE]
)
def test_dashboard_builder_quick_add_suggestions_add_canonical_timezones(
    page: Page,
    app_url: str,
    path: str,
    production_base: str,
) -> None:
    open_builder(page, app_url, path, "dashboard")
    canonical_utc = resolved_timezone(page, "UTC")
    canonical_tokyo = resolved_timezone(page, "Asia/Tokyo")
    suggestions = page.locator("#tzSuggestions .tz-suggestion")
    labels = suggestions.evaluate_all(
        "elements => elements.map(element => element.getAttribute('aria-label'))"
    )
    assert labels[0] == "Add " + canonical_utc
    assert "Add " + canonical_tokyo in labels
    assert len(labels) == len(set(labels))

    page.get_by_role("button", name="Add " + canonical_utc, exact=True).click()
    assert dashboard_chip_names(page) == [canonical_utc]
    assert page.get_by_role("button", name="Add " + canonical_utc, exact=True).count() == 0
    assert page.locator("#dashboardUrl").input_value() == ""

    page.get_by_role("button", name="Add " + canonical_tokyo, exact=True).click()
    assert dashboard_chip_names(page) == [canonical_utc, canonical_tokyo]
    assert page.evaluate("() => document.activeElement.classList.contains('tz-suggestion')") is True
    url = page.locator("#dashboardUrl").input_value()
    assert url.startswith(production_base + "?")
    assert query_values(url)["tz"] == [canonical_utc + "," + canonical_tokyo]
    assert page.locator("#tzChips .tz-chip-offset").all_text_contents()[1] == "GMT+9"

    page.locator("#tzChips .tz-chip-remove").nth(0).click()
    assert dashboard_chip_names(page) == [canonical_tokyo]
    assert page.evaluate("() => document.activeElement.getAttribute('aria-label')") == (
        "Remove " + canonical_tokyo
    )
    assert page.get_by_role("button", name="Add " + canonical_utc, exact=True).count() == 1


@pytest.mark.parametrize(
    ("path", "production_base"), [DIGITAL_DASHBOARD_CASE]
)
def test_dashboard_builder_invalid_timezone_has_accessible_error_and_no_actions(
    page: Page,
    app_url: str,
    path: str,
    production_base: str,
) -> None:
    install_clipboard_mock(page, "success")
    open_builder(page, app_url, path, "dashboard")
    page.evaluate(
        """() => {
            window.__openCalls = [];
            window.open = function (url, target) {
                window.__openCalls.push({ url: url, target: target });
                return null;
            };
        }"""
    )
    add_dashboard_timezone(page, "Mars/Olympus")
    validation = page.locator("#dashboardTzInput").evaluate(
        "element => ({ valid: element.checkValidity(), message: element.validationMessage })"
    )
    assert validation == {"valid": False, "message": "Invalid timezone"}
    assert page.locator("#dashboardUrl").input_value() == ""
    assert page.locator("#dashboardPreview").get_attribute("src") == "about:blank"
    page.locator("#dashboardCopyBtn").click()
    page.locator("#dashboardOpenBtn").click()
    assert page.evaluate("() => window.__clipboardWrites") == []
    assert page.evaluate("() => window.__openCalls") == []


@pytest.mark.parametrize("path", ["/", "/digital/"])
def test_every_dashboard_builder_control_reaches_url_and_preview_dom(
    page: Page,
    app_url: str,
    path: str,
) -> None:
    open_page(page, app_url, {"theme": "dark"}, path=path)
    page.evaluate("() => document.getElementById('dashboardLink').click()")
    canonical_utc = resolved_timezone(page, "UTC")
    canonical_kathmandu = resolved_timezone(page, "Asia/Kathmandu")
    encoded_timezones = quote(canonical_utc + "," + canonical_kathmandu, safe="")
    add_dashboard_timezone(page, "UTC")
    add_dashboard_timezone(page, "Asia/Kathmandu", "enter")
    initial_url = page.locator("#dashboardUrl").input_value()
    if path == "/":
        assert page.locator("#dashboardShadows").input_value() == "false"
        assert "shadows=" not in initial_url
    select_and_dispatch(page, "#dashboardRows", "2")
    select_and_dispatch(page, "#dashboardTheme", "light")
    select_and_dispatch(page, "#dashboardSeconds", "hide")
    select_and_dispatch(page, "#dashboardDayNight", "show")
    if path == "/":
        select_and_dispatch(page, "#dashboardNumbers", "hide")
        select_and_dispatch(page, "#dashboardShadows", "true")
        select_and_dispatch(page, "#dashboardBorder", "hide")
        expected_query = (
            "?tz=" + encoded_timezones + "&rows=2&theme=light&seconds=hide"
            "&border=hide&daynight=show&numbers=hide&shadows=true"
        )
        production_base = "https://clocksimulator.com/"
    else:
        select_and_dispatch(page, "#dashboardFormat", "12")
        select_and_dispatch(page, "#dashboardBorder", "show")
        expected_query = (
            "?tz=" + encoded_timezones + "&rows=2&theme=light&seconds=hide"
            "&format=12&border=show&daynight=show"
        )
        production_base = "https://clocksimulator.com/digital/"

    assert page.locator("#dashboardUrl").input_value() == initial_url
    page.clock.run_for(300)
    assert page.locator("#dashboardUrl").input_value() == production_base + expected_query
    preview_src = str(page.locator("#dashboardPreview").get_attribute("src"))
    assert preview_src.endswith(expected_query + "&embed=true")
    assert "embed=true" not in page.locator("#dashboardUrl").input_value()
    frame = wait_for_preview(
        page,
        "#dashboardPreview",
        ".clock-grid" if path == "/" else ".digital-grid",
    )
    assert frame.locator("html").evaluate(
        "element => !element.classList.contains('dark-mode')"
    ) is True
    if path == "/":
        assert frame.locator(".clock-cell").count() == 2
        second_hands = frame.locator(".clock-grid .second-hand")
        assert second_hands.count() == 2
        assert second_hands.evaluate_all(
            "elements => elements.every(element => getComputedStyle(element).display === 'none')"
        ) is True
        assert frame.locator(".clock-grid .clock-border").evaluate_all(
            "elements => elements.map(element => element.getAttribute('stroke'))"
        ) == ["none", "none"]
        numbers = frame.locator(".clock-grid .numbers")
        assert numbers.count() == 2
        assert numbers.evaluate_all(
            "elements => elements.every(element => getComputedStyle(element).display === 'none')"
        ) is True
        assert frame.locator(".clock-grid [filter]").count() == 8
        sun_icons = frame.locator(".clock-grid .sun-icon")
        assert sun_icons.count() == 2
        assert sun_icons.evaluate_all(
            "elements => elements.every(element => getComputedStyle(element).display === 'inline')"
        ) is True
    else:
        assert frame.locator(".digital-cell").count() == 2
        assert frame.locator(".digital-grid .digital-time").all_text_contents() == [
            "12:00 PM",
            "05:45 PM",
        ]
        assert frame.locator(".digital-cell.bordered").count() == 2
        assert frame.locator(".digital-grid .daynight-mark").evaluate_all(
            "elements => elements.map(element => element.dataset.state)"
        ) == ["day", "day"]


@pytest.mark.parametrize(
    ("path", "production_base"), [ANALOG_DASHBOARD_CASE]
)
def test_dashboard_builder_copy_and_open_receive_exact_production_url(
    page: Page,
    app_url: str,
    path: str,
    production_base: str,
) -> None:
    install_clipboard_mock(page, "success")
    open_builder(page, app_url, path, "dashboard")
    page.evaluate(
        """() => {
            window.__openCalls = [];
            window.open = function (url, target) {
                window.__openCalls.push({ url: url, target: target });
                return null;
            };
        }"""
    )
    add_dashboard_timezone(page, "UTC")
    add_dashboard_timezone(page, "Europe/Helsinki", "enter")
    expected_url = page.locator("#dashboardUrl").input_value()
    assert expected_url.startswith(production_base + "?")
    page.locator("#dashboardCopyBtn").click()
    page.wait_for_function(
        "() => document.getElementById('dashboardCopyBtn').textContent === 'Copied!'"
    )
    page.locator("#dashboardOpenBtn").click()
    assert page.evaluate("() => window.__clipboardWrites") == [expected_url]
    assert page.evaluate("() => window.__openCalls") == [
        {"url": expected_url, "target": "_blank"}
    ]


@pytest.mark.parametrize(
    ("path", "params", "width", "height", "render_case", "theme"),
    REAL_IFRAME_CASES,
)
def test_real_cross_origin_iframe_contract_across_renderers_themes_and_sizes(
    page: Page,
    app_url: str,
    iframe_harness_url: str,
    theme: str,
    path: str,
    params: dict[str, str],
    width: int,
    height: int,
    render_case: str,
) -> None:
    install_test_clock(page)
    page.goto(iframe_harness_url + "/__iframe_harness__")
    resolved_params = {
        key: theme if value == "{theme}" else value
        for key, value in params.items()
    }
    child_url = app_url.rstrip("/") + path + "?" + urlencode(resolved_params)
    page.locator("#clockFrame").evaluate(
        """(element, config) => {
            element.width = config.width;
            element.height = config.height;
            element.src = config.src;
        }""",
        {"width": width, "height": height, "src": child_url},
    )
    frame = page.frame_locator("#clockFrame")
    frame.locator("body.embed-mode").wait_for()
    if render_case == "analog-single":
        frame.locator("#hourHand").wait_for()
        assert frame.locator("#clock").get_attribute("aria-label") == "The time is 17:45"
        assert frame.locator("#secondHand").evaluate(
            "element => getComputedStyle(element).display"
        ) == "none"
        assert frame.locator("#clockBorder").get_attribute("stroke") == "none"
        assert frame.locator("#numbers").evaluate(
            "element => getComputedStyle(element).display"
        ) == "none"
    elif render_case == "analog-dashboard":
        frame.locator(".clock-grid .clock-cell").first.wait_for()
        assert frame.locator(".clock-grid .clock-cell").count() == 2
        assert frame.locator(".clock-grid [filter]").count() == 0
        assert frame.locator(".clock-label").all_text_contents() == ["UTC", "Kathmandu"]
        assert frame.locator(".clock-grid .clock-cell svg").evaluate_all(
            "elements => elements.map(element => element.getAttribute('aria-label'))"
        ) == ["UTC: 12:00", "Kathmandu: 17:45"]
    elif render_case == "digital-single":
        frame.locator("#digitalTime").wait_for()
        assert frame.locator("#digitalTime").text_content() == "05:45 PM"
        assert frame.locator("#digitalContainer").get_attribute("aria-label") == (
            "The time is 05:45 PM"
        )
        assert frame.locator("#digitalContainer").evaluate(
            "element => element.classList.contains('bordered')"
        ) is False
    else:
        frame.locator(".digital-grid .digital-cell").first.wait_for()
        assert frame.locator(".digital-grid .digital-cell").count() == 2
        assert frame.locator(".digital-label").all_text_contents() == ["UTC", "Kathmandu"]
        assert frame.locator(".digital-grid .digital-time").all_text_contents() == [
            "12:00 PM",
            "05:45 PM",
        ]
        assert frame.locator(".digital-cell").evaluate_all(
            "elements => elements.map(element => element.getAttribute('aria-label'))"
        ) == ["UTC: 12:00 PM", "Kathmandu: 05:45 PM"]
        assert frame.locator(".digital-grid .digital-cell.bordered").count() == 0

    assert frame.locator("html").evaluate(
        """(element, expectedTheme) => ({
            dark: element.classList.contains('dark-mode'),
            transparent: element.classList.contains('transparent-mode'),
            matches: (expectedTheme === 'dark') === element.classList.contains('dark-mode') &&
                (expectedTheme === 'transparent') === element.classList.contains('transparent-mode')
        })""",
        theme,
    )["matches"] is True
    assert frame.locator(".toggle-wrapper").evaluate(
        "element => getComputedStyle(element).display"
    ) == "none"
    assert frame.locator("#embedOverlay").is_visible() is False
    assert frame.locator("#dashboardOverlay").is_visible() is False
    assert frame.locator("#helpOverlay").is_visible() is False
    assert frame.locator("#favicon").count() == 0
    assert frame.locator("#timeAnnounce").text_content() == ""

    geometry = frame.locator("body").evaluate(
        """() => ({
            scrollWidth: document.documentElement.scrollWidth,
            scrollHeight: document.documentElement.scrollHeight,
            bodyScrollWidth: document.body.scrollWidth,
            bodyScrollHeight: document.body.scrollHeight,
            innerWidth: window.innerWidth,
            innerHeight: window.innerHeight,
            noScroll: document.documentElement.scrollWidth <= window.innerWidth &&
                document.documentElement.scrollHeight <= window.innerHeight &&
                document.body.scrollWidth <= window.innerWidth &&
                document.body.scrollHeight <= window.innerHeight
        })"""
    )
    assert geometry["noScroll"] is True, geometry
    assert page.locator("#parentSentinel").evaluate(
        "element => getComputedStyle(element).color"
    ) == "rgb(1, 2, 3)"
    assert frame.locator("body").evaluate(
        "element => getComputedStyle(element).fontFamily"
    ) != "Papyrus, serif"
    if render_case.startswith("digital"):
        digital_time_selector = (
            ".digital-grid .digital-time" if "dashboard" in render_case else "#digitalTime"
        )
        assert frame.locator(digital_time_selector).first.evaluate(
            "element => getComputedStyle(element).color"
        ) != "rgb(0, 255, 0)"
    content_selector = (
        ".clock-container, .clock-grid"
        if render_case.startswith("analog")
        else ".digital-container, .digital-grid"
    )
    assert frame.locator(content_selector).evaluate_all(
        "elements => elements.filter(element => getComputedStyle(element).display !== 'none').length"
    ) == 1

    iframe_box = page.locator("#clockFrame").bounding_box()
    assert iframe_box is not None
    with Image.open(io.BytesIO(page.screenshot())) as screenshot:
        pixel = screenshot.convert("RGB").getpixel(
            (int(iframe_box["x"]) + 2, int(iframe_box["y"]) + 2)
        )
    parent_background = (21, 72, 94)
    if theme == "transparent":
        assert pixel == parent_background
    else:
        assert pixel != parent_background
