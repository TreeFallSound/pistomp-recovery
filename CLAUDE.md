# CLAUDE.md — pistomp-recovery

Package update and recovery service for pi-Stomp (Arch Linux ARM). Runs as an exclusive LCD service when the main app crashes (3× in 180 s via systemd `OnFailure`/`StartLimitBurst`) or when the user selects "Recovery" from the System Menu.

## Ecosystem

- **../pistomp-arch** — Build system that produces the OS image. PKGBUILDs, service files, build scripts. This project is a PKGBUILD there.
- **../pi-stomp** — Main app (Python). Has the LCD, encoders, pedalboards. `mod-ala-pi-stomp.service` conflicts with `pistomp-recovery.service`.
- **../mod-ui** — Web UI (Tornado). Talks to mod-host over TCP 5555/5556. Editable pip install.

## Key concepts

- **RecoveryApp** — The main loop. Owns the display, encoder input, and a `_screen_stack` of `Screen` objects. Polls input, routes events to the top screen, and redraws when dirty.
- **Screen** — Base class with `draw()` and `handle_event(InputEvent)`. The only concrete screen is `MenuScreen`; crash recovery uses `CrashScreen`, which subclasses `MenuScreen`.
- **MenuScreen** — Universal screen rendering a `Header` bar plus a list of `Row`s. States are `LIST | CONFIRM | PROGRESS`. Encoder rotation walks every enabled `Target` in reading order (header icon first, then rows top-to-bottom, left-to-right); click activates; destructive targets pop a `ConfirmDialog`. There is no DETAIL state — items with multiple actions push a *new* `MenuScreen` of action rows onto the stack. Long-press is inert: back/exit is the header icon only.
- **Header / Target / Row** — `Header` is the inverted (QBASIC-style) title bar; its top-right holds a selectable icon `Target` (`←` back on submenus, `►` exit/resume on the root). `Target` is one selectable reticule (`label`, `on_select`, optional `confirm`, `enabled`); selection is drawn in reverse video, never literal brackets. `Row` is one text line: a static `prefix` plus a tuple of `Target`s joined by ` | ` (so `RESTART [JACK] | [MOD]` is expressible type-safely), plus an optional right-aligned `right` badge.
- **Item / Action** — Legacy plain `@dataclass` objects still produced by the per-domain `list_*_items()` helpers. `RecoveryApp`/`EmulatorApp` adapt them into `Row`/`Target` (single action → direct target; multiple → a pushed detail screen). Closures capture arguments (e.g., `lambda n=name: rollback_pedalboard(n, "stamp")`).
- **Top menu / shared domain picker** — Root rows: `RESTART [JACK]|[MOD]`, `[RESET TO CHECKPOINT]`, `[FACTORY RESET]`, `[UPDATES]`, `[REBOOT]|[POWER OFF]`. The latter three drill into one shared picker (`Pedalboards / Plugins / Config / System`) parameterised by mode (`checkpoint` rolls back to stamp, `factory` to factory, `updates` lists scoped package updates via `PACKAGE_DOMAIN`). `Plugins` is a selectable no-op for now.
- **Per-domain modules** — `pedalboards.py`, `config.py`, `system.py`, and `packages/packages.py` each expose `list_*_items() → list[Item]` and stamp/rollback helpers. They are independent; there is no Facet base class.
- **Git versioning** — Each domain keeps a bare `.git` repo (or a git worktree via symlinks) with `factory` and `device` branches. `git_util.py` provides `init_repo`, `add_and_commit`, `stamp(tag_prefix)`, `rollback`, and `factory_reset`.
- **Stamp** — Marking state as known-good. `stamp.py` CLI (`pistomp-stamp stamp|status`) commits and tags. Called by pi-stomp on successful pedalboard load.
- **Package updates** — Pacman only. `get_available_updates()` calls `pacman -Sy` to sync repo DBs (including the `[pistomp]` GitHub Releases repo), then `pacman -Qu` lists pending updates. `pacman -Sw` downloads; `pacman -S` installs; `pacman -U` rolls back from cache. Per-package service restart awareness via `PACKAGE_SERVICES` map in `constants.py`.
- **Custom repo** — pi-Stomp packages are published as release assets on the `pistomp-arch` GitHub repo under the fixed tag `repo`. `pistomp.db.tar.zst` is generated with `repo-add` on the host after fetching built `.pkg.tar.zst` files back from the device via `deploy-pkg.sh`.
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

- **Bundled font** — `Mx437_IBM_VGA_8x16.ttf` (the "Mx" mixed outline+bitmap IBM VGA face from VileR's Ultimate Oldschool PC Font Pack, CC BY-SA 4.0 — see `ui/fonts/NOTICE.md` / `LICENSE-Mx437.txt`). One weight, one fixed pixel size (`FONT_SIZE = 16`), rendered **non-antialiased** for crisp pixels. Emphasis is reverse video, not bold/size. `cell_size()` exposes the 8×16 monospace cell; the screen is a 40×15 grid. Loaded via `pygame._freetype.Font` (not `pygame.font.Font`, which has a circular import on Python 3.14 / pygame 2.6.1).
- **Snapshot tests** — Widgets render to a pygame Surface → `FakeLcd` converts to a PIL Image → byte-for-byte `.tobytes()` comparison against `tests/snapshots/`. Run `--snapshot-update` to accept new baselines.
- **Headless-safe init** — `pygame_init.py` sets `SDL_VIDEODRIVER=dummy` in headless mode and calls `pygame._freetype.init()` idempotently. All font rendering goes through `SafeFont`, the `_freetype` wrapper that matches the `pygame.font.Font` API.

### Type safety

- **`pyright --typecheckingMode strict`** with zero errors. No bare `dict`, `list`, `set`, `object`, or `Any`.
- **Semantic type aliases** — `Color` (RGB or RGBA tuple), `ColorName` (literal union of color dictionary keys), `NavPos`, `SafeFont`. Hover any annotation to see what it actually is.
- Hardware-only modules (`hardware/encoder.py`, `hardware/lcd.py`) gracefully degrade when `gpiozero`/`board` aren't importable — they `try/except ImportError` and log a warning.

### Widgets are plain renderers

There is no `Widget` base class or `Container` hierarchy. Widgets are simple classes with a `draw(surface: pygame.Surface)` method:

- `Header` — Inverted QBASIC-style title bar with a selectable back/exit icon at top-right (`ui/widgets/header.py`). The row-rendering, scrolling, and selection live in `MenuScreen` itself rather than a separate list widget.
- `ProgressBar` — Square (no radius) bar with optional centred label.
- `StatusLine` — Single-line text at the bottom of a screen.
- `ConfirmDialog` — Modal overlay with No/Yes choices in reverse video. Intercepts all input until dismissed.
- All text blits apply `fonts.TEXT_DY` (1px) so glyphs sit optically centred in their lane; the first content row is inset from the header by one cell to match the left text margin.

`PaintContext` exists in `ui/widgets/paint.py` but is not currently used by the live widgets; screens draw directly to `pygame.Surface`.

### Service crash loop

The systemd unit chain is: `mod-ala-pi-stomp.service` has `OnFailure=pistomp-recovery.service` and `StartLimitBurst=3/180s`. When pi-stomp crashes 3× in 3 minutes, systemd starts pistomp-recovery instead. Recovery shows a crash screen with the last journal lines and a `[RESUME] | [RECOVERY]` row (resume restarts pi-stomp once more; recovery opens the menu). The header `►` icon also resumes. The `Conflicts=` relationship ensures only one app owns the LCD at a time.

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

- `←`/`→` — Navigate reticules (including the header back/exit icon)
- `Enter`/`Space` — Select
- `Esc` — Quit
- `--force-crash` — Start in crash recovery mode

(Long-press is no longer a back affordance — navigate to the header `←`/`►` icon instead.)

## File map

```
src/pistomp_recovery/
├── __main__.py          — Entry point: argparse, boot mode, main loop, top menu + domain picker
├── constants.py         — Paths, package list, PACKAGE_SERVICES/PACKAGE_DOMAIN maps, LCD dims
├── items.py             — Action/Item (legacy) + Target/Row dataclasses (currency of the UI)
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
    ├── colors.py         — Color type alias, ColorName literal union, COLORS dict (softened EGA / QBASIC theme)
    ├── input.py          — Encoder rotation + GPIO switch → InputEvent
    ├── fonts/
    │   ├── __init__.py   — SafeFont (non-AA _freetype wrapper), get_font(), cell_size(), text_width(), FONT_SIZE, TEXT_DY
    │   ├── Mx437_IBM_VGA_8x16.ttf — Bundled pixel font (CC BY-SA 4.0)
    │   ├── LICENSE-Mx437.txt      — CC BY-SA 4.0 license text
    │   └── NOTICE.md              — Font attribution
    ├── screens/
    │   ├── __init__.py   — Screen base class with draw(), handle_event()
    │   ├── crash.py      — CrashScreen (MenuScreen subclass): service states + log + [RESUME]|[RECOVERY]
    │   └── menu_screen.py — Universal screen: Header + Row list, states LIST/CONFIRM/PROGRESS
    └── widgets/
        ├── __init__.py   — (empty)
        ├── misc.py       — Box geometry class, InputEvent enum
        ├── paint.py      — PaintContext (surface, clip rect, frame) — available but unused
        ├── header.py      — Inverted title bar + selectable back/exit icon (ICON_BACK/ICON_EXIT)
        ├── confirm_dialog.py — Modal overlay: encoder selects No/Yes (reverse video)
        └── text.py        — ProgressBar, StatusLine

files/
└── pistomp-recovery.service — systemd unit (Conflicts=mod-ala-pi-stomp, OnFailure target)

pkgbuilds/
└── pistomp-recovery/PKGBUILD — pacman package (uv venv + service file install)
```

## When editing

- **Changing a color?** Edit `COLORS` in `ui/colors.py`. The `Color` type alias is `tuple[int, int, int] | tuple[int, int, int, int]` — alpha is supported.
- **Changing the look?** It's a single 8×16 pixel font and one fixed size — vary emphasis with reverse video / `COLORS`, not size or bold. `SIZES` is retained only for source compatibility.
- **Adding a widget?** Implement `draw(surface: pygame.Surface)` and apply `fonts.TEXT_DY` to text blits. Add a snapshot test in `tests/test_widgets.py`.
- **Adding a screen?** Inherit from `Screen` in `ui/screens/__init__.py`. Most new flows should build `Row`/`Target` lists and reuse `MenuScreen` (pass it a header icon `Target`) instead of creating a new screen class.
- **Adding a font?** Drop the `.ttf` into `ui/fonts/`, point `_FONT_PATH` at it, and keep `antialiased = False`. Never use `pygame.font.Font` — always go through `SafeFont` / `get_font()`.
- **Menu rows/targets** — Build `Row((Target(label, on_select, confirm=..., enabled=...), ...), prefix="…", right="3 changed")`. Use closures (`lambda: self.foo(arg)`) to capture state; never pass user data through a callback arg. Selection is reverse video — don't put literal brackets in labels.
- **Confirm dialog** — `ConfirmDialog(surface, title, on_confirm, on_cancel)` is a modal overlay, but prefer setting `Target.confirm=` — `MenuScreen` opens/handles the dialog for you. Use it for any destructive action (rollback, factory reset, reboot).
- **Per-domain item lists** — To add a new recoverable domain, create a module with `list_*_items() → list[Item]`, then route it through `RecoveryApp._raw_domain_items()` / `_domain_items()` and add it to `_DOMAINS`. Updates are scoped via `PACKAGE_DOMAIN` in `constants.py`.
- **Hardware deps** — `lgpio`, `spidev`, `adafruit_*` go in `[project.optional-dependencies] hardware` with `sys_platform == 'linux'` markers. Never import outside `try/except ImportError`.
- **Emulator stub data** — When adding a new domain to the real app, add matching `STUB_*` lists in `emulator/bootstrap.py` so the emulator still exercises all four item states (clean stamped, dirty stamped, factory, unknown).
