#!/usr/bin/env bash
set -euo pipefail

repository_root="$(CDPATH= cd "$(dirname "$0")" && pwd -P)"
seed=""
dry_run=false
trace_root=""

usage() {
  cat <<'EOF'
Usage: ./run_release_tests.sh [options]

Run the complete local clocksimulator release test matrix.

Options:
  --seed VALUE       Reuse an explicit non-negative pytest-randomly seed.
  --dry-run          Print the three release-gate commands without running them.
  -h, --help         Show this help.
EOF
}

argument_error() {
  printf 'Error: %s\n\n' "$1" >&2
  usage >&2
  exit 2
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

while [ "$#" -gt 0 ]; do
  case "$1" in
    --seed)
      [ "$#" -ge 2 ] || argument_error "--seed requires a value."
      seed="$2"
      shift 2
      ;;
    --seed=*)
      seed="${1#--seed=}"
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

if [ -z "$seed" ]; then
  seed="$(date -u +%s)"
fi
case "$seed" in
  *[!0-9]*) argument_error "--seed must be a non-negative integer." ;;
esac

cd "$repository_root"

run_gate() {
  local gate_name="$1"
  local gate_slug="$2"
  local status
  shift 2
  local command=(
    "$repository_root/run_tests.sh"
    "$@"
    "--randomly-seed=$seed"
    --tracing=retain-on-failure
    "--output=$trace_root/$gate_slug"
  )

  if [ "$dry_run" = true ]; then
    printf 'DRY-RUN [%s] ' "$gate_slug"
    print_shell_command "${command[@]}"
    return
  fi

  printf '\n==> %s\n' "$gate_name"
  printf 'Command: '
  print_shell_command "${command[@]}"
  if "${command[@]}"; then
    printf 'PASSED: %s\n' "$gate_name"
  else
    status=$?
    printf '\nFAILED: %s\n' "$gate_name" >&2
    printf 'Seed: %s\n' "$seed" >&2
    printf 'Failure traces: %s\n' "$trace_root" >&2
    exit "$status"
  fi
}

if [ "$dry_run" = true ]; then
  trace_root="${TMPDIR:-/tmp}"
  trace_root="${trace_root%/}/clocksimulator-release.DRY-RUN-$seed"
else
  trace_root="${TMPDIR:-/tmp}"
  trace_root="$(mktemp -d "${trace_root%/}/clocksimulator-release.XXXXXX")"
fi

printf 'Clocksimulator release test matrix\n'
printf 'Seed: %s\n' "$seed"
if [ "$dry_run" = false ]; then
  printf 'Failure traces: %s\n' "$trace_root"
fi

run_gate "Chromium full suite" "chromium" --browser-engine=chromium
run_gate "Firefox cross-browser suite" "firefox" -m cross_browser --browser-engine=firefox
run_gate "WebKit cross-browser suite" "webkit" -m cross_browser --browser-engine=webkit

if [ "$dry_run" = false ]; then
  printf '\nRelease test matrix PASSED.\n'
fi
