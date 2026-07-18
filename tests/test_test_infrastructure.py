from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from playwright.sync_api import Page

from tests.conftest import (
    BrowserError,
    assert_expected_browser_errors,
    browser_fixture_scope,
    finalize_test_context,
)
from tests.helpers import (
    TimerRecord,
    assert_image_snapshot,
    build_clock_url,
    install_timer_probe,
    open_page,
)
from tests.js_coverage import (
    ScriptCoverage,
    enforce_coverage_baseline,
    page_kind,
    summarize_scripts,
)


def save_image(path: Path, mode: str, size: tuple[int, int], color) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new(mode, size, color).save(path)


def test_teardown_browser_error_forces_trace_retention(tmp_path: Path) -> None:
    class FakeTracing:
        def __init__(self) -> None:
            self.path: Path | None = None

        def stop(self, path: Path | None = None) -> None:
            self.path = path

    class FakeContext:
        def __init__(self) -> None:
            self.tracing = FakeTracing()
            self.closed = False

        def close(self) -> None:
            self.closed = True

    class FakeCoverageManager:
        def finalize_context(self, context) -> None:
            assert context.closed is False

    class FakeConfig:
        rootpath = tmp_path

        def getoption(self, name: str):
            return {
                "--output": "test-results/playwright",
                "--tracing": "retain-on-failure",
            }[name]

    context = FakeContext()
    request = SimpleNamespace(
        config=FakeConfig(),
        node=SimpleNamespace(nodeid="tests/test_example.py::test_console_error"),
    )
    errors = [BrowserError("pageerror", "boom", "https://example.test/")]

    with pytest.raises(pytest.fail.Exception, match="Unexpected browser errors"):
        finalize_test_context(
            context,
            request,
            "retain-on-failure",
            FakeCoverageManager(),
            errors,
            [],
        )

    assert context.closed is True
    assert context.tracing.path == (
        tmp_path
        / "test-results/playwright"
        / "tests-test_example.py-test_console_error"
        / "trace.zip"
    )


def test_expected_browser_errors_match_exactly_and_preserve_multiplicity() -> None:
    error = BrowserError("console.error", "network failed", "https://example.test/")
    expected = "console.error: network failed (https://example.test/)"

    assert_expected_browser_errors([error, error], [expected, expected])

    with pytest.raises(pytest.fail.Exception, match="Unexpected browser errors"):
        assert_expected_browser_errors([error, error], [expected])
    with pytest.raises(pytest.fail.Exception, match="Expected browser error was not observed"):
        assert_expected_browser_errors(
            [error],
            ["console.error: network failed (https://wrong.test/)"],
        )


@pytest.mark.parametrize(
    ("engine", "expected_scope"),
    [
        pytest.param("chromium", "session", id="chromium"),
        pytest.param("firefox", "session", id="firefox"),
        pytest.param("webkit", "module", id="webkit"),
    ],
)
def test_browser_fixture_scope_limits_webkit_context_lifetime(
    engine: str,
    expected_scope: str,
) -> None:
    config = SimpleNamespace(getoption=lambda name: engine)
    assert browser_fixture_scope("browser", config) == expected_scope


def test_missing_snapshot_baseline_fails_without_creating_files(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "missing"
    actual = Image.new("RGB", (2, 2), (0, 0, 0))

    with pytest.raises(pytest.fail.Exception, match="Missing baseline screenshot"):
        assert_image_snapshot(actual, "clock.png", baseline_dir=baseline_dir)

    assert baseline_dir.exists() is False


def test_snapshot_update_writes_baseline_and_removes_old_diff(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "screenshots"
    diff_path = baseline_dir / "clock_diff.png"
    save_image(diff_path, "RGB", (2, 2), (255, 0, 0))
    actual = Image.new("RGB", (2, 2), (1, 2, 3))

    assert_image_snapshot(
        actual,
        "clock.png",
        update=True,
        baseline_dir=baseline_dir,
    )

    with Image.open(baseline_dir / "clock.png") as baseline:
        assert baseline.mode == "RGB"
        assert baseline.getpixel((0, 0)) == (1, 2, 3)
    assert diff_path.exists() is False


def test_snapshot_size_mismatch_fails_and_writes_diff(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "screenshots"
    save_image(baseline_dir / "clock.png", "RGB", (2, 2), (0, 0, 0))
    actual = Image.new("RGB", (3, 2), (0, 0, 0))

    with pytest.raises(pytest.fail.Exception, match="size mismatch"):
        assert_image_snapshot(actual, "clock.png", baseline_dir=baseline_dir)

    assert (baseline_dir / "clock_diff.png").exists() is True


def test_snapshot_color_mode_mismatch_fails_and_writes_diff(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "screenshots"
    save_image(baseline_dir / "clock.png", "RGB", (2, 2), (0, 0, 0))
    actual = Image.new("RGBA", (2, 2), (0, 0, 0, 255))

    with pytest.raises(pytest.fail.Exception, match="color mode mismatch"):
        assert_image_snapshot(actual, "clock.png", baseline_dir=baseline_dir)

    assert (baseline_dir / "clock_diff.png").exists() is True


def test_snapshot_channel_difference_at_tolerance_passes(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "screenshots"
    save_image(baseline_dir / "clock.png", "RGB", (2, 2), (10, 10, 10))
    save_image(baseline_dir / "clock_diff.png", "RGB", (2, 2), (255, 0, 0))
    actual = Image.new("RGB", (2, 2), (15, 10, 10))

    assert_image_snapshot(
        actual,
        "clock.png",
        channel_tolerance=5,
        baseline_dir=baseline_dir,
    )

    assert (baseline_dir / "clock_diff.png").exists() is False


def test_snapshot_channel_difference_over_tolerance_fails(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "screenshots"
    save_image(baseline_dir / "clock.png", "RGB", (2, 2), (10, 10, 10))
    actual = Image.new("RGB", (2, 2), (10, 10, 10))
    actual.putpixel((0, 0), (16, 10, 10))

    with pytest.raises(pytest.fail.Exception, match="1/4 pixels differ"):
        assert_image_snapshot(
            actual,
            "clock.png",
            channel_tolerance=5,
            baseline_dir=baseline_dir,
        )

    assert (baseline_dir / "clock_diff.png").exists() is True


def test_snapshot_changed_pixel_limit_is_exact(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "screenshots"
    save_image(baseline_dir / "clock.png", "RGB", (3, 1), (0, 0, 0))
    allowed = Image.new("RGB", (3, 1), (0, 0, 0))
    allowed.putpixel((0, 0), (1, 0, 0))

    assert_image_snapshot(
        allowed,
        "clock.png",
        max_changed_pixels=1,
        baseline_dir=baseline_dir,
    )

    rejected = allowed.copy()
    rejected.putpixel((1, 0), (1, 0, 0))
    with pytest.raises(pytest.fail.Exception, match="2/3 pixels differ"):
        assert_image_snapshot(
            rejected,
            "clock.png",
            max_changed_pixels=1,
            baseline_dir=baseline_dir,
        )


def test_transparent_snapshot_requires_alpha_background_and_content(
    tmp_path: Path,
) -> None:
    baseline_dir = tmp_path / "screenshots"
    valid = Image.new("RGBA", (3, 3), (0, 0, 0, 0))
    valid.putpixel((1, 1), (255, 255, 255, 255))

    assert_image_snapshot(
        valid,
        "transparent.png",
        update=True,
        baseline_dir=baseline_dir,
        transparent=True,
    )
    assert_image_snapshot(
        valid,
        "transparent.png",
        baseline_dir=baseline_dir,
        transparent=True,
    )

    opaque = Image.new("RGBA", (3, 3), (0, 0, 0, 255))
    with pytest.raises(pytest.fail.Exception, match="no fully transparent"):
        assert_image_snapshot(
            opaque,
            "transparent.png",
            baseline_dir=baseline_dir,
            transparent=True,
        )

    empty = Image.new("RGBA", (3, 3), (0, 0, 0, 0))
    with pytest.raises(pytest.fail.Exception, match="no visible clock content"):
        assert_image_snapshot(
            empty,
            "transparent.png",
            baseline_dir=baseline_dir,
            transparent=True,
        )

    leaked_background = valid.copy()
    leaked_background.putpixel((0, 0), (0, 0, 0, 1))
    with pytest.raises(pytest.fail.Exception, match="known transparent corner"):
        assert_image_snapshot(
            leaked_background,
            "transparent.png",
            baseline_dir=baseline_dir,
            transparent=True,
        )


def test_clock_url_uses_standard_query_encoding() -> None:
    assert build_clock_url(
        "http://127.0.0.1:8000/",
        "/digital/",
        {"tz": "UTC,Asia/Kathmandu", "label": "A/B + C"},
    ) == (
        "http://127.0.0.1:8000/digital/"
        "?tz=UTC%2CAsia%2FKathmandu&label=A%2FB+%2B+C"
    )
    assert build_clock_url("http://127.0.0.1:8000/?") == "http://127.0.0.1:8000/?"


def test_managed_clock_records_clears_and_runs_timers(
    page: Page,
    app_url: str,
) -> None:
    clock = install_timer_probe(page, "2026-01-01T12:00:00Z")
    page.goto(app_url.rstrip("/") + "/robots.txt", wait_until="domcontentloaded")
    timer_id = page.evaluate(
        """() => {
            window.__timerEffect = 0;
            return setInterval(function () { window.__timerEffect += 1; }, 600000);
        }"""
    )

    records = clock.timers()
    assert records == [
        TimerRecord(
            timer_id=timer_id,
            kind="interval",
            delay=600000,
            calls=0,
            cleared=False,
        )
    ]

    clock.run_timer(timer_id)
    assert page.evaluate("() => window.__timerEffect") == 1
    assert clock.timers()[0].calls == 1

    page.evaluate("timerId => clearInterval(timerId)", timer_id)
    assert clock.timers()[0].cleared is True

    clock.set_time("2026-01-01T12:01:00Z")
    assert page.evaluate("() => new Date().toISOString()") == "2026-01-01T12:01:00.000Z"


def test_open_page_skips_only_redundant_fresh_storage_navigation(
    page: Page,
    app_url: str,
) -> None:
    requested_paths = []
    page.on("request", lambda request: requested_paths.append(request.url))

    open_page(page, app_url)
    assert not any("/robots.txt" in url for url in requested_paths)

    page.evaluate("() => localStorage.setItem('transient-test-value', 'present')")
    requested_paths.clear()
    open_page(page, app_url)
    assert sum("/robots.txt" in url for url in requested_paths) == 1
    assert page.evaluate(
        "() => localStorage.getItem('transient-test-value')"
    ) is None


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        pytest.param("https://clocksimulator.com/", "analog", id="analog-root"),
        pytest.param("https://clocksimulator.com/index.html", "analog", id="analog-index"),
        pytest.param("https://clocksimulator.com/digital/", "digital", id="digital-root"),
        pytest.param("https://clocksimulator.com/digital/index.html", "digital", id="digital-index"),
        pytest.param("https://clocksimulator.com/extension/", None, id="extension"),
        pytest.param("about:blank", None, id="test-page"),
        pytest.param("https://third-party.example/", None, id="third-party"),
    ],
)
def test_js_coverage_page_classification(url: str, expected: str | None) -> None:
    assert page_kind(url) == expected


def test_js_coverage_merges_ranges_and_named_functions() -> None:
    script = ScriptCoverage(
        kind="analog",
        source_hash="abc",
        source_bytes=20,
    )
    script.merge(
        "https://clocksimulator.com/",
        [
            {
                "functionName": "updateClock",
                "ranges": [
                    {"startOffset": 0, "endOffset": 15, "count": 0},
                    {"startOffset": 0, "endOffset": 10, "count": 1},
                ],
            },
            {
                "functionName": "unusedFunction",
                "ranges": [{"startOffset": 10, "endOffset": 20, "count": 0}],
            },
        ],
    )
    script.merge(
        "https://clocksimulator.com/?theme=dark",
        [
            {
                "functionName": "updateClock",
                "ranges": [
                    {"startOffset": 0, "endOffset": 15, "count": 0},
                    {"startOffset": 5, "endOffset": 15, "count": 1},
                ],
            }
        ],
    )

    report = summarize_scripts([script])
    assert report["summary"] == {
        "script_count": 1,
        "source_bytes": 20,
        "executed_bytes": 15,
        "executed_byte_ratio": 0.75,
        "named_functions": 2,
        "covered_named_functions": 1,
        "named_function_ratio": 0.5,
    }
    assert report["scripts"][0]["covered_function_names"] == ["updateClock"]


def sample_js_coverage_contract() -> tuple[dict, dict]:
    report = {"schema_version": 1}
    measured_baseline = {
        "captured_on": "2026-07-18",
        "browser_engine": "Playwright Chromium 1.58.0",
    }
    minimums = {}
    for kind, source_hash, required_name in (
        ("analog", "a" * 64, "updateClock"),
        ("digital", "d" * 64, "scheduleNextTick"),
    ):
        script = {
            "source_hash": source_hash,
            "urls": ["https://clocksimulator.com/"],
            "source_bytes": 100,
            "executed_bytes": 80,
            "named_functions": 3,
            "covered_named_functions": 2,
            "covered_function_names": [required_name, "sharedFunction"],
        }
        report[kind] = {
            "scripts": [script],
            "summary": {
                "script_count": 1,
                "source_bytes": 100,
                "executed_bytes": 80,
                "executed_byte_ratio": 0.8,
                "named_functions": 3,
                "covered_named_functions": 2,
                "named_function_ratio": 0.666667,
            },
        }
        measured_baseline[kind] = {
            "scripts": [
                {
                    field: script[field]
                    for field in (
                        "source_hash",
                        "source_bytes",
                        "executed_bytes",
                        "named_functions",
                        "covered_named_functions",
                    )
                }
            ],
            "summary": {
                "script_count": 1,
                "source_bytes": 100,
                "executed_bytes": 80,
                "named_functions": 3,
                "covered_named_functions": 2,
            },
        }
        minimums[kind] = {
            "covered_named_functions": 1,
            "executed_bytes": 50,
            "required_function_names": [required_name],
        }
    baseline = {
        "schema_version": 2,
        "measured_baseline": measured_baseline,
        "minimums": minimums,
    }
    return report, baseline


def write_js_coverage_baseline(path: Path, baseline: dict) -> None:
    path.write_text(json.dumps(baseline))


def test_js_coverage_measured_baseline_and_floors_pass(tmp_path: Path) -> None:
    report, baseline = sample_js_coverage_contract()
    baseline_path = tmp_path / "coverage-baseline.json"
    write_js_coverage_baseline(baseline_path, baseline)

    enforce_coverage_baseline(report, baseline_path)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        pytest.param("source_hash", "b" * 64, id="source-hash"),
        pytest.param("source_bytes", 101, id="source-length"),
    ],
)
def test_js_coverage_stale_source_fingerprint_fails(
    tmp_path: Path,
    field: str,
    replacement: str | int,
) -> None:
    report, baseline = sample_js_coverage_contract()
    baseline["measured_baseline"]["analog"]["scripts"][0][field] = replacement
    if field == "source_bytes":
        baseline["measured_baseline"]["analog"]["summary"][field] = replacement
    baseline_path = tmp_path / "coverage-baseline.json"
    write_js_coverage_baseline(baseline_path, baseline)

    with pytest.raises(pytest.fail.Exception, match="source fingerprint changed"):
        enforce_coverage_baseline(report, baseline_path)


def test_js_coverage_inconsistent_measured_summary_fails(tmp_path: Path) -> None:
    report, baseline = sample_js_coverage_contract()
    baseline["measured_baseline"]["analog"]["summary"]["executed_bytes"] += 1
    baseline_path = tmp_path / "coverage-baseline.json"
    write_js_coverage_baseline(baseline_path, baseline)

    with pytest.raises(pytest.fail.Exception, match="summary is inconsistent"):
        enforce_coverage_baseline(report, baseline_path)


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        pytest.param(
            "covered_named_functions",
            0,
            "named-function coverage regressed",
            id="named-functions",
        ),
        pytest.param(
            "executed_bytes",
            49,
            "executed-byte coverage regressed",
            id="executed-bytes",
        ),
    ],
)
def test_js_coverage_regression_floors_fail(
    tmp_path: Path,
    field: str,
    replacement: int,
    message: str,
) -> None:
    report, baseline = sample_js_coverage_contract()
    report = copy.deepcopy(report)
    report["analog"]["summary"][field] = replacement
    baseline_path = tmp_path / "coverage-baseline.json"
    write_js_coverage_baseline(baseline_path, baseline)

    with pytest.raises(pytest.fail.Exception, match=message):
        enforce_coverage_baseline(report, baseline_path)


def test_js_coverage_missing_critical_function_fails(tmp_path: Path) -> None:
    report, baseline = sample_js_coverage_contract()
    report["analog"]["scripts"][0]["covered_function_names"] = ["sharedFunction"]
    baseline_path = tmp_path / "coverage-baseline.json"
    write_js_coverage_baseline(baseline_path, baseline)

    with pytest.raises(pytest.fail.Exception, match="critical functions were not executed"):
        enforce_coverage_baseline(report, baseline_path)
