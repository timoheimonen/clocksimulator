# clocksimulator

A clean, fullscreen analog clock simulator built with plain HTML, CSS, and JavaScript.

## Timezone support

By default the clock shows your local time. To display a different timezone, add the `tz` query parameter with any valid [IANA timezone identifier](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones):

```
https://clocksimulator.com/?tz=America/New_York
https://clocksimulator.com/?tz=Asia/Tokyo
https://clocksimulator.com/?tz=Europe/Helsinki
https://clocksimulator.com/?tz=UTC
```

If the value is invalid or omitted, the clock falls back to your local timezone.

## Embed

You can embed the clock on any website using an iframe. Click the **info button** on [clocksimulator.com](https://clocksimulator.com) and select **Embed this clock** to open the generator with a live preview and copy-ready code.

### Quick start

Round (default):

```html
<iframe src="https://clocksimulator.com/?embed=true"
  width="200" height="200" frameborder="0"
  style="border:none; border-radius:50%; overflow:hidden;">
</iframe>
```

Square:

```html
<iframe src="https://clocksimulator.com/?embed=true"
  width="200" height="200" frameborder="0"
  style="border:none; overflow:hidden;">
</iframe>
```

### Parameters

All parameters are optional and can be combined:

| Parameter | Values | Default | Description |
|-----------|--------|---------|-------------|
| `embed`   | `true` | — | Activates embed mode (hides UI controls) |
| `tz`      | IANA timezone | Local | Timezone, e.g. `Europe/Helsinki` |
| `theme`   | `dark`, `light`, `transparent` | `dark` | Color theme |
| `seconds` | `tick`, `smooth`, `hide` | `tick` | Second hand mode |
| `border`  | `show`, `hide` | `show` | Clock border visibility |

### Examples

```
https://clocksimulator.com/?embed=true&tz=Asia/Tokyo&theme=light
https://clocksimulator.com/?embed=true&seconds=smooth&border=hide
https://clocksimulator.com/?embed=true&tz=America/New_York&theme=dark&seconds=hide
```

## License

MIT. See `LICENSE`.
