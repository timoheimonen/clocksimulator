# Testing clocksimulator

The test suite is a release gate for the analog and digital applications, not a source-code string checker. It verifies rendered time, URL contracts, browser API lifecycles, accessibility, offline behavior, Cloudflare routing, and visual output.

Do not maintain a hand-written test count here. Use collection when a count is needed:

```bash
conda run -n clocksimulator python -m pytest --collect-only
```

## Environment

All tests run in the project-specific Conda environment:

```bash
conda env create --file environment.yml
conda run -n clocksimulator python -m playwright install chromium firefox webkit
npm install --global wrangler@4.28.0
```

Update an existing environment with:

```bash
conda env update --name clocksimulator --file environment.yml --prune
conda run -n clocksimulator python -m playwright install chromium firefox webkit
npm install --global wrangler@4.28.0
```

`requirements-dev.txt` is the single pip dependency list consumed by `environment.yml`. Browser versions come from the pinned Playwright package. The full suite also requires Node.js and the explicitly pinned Wrangler 4.28.0 command above.

## Common commands

```bash
./run_release_tests.sh
./run_release_tests.sh --seed 20260718
./run_release_tests.sh --output /tmp/clocksimulator-release
./run_release_tests.sh --dry-run
conda run -n clocksimulator python -m pytest
conda run -n clocksimulator python -m pytest -p no:randomly
conda run -n clocksimulator python -m pytest --randomly-seed=20260718
conda run -n clocksimulator python -m pytest -m visual
conda run -n clocksimulator python -m pytest -m service_worker
conda run -n clocksimulator python -m pytest -m deployment
conda run -n clocksimulator python -m pytest -m "cross_browser and not chromium_only" --browser-engine=firefox
conda run -n clocksimulator python -m pytest -m "cross_browser and not chromium_only" --browser-engine=webkit
```

`./run_tests.sh` is a small live-streaming wrapper around one pytest invocation and forwards all arguments. `./run_release_tests.sh` is the canonical one-command local release gate. It runs the complete Chromium suite, the isolated visual, service-worker and deployment gates, the Firefox and WebKit core matrices, and Chromium JavaScript coverage sequentially with one recorded random seed. It stops at the first failure and prints the exact failed-gate command for reproduction.

## Markers

| Marker | Purpose |
|---|---|
| `visual` | Compares rendered output with committed baselines |
| `service_worker` | Runs with service workers enabled in an isolated context |
| `deployment` | Runs against pinned Wrangler 4.28.0 rather than the fast test server |
| `cross_browser` | Critical behavior required in Chromium, Firefox, and WebKit |
| `chromium_only` | Depends on Chromium-specific APIs such as CDP or service workers in this harness |
| `accessibility` | Semantics, focus, reflow, contrast, and user preferences |

Markers are registered under `--strict-markers`. Release checks are run manually. When changing marker assignments or commands, use `--collect-only` with the same marker expression first so an empty selection cannot pass unnoticed.

## Behavior responsibility matrix

| Contract | A single top | A dash top | D single top | D dash top | A single iframe | A dash iframe | D single iframe | D dash iframe | Browsers | Primary tests |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Time, target timezone, offsets, DST | Yes | Yes | Yes | Yes | Exact time | Exact time | Exact time | Exact time | Cross-browser | `test_timezone_dst.py`, `test_builders.py` |
| Feature parameters and defaults | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Core subset | `test_embed_mode.py`, `test_dashboard_mode.py`, `test_digital_clock.py`, `test_builders.py` |
| Theme priority and pre-render FOUC | Yes | Shared root | Yes | Shared root | Yes | Yes | Yes | Yes | Cross-browser | `test_theme_handling.py`, `test_builders.py` |
| Embed and dashboard builders | Output | Output | Output | Output | Yes | Yes | Yes | Yes | Cross-browser | `test_builders.py` |
| Saved settings and cross-page fields | Yes | Same app | Yes | Same app | URL-only | URL-only | URL-only | URL-only | Cross-browser | `test_saved_settings.py` |
| Wake Lock intent and races | Yes | Same app | Yes | Same app | Disabled | Disabled | Disabled | Disabled | Cross-browser | `test_wake_lock.py` |
| Keyboard, dialogs, semantics, reflow | Yes | Yes | Yes | Yes | Embed semantics | Embed semantics | Embed semantics | Embed semantics | Cross-browser | `test_accessibility.py`, `test_builders.py` |
| Offline install/activate/fetch | Yes | Fallback | Yes | Fallback | — | — | — | — | Chromium | `test_service_worker.py` |
| Cloudflare routes, headers, MIME | Yes | Shared page | Yes | Shared page | Cross-origin | Cross-origin | Cross-origin | Cross-origin | Chromium | `test_deployment_contract.py` |
| Versions, manifest, icons, canonicals | Yes | Shared app | Yes | Shared app | — | — | — | — | Static | `test_static_contracts.py` |
| Snapshot oracle itself | Yes | Yes | Yes | Yes | Transparent | Embed view | Transparent | Dashboard view | Chromium | `test_test_infrastructure.py`, visual-marked tests |

The matrix names the primary owner. Tests may deliberately overlap when they exercise a distinct implementation path or integration boundary.

## Fixture isolation

Every test receives a fresh `BrowserContext` and page. The normal context blocks service workers; the service-worker context allows them and is discarded after one test. Locale, viewport, device scale factor, color scheme, reduced-motion preference, and timezone are explicit.

Chromium and Firefox share one browser process per session. WebKit restarts the browser process for each test module because its macOS network process stops accepting navigations after a large number of short-lived contexts; the contexts and pages remain function-scoped and isolated. Keyboard traversal uses Option+Tab in macOS WebKit, matching the platform setting that includes form controls, and ordinary Tab in Chromium and Firefox.

`open_page()` installs Playwright's controlled clock, ensures that test's origin storage is empty, navigates, and waits for exact render readiness. A fresh isolated `about:blank` page is already empty, so the helper skips the otherwise redundant storage navigation in that one case. Explicit storage seeds and repeated calls still navigate to the origin and clear it; an infrastructure regression test enforces both branches. Separate helpers support navigation and reload without clearing storage. Tests that need another timezone use a separate Helsinki context rather than mutating a shared session.

The timer probe records timeout and interval identity, delay, calls, and cancellation. Manual mode invokes callbacks without real waiting. Production and test code must not use sleep-based synchronization.

Builder and Wake Lock behavior tests inject test-only CSS that removes transition and animation durations. This does not change `prefers-reduced-motion`, so application JavaScript follows the ordinary-motion path while Playwright avoids waiting for purely decorative transitions. Dedicated normal-motion, reduced-motion, and visual tests run without that suppression.

The ordinary asset server is threaded so intercepted document requests can fetch the original response without deadlocking the server. Shutdown closes the socket and joins the serving thread; daemon request threads cannot hold the test process open.

Unexpected `pageerror` and `console.error` events fail teardown. A test that intentionally causes an error must declare the exact expected kind, message, URL, and multiplicity. `--tracing=retain-on-failure` records a trace from these custom contexts under `--output`.

## Time contracts

The browser's default timezone is UTC. Clock screenshots use `2026-01-01T12:00:00Z`. DST tests cross the exact 2026 New York spring and fall transitions within one page session. The target-timezone offset must be recalculated on the first update at or after 60,000 ms. Day is `[06:00, 18:00)` in the target timezone.

The offset matrix includes `America/St_Johns`, `Pacific/Kiritimati`, `Pacific/Pago_Pago`, `Asia/Kathmandu`, and the 30-minute `Australia/Lord_Howe` DST transition.

## Persisted-state contracts

- Unknown fields in the shared settings object are preserved on every write.
- Analog and digital page-specific fields do not overwrite one another.
- `theme=transparent` is a URL/embed mode and is not restored as a top-level persistent theme.
- Any URL query is a temporary override and must leave existing storage byte-for-byte unchanged.
- Wake Lock desired intent is distinct from an active or pending sentinel. System release, a missing API, or a rejected request does not erase user intent.
- At most one Wake Lock request may be active or pending.

## Builder contracts

Generated HTML contains exactly one parseable iframe. Every visible control must affect both the canonical URL and the live preview. Clipboard and open actions receive the exact generated value. Invalid dimensions are rejected; valid inclusive boundaries are accepted. Preview dimensions may be capped for the dialog but generated dimensions are not silently changed.

## Visual regression policy

The canonical environment is Chromium from Playwright 1.58.0 on macOS 26 arm64, matching the committed baselines. Ordinary local runs never update baselines.

Before capture, the helper waits for exact clock readiness and `document.fonts.ready`, disables animations, hides the caret, and uses the fixed context settings. Comparisons use explicit per-channel and changed-pixel limits; the default is exact. A missing baseline is a failure. Only `--update-snapshots` may create or replace one.

```bash
conda run -n clocksimulator python -m pytest -m visual
conda run -n clocksimulator python -m pytest -m visual --update-snapshots
```

Update only reviewed, intentional baselines. A failed comparison writes `*_diff.png`; a passing comparison removes its stale diff. Transparent baselines use RGBA with `omit_background=True`, require zero alpha in known corner background pixels, require non-empty visible content, and compare alpha like every other channel. Small day/night and second-hand details have focused baselines alongside DOM assertions.

## Service worker and deployment

Service-worker tests use a controlled document and browser-side `fetch()` because `page.request` bypasses the service worker. The cache contract keeps the current cache, deletes only older `clocksimulator-v*` caches, preserves unrelated origin caches, and stores only successful runtime responses.

Deployment tests copy the real `public/` directory and `wrangler.jsonc` into a temporary runtime directory, start exactly Wrangler 4.28.0 on a free port, and verify Cloudflare's actual HTML handling, redirects, headers, MIME types, and cross-origin iframe behavior. The ordinary SimpleHTTP fixture remains the fast DOM-test server and does not substitute for this suite.

## JavaScript coverage

Chromium coverage is opt-in:

```bash
conda run -n clocksimulator python -m pytest \
  -m "not visual and not service_worker and not deployment" \
  --browser-engine=chromium \
  --js-coverage \
  --js-coverage-output=test-results/js-coverage \
  --randomly-seed=20260718
```

The harness starts precise V8 coverage before navigation, merges every managed page by script hash, excludes test-injected and third-party scripts, and reports analog and digital code separately. It writes `coverage.json` and `summary.txt`.

The canonical measurement on 2026-07-18 used the command above with Playwright Chromium 1.58.0. It observed 45/45 named functions and 46,941/47,954 executed source units for analog, and 48/48 named functions and 42,732/43,687 executed source units for digital. `tests/js_coverage_baseline.json` publishes those measurements and the exact source hashes and lengths. A production-script change therefore requires a fresh canonical run and an intentional baseline update.

The regression gate does not require the execution totals to match the observation exactly. Its floors are 40 named functions and 42,000 executed units for analog, and 44 named functions and 39,000 executed units for digital. This leaves roughly 8–11% headroom for harmless V8 range variation while still detecting a material loss. Critical function names are gated separately. V8 byte coverage proves execution, not assertion quality, so the behavior matrices and mutation checks remain the primary oracles.

## Manual release checks

The repository does not use GitHub Actions or another automated CI service. Tests are run manually in the local `clocksimulator` Conda environment.

Before a release, run the complete local matrix with:

```bash
./run_release_tests.sh
```

The wrapper verifies the pinned Conda dependencies, all three Playwright browsers, Wrangler 4.28.0, and the canonical macOS 26 arm64 visual environment before starting. It then runs the complete Chromium suite, the visual, service-worker and deployment marker suites, both cross-browser core matrices, and the JavaScript coverage command documented above. The gates run sequentially and fail fast. Do not use retries to turn a failing release check green.

The default seed is generated once, printed, and reused for every gate. Reproduce a run with `--seed VALUE`. Release gates ignore ambient pytest, Python-path, and user-site overrides so shell or Conda settings cannot narrow the matrix, inject plugins, or update snapshots. By default the summary, gate logs and statuses, Playwright failure traces, and coverage reports are written to a new directory under `${TMPDIR:-/tmp}` so the repository remains clean. Use `--output PATH` to select a new artifact directory; an existing path is never overwritten. `--dry-run` prints the seven shell-escaped commands without running preflight checks, creating artifacts, or executing tests.

## Consolidation record

Tests are removed only after a stronger replacement exercises the same implementation path. The current consolidation maps are:

| Removed tests or family | Replacement |
|---|---|
| `test_mouse_click_does_not_show_switch_focus_ring` | `test_pointer_activation_does_not_force_keyboard_focus_indicator` |
| `test_keyboard_can_open_embed_dialog_from_about_menu`, `test_every_dialog_control_has_keyboard_focus_indicator` | The parameterized dialog keyboard lifecycle, close-method, and all-controls focus tests in `test_accessibility.py` |
| `test_normal_motion_keeps_transitions` | `test_ui_normal_motion_retains_transitions`, alongside the reduced-motion and embed transition matrices |
| Analog dashboard activation/title/grid/label/count tests | `test_dashboard_mode_activation_has_exact_structure` |
| Analog dashboard rows, three/four-clock, and auto-grid 4/5/6/9 tests | `test_dashboard_grid_layout` with explicit case IDs |
| Analog dashboard per-theme and negative-only feature tests | `test_dashboard_theme_visible_state` and the seconds/border/numbers/shadows positive-and-negative pairs |
| Analog dashboard invalid, mixed, empty, and single-timezone fallbacks | `test_dashboard_mixed_valid_invalid_timezones_keep_order_and_time` and `test_dashboard_fallbacks_render_initialized_single_clock` |
| Analog single/dashboard embed transition checks and dashboard combined-state tests | The four-renderer accessibility transition matrix, `test_dashboard_embed_combined_hides_ui_and_keeps_labels`, and `test_dashboard_all_params_combined` |
| Three embed/dashboard/digital sleep-based burn-in tests and the old partial timer test | The four-renderer burn-in lifecycle and disabled-mode matrices in `test_accessibility.py` |
| Digital dashboard activation existence test | `test_digital_dashboard_activation_has_exact_structure` |
| Digital embed output, missing-clipboard, and dashboard URL builder tests | The shared end-to-end analog/digital builder matrices in `test_builders.py` |
| Digital static analog/digital HTML link tests | Real locator navigation tests on both pages |
| Digital service-worker source-string test | The isolated install, runtime-cache, and offline behavior suite in `test_service_worker.py` |
| Digital theme class/toggle tests and all digital-only DOMContentLoaded priority probes | The shared analog/digital theme priority, OS resynchronization, base-rendering, switch, and visual matrices in `test_theme_handling.py` |
| Full-page `embed-daynight.png` baseline | The exact day/night DOM assertion plus focused `embed-daynight-icon.png` baseline; the dark embed layout remains covered by `embed-dark.png` |
| Embed overlay/about initial-state and no-op Escape tests | Real dialog open/close, inert, focus restoration, backdrop, button, and keyboard lifecycle tests |
| Old analog/digital saved-field preservation and write-time reread pairs | The bidirectional navigation, unknown-field preservation, and write-time reread matrices in `test_saved_settings.py` |
| Old storage normalization, disable, URL-write, and blocked-storage tests | The real reload/disable, byte-preserving URL, complete-default, normalization-on-write, and per-operation exception matrices |
| Legal-precache presence test | Exact successful precache contents plus online/offline legal navigation behavior |
| Individual analog theme params, CSS variables, saved/OS priority, FOUC, toggles, dashboard, and three separate visual tests | The shared theme matrices and parameterized visual test in `test_theme_handling.py` |

## Mutation smoke checks

During changes, make a reversible local mutation, run the named test, and restore the mutation immediately. The required mappings are:

| Mutation | Expected detector |
|---|---|
| Remove a snapshot baseline | Snapshot helper infrastructure test or matching visual test |
| Register burn-in in embed mode | Burn-in lifecycle matrix |
| Force seconds always hidden or shown | Positive/negative seconds parameter tests |
| Remove day/night update | Boundary and focused icon tests |
| Remove target offset recalculation | 60,000 ms SLA and live DST tests |
| Remove digital minute callback | Deterministic minute-boundary tests |
| Remove service-worker `cache.put` | Runtime cache then offline-hit test |
| Make an all-params NodeList empty | Exact element-count assertion before collection checks |

Mutations are never committed.

The complete mutation audit was executed on 2026-07-18 with exact node IDs, `--randomly-dont-reorganize`, and tracing disabled. Every restored target passed immediately after its mutant run.

| Verified mutation | Observed detector |
|---|---|
| Missing `embed-daynight-icon.png` baseline | Killed by the missing-baseline failure; restoration passed |
| Burn-in registered in analog embed mode | Killed by the active 600,000 ms interval assertion; restoration passed |
| Analog seconds forced hidden by default | Killed by the visible second-hand default assertion; restoration passed |
| Analog day/night updater returned early | Killed at the 06:00 day boundary; restoration passed |
| Analog offset recalculation disabled | Killed by the exact 60,000 ms formatter-call SLA; restoration passed |
| Digital minute callback removed | Killed by the required effectful minute timer assertion; restoration passed |
| Service-worker runtime `cache.put` removed | Killed by the absent cache entry/offline-hit contract; restoration passed |
| All-params second-hand selector made empty | Killed by the exact two-element count assertion; restoration passed |

Removing only the inner `!embedMode` term from the burn-in expression survived because an outer `if (!embedMode)` independently guards the same block. The effective behavioral mutation moved only burn-in registration outside that outer guard and was killed. This redundant-guard probe is retained in the audit record so a source-shape mutation is not misreported as a test weakness.
