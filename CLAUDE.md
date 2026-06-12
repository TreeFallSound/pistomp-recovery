# CLAUDE.md — pistomp-recovery

Package update and recovery service for pi-Stomp (Arch Linux ARM). Runs as an exclusive LCD service when the main app crashes (3× in 180 s via systemd `OnFailure`/`StartLimitBurst`) or when the user selects "Recovery" from the System Menu.

## Ecosystem

- **../pistomp-arch** — Build system that produces the OS image. PKGBUILDs, service files, build scripts. This project is a PKGBUILD there.
- **../pi-stomp** — Main app (Python). Has the LCD, encoders, pedalboards. `mod-ala-pi-stomp.service` conflicts with `pistomp-recovery.service`.
- **../mod-ui** — Web UI (Tornado). Talks to mod-host over TCP 5555/5556. Editable pip install.

## Key concepts

- **RecoveryApp** — The main loop. Owns the display, encoder input, and a `_screen_stack` of `Screen` objects. Polls input, routes events to the top screen, and redraws when dirty.
- **Screen** — Base class with `draw()` and `handle_event(InputEvent)`. The only concrete screen is `MenuScreen`; crash recovery uses `CrashScreen`, which delegates to an internal `MenuScreen`.
- **MenuScreen** — Universal list/detail/progress/confirm screen. Renders a scrollable `Menu` widget, a `ProgressBar`, a `StatusLine`, and a `ConfirmDialog` modal. Handles the LIST → DETAIL → CONFIRM state machine internally.
- **Item / Action** — `Item` is a row in a menu. `Action` is a button inside DETAIL mode. Both are plain `@dataclass` objects with no behaviour. Closures capture arguments (e.g., `lambda n=name: rollback_pedalboard(n, "stamp")`).
- **Per-domain modules** — `pedalboards.py`, `config.py`, `system.py`, and `packages/packages.py` each expose `list_*_items() → list[Item]` and stamp/rollback helpers. They are independent; there is no Facet base class.
- **Git versioning** — Each domain keeps a bare `.git` repo (or a git worktree via symlinks) with `factory` and `device` branches. `git_util.py` provides `init_repo`, `add_and_commit`, `stamp(tag_prefix)`, `rollback`, and `factory_reset`.
- **Stamp** — Marking state as known-good. `stamp.py` CLI (`pistomp-stamp stamp|status`) commits and tags. Called by pi-stomp on successful pedalboard load.
- **Package updates** — Pacman only. `pacman -Qu` lists updates; `pacman -Sw` downloads; `pacman -S` installs; `pacman -U` rolls back from cache. Per-package service restart awareness via `PACKAGE_SERVICES` map in `constants.py`.
- **Exclusive LCD** — `pistomp-recovery.service` has `Conflicts=mod-ala-pi-stomp.service`. Recovery takes the LCD; resuming stops recovery and starts the main app.
- **Crash loop detection** — `mod-ala-pi-stomp.service`: `Restart=on-failure`, `StartLimitBurst=3`, `StartLimitIntervalSec=180`, `OnFailure=pistomp-recovery.service`.
- **Health check** — Simple `systemctl is-active` helpers in `packages/health.py`. Full pipeline check (JACK → mod-host → mod-ui) is done by restarting services in dependency order and letting systemd report failures.
- **Emulator** — `pistomp-recovery-emulator` runs an interactive pygame window on macOS/Linux with keyboard navigation. Uses `FakeEncoderInput` / `FakeInputManager` instead of GPIO.

## Scope

- In scope: package updates/rollback, crash recovery LCD UI, per-domain git versioning (pedalboards, config, system, packages), factory reset, health checks.
- Out of scope: WiFi config, pedalboard editing, plugin management, audio processing, web UI.

## Design principles

### Deterministic rendering

The LCD renders into a 320×240 pygame Surface. To ensure pixel-identical output on macOS (dev), CI, and the Pi:

- **Bundled fonts** — DejaVu Sans (regular + bold) shipped in `ui/fonts/`. Loaded via `pygame._freetype.Font` (not `pygame.font.Font`, which has a circular import on Python 3.14 / pygame 2.6.1). Fonts are cache-keyed by `(path, size)` so the same font object is reused.
- **Snapshot tests** — Widgets render to a pygame Surface → `FakeLcd` converts to a PIL Image → byte-for-byte `.tobytes()` comparison against `tests/snapshots/`. Run `--snapshot-update` to accept new baselines.
- **Headless-safe init** — `pygame_init.py` sets `SDL_VIDEODRIVER=dummy` in headless mode and calls `pygame._freetype.init()` idempotently. All font rendering goes through `SafeFont`, the `_freetype` wrapper that matches the `pygame.font.Font` API.

### Type safety

- **`pyright --typecheckingMode strict`** with zero errors. No bare `dict`, `list`, `set`, `object`, or `Any`.
- **Semantic type aliases** — `Color` (RGB or RGBA tuple), `ColorName` (literal union of color dictionary keys), `MenuItem`, `SafeFont`. Hover any annotation to see what it actually is.
- Hardware-only modules (`hardware/encoder.py`, `hardware/lcd.py`) gracefully degrade when `gpiozero`/`board` aren't importable — they `try/except ImportError` and log a warning.

### Widgets are plain renderers

There is no `Widget` base class or `Container` hierarchy. Widgets are simple classes with a `draw(surface: pygame.Surface)` method:

- `Menu` — Scrollable vertical list with selection highlight, scrollbar for overflow, right-aligned badge column, and `Callable[[], None]` callbacks. No opaque arg-passing; closures capture what they need.
- `ProgressBar` — Rectangular bar with optional centred label.
- `StatusLine` — Single-line text at the bottom of a screen.
- `ConfirmDialog` — Modal overlay with Cancel/Confirm buttons. Intercepts all input until dismissed.

`PaintContext` exists in `ui/widgets/paint.py` but is not currently used by the live widgets; screens draw directly to `pygame.Surface`.

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
├── __main__.py          — Entry point: argparse, boot mode, main loop, screen stack
├── constants.py         — Paths, package list, PACKAGE_SERVICES map, LCD dims
├── items.py             — Action and Item dataclasses (currency of the UI)
├── util.py              — human_time() relative timestamp utility
├── stamp.py             — CLI: pistomp-stamp (stamp/snapshot/status)
├── service.py           — systemd integration: boot mode, start/stop, crash log, system info
├── git_util.py          — Git operations: init, commit, tag, checkout, rollback, per-item stamps
├── pygame_init.py       — Idempotent pygame + _freetype init (headless-safe)
├── config.py            — Config domain: settings.yml, default_config.yml git versioning
├── pedalboards.py       — Pedalboard domain: per-directory git-scoped stamp/rollback
├── system.py            — System domain: /boot/config.txt, /etc/jackdrc, ALSA state git versioning
├── hardware/
│   ├── encoder.py       — Rotary encoder GPIO input (nav encoder D=17 CLK=4)
│   └── lcd.py           — SPI ILI9341 LCD driver (adafruit_rgb_display, 56MHz, /run/lcd.init stamp)
├── packages/
│   ├── __init__.py      — Re-exports for convenience
│   ├── installer.py     — Pacman wrapper: download, install, rollback from cache
│   ├── packages.py      — Package domain: version tracking, Item list, stamp/rollback
│   └── health.py        — Service health checks: systemctl is-active, journalctl
├── emulator/
│   ├── bootstrap.py     — EmulatorApp: interactive pygame window, navigation stack, stub data
│   ├── controls.py      — FakeEncoderInput, FakeInputManager for emulator
│   ├── lcd_pygame.py    — LcdPygame: renders Surface to pygame window
│   └── window.py        — EmulatorWindow: pygame event loop, keyboard → InputEvent
└── ui/
    ├── display.py        — Pygame surface ↔ SPI LCD bridge (Display class)
    ├── colors.py         — Color type alias, ColorName literal union, COLORS dict (320×240 dark theme)
    ├── input.py          — Encoder rotation + GPIO switch → InputEvent (long-press detection)
    ├── fonts/
    │   ├── __init__.py   — SafeFont (pygame._freetype wrapper), get_font(), FONT_CACHE, SIZES dict
    │   ├── DejaVuSans.ttf       — Regular weight (from pi-stomp)
    │   └── DejaVuSans-Bold.ttf  — Bold weight (from pi-stomp)
    ├── screens/
    │   ├── __init__.py   — Screen base class with draw(), handle_event(), set_back_callback()
    │   ├── crash.py      — "App Crashed" + last journal lines, Resume/Recovery Menu
    │   ├── menu_screen.py — Universal screen: list → detail → confirm → progress
    │   └── system_info.py  — Kernel, uptime, temp, OS version
    └── widgets/
        ├── __init__.py   — (empty)
        ├── misc.py       — Box geometry class, InputEvent enum
        ├── paint.py      — PaintContext (surface, clip rect, frame) — available but unused
        ├── menu.py        — Scrollable vertical menu with selection, scrollbar, right badges
        ├── confirm_dialog.py — Modal overlay: encoder selects Cancel/Confirm, long-press = Cancel
        └── text.py        — ProgressBar, StatusLine

files/
└── pistomp-recovery.service — systemd unit (Conflicts=mod-ala-pi-stomp, OnFailure target)

pkgbuilds/
└── pistomp-recovery/PKGBUILD — pacman package (uv venv + service file install)
```

## When editing

- **Changing a color?** Edit `COLORS` in `ui/colors.py`. The `Color` type alias is `tuple[int, int, int] | tuple[int, int, int, int]` — alpha is supported.
- **Changing a font size?** Edit `SIZES` in `ui/fonts/__init__.py`. Title and heading use bold; everything else uses regular.
- **Adding a widget?** Implement `draw(surface: pygame.Surface)`. Add a snapshot test in `tests/test_widgets.py`.
- **Adding a screen?** Inherit from `Screen` in `ui/screens/__init__.py`. Most new flows should reuse `MenuScreen` instead of creating a new screen class.
- **Adding a font?** Drop the `.ttf` into `ui/fonts/` and update `SafeFont` / `FONT_CACHE` / `SIZES` in `__init__.py`. Never use `pygame.font.Font` — always go through `SafeFont` / `get_font()`.
- **Menu callbacks** — `Menu.add_item(label, callback)` takes `Callable[[], None]`. Use closures (`lambda: self.foo(arg)`) to capture state. Never pass user data through the callback arg. For right-aligned badges: `Menu.add_item(label, callback, right="3 changed")`.
- **Confirm dialog** — `ConfirmDialog(surface, title, on_confirm, on_cancel)` is a modal overlay. It renders on top of the current screen and intercepts all input until dismissed. Use for any destructive action (rollback, factory reset).
- **Per-domain item lists** — To add a new recoverable domain, create a module with `list_*_items() → list[Item]` and stamp/rollback helpers, then wire it into `RecoveryApp._show_main_menu()` and `_show_*()`.
- **Hardware deps** — `lgpio`, `spidev`, `adafruit_*` go in `[project.optional-dependencies] hardware` with `sys_platform == 'linux'` markers. Never import outside `try/except ImportError`.
- **Emulator stub data** — When adding a new domain to the real app, add matching `STUB_*` lists in `emulator/bootstrap.py` so the emulator still exercises all four item states (clean stamped, dirty stamped, factory, unknown).
