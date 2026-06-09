# Menu Redesign Plan

## Goals

1. Surface *what changed and when* immediately, without drilling through submenus.
2. Break pedalboards and packages out of their monolithic facets so individual items can be stamped, rolled back, or updated independently.
3. Sort every list by recency (most recently touched first), with human-relative timestamps.
4. Fix the architectural bugs that make the current menus non-functional.

---

## New menu structure

```
[Resume]                   ← always first; exits recovery, restarts main app
──────────────────────
Reset...  (3 changed)      ← only shown when ≥1 dirty item exists
Update... (2 available)    ← only shown when ≥1 update is available
──────────────────────
Pedalboards...             ← always shown
Packages...                ← always shown
──────────────────────
System Info...
──────────────────────
Reboot
Power Off
```

The **Reset...** and **Update...** items are the "action inbox": you land there when something needs attention. The always-visible **Pedalboards...** and **Packages...** submenus are for deliberate browsing.

---

## Data model: breaking out individual items

### Individual pedalboard items

The `.pedalboards/` directory is already one git repo (`PedalboardsFacet`). Per-pedalboard operations scope every git command to the subdirectory:

| Operation | Git command |
|---|---|
| Dirty check | `git status --porcelain -- $NAME.pedalboard/` |
| Last stamp | tag `stamp/pedalboard/$NAME/$timestamp` |
| Stamp | `git add $NAME.pedalboard/` → commit → tag |
| Rollback to stamp | `git checkout stamp/pedalboard/$NAME/$ts -- $NAME.pedalboard/` |
| Rollback to factory | `git checkout factory -- $NAME.pedalboard/` |

A new `PedalboardItem` class (not a `Facet` subclass — no `repo_path`, no `init()`) wraps these path-scoped operations and is produced by `PedalboardsFacet.list_items() -> list[PedalboardItem]`.

### Individual package items

Each entry in `PISTOMP_PACKAGES` becomes a `PackageItem`:

| Field | Source |
|---|---|
| `name` | Package name string |
| `installed_version` | `pacman -Q $name` |
| `stamped_version` | Entry in last-committed `packages.json` manifest |
| `available_version` | `pacman -Qu $name` (None if up to date) |
| `is_dirty` | `installed_version != stamped_version` |
| `services` | See service map below |

`PackagesFacet` grows a `list_items() -> list[PackageItem]` method that reads the manifest once, runs `pacman -Q` once, and diffs.

### Package → service restart map

Changing a package requires restarting dependent services. Anything in the JACK chain must restart the chain in order.

```python
PACKAGE_SERVICES: dict[str, list[str]] = {
    "jack2-pistomp":       ["jack", "mod-host", "mod-ui", "mod-ala-pi-stomp"],
    "mod-host-pistomp":    ["mod-host", "mod-ui", "mod-ala-pi-stomp"],
    "mod-ui":              ["mod-ui"],
    "pi-stomp":            ["mod-ala-pi-stomp"],
    "pistomp-recovery":    [],   # can't restart self; note to user
    # all others default to full chain restart
}
```

After any package rollback or update, the UI shows "Restart required: jack, mod-host, mod-ui" and offers a **Restart services** action before returning to the menu.

---

## Reset... submenu

Populated at entry time (lazy, with a "Checking..." status line while git/pacman queries run).

Items are all dirty things — mixed pedalboards and packages — sorted by the timestamp of their last change (git log mtime for pedalboards, file mtime of the manifest diff for packages), most recent first:

```
Reset...
──────────────────────────
AmpBud.pedalboard    3h ago
jack2-pistomp        1.9.12 → 1.9.11  yesterday
Carbon-Copy          2 days ago
──────────────────────────
← Back
```

- Pedalboard items show name + human-relative time of last git commit to that subdirectory.
- Package items show name + version drift (`current → stamped`) + human-relative time.

Selecting any item opens a **confirm dialog** (see below) with:
- **Rollback to last stamp** — git checkout or pacman -U from cache
- **Rollback to factory** — git checkout factory branch path
- **Cancel**

---

## Update... submenu

Populated at entry (lazy). Items are packages with newer versions in the pacman repo, sorted by... the version-string build date if parseable, otherwise alphabetically. (pacman version strings embed epoch/release dates; we can sort lexicographically as a proxy.)

```
Update...
──────────────────────────
mod-ui          0.12.1 → 0.13.0
pi-stomp        2.4.0  → 2.4.1
──────────────────────────
Update All
← Back
```

Selecting an individual package:
1. Shows what services will be restarted.
2. Confirm → download → install → health check → stamp → show result.

**Update All**: same pipeline for each package in dependency order (jack chain first).

Post-install health check (existing `packages/health.py` chain: JACK → mod-host → mod-ui → pi-stomp stamp file). On failure: automatic rollback via `install_from_cache`, status shown.

---

## Pedalboards... submenu

All `$NAME.pedalboard/` directories, sorted by last stamp timestamp descending. Never-stamped go to the bottom, sorted by directory mtime.

```
Pedalboards...
──────────────────────────
● AmpBud              3h ago      ← ● = dirty (unstamped changes)
  Beths               yesterday
  Carbon-Copy         2 days ago
  (factory defaults)  never
──────────────────────────
← Back
```

Dirty indicator (●) is shown when `git status --porcelain -- $NAME.pedalboard/` is non-empty.

Selecting a pedalboard:
```
AmpBud.pedalboard
──────────────────────────
Stamp
Rollback to stamp
Rollback to factory
──────────────────────────
← Back
```

Long-press anywhere = back. All destructive actions go through a confirm dialog.

---

## Packages... submenu

All `PISTOMP_PACKAGES` entries, sorted by last stamp timestamp descending. Items show name, installed version, and status indicators:

```
Packages...
──────────────────────────
● jack2-pistomp  1.9.12  ↑1.9.13   ← ● dirty, ↑ update available
  mod-ui         0.13.0  ↑0.14.0   ← clean but update available
  pi-stomp       2.4.1              ← clean, up to date
──────────────────────────
← Back
```

Selecting a package:
```
jack2-pistomp  1.9.12
──────────────────────────
Update to 1.9.13          ← only if update available
Stamp current version
Rollback to stamp         ← only if stamped_version exists
Rollback to factory
──────────────────────────
Restart: jack mod-host…   ← shown if pending restart
← Back
```

---

## Human-relative timestamps

A utility `human_time(ts: datetime) -> str` used throughout:

| Age | Display |
|---|---|
| < 1 minute | "just now" |
| < 1 hour | "42m ago" |
| < 24 hours | "3h ago" |
| < 7 days | "2 days ago" |
| ≥ 7 days | "Jun 3" |

Stamp tag format is `stamp/<prefix>/<name>/<YYYYMMDD-HHMMSS>` for per-item tags and `stamp/<prefix>/<YYYYMMDD-HHMMSS>` for facet-level tags. The timestamp is parsed from the last `/`-delimited segment.

---

## Confirm dialog widget

All destructive actions (rollback, factory reset) require confirmation. A new `ConfirmDialog` widget overlays the current screen:

```
┌─────────────────────────┐
│  Rollback AmpBud        │
│  to factory?            │
│                         │
│  [Cancel]  [Confirm]    │
└─────────────────────────┘
```

- Encoder rotation moves between Cancel and Confirm.
- Click confirms the selection.
- Long-press = Cancel.

`ConfirmDialog` is not a screen — it's a floating overlay rendered on top of the current screen's surface.

---

## Architectural fixes (required before the above lands)

These bugs make the current UI non-functional and must be fixed first.

### 1. Screens recreated on every event and every draw

`RecoveryApp._make_*_screen()` is called inside both `_handle_event` and `_draw_current_screen`, so every encoder tick destroys and recreates the screen, losing all state (selection position, detail view, status text).

**Fix:** Instantiate each screen once (or lazily on first navigation) and store as `RecoveryApp` fields. Pass facet references at construction so all screens share the same objects. Screens are only rebuilt when explicitly navigated to for the first time.

### 2. Only the menu screen is drawn

`_draw_current_screen` has a bare `if self._current_screen == "menu":` with no other branches. Updates, Config, and System Info screens navigate correctly but are never painted.

**Fix:** Dispatch to each screen's `draw()` method based on `_current_screen`.

### 3. Crash screen Resume is broken

`_handle_event` for the crash screen unconditionally sets `_current_screen = "menu"` at line 78 regardless of which action the user took. The `on_resume` callback fires correctly, but then `_current_screen = "menu"` overwrites the intended exit.

**Fix:** Only transition to menu from the crash screen when "Recovery Menu" is selected; let `on_resume` set `_running = False` and return without touching `_current_screen`.

### 4. `UpdatesScreen.check_updates()` called on every event

`_make_updates_screen()` calls `check_updates()` inside it, and that method runs `pacman -Qu` synchronously. Because screens are recreated per event, this hammers the network on every encoder tick.

**Fix:** Covered by fix #1 (screen lifetime). Additionally, check_updates results should be cached on the screen object and refreshed only on explicit re-entry.

### 5. `ConfigScreen` owns its own facet instances

`ConfigScreen.__init__` constructs a new `dict[str, Facet]` rather than receiving the shared instances from `RecoveryApp`. This wastes init work and means config screen operations are not reflected in `RecoveryApp._facets`.

**Fix:** Pass facets (and eventually `list[PedalboardItem]`, `list[PackageItem]`) as constructor arguments from `RecoveryApp`.

### 6. Factory Reset is a no-op

`_on_menu_action(MenuAction.FACTORY_RESET)` is `pass`.

**Fix:** Implement. Factory reset should show the `ConfirmDialog`, then call `factory_reset()` on each facet (or user-selected subset), then reboot.

### 7. Package install skips health check and stamp

`UpdatesScreen._install_all()` goes download → install → done. The full pipeline defined in `PackageManager` (`UpdateState.HEALTH_CHECKING`, `UpdateState.STAMPING`, `UpdateState.ROLLING_BACK`) and the existing `packages/health.py` are never invoked.

**Fix:** After install, run the health check chain. On failure, call `install_from_cache` (rollback) and surface the error. On success, stamp the packages facet.

---

## Implementation order

1. **Fix the three render/lifecycle bugs** (#1, #2, #3 above) — without these, nothing is testable.
2. **`PedalboardItem` and `PackageItem` data classes** — pure data, no UI. Testable in isolation.
3. **`human_time` utility** — one function, snapshot-testable.
4. **`ConfirmDialog` widget** — needed by everything destructive.
5. **Rebuild `MainMenuScreen`** with the new structure and badge counts.
6. **`Reset...` submenu screen** — reads dirty items from both facets.
7. **`Pedalboards...` submenu screen** — replaces current `ConfigScreen` pedalboard section.
8. **`Packages...` submenu screen** — replaces current packages section + adds service restart awareness.
9. **`Update...` submenu screen** — replaces `UpdatesScreen`, wires full health-check/stamp pipeline.
10. **Fix Factory Reset** — confirm dialog → all-facets factory reset → reboot.
