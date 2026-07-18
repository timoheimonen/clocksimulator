from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import time
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


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TEST_WRAPPER = REPOSITORY_ROOT / "run_tests.sh"
RELEASE_WRAPPER = REPOSITORY_ROOT / "run_release_tests.sh"


def save_image(path: Path, mode: str, size: tuple[int, int], color) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new(mode, size, color).save(path)


def run_release_wrapper(
    arguments: list[str],
    cwd: Path,
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(RELEASE_WRAPPER), *arguments],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        env=env,
    )


def release_dry_run_commands(stdout: str) -> list[tuple[str, list[str]]]:
    commands = []
    for line in stdout.splitlines():
        if not line.startswith("DRY-RUN ["):
            continue
        prefix, command_text = line.split("] ", 1)
        commands.append((prefix.removeprefix("DRY-RUN ["), shlex.split(command_text)))
    return commands


def write_executable(path: Path, body: str) -> None:
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(0o755)


def fake_release_environment(
    tmp_path: Path,
    *,
    gate_status: int,
    gate_sleep: int = 0,
) -> dict[str, str]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_executable(
        fake_bin / "conda",
        """if printf '%s' "$*" | grep -q 'python -m pytest'; then
    export PYTEST_ADDOPTS='--collect-only --update-snapshots'
    export PYTEST_PLUGINS='unexpected_plugin'
    export PYTEST_DISABLE_PLUGIN_AUTOLOAD=0
    export PYTHONOPTIMIZE=2
    export PYTHONPATH=/poisoned/python/path
    export PYTHONUSERBASE=/poisoned/user/base
    export PYTHONNOUSERSITE=0
    shift 4
    exec "$@"
fi
printf 'Python=3.12.0 pytest=9.0.2 Playwright=1.58.0 Pillow=12.0.0\n'
""",
    )
    write_executable(
        fake_bin / "python",
        """if [ "${PYTEST_ADDOPTS+set}" = set ] || [ "${PYTEST_PLUGINS+set}" = set ] || [ "${PYTHONOPTIMIZE+set}" = set ] || [ "${PYTHONPATH+set}" = set ] || [ "${PYTHONUSERBASE+set}" = set ]; then
    exit 90
fi
if [ "${PYTEST_DISABLE_PLUGIN_AUTOLOAD:-}" != 1 ] || [ "${PYTHONNOUSERSITE:-}" != 1 ]; then
    exit 91
fi
case " $* " in
    *" -p pytest_playwright.pytest_playwright -p pytest_randomly "*) ;;
    *) exit 92 ;;
esac
if [ "${FAKE_GATE_SLEEP:-0}" -gt 0 ]; then
    exec sleep "$FAKE_GATE_SLEEP"
fi
printf 'synthetic gate result\n'
exit "${FAKE_GATE_STATUS:-7}"
""",
    )
    write_executable(fake_bin / "node", "exit 0\n")
    write_executable(fake_bin / "wrangler", "printf '4.28.0\\n'\n")
    write_executable(
        fake_bin / "uname",
        """case "$1" in
    -s) printf 'Darwin\n' ;;
    -m) printf 'arm64\n' ;;
esac
""",
    )
    write_executable(fake_bin / "sw_vers", "printf '26.0\n'\n")
    write_executable(
        fake_bin / "git",
        """if [ "$1" = rev-parse ]; then
    printf '0123456789abcdef\n'
elif [ "$1" = status ] && [ -e "${FAKE_OUTPUT_PATH:-}" ]; then
    printf '?? release-output\n'
fi
""",
    )
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": str(fake_bin) + os.pathsep + environment["PATH"],
            "PYTEST_ADDOPTS": "--collect-only --update-snapshots",
            "PYTEST_PLUGINS": "unexpected_plugin",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "0",
            "PYTHONOPTIMIZE": "2",
            "PYTHONPATH": "/poisoned/python/path",
            "PYTHONUSERBASE": "/poisoned/user/base",
            "PYTHONNOUSERSITE": "0",
            "FAKE_GATE_STATUS": str(gate_status),
            "FAKE_GATE_SLEEP": str(gate_sleep),
            "FAKE_OUTPUT_PATH": str(tmp_path / "release-output"),
        }
    )
    return environment


def wait_for_path(path: Path, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.01)
    pytest.fail("Timed out waiting for path: " + str(path))


def test_test_wrapper_runs_from_repository_and_streams_conda_output(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_executable(
        fake_bin / "conda",
        "printf 'cwd=%s\\nargs=%s\\n' \"$PWD\" \"$*\"\n",
    )
    environment = os.environ.copy()
    environment["PATH"] = str(fake_bin) + os.pathsep + environment["PATH"]

    result = subprocess.run(
        [str(TEST_WRAPPER), "--collect-only"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        env=environment,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "cwd=" + str(REPOSITORY_ROOT),
        "args=run --no-capture-output -n clocksimulator env -u PYTEST_ADDOPTS "
        "-u PYTEST_PLUGINS -u PYTEST_DISABLE_PLUGIN_AUTOLOAD -u PYTHONOPTIMIZE "
        "-u PYTHONPATH -u PYTHONUSERBASE PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "
        "PYTHONNOUSERSITE=1 python -m pytest -p "
        "pytest_playwright.pytest_playwright -p pytest_randomly --collect-only",
    ]


def test_release_wrapper_is_executable_and_runs_from_outside_repository(
    tmp_path: Path,
) -> None:
    syntax = subprocess.run(
        ["bash", "-n", str(RELEASE_WRAPPER)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stderr
    assert os.access(RELEASE_WRAPPER, os.X_OK) is True

    output_path = tmp_path / "release artifacts"
    result = run_release_wrapper(
        [
            "--dry-run",
            "--seed",
            "20260718",
            "--output",
            str(output_path),
        ],
        tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert "Seed: 20260718" in result.stdout
    assert "Artifacts: " + str(output_path) in result.stdout
    assert output_path.exists() is False


def test_release_wrapper_dry_run_defines_exact_gate_matrix(tmp_path: Path) -> None:
    output_path = tmp_path / "release-output"
    result = run_release_wrapper(
        ["--dry-run", "--seed=20260718", "--output=" + str(output_path)],
        tmp_path,
    )

    assert result.returncode == 0, result.stderr
    commands = release_dry_run_commands(result.stdout)
    assert [slug for slug, _ in commands] == [
        "chromium-full",
        "visual",
        "service-worker",
        "deployment",
        "firefox",
        "webkit",
        "js-coverage",
    ]

    sanitized_prefix = [
        "env",
        "-u",
        "PYTEST_ADDOPTS",
        "-u",
        "PYTEST_PLUGINS",
        "-u",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
        "-u",
        "PYTHONOPTIMIZE",
        str(TEST_WRAPPER),
    ]
    expected_gate_arguments = {
        "chromium-full": [
            "--browser-engine=chromium",
            "--randomly-seed=20260718",
        ],
        "visual": [
            "-m",
            "visual",
            "--browser-engine=chromium",
            "--randomly-seed=20260718",
        ],
        "service-worker": [
            "-m",
            "service_worker",
            "--browser-engine=chromium",
            "--randomly-seed=20260718",
        ],
        "deployment": [
            "-m",
            "deployment",
            "--browser-engine=chromium",
            "--randomly-seed=20260718",
        ],
        "firefox": [
            "-m",
            "cross_browser and not chromium_only",
            "--browser-engine=firefox",
            "--randomly-seed=20260718",
        ],
        "webkit": [
            "-m",
            "cross_browser and not chromium_only",
            "--browser-engine=webkit",
            "--randomly-seed=20260718",
        ],
        "js-coverage": [
            "-m",
            "not visual and not service_worker and not deployment",
            "--browser-engine=chromium",
            "--js-coverage",
            "--js-coverage-output=" + str(output_path / "js-coverage"),
            "--randomly-seed=20260718",
        ],
    }

    for slug, command in commands:
        assert command == [
            *sanitized_prefix,
            *expected_gate_arguments[slug],
            "--output=" + str(output_path / "playwright" / slug),
            "--tracing=retain-on-failure",
        ]


@pytest.mark.parametrize("equals_form", [False, True], ids=("split", "equals"))
def test_release_wrapper_accepts_both_option_forms(
    tmp_path: Path, equals_form: bool
) -> None:
    output_path = tmp_path / ("release output " + str(equals_form))
    if equals_form:
        arguments = [
            "--dry-run",
            "--seed=00123",
            "--output=" + str(output_path),
        ]
    else:
        arguments = [
            "--dry-run",
            "--seed",
            "00123",
            "--output",
            "./" + output_path.name,
        ]

    result = run_release_wrapper(arguments, tmp_path)

    assert result.returncode == 0, result.stderr
    assert "Seed: 00123" in result.stdout
    assert "Artifacts: " + str(output_path) in result.stdout
    assert len(release_dry_run_commands(result.stdout)) == 7
    assert output_path.exists() is False


@pytest.mark.parametrize(
    ("arguments", "expected_error"),
    [
        pytest.param(["--dry-run", "--unknown"], "Unknown argument", id="unknown"),
        pytest.param(["--dry-run", "--seed"], "--seed requires a value", id="seed-missing"),
        pytest.param(["--seed", "--dry-run"], "--seed requires a value before the next option", id="seed-next-option"),
        pytest.param(["--dry-run", "--output"], "--output requires a value", id="output-missing"),
        pytest.param(["--output", "--dry-run"], "--output requires a value before the next option", id="output-next-option"),
        pytest.param(["--dry-run", "--seed=abc"], "--seed must be a non-negative integer", id="seed-invalid"),
        pytest.param(["--dry-run", "--seed="], "--seed must not be empty", id="seed-empty"),
        pytest.param(["--dry-run", "--output="], "--output must not be empty", id="output-empty"),
        pytest.param(
            ["--dry-run", "--output=missing/../existing"],
            "--output must not contain . or .. path components",
            id="output-parent-component",
        ),
        pytest.param(
            ["--dry-run", "--output=missing/."],
            "--output must not contain . or .. path components",
            id="output-current-component",
        ),
        pytest.param(
            ["--dry-run", "--output=./"],
            "--output must identify a new directory",
            id="output-leading-current-only",
        ),
    ],
)
def test_release_wrapper_rejects_invalid_arguments(
    tmp_path: Path, arguments: list[str], expected_error: str
) -> None:
    result = run_release_wrapper(arguments, tmp_path)

    assert result.returncode == 2
    assert expected_error in result.stderr
    assert "Usage: ./run_release_tests.sh" in result.stderr
    assert "DRY-RUN [" not in result.stdout
    assert (tmp_path / "--dry-run").exists() is False


def test_release_wrapper_anchors_relative_tmpdir_to_invocation_directory(
    tmp_path: Path,
) -> None:
    environment = os.environ.copy()
    environment["TMPDIR"] = "relative-temp"

    result = run_release_wrapper(
        ["--dry-run", "--seed=20260718"],
        tmp_path,
        env=environment,
    )

    expected_root = tmp_path / "relative-temp"
    assert result.returncode == 0, result.stderr
    assert (
        "Artifacts: " + str(expected_root / "clocksimulator-release.DRY-RUN-20260718")
        in result.stdout
    )
    assert expected_root.exists() is False


def test_release_wrapper_never_reuses_an_existing_output_directory(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "existing-output"
    output_path.mkdir()
    marker_path = output_path / "keep.txt"
    marker_path.write_text("keep", encoding="utf-8")

    result = run_release_wrapper(
        ["--seed=20260718", "--output=" + str(output_path)],
        tmp_path,
    )

    assert result.returncode == 1
    assert "Output path already exists: " + str(output_path) in result.stderr
    assert marker_path.read_text(encoding="utf-8") == "keep"
    assert list(output_path.iterdir()) == [marker_path]


def test_release_wrapper_sanitizes_pytest_environment_and_records_failure(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "release-output"
    poisoned_environment = fake_release_environment(tmp_path, gate_status=7)

    result = run_release_wrapper(
        ["--seed=20260718", "--output=" + str(output_path)],
        tmp_path,
        env=poisoned_environment,
    )

    assert result.returncode == 7
    assert result.stdout.count("==>") == 1
    assert "FAILED: Chromium full suite" in result.stderr
    assert "Re-run:" in result.stderr
    assert str(REPOSITORY_ROOT / "run_tests.sh") in result.stderr
    assert (output_path / "logs" / "chromium-full.log").read_text(
        encoding="utf-8"
    ) == "synthetic gate result\n"
    assert (output_path / "logs" / "visual.log").exists() is False
    summary = (output_path / "summary.txt").read_text(encoding="utf-8")
    assert "Dirty worktree: no" in summary
    assert "FAIL\tchromium-full\t" in summary
    assert "RESULT\tFAIL\t" in summary
    assert "gate=chromium-full exit=7" in summary


def test_release_wrapper_records_all_successful_gates(tmp_path: Path) -> None:
    output_path = tmp_path / "release-output"
    environment = fake_release_environment(tmp_path, gate_status=0)

    result = run_release_wrapper(
        ["--seed=20260718", "--output=" + str(output_path)],
        tmp_path,
        env=environment,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.count("==>") == 7
    assert "Release test matrix PASSED" in result.stdout
    summary = (output_path / "summary.txt").read_text(encoding="utf-8")
    for slug in (
        "chromium-full",
        "visual",
        "service-worker",
        "deployment",
        "firefox",
        "webkit",
        "js-coverage",
    ):
        assert "PASS\t" + slug + "\t" in summary
        assert (output_path / "logs" / (slug + ".log")).read_text(
            encoding="utf-8"
        ) == "synthetic gate result\n"
        assert (output_path / "logs" / (slug + ".status")).read_text(
            encoding="utf-8"
        ) == "0\t0\n"
    assert sum(line.startswith("PASS\t") for line in summary.splitlines()) == 7
    assert "RESULT\tPASS\t" in summary


def test_release_wrapper_forwards_targeted_termination_to_active_gate(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "release-output"
    environment = fake_release_environment(
        tmp_path,
        gate_status=0,
        gate_sleep=3,
    )
    process = subprocess.Popen(
        [
            str(RELEASE_WRAPPER),
            "--seed=20260718",
            "--output=" + str(output_path),
        ],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )

    wait_for_path(output_path / "logs" / "chromium-full.log")
    termination_started = time.monotonic()
    process.send_signal(signal.SIGTERM)
    stdout, stderr = process.communicate(timeout=5)

    assert process.returncode == 143
    assert time.monotonic() - termination_started < 2
    assert "Release test run interrupted by SIGTERM" in stderr
    assert stdout.count("==>") == 1
    summary = (output_path / "summary.txt").read_text(encoding="utf-8")
    assert "RESULT\tINTERRUPTED\t" in summary
    assert "signal=SIGTERM gate=chromium-full" in summary


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
