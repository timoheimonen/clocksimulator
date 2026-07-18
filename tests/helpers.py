from __future__ import annotations

from dataclasses import dataclass
import io
import json
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest
from PIL import Image, ImageChops
from playwright.sync_api import Page


SCREENSHOTS_DIR = Path(__file__).with_name("screenshots")
DEFAULT_FIXED_TIME = "2026-01-01T12:00:00Z"


@dataclass(frozen=True)
class TimerRecord:
    timer_id: int
    kind: str
    delay: float
    calls: int
    cleared: bool


class TestClock:
    __test__ = False

    def __init__(self, page: Page) -> None:
        self.page = page

    def set_time(self, value: str) -> None:
        self.page.clock.set_fixed_time(value)

    def advance(self, milliseconds: int) -> None:
        self.page.clock.run_for(milliseconds)

    def fast_forward(self, milliseconds: int) -> None:
        self.page.clock.fast_forward(milliseconds)

    def timers(self) -> list[TimerRecord]:
        raw_records = self.page.evaluate(
            "() => window.__testTimers ? window.__testTimers.records() : []"
        )
        return [
            TimerRecord(
                timer_id=record["id"],
                kind=record["kind"],
                delay=record["delay"],
                calls=record["calls"],
                cleared=record["cleared"],
            )
            for record in raw_records
        ]

    def run_timer(self, timer_id: int) -> None:
        self.page.evaluate(
            "timerId => window.__testTimers.run(timerId)",
            timer_id,
        )


def install_test_clock(page: Page, fixed_time: str = DEFAULT_FIXED_TIME) -> TestClock:
    if getattr(page, "_clocksimulator_clock_installed", False):
        page.clock.set_fixed_time(fixed_time)
    else:
        page.clock.install(time=fixed_time)
        setattr(page, "_clocksimulator_clock_installed", True)
        page.clock.set_fixed_time(fixed_time)
    return TestClock(page)


def install_timer_probe(
    page: Page,
    fixed_time: str = DEFAULT_FIXED_TIME,
    manual: bool = False,
) -> TestClock:
    clock = install_test_clock(page, fixed_time)
    page.add_init_script(
        """(function (manual) {
            const nativeSetTimeout = window.setTimeout.bind(window);
            const nativeClearTimeout = window.clearTimeout.bind(window);
            const nativeSetInterval = window.setInterval.bind(window);
            const nativeClearInterval = window.clearInterval.bind(window);
            const records = new Map();
            let nextManualId = 900000000;

            function register(kind, nativeSet, callback, delay, args) {
                let id;
                const wrapped = function () {
                    const record = records.get(Number(id));
                    if (record) record.calls += 1;
                    if (typeof callback === 'function') return callback.apply(window, args);
                    return window.eval(String(callback));
                };
                id = manual ? nextManualId++ : nativeSet(wrapped, delay);
                records.set(Number(id), {
                    id: Number(id),
                    kind: kind,
                    delay: Number(delay) || 0,
                    calls: 0,
                    cleared: false,
                    callback: wrapped
                });
                return id;
            }

            window.setTimeout = function (callback, delay) {
                return register(
                    'timeout', nativeSetTimeout, callback, delay,
                    Array.prototype.slice.call(arguments, 2)
                );
            };
            window.setInterval = function (callback, delay) {
                return register(
                    'interval', nativeSetInterval, callback, delay,
                    Array.prototype.slice.call(arguments, 2)
                );
            };
            window.clearTimeout = function (id) {
                const record = records.get(Number(id));
                if (record) record.cleared = true;
                if (!manual) nativeClearTimeout(id);
            };
            window.clearInterval = function (id) {
                const record = records.get(Number(id));
                if (record) record.cleared = true;
                if (!manual) nativeClearInterval(id);
            };
            window.__testTimers = {
                records: function () {
                    return Array.from(records.values()).map(function (record) {
                        return {
                            id: record.id,
                            kind: record.kind,
                            delay: record.delay,
                            calls: record.calls,
                            cleared: record.cleared
                        };
                    });
                },
                run: function (id) {
                    const record = records.get(Number(id));
                    if (!record || record.cleared) throw new Error('Timer is unavailable: ' + id);
                    record.callback();
                }
            };
        })(%s);""" % json.dumps(manual)
    )
    return clock


def install_css_motion_suppression(page: Page) -> None:
    page.add_init_script("""(() => {
        function suppress() {
            if (!document.head) return;
            const style = document.createElement('style');
            style.textContent = '*,:before,:after {' +
                'transition-duration: 0s !important;' +
                'transition-delay: 0s !important;' +
                'animation-duration: 0s !important;' +
                'animation-delay: 0s !important;' +
                '}';
            document.head.appendChild(style);
        }
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', suppress, { once: true });
        } else {
            suppress();
        }
    })();""")


def press_tab(page: Page, reverse: bool = False) -> None:
    browser = page.context.browser
    keys = []
    if browser and browser.browser_type.name == "webkit":
        keys.append("Alt")
    if reverse:
        keys.append("Shift")
    keys.append("Tab")
    page.keyboard.press("+".join(keys))


def install_visibility_mock(page: Page, initial_state: str = "visible") -> None:
    page.add_init_script(
        """(function (initialState) {
            let state = initialState;
            Object.defineProperty(document, 'hidden', {
                configurable: true,
                get: function () { return state === 'hidden'; }
            });
            Object.defineProperty(document, 'visibilityState', {
                configurable: true,
                get: function () { return state; }
            });
            window.__setTestVisibility = function (nextState) {
                state = nextState;
                document.dispatchEvent(new Event('visibilitychange'));
            };
        })(%s);""" % json.dumps(initial_state)
    )


def build_clock_url(
    app_url: str,
    path: str = "",
    params: dict[str, str] | None = None,
) -> str:
    parsed = urlsplit(app_url)
    origin = parsed.scheme + "://" + parsed.netloc
    if not path and not params and app_url.endswith("?"):
        return origin + "/?"
    normalized_path = path if path.startswith("/") else "/" + path
    url = origin + (normalized_path or "/")
    if params:
        url += "?" + urlencode(params)
    return url


def seed_local_storage(
    page: Page,
    app_url: str,
    items: dict[str, str] | None = None,
    clear: bool = True,
) -> bool:
    parsed = urlsplit(app_url)
    origin = parsed.scheme + "://" + parsed.netloc
    page.goto(origin + "/robots.txt", wait_until="domcontentloaded")
    return page.evaluate(
        """({ items, clear }) => {
            try {
                if (clear) localStorage.clear();
                Object.keys(items).forEach(function (key) {
                    localStorage.setItem(key, items[key]);
                });
                return true;
            } catch (error) {
                return false;
            }
        }""",
        {"items": items or {}, "clear": clear},
    )


def expected_clock_count(params: dict[str, str] | None) -> int:
    if not params or "tz" not in params:
        return 1
    valid = []
    for candidate in params["tz"].split(","):
        timezone = candidate.strip()
        if not timezone:
            continue
        try:
            ZoneInfo(timezone)
        except ZoneInfoNotFoundError:
            continue
        valid.append(timezone)
    return len(valid) if len(valid) > 1 else 1


def wait_for_clock_ready(page: Page, expected_count: int = 1) -> None:
    page.wait_for_function(
        """expectedCount => {
            const appHeightReady = document.documentElement.style
                .getPropertyValue('--app-height') !== '';
            if (!appHeightReady) return false;

            const analogGrid = document.querySelector('.clock-grid');
            if (analogGrid) {
                const cells = Array.from(analogGrid.querySelectorAll('.clock-cell'));
                if (cells.length !== expectedCount) return false;
                return cells.every(function (cell) {
                    const hour = cell.querySelector('.hour-hand');
                    const minute = cell.querySelector('.minute-hand');
                    const label = cell.querySelector('.clock-label');
                    return hour && minute && label && label.textContent.trim() !== '' &&
                        hour.style.transform !== '' && minute.style.transform !== '';
                });
            }

            const digitalGrid = document.querySelector('.digital-grid');
            if (digitalGrid) {
                const cells = Array.from(digitalGrid.querySelectorAll('.digital-cell'));
                if (cells.length !== expectedCount) return false;
                return cells.every(function (cell) {
                    const time = cell.querySelector('time.digital-time');
                    const label = cell.querySelector('.digital-label');
                    return time && label && time.textContent.trim() !== '' &&
                        time.hasAttribute('datetime') && time.getAttribute('datetime') !== '' &&
                        label.textContent.trim() !== '';
                });
            }

            if (expectedCount !== 1) return false;
            const digitalTime = document.getElementById('digitalTime');
            if (digitalTime) {
                return digitalTime.textContent.trim() !== '' &&
                    digitalTime.hasAttribute('datetime') &&
                    digitalTime.getAttribute('datetime') !== '';
            }
            const hour = document.getElementById('hourHand');
            const minute = document.getElementById('minuteHand');
            return !!hour && !!minute && hour.style.transform !== '' && minute.style.transform !== '';
        }""",
        arg=expected_count,
    )


def navigate_clock_page(
    page: Page,
    url: str,
    expected_count: int = 1,
) -> None:
    page.goto(url)
    page.wait_for_load_state("domcontentloaded")
    wait_for_clock_ready(page, expected_count)


def reload_clock_page(page: Page, expected_count: int = 1) -> None:
    page.reload()
    page.wait_for_load_state("domcontentloaded")
    wait_for_clock_ready(page, expected_count)


def open_page(
    page: Page,
    app_url: str,
    params: dict[str, str] | None = None,
    localStorage_items: dict[str, str] | None = None,
    path: str = "",
    fixed_time: str = DEFAULT_FIXED_TIME,
) -> None:
    install_test_clock(page, fixed_time)
    seed_local_storage(page, app_url, localStorage_items, clear=True)
    navigate_clock_page(
        page,
        build_clock_url(app_url, path, params),
        expected_clock_count(params),
    )


def set_test_time(page: Page, value: str, advance_milliseconds: int = 20) -> None:
    page.clock.set_fixed_time(value)
    if advance_milliseconds:
        page.clock.run_for(advance_milliseconds)


def _diff_path(baseline_path: Path) -> Path:
    return baseline_path.with_name(baseline_path.stem + "_diff" + baseline_path.suffix)


def _write_diff_artifact(
    actual: Image.Image,
    baseline: Image.Image | None,
    diff_path: Path,
) -> None:
    diff_path.parent.mkdir(parents=True, exist_ok=True)
    if baseline is None or actual.size != baseline.size or actual.mode != baseline.mode:
        actual.convert("RGBA").save(diff_path)
        return

    mask = _changed_pixel_mask(actual, baseline)
    grey = Image.new("RGBA", actual.size, (128, 128, 128, 255))
    red = Image.new("RGBA", actual.size, (255, 0, 0, 255))
    Image.composite(red, grey, mask).save(diff_path)


def _changed_pixel_mask(actual: Image.Image, baseline: Image.Image) -> Image.Image:
    channel_masks = [
        channel.point(lambda value: 255 if value else 0)
        for channel in ImageChops.difference(actual, baseline).split()
    ]
    mask = channel_masks[0]
    for channel_mask in channel_masks[1:]:
        mask = ImageChops.lighter(mask, channel_mask)
    return mask


def _assert_transparent_image(image: Image.Image, name: str) -> None:
    if image.mode != "RGBA":
        pytest.fail(f"Transparent snapshot {name} must use RGBA mode, got {image.mode}")
    alpha = image.getchannel("A")
    minimum, maximum = alpha.getextrema()
    if minimum != 0:
        pytest.fail(f"Transparent snapshot {name} has no fully transparent background pixels")
    if maximum == 0:
        pytest.fail(f"Transparent snapshot {name} contains no visible clock content")
    corners = (
        alpha.getpixel((0, 0)),
        alpha.getpixel((image.width - 1, 0)),
        alpha.getpixel((0, image.height - 1)),
        alpha.getpixel((image.width - 1, image.height - 1)),
    )
    if corners != (0, 0, 0, 0):
        pytest.fail(
            f"Transparent snapshot {name} does not preserve the known transparent corner background"
        )


def assert_image_snapshot(
    actual: Image.Image,
    name: str,
    update: bool = False,
    baseline_dir: Path | str = SCREENSHOTS_DIR,
    transparent: bool = False,
) -> None:
    baseline_path = Path(baseline_dir) / name
    diff_path = _diff_path(baseline_path)

    if transparent:
        _assert_transparent_image(actual, name)

    if update:
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        actual.save(baseline_path)
        if diff_path.exists():
            diff_path.unlink()
        return

    if not baseline_path.exists():
        pytest.fail(
            f"Missing baseline screenshot: {baseline_path}. "
            "Run with --update-snapshots to create it explicitly."
        )

    with Image.open(baseline_path) as opened_baseline:
        baseline = opened_baseline.copy()

    if transparent:
        _assert_transparent_image(baseline, name)

    if actual.size != baseline.size:
        _write_diff_artifact(actual, baseline, diff_path)
        pytest.fail(
            f"Screenshot size mismatch for {name}: expected {baseline.size}, got {actual.size}. "
            "Run with --update-snapshots to regenerate the baseline."
        )

    if actual.mode != baseline.mode:
        _write_diff_artifact(actual, baseline, diff_path)
        pytest.fail(
            f"Screenshot color mode mismatch for {name}: "
            f"expected {baseline.mode}, got {actual.mode}."
        )

    mask = _changed_pixel_mask(actual, baseline)
    changed_pixels = mask.histogram()[255]

    if changed_pixels:
        total_pixels = actual.width * actual.height
        _write_diff_artifact(actual, baseline, diff_path)
        pytest.fail(
            f"Screenshot mismatch for {name}: {changed_pixels}/{total_pixels} pixels differ "
            f"Diff saved to {diff_path.name}."
        )

    if diff_path.exists():
        diff_path.unlink()


def assert_screenshot(
    page: Page,
    name: str,
    update: bool = False,
    transparent: bool = False,
    selector: str | None = None,
    clip: dict[str, float] | None = None,
    baseline_dir: Path | str = SCREENSHOTS_DIR,
) -> None:
    if selector and clip:
        raise ValueError("A screenshot cannot use both selector and clip")
    wait_for_clock_ready(page, expected_count=_rendered_clock_count(page))
    page.evaluate("() => document.fonts.ready")
    screenshot_options = {
        "animations": "disabled",
        "caret": "hide",
        "omit_background": transparent,
    }
    if selector:
        screenshot_bytes = page.locator(selector).screenshot(**screenshot_options)
    else:
        if clip:
            screenshot_options["clip"] = clip
        screenshot_bytes = page.screenshot(**screenshot_options)
    with Image.open(io.BytesIO(screenshot_bytes)) as opened_actual:
        actual = opened_actual.copy()
    assert_image_snapshot(
        actual,
        name,
        update=update,
        baseline_dir=baseline_dir,
        transparent=transparent,
    )


def _rendered_clock_count(page: Page) -> int:
    return page.evaluate(
        """() => {
            const analog = document.querySelectorAll('.clock-grid .clock-cell').length;
            const digital = document.querySelectorAll('.digital-grid .digital-cell').length;
            return analog || digital || 1;
        }"""
    )
