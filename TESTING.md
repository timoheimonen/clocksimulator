# Testing

90 tests across 3 test files. Run with `python -m pytest`.

## Embed mode (`test_embed_mode.py` — 29 tests)

### Parameter handling

| Test | Verifies |
|---|---|
| `test_embed_mode_adds_embed_mode_class` | `body.embed-mode` class applied |
| `test_embed_mode_defaults_to_dark_theme` | Dark theme when no `theme` param |
| `test_embed_mode_theme_light_override` | `theme=light` overrides embed default |
| `test_embed_mode_theme_transparent` | `theme=transparent` applies transparent mode |
| `test_embed_mode_with_single_timezone` | Single `tz` value works in embed |
| `test_embed_mode_seconds_hide` | `seconds=hide` hides second hand |
| `test_embed_mode_seconds_smooth` | `seconds=smooth` sets smooth mode |
| `test_embed_mode_border_hide` | `border=hide` removes clock border |
| `test_embed_mode_numbers_hide` | `numbers=hide` hides hour numbers |
| `test_embed_mode_shadows_disabled` | `shadows=false` removes SVG filters |
| `test_embed_mode_daynight_show` | `daynight=show` displays sun/moon icon |
| `test_embed_mode_all_params_combined` | All params work together |

### UI isolation

| Test | Verifies |
|---|---|
| `test_embed_mode_hides_toggle_wrapper` | Controls hidden (zero width) |
| `test_embed_mode_clock_container_full_size` | Clock fills container |
| `test_embed_mode_removes_favicon` | Dynamic favicon removed |
| `test_embed_mode_disables_save_settings` | Save settings toggle disabled |
| `test_embed_mode_no_time_announcements` | Aria-live announcements suppressed |
| `test_embed_mode_wakelock_hidden` | Wake lock label hidden |
| `test_embed_mode_overlays_not_visible` | Embed/dashboard/help overlays not visible |
| `test_embed_mode_about_bubble_hidden` | About button and bubble hidden |
| `test_embed_mode_burnin_disabled` | No burn-in position shifting |
| `test_embed_mode_clock_container_no_transition` | CSS transition is `none` |
| `test_embed_mode_escape_key_no_effect` | Escape key triggers nothing |

### Visual snapshots

| Test | Snapshot |
|---|---|
| `test_embed_mode_visual_snapshot_dark` | `embed-dark.png` |
| `test_embed_mode_visual_snapshot_light` | `embed-light.png` |
| `test_embed_mode_visual_snapshot_transparent` | `embed-transparent.png` |
| `test_embed_mode_visual_snapshot_daynight` | `embed-daynight.png` |
| `test_embed_mode_visual_snapshot_seconds_hide` | `embed-seconds-hide.png` |
| `test_embed_mode_visual_snapshot_all_params` | `embed-all-params.png` |

## Dashboard mode (`test_dashboard_mode.py` — 37 tests)

### Grid activation and layout

| Test | Verifies |
|---|---|
| `test_dashboard_mode_activates_with_multiple_tz` | Grid created with 2+ timezones |
| `test_dashboard_mode_clock_grid_created` | `.clock-grid` element exists |
| `test_dashboard_mode_grid_columns_correct` | 2 TZs = 2 columns |
| `test_dashboard_auto_grid_4tz` | 4 TZs = 2 cols x 2 rows |
| `test_dashboard_auto_grid_5tz` | 5 TZs = 3 cols x 2 rows |
| `test_dashboard_auto_grid_6tz` | 6 TZs = 3 cols x 2 rows |
| `test_dashboard_auto_grid_9tz` | 9 TZs = 3 cols x 3 rows |
| `test_dashboard_mode_rows_parameter` | `rows` param overrides auto layout |
| `test_dashboard_mode_four_tz_with_rows` | 4 TZs with `rows=2` |
| `test_dashboard_mode_three_timezones` | 3 TZs renders 3 clocks |

### DOM structure and rendering

| Test | Verifies |
|---|---|
| `test_dashboard_mode_title_changes` | Page title includes "Dashboard" |
| `test_dashboard_mode_clock_labels_show` | Labels rendered for each clock |
| `test_dashboard_label_text_matches_tz` | Labels show display names (Helsinki, not Europe/Helsinki) |
| `test_dashboard_clocks_different_hand_angles` | Different TZs show different hand positions |
| `test_dashboard_no_duplicate_svg_ids` | Cloned SVGs have internal IDs stripped |
| `test_dashboard_original_container_hidden` | Single-clock container hidden when grid active |
| `test_dashboard_mode_filters_removed` | SVG filters removed from grid clones |

### Parameter handling

| Test | Verifies |
|---|---|
| `test_dashboard_mode_theme_dark` | `theme=dark` in dashboard |
| `test_dashboard_mode_theme_light` | `theme=light` in dashboard |
| `test_dashboard_mode_seconds_hide` | `seconds=hide` hides all second hands |
| `test_dashboard_mode_border_hide` | `border=hide` removes all borders |
| `test_dashboard_mode_numbers_hide` | `numbers=hide` hides all numbers |
| `test_dashboard_mode_daynight_show` | `daynight=show` shows icons on all clocks |
| `test_dashboard_mode_all_params_combined` | All params work together |

### Edge cases

| Test | Verifies |
|---|---|
| `test_dashboard_mode_invalid_timezone_ignored` | Invalid TZ filtered, falls back to single clock |
| `test_dashboard_mode_mixed_valid_invalid_tz` | Valid TZs kept, invalid ones dropped |
| `test_dashboard_single_tz_no_grid` | Single `tz` value does not create a grid |
| `test_dashboard_all_invalid_tz_fallback` | All-invalid TZs fall back to local clock |
| `test_dashboard_empty_tz_param` | Empty `tz=` does not crash |

### Embed + dashboard combined

| Test | Verifies |
|---|---|
| `test_dashboard_mode_embed_combined` | Embed class + grid + controls hidden |
| `test_dashboard_mode_embed_grid_no_transition` | Grid transition is `none` in embed |
| `test_dashboard_embed_labels_visible` | Labels remain visible in embed mode |
| `test_dashboard_embed_burnin_disabled` | No burn-in shifting in embed dashboard |

### Visual snapshots

| Test | Snapshot |
|---|---|
| `test_dashboard_mode_visual_snapshot_dark_2tz` | `dashboard-dark-2tz.png` |
| `test_dashboard_mode_visual_snapshot_light_3tz` | `dashboard-light-3tz.png` |
| `test_dashboard_mode_visual_snapshot_dark_4tz` | `dashboard-dark-4tz.png` |
| `test_dashboard_mode_visual_snapshot_embed_2tz` | `dashboard-embed-2tz.png` |

## Theme handling (`test_theme_handling.py` — 24 tests)

### URL parameter themes

| Test | Verifies |
|---|---|
| `test_theme_dark_param` | `theme=dark` adds `dark-mode` class |
| `test_theme_light_param` | `theme=light` removes dark/transparent |
| `test_theme_transparent_param` | `theme=transparent` adds `transparent-mode` class |
| `test_theme_dark_css_variables` | Dark `--bg` is `#000000` |
| `test_theme_light_css_variables` | Light `--bg` is `#f0f0f0` |
| `test_theme_transparent_css_variables` | Transparent `--bg` is `transparent` |

### Theme priority chain

| Test | Verifies |
|---|---|
| `test_embed_mode_default_dark` | Embed defaults to dark |
| `test_embed_mode_theme_light_override` | URL param overrides embed default |
| `test_embed_mode_theme_transparent_override` | Transparent overrides embed default |
| `test_saved_settings_theme_dark` | Saved dark theme restored |
| `test_saved_settings_theme_light` | Saved light theme restored |
| `test_os_dark_preference_applied` | OS dark preference applied |
| `test_os_light_preference_applied` | OS light preference applied |
| `test_theme_param_overrides_saved_settings` | URL param beats saved settings |
| `test_theme_param_overrides_os_preference` | URL param beats OS preference |

### Theme interactions

| Test | Verifies |
|---|---|
| `test_theme_toggle_changes_class` | Toggle switches light to dark |
| `test_theme_toggle_removes_transparent_mode` | Toggle from transparent goes to dark |
| `test_theme_transparent_in_embed_mode` | Transparent works in embed |
| `test_theme_dashboard_dark` | Dark theme works in dashboard |

### FOUC prevention

| Test | Verifies |
|---|---|
| `test_theme_no_fouc_dark_mode` | Dark class exists at DOMContentLoaded |
| `test_theme_no_fouc_embed_mode` | Embed dark class exists at DOMContentLoaded |

### Visual snapshots

| Test | Snapshot |
|---|---|
| `test_theme_visual_snapshot_dark` | `theme-dark.png` |
| `test_theme_visual_snapshot_light` | `theme-light.png` |
| `test_theme_visual_snapshot_transparent` | `theme-transparent.png` |
