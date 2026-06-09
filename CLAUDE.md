# CLAUDE.md — pistomp-recovery

Package update and recovery service for pi-Stomp (Arch Linux ARM). Runs as an exclusive LCD service when the main app crashes (3x in 180s via systemd `OnFailure`/`StartLimitBurst`) or when the user selects "Recovery" from the System Menu.

## Ecosystem

- **../pistomp-arch** — Build system that produces the OS image. PKGBUILDs, service files, build scripts. This project is a PKGBUILD there.
- **../pi-stomp** — Main app (Python). Has the LCD, encoders, pedalboards. `mod-ala-pi-stomp.service` conflicts with `pistomp-recovery.service`.
- **../mod-ui** — Web UI (Tornado). Talks to mod-host over TCP 5555/5556. Editable pip install.

## Key concepts

- **Facet** — A git-backed versioned unit of system state. Each facet has a `factory` branch (image-shipped state), a `device` branch (working state), and stamp tags (`stamp/<name>/<timestamp>`).
- **Stamp** — Marking a facet as known-good. `pistomp-stamp stamp -f config` commits current state and tags it. Called by pi-stomp on successful pedalboard load.
- **Exclusive LCD** — `pistomp-recovery.service` has `Conflicts=mod-ala-pi-stomp.service`. Recovery takes the LCD; resuming stops recovery and starts the main app.
- **Crash loop detection** — `mod-ala-pi-stomp.service`: `Restart=on-failure`, `StartLimitBurst=3`, `StartLimitIntervalSec=180`, `OnFailure=pistomp-recovery.service`.
- **Package updates** — pacman backed by GitHub Releases repo. Download → install → health check → stamp, or rollback.
- **Health check** — JACK → mod-host → mod-ui → pi-stomp (via `/run/pistomp-healthy` stamp file).
- **LCD splash coordination** — `/run/lcd.init` (tmpfs) created by `lcd-splash` C binary at boot; checked by Python to skip hardware reset.

## Scope

- In scope: facet versioning, package updates/rollback, crash recovery LCD UI, health checks, factory reset.
- Out of scope: WiFi config, pedalboard editing, plugin management, audio processing, web UI.

## Design principles

### Deterministic rendering

The LCD renders into a 320×240 pygame Surface. To ensure pixel-identical output on macOS (dev), CI, and the Pi:

- **Bundled fonts** — DejaVu Sans (regular + bold) shipped in `ui/fonts/`. Loaded via `pygame._freetype.Font` (not `pygame.font.Font`, which has a circular import on Python 3.14 / pygame 2.6.1). Fonts are cache-keyed by `(path, size)` so the same font object is reused.
- **Snapshot tests** — Widgets render to a pygame Surface → FakeLcd converts to a PIL Image → byte-for-byte `.tobytes()` comparison against `tests/snapshots/`. Run `--snapshot-update` to accept new baselines.
- **Headless-safe init** — `pygame_init.py` sets `SDL_VIDEODRIVER=dummy` in headless mode and calls `pygame._freetype.init()` idempotently. All font rendering goes through `SafeFont`, the `_freetype` wrapper that matches the `pygame.font.Font` API.

### Type safety

- **`pyright --typecheckingMode strict`** with zero errors. No bare `dict`, `list`, `set`, `object`, or `Any`.
- **Semantic type aliases** — `Color` (RGB or RGBA tuple), `ColorName` (literal union of color dictionary keys), `MenuItem`, `SafeFont`. Hover any annotation to see what it actually is.
- Hardware-only modules (`hardware/encoder.py`, `hardware/lcd.py`) gracefully degrade when gpiozero/board aren't importable — they `try/except ImportError` and log a warning.

### Widget architecture

- **Single-responsibility widgets** — `Widget` base carries `bounds`, `_dirty`, `_parent`, and no-op `propagate_dirty`. `Container` overrides it to merge dirty regions upward. Leaf widgets (`TextWidget`, `ProgressBar`, `StatusLine`, `Menu`) only implement `draw()`.
- **PaintContext** — Not a bare `pygame.Rect`. Carries `surface`, `clip` (visible area), and `frame` (widget-local coords). Screens create a root `PaintContext(surface, Box(0,0,320,240), Box(0,0,320,240))` and pass it to widget `draw()`.
- **Menu** — Scrollable vertical list with selection highlight, scrollbar for overflow items, and `Callable[[], None]` callbacks. No opaque arg-passing; closures capture what they need.

### Service crash loop

The systemd unit chain is: `mod-ala-pi-stomp.service` has `OnFailure=pistomp-recovery.service` and `StartLimitBurst=3/180s`. When pi-stomp crashes 3× in 3 minutes, systemd starts pistomp-recovery instead. Recovery shows a crash screen with the last journal lines, offers "Resume" (restart pi-stomp once more) or "Recovery Menu" (updates, config, factory reset). The `Conflicts=` relationship ensures only one app owns the LCD at a time.

## Python requirement

`>=3.12`, strict typing (`pyright --typecheckingMode strict`). System Python + `--system-site-packages` for lgpio/spidev access.

## Building and testing

```bash
uv sync --group dev         # Install dev dependencies
uv run pytest                # Run tests (needs SDL_VIDEODRIVER=dummy, set in conftest)
uv run pytest --snapshot-update  # Accept changed widget snapshots
uv run ruff check src/       # Lint
uv run pyright src/           # Type check (zero errors required)
uv run pistomp-recovery-emulator  # Interactive pygame window with keyboard controls
```

### Emulator controls

- `←`/`→` — Navigate menu
- `Enter`/`Space` — Select
- `L` — Long press (back/cancel)
- `Esc` — Quit
- `--force-crash` — Start in crash recovery mode

## File map

```
src/pistomp_recovery/
├── __main__.py          — Entry point: boot mode detection, main loop, screen routing
├── constants.py         — Paths, package list, service list, LCD dims
├── stamp.py             — CLI: pistomp-stamp (stamp/snapshot/status per facet)
├── service.py           — systemd integration: boot mode, start/stop, crash log, system info
├── git_util.py          — Git operations: init, commit, tag, checkout, rollback
├── pygame_init.py       — Idempotent pygame + _freetype init (headless-safe)
├── hardware/
│   ├── encoder.py       — Rotary encoder GPIO input (nav encoder D=17 CLK=4)
│   └── lcd.py           — SPI ILI9341 LCD driver (adafruit_rgb_display, 24MHz, /run/lcd.init stamp)
├── facets/
│   ├── base.py          — Facet ABC: init, snapshot, stamp, rollback, factory_reset, status
│   ├── config_facet.py  — /home/pistomp/data/config/ — default_config.yml, settings.yml
│   ├── pedalboards_facet.py — /home/pistomp/data/.pedalboards/ — git repo, upstream+device branches
│   ├── packages_facet.py — Package version manifest (pacman -Q), installs on rollback
│   └── system_facet.py  — /boot/config.txt, /etc/jackdrc, ALSA state, pistomp.conf
├── packages/
│   ├── manager.py       — Pacman wrapper: download, install, rollback from cache
│   └── health.py        — Service health checks: JACK, mod-host, mod-ui, pi-stomp stamp
├── emulator/
│   ├── bootstrap.py     — EmulatorApp: interactive pygame window, screen routing
│   ├── controls.py      — FakeEncoder, FakeInputManager for emulator
│   ├── lcd_pygame.py    — LcdPygame: renders Surface to pygame window
│   └── window.py        — EmulatorWindow: pygame event loop, keyboard → InputEvent
└── ui/
    ├── display.py        — Pygame surface ↔ SPI LCD bridge
    ├── colors.py         — Color type alias, ColorName literal union, COLORS dict (320×240 dark theme)
    ├── fonts/
    │   ├── __init__.py   — SafeFont (pygame._freetype wrapper), get_font(), FONT_CACHE, SIZES dict
    │   ├── DejaVuSans.ttf       — Regular weight (from pi-stomp)
    │   └── DejaVuSans-Bold.ttf  — Bold weight (from pi-stomp)
    ├── input.py          — Encoder rotation + GPIO switch → InputEvent
    ├── screens/
    │   ├── crash.py      — "App Crashed" + last journal lines, Resume/Recovery
    │   ├── main_menu.py  — Resume, System Info, Updates, Config, Factory Reset, Reboot, Power Off
    │   ├── updates.py    — Check/download/install updates with progress
    │   ├── config_screen.py — Per-facet stamp/rollback/factory-reset menu
    │   ├── system_info.py  — Kernel, uptime, temp, OS version
    │   └── status_screen.py — Progress bar + status text for update operations
    └── widgets/
        ├── misc.py        — Box, InputEvent enum
        ├── paint.py       — PaintContext (surface, clip rect, frame)
        ├── widget.py      — Base Widget with bounds, dirty flag, parent ref, no-op propagate_dirty
        ├── container.py   — ContainerWidget: surface cache, dirty region, children
        ├── panel.py       — Panel: titled rectangle with content area
        ├── panel_stack.py — Layered panel compositor → LCD
        ├── menu.py        — Vertical scrollable menu with selection highlight, scrollbar
        └── text.py        — TextWidget, ProgressBar, StatusLine

files/
└── pistomp-recovery.service — systemd unit (Conflicts=mod-ala-pi-stomp, OnFailure target)

pkgbuilds/
└── pistomp-recovery/PKGBUILD — pacman package (uv venv + service file install)
```

## When editing

- **Changing a color?** Edit `COLORS` in `ui/colors.py`. The `Color` type alias is `tuple[int, int, int] | tuple[int, int, int, int]` — alpha is supported.
- **Changing a font size?** Edit `SIZES` in `ui/fonts/__init__.py`. Title and heading use bold; everything else uses regular.
- **Adding a widget?** Implement `draw(ctx: PaintContext)`. No bare `pygame.Rect` — always construct a `PaintContext` from a `Box`. Add a snapshot test in `tests/test_widgets.py`.
- **Adding a screen?** Import `PaintContext` and `Box`; create root context with `PaintContext(surface, Box(0, 0, LCD_WIDTH, LCD_HEIGHT), Box(0, 0, LCD_WIDTH, LCD_HEIGHT))`.
- **Adding a font?** Drop the `.ttf` into `ui/fonts/` and update `SafeFont` / `FONT_CACHE` / `SIZES` in `__init__.py`. Never use `pygame.font.Font` — always go through `SafeFont` / `get_font()`.
- **Menu callbacks** — `Menu.add_item(label, callback)` takes `Callable[[], None]`. Use closures (`lambda: self.foo(arg)`) to capture state. Never pass user data through the callback arg.
- **Hardware deps** — `lgpio`, `spidev`, `adafruit_*` go in `[hardware]` extra with `sys_platform == 'linux'` markers. Never import outside `try/except ImportError`.