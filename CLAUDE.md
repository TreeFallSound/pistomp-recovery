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

## Python requirement

`>=3.12`, strict typing (`pyright --typechecking-mode strict`). System Python + `--system-site-packages` for lgpio/spidev access.

## File map

```
src/pistomp_recovery/
├── __main__.py          — Entry point: boot mode detection, main loop, screen routing
├── constants.py         — Paths, package list, service list, LCD dims
├── stamp.py             — CLI: pistomp-stamp (stamp/snapshot/status per facet)
├── service.py           — systemd integration: boot mode, start/stop, crash log, system info
├── git_util.py          — Git operations: init, commit, tag, checkout, rollback
├── hardware/
│   ├── encoder.py        — Rotary encoder GPIO input (nav encoder D=17 CLK=4)
│   └── lcd.py            — SPI ILI9341 LCD driver (adafruit_rgb_display, 24MHz, /run/lcd.init stamp)
├── facets/
│   ├── base.py           — Facet ABC: init, snapshot, stamp, rollback, factory_reset, status
│   ├── config_facet.py   — /home/pistomp/data/config/ — default_config.yml, settings.yml
│   ├── pedalboards_facet.py — /home/pistomp/data/.pedalboards/ — git repo, upstream+device branches
│   ├── packages_facet.py — Package version manifest (pacman -Q), installs on rollback
│   └── system_facet.py   — /boot/config.txt, /etc/jackdrc, ALSA state, pistomp.conf
├── packages/
│   ├── manager.py        — Pacman wrapper: download, install, rollback from cache
│   └── health.py         — Service health checks: JACK, mod-host, mod-ui, pi-stomp stamp
└── ui/
    ├── display.py        — Pygame surface ↔ SPI LCD bridge
    ├── colors.py         — RGB color dict for 320x240 dark theme
    ├── fonts.py          — Pygame font cache
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
        ├── widget.py      — Base Widget with bounds, dirty flag, parent ref
        ├── container.py    — ContainerWidget: surface cache, dirty region, children
        ├── panel.py        — Panel: titled rectangle with content area
        ├── panel_stack.py  — Layered panel compositor → LCD
        ├── menu.py        — Vertical scrollable menu with selection highlight, scrollbar
        └── text.py         — TextWidget, ProgressBar, StatusLine

files/
└── pistomp-recovery.service — systemd unit (Conflicts=mod-ala-pi-stomp, OnFailure target)

pkgbuilds/
└── pistomp-recovery/PKGBUILD — pacman package (uv venv + service file install)
```