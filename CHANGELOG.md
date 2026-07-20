# Changelog

## 1.3.5 - 2026-07-20

### Changed
- Analog and digital timezone clocks, including dashboards, now stay accurate across the viewer's daylight-saving time changes.
- Saved settings now preserve each clock's seconds preference when switching between the analog and digital pages.
- Digital clocks now announce the time to screen readers no more than once per minute; dashboard announcements remain accessible, while embedded clocks stay silent.
- Shared analog and digital clock links now choose their theme predictably from the link, the embed default, or the viewer's device color preference, without saved settings overriding URL options.
- Keyboard focus, dashboard timezone fields, generated embeds, and reduced-motion behavior are now more accessible across both clock pages.
- Help dialog URL examples can now be reached and scrolled with a keyboard and are clearly identified for screen readers on both clock pages.
- Offline reloads now keep the Privacy Policy and Terms of Service pages open instead of showing the analog clock.
- Clock controls, dialogs, status messages, and time displays now work more reliably with keyboards and screen readers across browsers.
- Saved settings, screen-on mode, burn-in protection, and timezone updates now handle interruptions and repeated actions more reliably.
- Embedded clocks, dashboard layouts, and previews now fit small displays better while preserving their intended contrast and appearance.
- The analog dashboard builder now lets you show or hide clock-hand shadows.
- Offline updates now retain only successful site files, and legal-page links use their clean public addresses consistently.

## 1.3.4 - 2026-05-18

### Added
- Added a new digital clock page at `/digital/` with fullscreen, embed, timezone, dashboard, theme, 12/24-hour format, seconds, border, day/night, burn-in protection, and saved settings support.
- Added high-contrast transparent digital embeds for use over dark or video backgrounds.
- Added analog-style SVG sun and moon artwork for the digital clock day/night indicator.
- Added viewport-fitting digital dashboard text scaling and graceful clipboard fallback behavior.
- Added digital clock screenshots and regression coverage for the new page.
- Added cross-links between the analog and digital clock pages in the about/info menus.

### Changed
- The analog page now labels its embed action as "Embed this analog clock" to match the digital page wording.
- The default digital clock shows only the time unless a timezone or day/night indicator is requested.

## 1.3.3 - 2026-04-27

### Changed
- Changed the about/info menu icon from an information symbol to a question mark to better match the help-oriented menu contents.

## 1.3.2 - 2026-04-26

### Changed
- Dashboard row settings now handle invalid or overly large values more gracefully.
- Copy buttons now return to their normal label reliably after quick repeated clicks.

## 1.3.1 - 2026-04-18

### Fixed
- Theme flash on pages loaded with an explicit `theme=` URL parameter (for example `?embed=true&theme=dark`) when the OS or browser prefers the opposite color scheme. The early theme-preset script now reads the `theme` parameter (including `dark`, `light`, and `transparent`) and applies the matching class before first paint.

## 1.3.0 - 2026-04-08

### Changed
- Accessibility was improved across controls, menus, and dialogs for both keyboard and screen reader users.
- About menu now clearly reports when it is open or closed to assistive technology.
- Hidden controls and closed menus/dialogs are no longer reachable while navigating with the keyboard.
- When a dialog is open, background content is excluded from keyboard and assistive technology navigation.
- Dashboard clocks now announce the time in each timezone every minute for screen reader users.

### Removed
- Duplicate accessibility labels were removed from preview frames.

## 1.2.9 - 2026-04-06

### Changed
- Hour and minute hands now use CSS transforms instead of SVG attribute updates, enabling GPU-composited animation and reducing per-frame rendering cost.
- Day/night icon updates are now throttled to once per second instead of every frame.
- Clock hands are promoted to their own compositor layers for smoother rotation.

## 1.2.8 - 2026-04-04

### Changed
- Default theme is now light mode. Dark mode is opt-in.
- Embeds without a theme parameter default to dark for backwards compatibility.
- Service worker now pre-caches TOS and sitemap pages.
- Simplify theme initialization logic.
- Replace magic numbers with named constants for maintainability.

### Fixed
- Variable shadowing in clock update function that could cause subtle bugs during refactoring.
- Burn-in protection timer now pauses when the tab is hidden instead of running unnecessarily.
- Theme no longer flashes on page load when OS or saved preference differs from default.

## 1.2.7 - 2026-03-29

### Added
- og-image

### Changed
- all addresses are now clocksimulator.com instead of www.clocksimulator.com

## 1.2.6 - 2026-03-26

### Fixed
- Shadow direction calculations

## 1.2.5 - 2026-03-25

### Improved
- Second hand now uses hardware-accelerated CSS transforms instead of per-frame DOM updates, reducing CPU load when showing multiple clocks.
- Dashboard mode disables the tick bounce effect for consistent ticking across all clocks.
- Dashboard clocks now use a single global seconds value for synchronized second hand movement across all timezone clocks.

## 1.2.4 - 2026-03-25

### Changed
- Default theme now respects the user's OS color scheme preference (prefers-color-scheme), with light as the fallback.
- Embed builder defaults to light theme. Embeds are backwards compatible, if ?theme not set, it will default to dark as before.
- Dashboard builder defaults to the user's OS color scheme preference, with light as the fallback.

## 1.2.3 - 2026-03-23

### Changed
- DRY cleanup on index.html, total of 96 lines net removed.

### Improved
- Clock hand shadows now use SVG feDropShadow filters instead of separate shadow elements, enabling GPU-accelerated rendering. Shadow direction updates are throttled to ~2x/min instead of every frame.
- Shadow filter regions tightened to match actual hand sweep areas, reducing GPU compositing work by ~58%. Center dot filter reduced from 200×200 to 22×22 SVG units.
- Shadows and the second hand are now automatically disabled when the OS prefers-reduced-motion setting is active.

## 1.2.2 - 2026-03-22

### Changed
- Sun icon changed to same style as in dark/light toggle

## 1.2.1 - 2026-03-22

### Changed
- Meta description/titles changed.

## 1.2.0 - 2026-03-20

### Added
- VoiceOver time announcements: Screen readers now automatically announce the time every minute via an aria-live region on single clock use.

### Improved
- Accessibility: Clock element now has a live region for proactive time announcements instead of relying on passive aria-label changes.

## 1.1.9 - 2026-03-16

### Changed
- Removed animation from the menu-window embed-text for keeping page minimal and distraction free.

## 1.1.8 - 2026-03-09

### Added
- Clocksimulator.com Chrome extension link to about-menu. Extension follows site's no ads, no analytics promise.
  Extension has only one permission: replace default view with analog clock when new tab is opened. Extension is 100% local.

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
