from __future__ import annotations

import os
from pathlib import Path
import shlex
import subprocess
from types import SimpleNamespace

import pytest
from PIL import Image
from playwright.sync_api import Page

from tests.conftest import (
    BrowserError,
    assert_expected_browser_errors,
    finalize_test_context,
)
from tests.helpers import (
    TimerRecord,
    assert_image_snapshot,
    install_timer_probe,
    open_page,
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


def test_release_wrapper_defines_safe_three_gate_matrix(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment["TMPDIR"] = str(tmp_path)
    result = run_release_wrapper(
        ["--dry-run", "--seed", "20260718"],
        tmp_path,
        env=environment,
    )

    assert result.returncode == 0, result.stderr
    assert os.access(RELEASE_WRAPPER, os.X_OK) is True
    commands = release_dry_run_commands(result.stdout)
    trace_root = tmp_path / "clocksimulator-release.DRY-RUN-20260718"
    assert commands == [
        (
            "chromium",
            [
                str(TEST_WRAPPER),
                "--browser-engine=chromium",
                "--randomly-seed=20260718",
                "--tracing=retain-on-failure",
                "--output=" + str(trace_root / "chromium"),
            ],
        ),
        (
            "firefox",
            [
                str(TEST_WRAPPER),
                "-m",
                "cross_browser",
                "--browser-engine=firefox",
                "--randomly-seed=20260718",
                "--tracing=retain-on-failure",
                "--output=" + str(trace_root / "firefox"),
            ],
        ),
        (
            "webkit",
            [
                str(TEST_WRAPPER),
                "-m",
                "cross_browser",
                "--browser-engine=webkit",
                "--randomly-seed=20260718",
                "--tracing=retain-on-failure",
                "--output=" + str(trace_root / "webkit"),
            ],
        ),
    ]
    assert "--update-snapshots" not in result.stdout
    assert trace_root.exists() is False


def test_release_wrapper_stops_after_first_failed_gate(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    calls_path = tmp_path / "calls.txt"
    write_executable(
        fake_bin / "conda",
        "printf '%s\\n' \"$*\" >> \"$FAKE_CALLS\"\n"
        "printf 'synthetic gate failure\\n'\n"
        "exit 7\n",
    )
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": str(fake_bin) + os.pathsep + environment["PATH"],
            "TMPDIR": str(tmp_path),
            "FAKE_CALLS": str(calls_path),
            "PYTEST_ADDOPTS": "--collect-only --update-snapshots",
        }
    )

    result = run_release_wrapper(
        ["--seed=20260718"],
        tmp_path,
        env=environment,
    )

    assert result.returncode == 7
    assert result.stdout.count("==>") == 1
    assert "FAILED: Chromium full suite" in result.stderr
    calls = calls_path.read_text(encoding="utf-8").splitlines()
    assert len(calls) == 1
    assert "-u PYTEST_ADDOPTS" in calls[0]
    assert "--update-snapshots" not in calls[0]


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


@pytest.mark.parametrize(
    ("variant", "message"),
    [
        pytest.param("size", "size mismatch", id="size"),
        pytest.param("color-mode", "color mode mismatch", id="color-mode"),
        pytest.param("pixel", "1/4 pixels differ", id="pixel"),
    ],
)
def test_snapshot_mismatch_fails_and_writes_diff(
    tmp_path: Path,
    variant: str,
    message: str,
) -> None:
    baseline_dir = tmp_path / "screenshots"
    save_image(baseline_dir / "clock.png", "RGB", (2, 2), (0, 0, 0))
    if variant == "size":
        actual = Image.new("RGB", (3, 2), (0, 0, 0))
    elif variant == "color-mode":
        actual = Image.new("RGBA", (2, 2), (0, 0, 0, 255))
    else:
        actual = Image.new("RGB", (2, 2), (0, 0, 0))
        actual.putpixel((0, 0), (1, 0, 0))

    with pytest.raises(pytest.fail.Exception, match=message):
        assert_image_snapshot(actual, "clock.png", baseline_dir=baseline_dir)

    assert (baseline_dir / "clock_diff.png").exists() is True


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

    invalid_cases = [
        (
            Image.new("RGBA", (3, 3), (0, 0, 0, 255)),
            "no fully transparent",
        ),
        (
            Image.new("RGBA", (3, 3), (0, 0, 0, 0)),
            "no visible clock content",
        ),
    ]
    leaked_background = valid.copy()
    leaked_background.putpixel((0, 0), (0, 0, 0, 1))
    invalid_cases.append((leaked_background, "known transparent corner"))

    for actual, message in invalid_cases:
        with pytest.raises(pytest.fail.Exception, match=message):
            assert_image_snapshot(
                actual,
                "transparent.png",
                baseline_dir=baseline_dir,
                transparent=True,
            )


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

    assert clock.timers() == [
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


def test_open_page_clears_storage_between_tests(page: Page, app_url: str) -> None:
    open_page(page, app_url)
    page.evaluate("() => localStorage.setItem('transient-test-value', 'present')")

    open_page(page, app_url)

    assert page.evaluate("() => localStorage.getItem('transient-test-value')") is None
