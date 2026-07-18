from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import BrowserContext, CDPSession, Page


@dataclass
class ScriptCoverage:
    kind: str
    source_hash: str
    source_bytes: int
    urls: set[str] = field(default_factory=set)
    executed_ranges: list[tuple[int, int]] = field(default_factory=list)
    named_functions: dict[tuple[str, int, int], bool] = field(default_factory=dict)

    def merge(self, url: str, functions: list[dict[str, Any]]) -> None:
        self.urls.add(url)
        ranges = [
            (
                int(coverage_range["startOffset"]),
                int(coverage_range["endOffset"]),
                int(coverage_range.get("count", 0)),
            )
            for function in functions
            for coverage_range in function.get("ranges", [])
        ]
        boundaries = sorted(
            {
                boundary
                for start, end, _ in ranges
                for boundary in (max(0, start), min(self.source_bytes, end))
                if 0 <= boundary <= self.source_bytes
            }
        )
        for start, end in zip(boundaries, boundaries[1:]):
            if end <= start:
                continue
            covering = [
                coverage_range
                for coverage_range in ranges
                if coverage_range[0] <= start and coverage_range[1] >= end
            ]
            if not covering:
                continue
            smallest_span = min(item[1] - item[0] for item in covering)
            if any(
                item[2] > 0 and item[1] - item[0] == smallest_span
                for item in covering
            ):
                self.executed_ranges.append((start, end))
        for function in functions:
            function_ranges = function.get("ranges", [])
            name = function.get("functionName", "").strip()
            if not name or not function_ranges:
                continue
            first_range = function_ranges[0]
            signature = (
                name,
                int(first_range["startOffset"]),
                int(first_range["endOffset"]),
            )
            covered = any(
                coverage_range.get("count", 0) > 0
                for coverage_range in function_ranges
            )
            self.named_functions[signature] = (
                self.named_functions.get(signature, False) or covered
            )

    def executed_bytes(self) -> int:
        normalized = sorted(
            (
                max(0, start),
                min(self.source_bytes, end),
            )
            for start, end in self.executed_ranges
            if end > start
        )
        if not normalized:
            return 0
        total = 0
        current_start, current_end = normalized[0]
        for start, end in normalized[1:]:
            if start <= current_end:
                current_end = max(current_end, end)
            else:
                total += current_end - current_start
                current_start, current_end = start, end
        return total + current_end - current_start

    def as_dict(self) -> dict[str, Any]:
        names = sorted(
            {
                signature[0]
                for signature, covered in self.named_functions.items()
                if covered
            }
        )
        return {
            "source_hash": self.source_hash,
            "urls": sorted(self.urls),
            "source_bytes": self.source_bytes,
            "executed_bytes": self.executed_bytes(),
            "named_functions": len(self.named_functions),
            "covered_named_functions": sum(self.named_functions.values()),
            "covered_function_names": names,
        }


@dataclass
class CoverageSession:
    page: Page
    session: CDPSession


def application_source_hashes(public_directory: Path) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for kind, relative_path in (
        ("analog", "index.html"),
        ("digital", "digital/index.html"),
    ):
        html = (public_directory / relative_path).read_text()
        sources = re.findall(r"<script(?: [^>]*)?>(.*?)</script>", html, re.DOTALL)
        result[kind] = {
            hashlib.sha256(source.encode()).hexdigest() for source in sources
        }
    return result


def page_kind(url: str) -> str | None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        return None
    if parsed.hostname not in {
        "127.0.0.1",
        "localhost",
        "clocksimulator.com",
        "www.clocksimulator.com",
    }:
        return None
    if parsed.path in {"/", "/index.html"}:
        return "analog"
    if parsed.path in {"/digital", "/digital/", "/digital/index.html"}:
        return "digital"
    return None


def summarize_scripts(scripts: list[ScriptCoverage]) -> dict[str, Any]:
    script_rows = [script.as_dict() for script in scripts]
    source_bytes = sum(row["source_bytes"] for row in script_rows)
    executed_bytes = sum(row["executed_bytes"] for row in script_rows)
    named_functions = sum(row["named_functions"] for row in script_rows)
    covered_named_functions = sum(
        row["covered_named_functions"] for row in script_rows
    )
    return {
        "scripts": script_rows,
        "summary": {
            "script_count": len(script_rows),
            "source_bytes": source_bytes,
            "executed_bytes": executed_bytes,
            "executed_byte_ratio": (
                round(executed_bytes / source_bytes, 6) if source_bytes else 0
            ),
            "named_functions": named_functions,
            "covered_named_functions": covered_named_functions,
            "named_function_ratio": (
                round(covered_named_functions / named_functions, 6)
                if named_functions
                else 0
            ),
        },
    }


def enforce_coverage_baseline(
    report: dict[str, Any], baseline_path: Path
) -> None:
    if not baseline_path.exists():
        pytest.fail("JavaScript coverage baseline is missing: " + str(baseline_path))
    try:
        baseline = json.loads(baseline_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        pytest.fail("JavaScript coverage baseline is invalid: " + str(error))
    if baseline.get("schema_version") != 2:
        pytest.fail("JavaScript coverage baseline must use schema version 2")
    measured_root = baseline.get("measured_baseline")
    minimums = baseline.get("minimums")
    if not isinstance(measured_root, dict) or not isinstance(minimums, dict):
        pytest.fail("JavaScript coverage baseline sections are missing")

    measured_fields = (
        "source_bytes",
        "executed_bytes",
        "named_functions",
        "covered_named_functions",
    )
    for kind in ("analog", "digital"):
        measured = measured_root.get(kind)
        minimum = minimums.get(kind)
        if not isinstance(measured, dict) or not isinstance(minimum, dict):
            pytest.fail(kind + " JavaScript coverage baseline section is missing")
        measured_scripts = measured.get("scripts")
        measured_summary = measured.get("summary")
        if not isinstance(measured_scripts, list) or not isinstance(
            measured_summary, dict
        ):
            pytest.fail(kind + " measured JavaScript coverage is malformed")
        try:
            expected_summary = {
                "script_count": len(measured_scripts),
                **{
                    field: sum(int(script[field]) for script in measured_scripts)
                    for field in measured_fields
                },
            }
            measured_fingerprint = sorted(
                (str(script["source_hash"]), int(script["source_bytes"]))
                for script in measured_scripts
            )
            actual_scripts = report[kind]["scripts"]
            actual_summary = report[kind]["summary"]
            actual_fingerprint = sorted(
                (str(script["source_hash"]), int(script["source_bytes"]))
                for script in actual_scripts
            )
        except (KeyError, TypeError, ValueError) as error:
            pytest.fail(
                kind + " JavaScript coverage baseline is malformed: " + str(error)
            )
        for field, expected in expected_summary.items():
            if measured_summary.get(field) != expected:
                pytest.fail(
                    kind
                    + " measured JavaScript coverage summary is inconsistent for "
                    + field
                )
        if actual_fingerprint != measured_fingerprint:
            pytest.fail(
                kind
                + " JavaScript source fingerprint changed; publish a fresh canonical "
                + "coverage baseline"
            )
        try:
            minimum_named = int(minimum["covered_named_functions"])
            minimum_bytes = int(minimum["executed_bytes"])
        except (KeyError, TypeError, ValueError) as error:
            pytest.fail(
                kind + " JavaScript coverage minimum is malformed: " + str(error)
            )
        if measured_summary["covered_named_functions"] < minimum_named:
            pytest.fail(kind + " named-function minimum exceeds the measured baseline")
        if measured_summary["executed_bytes"] < minimum_bytes:
            pytest.fail(kind + " executed-byte minimum exceeds the measured baseline")
        if actual_summary["covered_named_functions"] < minimum_named:
            pytest.fail(kind + " named-function coverage regressed")
        if actual_summary["executed_bytes"] < minimum_bytes:
            pytest.fail(kind + " executed-byte coverage regressed significantly")
        covered_names = {
            name
            for script in actual_scripts
            for name in script["covered_function_names"]
        }
        missing_names = sorted(
            set(minimum.get("required_function_names", [])) - covered_names
        )
        if missing_names:
            pytest.fail(
                kind
                + " critical functions were not executed: "
                + ", ".join(missing_names)
            )


class JsCoverageManager:
    def __init__(
        self,
        enabled: bool,
        browser_engine: str,
        output_directory: Path,
        baseline_path: Path,
        allowed_source_hashes: dict[str, set[str]],
    ) -> None:
        self.enabled = enabled
        self.browser_engine = browser_engine
        self.output_directory = output_directory
        self.baseline_path = baseline_path
        self.allowed_source_hashes = allowed_source_hashes
        self.sessions: dict[Page, CoverageSession] = {}
        self.scripts: dict[tuple[str, str], ScriptCoverage] = {}

    def attach(self, page: Page) -> None:
        if not self.enabled or page in self.sessions:
            return
        if self.browser_engine != "chromium":
            pytest.fail("--js-coverage requires --browser-engine=chromium")
        session = page.context.new_cdp_session(page)
        session.send("Debugger.enable")
        session.send("Profiler.enable")
        session.send(
            "Profiler.startPreciseCoverage",
            {"callCount": True, "detailed": True, "allowTriggeredUpdates": False},
        )
        self.sessions[page] = CoverageSession(page=page, session=session)

    def finalize_context(self, context: BrowserContext) -> None:
        for page, coverage_session in list(self.sessions.items()):
            if page.context is context:
                self._finalize_session(coverage_session)
                del self.sessions[page]

    def _finalize_session(self, coverage_session: CoverageSession) -> None:
        page = coverage_session.page
        session = coverage_session.session
        if page.is_closed():
            return
        result = session.send("Profiler.takePreciseCoverage")
        for entry in result.get("result", []):
            kind = page_kind(entry.get("url", ""))
            if kind is None:
                continue
            try:
                source = session.send(
                    "Debugger.getScriptSource", {"scriptId": entry["scriptId"]}
                ).get("scriptSource", "")
            except Exception:
                source = ""
            if not source:
                continue
            source_hash = hashlib.sha256(source.encode()).hexdigest()
            if source_hash not in self.allowed_source_hashes[kind]:
                continue
            key = (kind, source_hash)
            script = self.scripts.setdefault(
                key,
                ScriptCoverage(
                    kind=kind,
                    source_hash=source_hash,
                    source_bytes=len(source),
                ),
            )
            script.merge(entry["url"], entry.get("functions", []))
        session.send("Profiler.stopPreciseCoverage")
        session.send("Profiler.disable")
        session.send("Debugger.disable")
        session.detach()

    def report(self) -> dict[str, Any]:
        report: dict[str, Any] = {"schema_version": 1}
        for kind in ("analog", "digital"):
            report[kind] = summarize_scripts(
                sorted(
                    (script for script in self.scripts.values() if script.kind == kind),
                    key=lambda script: script.source_hash,
                )
            )
        return report

    def finish(self) -> None:
        if not self.enabled:
            return
        for coverage_session in list(self.sessions.values()):
            self._finalize_session(coverage_session)
        self.sessions.clear()
        report = self.report()
        self.output_directory.mkdir(parents=True, exist_ok=True)
        report_path = self.output_directory / "coverage.json"
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        summary_lines = []
        for kind in ("analog", "digital"):
            summary = report[kind]["summary"]
            summary_lines.append(
                kind
                + ": "
                + str(summary["covered_named_functions"])
                + "/"
                + str(summary["named_functions"])
                + " named functions, "
                + str(summary["executed_bytes"])
                + "/"
                + str(summary["source_bytes"])
                + " executed bytes"
            )
        (self.output_directory / "summary.txt").write_text(
            "\n".join(summary_lines) + "\n"
        )
        self._assert_baseline(report)

    def _assert_baseline(self, report: dict[str, Any]) -> None:
        enforce_coverage_baseline(report, self.baseline_path)
