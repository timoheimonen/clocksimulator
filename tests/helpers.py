from __future__ import annotations

import io
import json
import os

import pytest
from PIL import Image, ImageChops
from playwright.sync_api import Page


SCREENSHOTS_DIR = os.path.join(os.path.dirname(__file__), "screenshots")


def open_page(
    page: Page,
    app_url: str,
    params: dict[str, str] | None = None,
    localStorage_items: dict[str, str] | None = None,
    path: str = "",
    fixed_time: str = "2026-01-01T12:00:00Z",
) -> None:
    page.add_init_script("""
        (function() {
            var storageItems = %s;
            localStorage.clear();
            Object.keys(storageItems).forEach(function(key) {
                localStorage.setItem(key, storageItems[key]);
            });
            var OrigDate = Date;
            var fixed = OrigDate.parse(%s);
            window.Date = function() {
                if (arguments.length) return new OrigDate(...arguments);
                return new OrigDate(fixed);
            };
            window.Date.prototype = OrigDate.prototype;
            window.Date.prototype.constructor = window.Date;
            window.Date.now = function() { return fixed; };
            window.Date.parse = OrigDate.parse.bind(OrigDate);
            window.Date.UTC = OrigDate.UTC.bind(OrigDate);
            window.__setMockDate = function(value) { fixed = OrigDate.parse(value); };
        })();
    """ % (json.dumps(localStorage_items or {}), json.dumps(fixed_time)))

    url = app_url.rstrip("/") + path if path else app_url
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url += f"?{qs}"

    page.goto(url)
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_function(
        """() => {
            return (!!document.getElementById('clock') || !!document.getElementById('digitalTime')) &&
                document.documentElement.style.getPropertyValue('--app-height') !== '';
        }"""
    )


def assert_screenshot(page: Page, name: str, update: bool = False, threshold: float = 0.01) -> None:
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    baseline_path = os.path.join(SCREENSHOTS_DIR, name)

    page.wait_for_function(
        """() => {
            var html = document.documentElement;
            var inDashboard = !!document.querySelector('.clock-grid');
            var inDigitalDashboard = !!document.querySelector('.digital-grid');
            var normalize = function (value) {
                return String(value || '').replace(/\\s+/g, '').toLowerCase();
            };

            var bg = normalize(getComputedStyle(document.body).backgroundColor);
            var darkReady = !html.classList.contains('dark-mode') || bg === 'rgb(0,0,0)';
            var transparentReady = !html.classList.contains('transparent-mode') || bg === 'rgba(0,0,0,0)' || bg === 'transparent';
            var lightReady = html.classList.contains('dark-mode') || html.classList.contains('transparent-mode') || bg === 'rgb(240,240,240)';

            var singleReady = true;
            if (!inDashboard) {
                var singleHourHand = document.getElementById('hourHand');
                singleReady = !singleHourHand || singleHourHand.style.transform !== '';
            }

            var dashboardReady = true;
            if (inDashboard) {
                var dashboardHands = document.querySelectorAll('.clock-grid .hour-hand');
                for (var i = 0; i < dashboardHands.length; i++) {
                    if (dashboardHands[i].style.transform === '') {
                        dashboardReady = false;
                        break;
                    }
                }
            }

            var digitalReady = true;
            var digitalTime = document.getElementById('digitalTime');
            if (digitalTime) {
                digitalReady = digitalTime.textContent.trim() !== '';
            }
            if (inDigitalDashboard) {
                var digitalTimes = document.querySelectorAll('.digital-grid .digital-time');
                digitalReady = digitalTimes.length > 0;
                for (var j = 0; j < digitalTimes.length; j++) {
                    if (digitalTimes[j].textContent.trim() === '') {
                        digitalReady = false;
                        break;
                    }
                }
            }

            return darkReady && transparentReady && lightReady && singleReady && dashboardReady && digitalReady;
        }"""
    )

    screenshot_bytes = page.screenshot()
    actual_img = Image.open(io.BytesIO(screenshot_bytes))

    if update or not os.path.exists(baseline_path):
        actual_img.save(baseline_path)
        pytest.skip(f"Baseline screenshot created: {name}")
        return

    baseline_img = Image.open(baseline_path)

    if actual_img.size != baseline_img.size:
        pytest.fail(
            f"Screenshot size mismatch for {name}: "
            f"expected {baseline_img.size}, got {actual_img.size}. "
            "Run with --update-snapshots to regenerate baselines."
        )

    width, height = actual_img.size
    total_pixels = width * height

    diff_raw = ImageChops.difference(actual_img, baseline_img)
    zero = tuple(0 for _ in diff_raw.getbands())
    diff_count = sum(1 for px in diff_raw.get_flattened_data() if px != zero)

    diff_ratio = diff_count / total_pixels

    if diff_ratio > threshold:
        mask = diff_raw.convert("L").point(lambda v: 255 if v > 0 else 0)
        grey = Image.new("RGBA", actual_img.size, (128, 128, 128, 255))
        red = Image.new("RGBA", actual_img.size, (255, 0, 0, 255))
        diff_img = Image.composite(red, grey, mask)

        diff_name = name.replace(".png", "_diff.png")
        diff_path = os.path.join(SCREENSHOTS_DIR, diff_name)
        diff_img.save(diff_path)

        pytest.fail(
            f"Screenshot mismatch for {name}: {diff_count}/{total_pixels} pixels differ "
            f"({diff_ratio:.2%}). Diff saved to {diff_name}. "
            f"Run with --update-snapshots to regenerate baselines."
        )
