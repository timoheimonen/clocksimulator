# Changelog

## 1.0.10 - 2026-02-27

### Fixed
- Clipboard copy now handles permission errors gracefully.
- Second hand toggle no longer shown when seconds are hidden via URL.
- Favicon updates now sync to the minute boundary.
- Escape key now closes help and embed panels.
- Theme toggle no longer conflicts with transparent mode.
- Improved timezone hour parsing reliability.

## 1.0.9 - 2026-02-27

### Added
- "How to use" help panel accessible from the info menu.

## 1.0.8 - 2026-02-27

### Added
- Option to hide clock face numbers in URL parameter.

## 1.0.7 - 2026-02-26

### Changed
- Improved timezone clock performance by caching the time formatter.

## 1.0.6 - 2026-02-26

### Fixed
- Keep screen on now correctly activates when opening the app in a background tab.
- Improved touch device support for showing controls.

## 1.0.5 - 2026-02-26

### Added
- Embed link highlights briefly when the info menu is opened.

### Fixed
- Controls and cursor no longer auto-hide while the about bubble or embed panel is open.
- Reduced unnecessary processing on mouse movement.

## 1.0.4 - 2026-02-26

### Changed
- Reduced the second hand mechanical overshoot effect.
- Changelog latest on top order.

## 1.0.3 - 2026-02-26

### Changed
- Hour and minute hands now have pointed tips instead of rounded ends.

## 1.0.2 - 2026-02-26

### Added
- Ticking second hand now has a momentum overshoot effect for a more realistic mechanical feel.

## 1.0.1 - 2026-02-26

### Changed
- Meta information changed.

## 1.0.0 - 2026-02-26

### Added
- Fullscreen analog clock showing current time
- Dark and light theme with toggle
- Timezone support via URL parameter (any IANA timezone)
- Tick or smooth second hand mode with toggle
- Keep screen on (wake lock) toggle
- Embeddable clock with customizable options (theme, shape, seconds, border, day/night indicator)
- Live embed code generator with preview
- Dynamic favicon that reflects the current time
- Burn-in protection for always-on displays
- Auto-hiding controls and cursor for distraction-free viewing
- Sun/moon day-night indicator for timezone clocks
- Transparent theme option for embeds