# Privacy Policy

Effective date: 2026-02-27

clocksimulator is a minimalist clock website. **We do not run ads, we do not use analytics, and we do not sell personal data.**

## Summary

- **No trackers / analytics**: We do not use third-party analytics scripts, tracking pixels, or advertising beacons.
- **No accounts**: There is no login and no user profile.
- **Optional local storage**: If you choose to enable **Save settings**, your preferences can be stored locally in your browser.
- **Offline/PWA support**: A service worker may cache a small set of static assets for offline use.

## What information we collect

**We do not intentionally collect personal information** (such as your name, email address, or precise location) through the clocksimulator app itself.

## Local device storage (optional)

The app includes an opt-in toggle **Save settings** (About menu). If you enable it, the site stores your preferences **locally in your browser** using Local Storage under this key:

- `clocksimulator-user-settings`

Stored fields:

- `theme` (`"dark"` or `"light"`)
- `wakeLock` (`true` or `false`)
- `secondModeTick` (`true` or `false`)

**Opting out / removing saved settings**

- Turn off **Save settings** to remove the saved item from Local Storage.
- You can also clear site data in your browser settings.

**When URL parameters are active**

When you use URL parameters (for example `?tz=...` or `?embed=true`), the **Save settings** toggle is disabled and the site will not load settings from Local Storage. This helps keep embeds and parameterized URLs predictable.

## Service worker / offline cache (PWA)

If your browser supports it, the site registers a service worker for offline/PWA behavior. The service worker uses the browser’s Cache Storage to cache a small set of static assets (such as `/`, `manifest.json`, and icons) and may cache fetched assets to improve offline use and load speed.

This cache contains **site files**, not your personal content.

## Hosting/provider logs

Like most websites, clocksimulator is served through a hosting provider (Cloudflare). The provider may process **standard server/edge request data** (such as IP address, user-agent, request path, timestamps, and similar operational metadata) in order to deliver the site, protect it from abuse, and operate the service.

We do not add trackers on top of that, and we do not use these logs for advertising or selling data.

## Open source verification

The project is open source, and you can verify the behavior described above in:

- `public/index.html` (UI + Local Storage usage)
- `public/sw.js` (service worker + caching)

Repository: `https://github.com/timoheimonen/clocksimulator`

## Contact

If you have privacy questions, contact:

- Timo Heimonen — `timo.heimonen@proton.me`

