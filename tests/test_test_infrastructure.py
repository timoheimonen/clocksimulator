from __future__ import annotations

import os
from pathlib import Path
import shlex
import subprocess

import pytest

from tests.conftest import BrowserError, assert_expected_browser_errors


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TEST_WRAPPER = REPOSITORY_ROOT / "run_tests.sh"
RELEASE_WRAPPER = REPOSITORY_ROOT / "run_release_tests.sh"


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


def test_release_wrapper_matrix_and_fail_fast(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment["TMPDIR"] = str(tmp_path)
    result = run_release_wrapper(
        ["--dry-run", "--seed", "20260718"],
        tmp_path,
        env=environment,
    )

    assert result.returncode == 0, result.stderr
    assert os.access(RELEASE_WRAPPER, os.X_OK) is True
    trace_root = tmp_path / "clocksimulator-release.DRY-RUN-20260718"
    common = ["--randomly-seed=20260718", "--tracing=retain-on-failure"]
    assert release_dry_run_commands(result.stdout) == [
        (
            "chromium",
            [str(TEST_WRAPPER), "--browser-engine=chromium", *common,
             "--output=" + str(trace_root / "chromium")],
        ),
        (
            "firefox",
            [str(TEST_WRAPPER), "-m", "cross_browser", "--browser-engine=firefox", *common,
             "--output=" + str(trace_root / "firefox")],
        ),
        (
            "webkit",
            [str(TEST_WRAPPER), "-m", "cross_browser", "--browser-engine=webkit", *common,
             "--output=" + str(trace_root / "webkit")],
        ),
    ]
    assert trace_root.exists() is False

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    calls_path = tmp_path / "calls.txt"
    write_executable(
        fake_bin / "conda",
        "printf '%s\\n' \"$*\" >> \"$FAKE_CALLS\"\n"
        "printf 'synthetic gate failure\\n'\n"
        "exit 7\n",
    )
    environment.update(
        {
            "PATH": str(fake_bin) + os.pathsep + environment["PATH"],
            "FAKE_CALLS": str(calls_path),
            "PYTEST_ADDOPTS": "--collect-only",
        }
    )

    result = run_release_wrapper(["--seed=20260718"], tmp_path, env=environment)

    assert result.returncode == 7
    assert result.stdout.count("==>") == 1
    assert "FAILED: Chromium full suite" in result.stderr
    calls = calls_path.read_text(encoding="utf-8").splitlines()
    assert len(calls) == 1
    assert "-u PYTEST_ADDOPTS" in calls[0]


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
