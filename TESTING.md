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
./run_release_tests.sh --dry-run
conda run -n clocksimulator python -m pytest
conda run -n clocksimulator python -m pytest -p no:randomly
conda run -n clocksimulator python -m pytest --randomly-seed=20260718
conda run -n clocksimulator python -m pytest -m visual
conda run -n clocksimulator python -m pytest -m service_worker
conda run -n clocksimulator python -m pytest -m deployment
conda run -n clocksimulator python -m pytest -m cross_browser --browser-engine=firefox
conda run -n clocksimulator python -m pytest -m cross_browser --browser-engine=webkit
```

`./run_tests.sh` is a small live-streaming wrapper around one pytest invocation and forwards all arguments. `./run_release_tests.sh` is the canonical one-command local release gate. It runs the complete Chromium suite and the Firefox and WebKit cross-browser matrices sequentially with one recorded random seed. It stops at the first failure and prints the failed command and retained trace location.

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

`open_page()` installs Playwright's controlled clock, initializes the test origin with empty or explicitly seeded storage, navigates, and waits for exact render readiness. Separate helpers support navigation and reload without clearing storage. Tests that need another timezone use a separate Helsinki context rather than mutating a shared session.

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

Before capture, the helper waits for exact clock readiness and `document.fonts.ready`, disables animations, hides the caret, and uses the fixed context settings. Comparisons are exact. A missing baseline is a failure. Only `--update-snapshots` may create or replace one.

```bash
conda run -n clocksimulator python -m pytest -m visual
conda run -n clocksimulator python -m pytest -m visual --update-snapshots
```

Update only reviewed, intentional baselines. A failed comparison writes `*_diff.png`; a passing comparison removes its stale diff. Transparent baselines use RGBA with `omit_background=True`, require zero alpha in known corner background pixels, require non-empty visible content, and compare alpha like every other channel. Small day/night and second-hand details have focused baselines alongside DOM assertions.

## Service worker and deployment

Service-worker tests use a controlled document and browser-side `fetch()` because `page.request` bypasses the service worker. The cache contract keeps the current cache, deletes only older `clocksimulator-v*` caches, preserves unrelated origin caches without using them to satisfy app requests, and stores only successful runtime responses.

Deployment tests copy the real `public/` directory and `wrangler.jsonc` into a temporary runtime directory, start exactly Wrangler 4.28.0 on a free port, and verify Cloudflare's actual HTML handling, redirects, headers, MIME types, and cross-origin iframe behavior. The ordinary SimpleHTTP fixture remains the fast DOM-test server and does not substitute for this suite.

## Manual release checks

The repository does not use GitHub Actions or another automated CI service. Tests are run manually in the local `clocksimulator` Conda environment.

Before a release, run the complete local matrix with:

```bash
./run_release_tests.sh
```

The wrapper intentionally has no separate dependency preflight: the real test processes validate the environment they use. It runs the complete Chromium suite first, followed by the Firefox and WebKit `cross_browser` selections. The gates run sequentially and fail fast. Do not use retries to turn a failing release check green.

The default seed is generated once, printed, and reused for every gate. Reproduce a run with `--seed VALUE`. `run_tests.sh` removes ambient pytest, Python-path, and user-site overrides so shell or Conda settings cannot narrow the matrix, inject plugins, or update snapshots. Playwright traces are written to a temporary release directory and retained for diagnosis. `--dry-run` prints the three shell-escaped commands without creating artifacts or executing tests.
