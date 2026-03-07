# Changelog

## 1.1.7 - 2026-03-07

### Fixed
- Timezone clocks and dashboards now show the correct time around midnight in all timezones.

## 1.1.6 - 2026-03-07

### Fixed
- Timezone clock now shows the correct time during daylight saving time transitions in the viewer's local timezone.
- Clean up CSS and variables.

### Added
- Toogle button animations
- Window animations

## 1.1.5 2026-03-03

### Added
- Terms of service document.

### Changed
- Rearranged privacy, TOS and github links in Info-window. 

## 1.1.4 2026-03-03

### Added
- Small carbon rating texts and links to embedded- and dashboard-overlays.

## 1.1.3 - 2026-03-03

### Fixed
- Timezone offset for non-local clocks is now calculated using numeric values instead of string parsing, for more reliable behavior across browsers and environments.
- Dashboard, embed, and help overlays no longer close when selecting text with the mouse inside the panel. Closing now requires a click that starts on the overlay backdrop.

## 1.1.2 - 2026-03-02

### Fixed
- Second-hand tick animation now stays consistent in timezone view, including embedded clocks.

## 1.1.1 - 2026-03-02

### Added
- Dashboard builder added to the info menu (Info -> Build dashboard). It opens a modal matching the embed panel style, lets users add and remove multiple IANA timezones, configure rows and visual options, and generates a ready-to-use dashboard link with live preview.

## 1.1.0 - 2026-03-02

### Added
- Multi-clock dashboard: show multiple clocks at once by separating timezones with commas in the URL. The grid layout is calculated automatically. Use the optional rows parameter to control the number of rows. Each clock displays its timezone label and supports all existing options such as theme, seconds, shadows, and day/night indicator. In dashboard mode, shadows and the second hand tick momentum are automatically disabled for better performance.

### Fixed
- Second hand shadow no longer visible when seconds are hidden via URL parameter.
- Reduced unnecessary processing when seconds are hidden.
- Save settings tooltip now displays correctly when URL parameters are active.

## 1.0.20 - 2026-03-02

### Added
- Sustainable section added to help window.

## 1.0.19 - 2026-03-01

### Added
- Help overlay now includes a short section explaining screen burn-in protection and how dark mode benefits OLED displays.

## 1.0.18 - 2026-02-28

### Added
- URL parameter shadows=true/false to show or hide clock hand shadows (default is true). Also added as a Shadows option in the embed overlay panel.

## 1.0.17 - 2026-02-28

### Added
- Dynamic soft shadows with time-based direction logic.

## 1.0.16 - 2026-02-27

### Fixed
- About bubble now stays fully within the screen on small devices by aligning it with the left edge of the controls.

## 1.0.15 - 2026-02-27

### Added
- Added a Save settings toggle in the About menu. Users can choose to save their settings locally in the browser. The following data is stored: {"theme":"dark/light","wakeLock":false/true,"secondModeTick":false/true}. This supports the author’s goal of keeping the site clean and lightweight while still allowing users to persist preferences. Local storage is disabled when URL parameters are present or in embedded mode.

### Fixed
- About bubble now follows dark/light mode instead of always appearing dark.
- Tooltips are disabled on toggle buttons and the info button while the about bubble is open.

## 1.0.14 - 2026-02-27

### Fixed
- Info button now shows a tooltip on hover.
- Info button is now vertically centered with the toggle buttons.

## 1.0.13 - 2026-02-27

### Added
- Added PWA information section to the help-overlay window.

## 1.0.12 - 2026-02-27

### Changed
- Keep screen on now defaults to off.
- Clock animation now pauses when the browser tab is hidden to reduce unnecessary processing.
- Modernized all variable declarations to use const/let for consistency.
- Clock border element now uses a dedicated ID instead of a fragile CSS selector.
- Consolidated duplicate CSS for embed and help panels into shared styles.
- Embed timezone field now validates input and shows a warning for invalid timezones.
- Service worker registration now handles errors silently.
- Help panel tables now use proper thead/tbody structure for better accessibility.

### Fixed
- Embed code now links to the correct URL.
- Generated embed code no longer includes a deprecated HTML attribute.
- About menu is no longer incorrectly announced as a dialog by screen readers.
- Embed preview and embed code field are now properly labeled for screen readers.
- About menu now opens directly below the info button instead of at the left edge of the screen.

## 1.0.11 - 2026-02-27

### Fixed
- Fixed extra spacing in toggle controls caused by hidden checkbox elements.
- Added keyboard focus trapping inside embed and help dialogs for better accessibility.
- Embed preview now clips correctly when using round shape.
- Favicon no longer triggers unnecessary network request on page load.
- Timezone clock no longer crashes if time formatting fails unexpectedly.

### Changed
- Day/night indicator no longer requires a timezone parameter.

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
