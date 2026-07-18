#!/usr/bin/env bash
set -euo pipefail

readonly REQUIRED_WRANGLER_VERSION="4.28.0"
readonly REQUIRED_MACOS_MAJOR="26"
readonly REQUIRED_ARCHITECTURE="arm64"

invocation_dir="$(pwd -P)"
repository_root="$(CDPATH= cd "$(dirname "$0")" && pwd -P)"
seed=""
requested_output=""
seed_was_set=false
output_was_set=false
dry_run=false
artifact_root=""
artifact_created=false
summary_ready=false
run_finalized=false
release_started_seconds=$SECONDS
active_gate_slug=""
active_pipeline_pid=""
release_started_at=""
git_commit="unknown"
git_dirty="unknown"
macos_version="unknown"
dependency_summary="unknown"
wrangler_version="unknown"

usage() {
  cat <<'EOF'
Usage: ./run_release_tests.sh [options]

Run the complete local clocksimulator release test matrix.

Options:
  --seed VALUE       Reuse an explicit non-negative pytest-randomly seed.
  --output PATH      Write logs, traces, and coverage under a new directory.
  --dry-run          Print the seven release-gate commands without running them.
  -h, --help         Show this help.
EOF
}

argument_error() {
  printf 'Error: %s\n\n' "$1" >&2
  usage >&2
  exit 2
}

fail() {
  if [ "$artifact_created" = true ] && [ "$summary_ready" != true ]; then
    write_summary_header || true
  fi
  finalize_summary "FAIL" "error=$1"
  printf 'Error: %s\n' "$1" >&2
  if [ "$artifact_created" = true ]; then
    printf 'Artifacts: %s\n' "$artifact_root" >&2
  fi
  exit 1
}

finalize_summary() {
  local result="$1"
  local detail="${2:-}"
  local release_duration

  if [ "$summary_ready" != true ] || [ "$run_finalized" = true ]; then
    return
  fi

  run_finalized=true
  release_duration=$((SECONDS - release_started_seconds))
  if [ -n "$detail" ]; then
    printf '\nRESULT\t%s\t%ss\t%s\n' "$result" "$release_duration" "$detail" >> "$artifact_root/summary.txt"
  else
    printf '\nRESULT\t%s\t%ss\n' "$result" "$release_duration" >> "$artifact_root/summary.txt"
  fi
}

write_summary_header() {
  if [ "$artifact_created" != true ] || [ "$summary_ready" = true ]; then
    return
  fi

  if {
    printf 'Clocksimulator release test run\n'
    printf 'Started: %s\n' "$release_started_at"
    printf 'Seed: %s\n' "$seed"
    printf 'Commit: %s\n' "$git_commit"
    printf 'Dirty worktree: %s\n' "$git_dirty"
    printf 'Platform: macOS %s %s\n' "$macos_version" "$(uname -m)"
    printf 'Dependencies: %s\n' "$dependency_summary"
    printf 'Wrangler: %s\n' "$wrangler_version"
    printf 'Artifacts: %s\n\n' "$artifact_root"
  } > "$artifact_root/summary.txt"; then
    summary_ready=true
    return
  fi

  return 1
}

print_shell_command() {
  local argument
  local separator=""
  for argument in "$@"; do
    printf '%s' "$separator"
    printf '%q' "$argument"
    separator=" "
  done
  printf '\n'
}

handle_signal() {
  local signal_name="$1"
  local exit_code="$2"
  local detail="signal=$signal_name"

  trap - HUP INT TERM
  set +e
  if [ -n "$active_pipeline_pid" ]; then
    kill -s "$signal_name" -- "-$active_pipeline_pid" 2>/dev/null
    wait "$active_pipeline_pid" 2>/dev/null
    active_pipeline_pid=""
  fi
  if [ "$artifact_created" = true ] && [ "$summary_ready" != true ]; then
    write_summary_header
  fi
  if [ -n "$active_gate_slug" ]; then
    detail="$detail gate=$active_gate_slug"
  fi
  finalize_summary "INTERRUPTED" "$detail"
  printf '\nRelease test run interrupted by %s.\n' "$signal_name" >&2
  if [ "$artifact_created" = true ]; then
    printf 'Artifacts: %s\n' "$artifact_root" >&2
  fi
  exit "$exit_code"
}

handle_exit() {
  local exit_code="$?"

  if [ "$exit_code" -ne 0 ]; then
    set +e
    finalize_summary "FAIL" "exit=$exit_code"
  fi
}

trap 'handle_signal SIGHUP 129' HUP
trap 'handle_signal SIGINT 130' INT
trap 'handle_signal SIGTERM 143' TERM
trap handle_exit EXIT

while [ "$#" -gt 0 ]; do
  case "$1" in
    --seed)
      [ "$#" -ge 2 ] || argument_error "--seed requires a value."
      case "$2" in
        -*) argument_error "--seed requires a value before the next option." ;;
      esac
      seed="$2"
      seed_was_set=true
      shift 2
      ;;
    --seed=*)
      seed="${1#--seed=}"
      seed_was_set=true
      shift
      ;;
    --output)
      [ "$#" -ge 2 ] || argument_error "--output requires a value."
      case "$2" in
        -*) argument_error "--output requires a value before the next option. Use --output=PATH for paths beginning with '-'." ;;
      esac
      requested_output="$2"
      output_was_set=true
      shift 2
      ;;
    --output=*)
      requested_output="${1#--output=}"
      output_was_set=true
      shift
      ;;
    --dry-run)
      dry_run=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      argument_error "Unknown argument: $1"
      ;;
  esac
done

if [ "$seed_was_set" = true ] && [ -z "$seed" ]; then
  argument_error "--seed must not be empty."
fi
if [ "$output_was_set" = true ] && [ -z "$requested_output" ]; then
  argument_error "--output must not be empty."
fi
if [ -z "$seed" ]; then
  seed="$(date -u +%s)"
fi
case "$seed" in
  *[!0-9]*) argument_error "--seed must be a non-negative integer." ;;
esac
if [ -n "$requested_output" ]; then
  while [ "${requested_output#./}" != "$requested_output" ]; do
    requested_output="${requested_output#./}"
    [ -n "$requested_output" ] || argument_error "--output must identify a new directory."
    case "$requested_output" in
      /*) argument_error "--output must not contain empty path components after a leading ./ prefix." ;;
    esac
  done
  case "/$requested_output/" in
    */./*|*/../*) argument_error "--output must not contain . or .. path components." ;;
  esac
  case "$requested_output" in
    /*) artifact_root="$requested_output" ;;
    *) artifact_root="$invocation_dir/$requested_output" ;;
  esac
else
  temporary_root="${TMPDIR:-/tmp}"
  case "$temporary_root" in
    /*) ;;
    *) temporary_root="$invocation_dir/$temporary_root" ;;
  esac
  if [ "$temporary_root" != "/" ]; then
    temporary_root="${temporary_root%/}"
  fi
  if [ "$dry_run" = true ]; then
    artifact_root="$temporary_root/clocksimulator-release.DRY-RUN-$seed"
  fi
fi

[ "$dry_run" = false ] || [ -n "$artifact_root" ] || argument_error "--output must not be empty."

[ -x "$repository_root/run_tests.sh" ] || fail "Repository test runner is missing or not executable: run_tests.sh"
for required_path in public tests wrangler.jsonc; do
  [ -e "$repository_root/$required_path" ] || fail "Repository file is missing: $required_path"
done

cd "$repository_root"

run_gate() {
  local gate_name="$1"
  local gate_slug="$2"
  local gate_started
  local gate_duration
  local test_status
  local tee_status
  local pipeline_status
  local pipeline_wrapper_status
  local gate_status_path
  local gate_command
  shift 2

  gate_command=(
    env
    -u PYTEST_ADDOPTS
    -u PYTEST_PLUGINS
    -u PYTEST_DISABLE_PLUGIN_AUTOLOAD
    -u PYTHONOPTIMIZE
    "$repository_root/run_tests.sh"
    "$@"
    "--output=$artifact_root/playwright/$gate_slug"
    --tracing=retain-on-failure
  )

  if [ "$dry_run" = true ]; then
    printf 'DRY-RUN [%s] ' "$gate_slug"
    print_shell_command "${gate_command[@]}"
    return
  fi

  printf '\n==> %s\n' "$gate_name"
  printf 'Command: '
  print_shell_command "${gate_command[@]}"
  gate_started=$SECONDS
  active_gate_slug="$gate_slug"
  gate_status_path="$artifact_root/logs/$gate_slug.status"

  set +e
  set -m
  (
    set +e
    "${gate_command[@]}" 2>&1 | tee "$artifact_root/logs/$gate_slug.log"
    pipeline_status=("${PIPESTATUS[@]}")
    printf '%s\t%s\n' "${pipeline_status[0]}" "${pipeline_status[1]}" > "$gate_status_path"
  ) &
  active_pipeline_pid=$!
  set +m
  wait "$active_pipeline_pid"
  pipeline_wrapper_status=$?
  active_pipeline_pid=""
  set -e

  if [ "$pipeline_wrapper_status" -ne 0 ]; then
    test_status="$pipeline_wrapper_status"
    tee_status=0
  elif [ -r "$gate_status_path" ]; then
    IFS=$'\t' read -r test_status tee_status < "$gate_status_path"
  else
    test_status=1
    tee_status=0
  fi
  gate_duration=$((SECONDS - gate_started))

  if [ "$test_status" -ne 0 ] || [ "$tee_status" -ne 0 ]; then
    if [ "$test_status" -eq 0 ]; then
      test_status="$tee_status"
    fi
    printf 'FAIL\t%s\t%ss\texit=%s\n' "$gate_slug" "$gate_duration" "$test_status" >> "$artifact_root/summary.txt"
    finalize_summary "FAIL" "gate=$gate_slug exit=$test_status"
    printf '\nFAILED: %s\n' "$gate_name" >&2
    printf 'Seed: %s\n' "$seed" >&2
    printf 'Re-run:\n' >&2
    print_shell_command \
      env \
      -u PYTEST_ADDOPTS \
      -u PYTEST_PLUGINS \
      -u PYTEST_DISABLE_PLUGIN_AUTOLOAD \
      -u PYTHONOPTIMIZE \
      "$repository_root/run_tests.sh" \
      "$@" \
      "--output=$artifact_root/playwright/rerun-$gate_slug" \
      --tracing=retain-on-failure >&2
    printf 'Artifacts: %s\n' "$artifact_root" >&2
    exit "$test_status"
  fi

  active_gate_slug=""
  printf 'PASS\t%s\t%ss\n' "$gate_slug" "$gate_duration" >> "$artifact_root/summary.txt"
  printf 'PASSED: %s (%ss)\n' "$gate_name" "$gate_duration"
}

run_release_matrix() {
  run_gate \
    "Chromium full suite" \
    "chromium-full" \
    --browser-engine=chromium \
    "--randomly-seed=$seed"
  run_gate \
    "Chromium visual snapshots" \
    "visual" \
    -m visual \
    --browser-engine=chromium \
    "--randomly-seed=$seed"
  run_gate \
    "Chromium service worker" \
    "service-worker" \
    -m service_worker \
    --browser-engine=chromium \
    "--randomly-seed=$seed"
  run_gate \
    "Chromium Wrangler deployment" \
    "deployment" \
    -m deployment \
    --browser-engine=chromium \
    "--randomly-seed=$seed"
  run_gate \
    "Firefox cross-browser core" \
    "firefox" \
    -m "cross_browser and not chromium_only" \
    --browser-engine=firefox \
    "--randomly-seed=$seed"
  run_gate \
    "WebKit cross-browser core" \
    "webkit" \
    -m "cross_browser and not chromium_only" \
    --browser-engine=webkit \
    "--randomly-seed=$seed"
  run_gate \
    "Chromium JavaScript coverage" \
    "js-coverage" \
    -m "not visual and not service_worker and not deployment" \
    --browser-engine=chromium \
    --js-coverage \
    "--js-coverage-output=$artifact_root/js-coverage" \
    "--randomly-seed=$seed"
}

printf 'Clocksimulator release test matrix\n'
printf 'Seed: %s\n' "$seed"

if [ "$dry_run" = true ]; then
  printf 'Artifacts: %s\n' "$artifact_root"
  run_release_matrix
  exit 0
fi

release_started_at="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
release_started_seconds=$SECONDS
git_commit="$(git rev-parse --verify HEAD 2>/dev/null || printf 'unknown')"
if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
  git_dirty="yes"
else
  git_dirty="no"
fi

if [ -n "$requested_output" ] && { [ -e "$artifact_root" ] || [ -L "$artifact_root" ]; }; then
  fail "Output path already exists: $artifact_root"
fi

printf 'Running preflight checks...\n'

command -v conda >/dev/null 2>&1 || fail "Conda is required. Install or enable Conda first."
command -v node >/dev/null 2>&1 || fail "Node.js is required for the Wrangler deployment gate."
command -v wrangler >/dev/null 2>&1 || fail "Wrangler $REQUIRED_WRANGLER_VERSION is required. Run: npm install --global wrangler@$REQUIRED_WRANGLER_VERSION"

[ "$(uname -s)" = "Darwin" ] || fail "The canonical visual release gate requires macOS."
[ "$(uname -m)" = "$REQUIRED_ARCHITECTURE" ] || fail "The canonical visual release gate requires $REQUIRED_ARCHITECTURE."
command -v sw_vers >/dev/null 2>&1 || fail "Unable to determine the macOS version with sw_vers."
macos_version="$(sw_vers -productVersion)"
case "$macos_version" in
  "$REQUIRED_MACOS_MAJOR".*) ;;
  *) fail "The canonical visual release gate requires macOS $REQUIRED_MACOS_MAJOR.x; found $macos_version." ;;
esac

if ! dependency_summary="$(conda run -n clocksimulator env -u PYTHONOPTIMIZE -u PYTHONPATH -u PYTHONUSERBASE PYTHONNOUSERSITE=1 python -c '
import sys
from importlib.metadata import version

expected = {
    "pytest": "9.0.2",
    "pytest-randomly": "4.1.0",
    "pytest-playwright": "0.7.2",
    "playwright": "1.58.0",
}
actual = {name: version(name) for name in expected}
mismatches = [
    name + "=" + actual[name] + " (expected " + expected[name] + ")"
    for name in expected
    if actual[name] != expected[name]
]
pillow = version("Pillow")
if not pillow.startswith("12."):
    mismatches.append("Pillow=" + pillow + " (expected 12.x)")
if sys.version_info[:2] != (3, 12):
    mismatches.append("Python=" + sys.version.split()[0] + " (expected 3.12.x)")
if mismatches:
    raise SystemExit("Dependency mismatch: " + ", ".join(mismatches))
print(
    "Python=" + sys.version.split()[0]
    + " pytest=" + actual["pytest"]
    + " Playwright=" + actual["playwright"]
    + " Pillow=" + pillow
)
')"; then
  fail "The clocksimulator Conda environment is missing or stale. Run: conda env update --name clocksimulator --file environment.yml --prune"
fi

if ! conda run --no-capture-output -n clocksimulator env -u PYTHONOPTIMIZE -u PYTHONPATH -u PYTHONUSERBASE PYTHONNOUSERSITE=1 python -c '
from playwright.sync_api import sync_playwright

with sync_playwright() as playwright:
    for name in ("chromium", "firefox", "webkit"):
        browser = getattr(playwright, name).launch()
        browser.close()
'; then
  fail "A Playwright browser is missing or cannot launch. Run: conda run -n clocksimulator python -m playwright install chromium firefox webkit"
fi

if ! wrangler_version="$(wrangler --version 2>/dev/null)"; then
  fail "Wrangler failed to report its version."
fi
[ "$wrangler_version" = "$REQUIRED_WRANGLER_VERSION" ] || fail "Wrangler $REQUIRED_WRANGLER_VERSION is required; found $wrangler_version."

if [ -n "$requested_output" ]; then
  artifact_parent="$(dirname "$artifact_root")"
  mkdir -p "$artifact_parent" || fail "Unable to create output parent directory: $artifact_parent"
  if ! mkdir "$artifact_root"; then
    fail "Unable to create new output directory: $artifact_root"
  fi
else
  if ! artifact_root="$(mktemp -d "$temporary_root/clocksimulator-release.XXXXXX")"; then
    fail "Unable to create a temporary output directory under: $temporary_root"
  fi
fi
artifact_created=true
write_summary_header || fail "Unable to initialize the release summary: $artifact_root/summary.txt"
mkdir "$artifact_root/logs" "$artifact_root/playwright" || fail "Unable to create artifact subdirectories under: $artifact_root"
printf 'Artifacts: %s\n' "$artifact_root"

if [ "$git_dirty" = "yes" ]; then
  printf 'Warning: the release matrix is running against a dirty worktree.\n' >&2
fi
printf 'Dependencies: %s\n' "$dependency_summary"
printf 'Wrangler: %s\n' "$wrangler_version"

run_release_matrix

release_duration=$((SECONDS - release_started_seconds))
finalize_summary "PASS"
printf '\nRelease test matrix PASSED in %ss.\n' "$release_duration"
printf 'Seed: %s\n' "$seed"
printf 'Artifacts: %s\n' "$artifact_root"
