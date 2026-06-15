# pistomp-recovery refactor plan

## Context

This refactor addresses the overengineering identified in `RECOVERY-REVIEW.md`, with one key correction: **full LCD redraw is not free on a 24 MHz SPI bus**. A 320×240 frame takes ~77ms to push. The current code redraws and pushes every 30ms regardless of changes, but the dirty-region tracking infrastructure is dead code (the main loop never checks it). The right approach is to flatten the widget hierarchy while adding a top-level dirty flag to skip redundant SPI transfers.

Additionally, pi-stomp does not yet call `pistomp-stamp` or write `/run/pistomp-healthy`. The stamp CLI and health stamp are designed but unwired. This changes the stamping design: recovery should not stamp on the user's behalf, since the whole point of a stamp is "I know this works."

## Principles

1. **Stamp = known-good, declared by the thing that knows.** Recovery doesn't know if pi-stomp is healthy. pi-stomp knows. So pi-stomp calls `pistomp-stamp` after a successful pedalboard load, and the stamp means "the system was working at this point."
2. **Recovery's job is rollback, not validation.** After installing a package update, recovery should not try to start the full audio stack to verify it. It should install, and the user resumes pi-stomp. If pi-stomp crashes 3× in 180s, recovery comes back and the user can roll back.
3. **The LCD is slow.** Only push frames when something changed. A dirty flag at the app level eliminates ~90% of SPI traffic since the user interacts intermittently.
4. **All screens are menus.** List view, detail view, confirm dialog, progress screen — all the same shape. One generic `MenuScreen` handles all of them.
5. **No Facet ABC.** The facet abstraction added indirection without generality. Operations are just functions. Pedalboards keep using git (it's already there), but through direct `git_util` calls, not through a class hierarchy.

---

## Phase 1: Flatten the UI and add dirty flag

**Goal:** Delete `Container`, `PanelStack`, `Panel`, `Widget` base class. Add top-level dirty flag. Reduce SPI traffic by ~90%.

### Delete these files entirely:
- `ui/widgets/widget.py` — base class with dirty propagation (unused)
- `ui/widgets/container.py` — container with dirty-region tracking (unused, `_cache` never populated)
- `ui/widgets/panel.py` — titled panel container (unnecessary hierarchy)
- `ui/widgets/panel_stack.py` — layered compositor (always redraws everything anyway)

### Keep these files (simplified):
- `ui/widgets/misc.py` — `Box` and `InputEvent` stay. Remove `Widget` base class dependency.
- `ui/widgets/paint.py` — `PaintContext` stays (30 lines, useful for future partial-frame support). Remove `Container` integration.
- `ui/widgets/menu.py` — stays as-is, but no longer extends `Container`. Becomes a standalone class with `draw(surface, rect)`.
- `ui/widgets/confirm_dialog.py` — stays, but becomes a standalone class (no inheritance).
- `ui/widgets/text.py` — `TextWidget`, `ProgressBar`, `StatusLine` become standalone classes with `draw(surface, rect)` instead of inheriting from `Widget`.

### Add dirty flag to main loop:

In `__main__.py`, change the main loop from:

```python
while self._running:
    events = self._input.poll()
    for event in events:
        self._handle_event(event)
    self._draw_current_screen()  # always draws + pushes to SPI
    time.sleep(POLL_INTERVAL)
```

To:

```python
while self._running:
    events = self._input.poll()
    for event in events:
        self._handle_event(event)
    if self._dirty:
        self._draw_current_screen()
        self._display.update(self._display.surface)
        self._dirty = False
```

Every event handler that changes state sets `self._dirty = True`. `Menu.handle_event()` sets a dirty flag on selection change. `set_status()`, `set_state()`, etc. all set dirty. The initial screen push sets dirty.

This means: when the user isn't touching the encoder, the LCD gets zero SPI traffic. When they scroll, each encoder tick pushes one frame (~77ms). This is fine — the user can't scroll faster than the LCD can update, and there's no animation or continuous rendering needed.

Even better if we update the LCD to drive at 56MHz, which has been tested stable and allows us to refresh the whole screen a lot faster.

### `Menu` changes:
- Remove `Container` inheritance. Menu becomes a plain class with `items`, `sel_index`, `scroll_offset`.
- `draw(surface, rect)` instead of `draw(ctx: PaintContext)`.
- `mark_dirty()` method that the app checks, or the app sets its own dirty flag when `handle_event` returns `True`.

### `ConfirmDialog` changes:
- Remove any widget inheritance. Just a plain class.
- `draw(surface)` draws the overlay + dialog directly.
- `handle_event(event)` returns `True` if the event was consumed.

### Screen changes:
- Each screen's `draw()` fills the surface, draws its menu/status/progress directly.
- Screens no longer create `PaintContext` — they draw directly to the `pygame.Surface`.
- `Screen` base class becomes just `surface`, `_on_back`, `draw()`, `handle_event()`.

---

## Phase 2: Generic `MenuScreen` replaces all detail screens

**Goal:** Replace `PedalboardsScreen`, `PackagesScreen`, `ResetScreen` with a single `MenuScreen` parameterized by items and actions.

### Item states and display

Every item (pedalboard, config file, system file, package) exists in one of four states, determined by comparing current state against two baselines: **factory** (image-shipped, always exists) and **last stamp** (created by pi-stomp on successful pedalboard load, may not exist yet).

| State | Stamp exists? | Current vs stamp | Current vs factory | Meaning | Display |
|---|---|---|---|---|---|
| Clean | Yes | Same | — | Known-good, unchanged since last confirmed working | `Hardware Config` `✓ 2d ago` |
| Dirty | Yes | Different | — | Changed since last confirmed working — could be the problem | `Hardware Config *` `2d ago` |
| Factory | No | — | Same | Never modified from image baseline | `Hardware Config` `factory` |
| Unknown | No | — | Different | Modified but never confirmed working — concerning | `Hardware Config ∗` `?` |

**Display rules:**
- The `∗` character (U+2217, centered asterisk operator) appears after the label for dirty/unknown items.
- The right column shows:
  - `✓ {relative_time}` for clean items (stamped, unchanged)
  - `{relative_time}` for dirty items (changed since stamp)
  - `factory` for factory items (never modified)
  - `?` for unknown items (modified, never stamped)
- For packages, an available update is shown as `↑{version}` in the right column, replacing the timestamp.

**Actions by state:**

| State | Available actions |
|---|---|
| Clean | Rollback to stamp, Rollback to factory |
| Dirty | Rollback to stamp, Rollback to factory |
| Factory | Rollback to factory |
| Unknown | Rollback to factory |

Note: there is no "Stamp" action in recovery. Stamping is pi-stomp's job — it calls `pistomp-stamp` after a successful pedalboard load because only pi-stomp knows the system is working.

### New data model:

```python
from dataclasses import dataclass
from typing import Callable

@dataclass
class Action:
    label: str
    callback: Callable[[], None]
    confirm: str | None = None  # if set, show ConfirmDialog with this title before calling callback

@dataclass
class Item:
    name: str          # internal identifier (pedalboard dir name, package name, etc.)
    label: str          # display text: "Hardware Config", "Big Reverb.pedalboard"
    dirty: bool         # True if current state differs from last stamp (or from factory if no stamp)
    right: str          # right column: "✓ 2d ago", "2d ago", "factory", "?", "↑1.2.3"
    actions: list[Action]
```

### `MenuScreen` state machine:

States: `LIST`, `DETAIL`, `CONFIRM`, `PROGRESS`

```
LIST ──select item──→ DETAIL
DETAIL ──action with confirm──→ CONFIRM
DETAIL ──action without confirm──→ execute
CONFIRM ──confirm──→ execute
CONFIRM ──cancel──→ DETAIL
LIST/DETAIL ──long-press──→ back
```

Each state renders differently:
- `LIST`: Menu with item labels + right badges, scroll
- `DETAIL`: Menu with `item.actions[i].label` entries + "← Back"
- `CONFIRM`: Dimmed background + centered ConfirmDialog
- `PROGRESS`: Title + ProgressBar + StatusLine (used by updates)

`MenuScreen.__init__` takes:
- `surface`: the shared pygame Surface
- `title`: screen title
- `items`: list of `Item`
- `back_callback`: called on long-press back from LIST state

### Files replaced:

| Current file | What happens |
|---|---|
| `pedalboards_screen.py` | Deleted. `__main__.py` constructs `Item` list from pedalboard data. |
| `packages_screen.py` | Deleted. Same pattern. |
| `reset_screen.py` | Deleted. Same pattern. |
| `updates.py` | Refactored to use `MenuScreen` with `PROGRESS` state, or stays as a thin subclass. |
| `crash.py` | Deleted. `CrashScreen` becomes a `MenuScreen` with two items ("Resume", "Recovery Menu") plus crash log rendering in `LIST` state (custom draw before the menu). |
| `system_info.py` | Kept as-is (renders key-value pairs, not a menu). Or becomes a `MenuScreen` where each line is a non-selectable item. |
| `main_menu.py` | Simplified — constructs a `MenuScreen` with fixed items. |

### `MainMenuScreen` still special:

The main menu is slightly different because it conditionally shows "Reset..." and "Update..." based on dirty/update counts. It can be a thin wrapper that rebuilds its item list when counts change.

---

## Phase 3: Replace Facet system with simple functions

**Goal:** Delete `Facet` ABC, `FacetItem` protocol, all four facet classes. Replace with direct functions.

### Delete these files entirely:
- `facets/base.py` — `Facet` ABC and `FacetItem` protocol
- `facets/config_facet.py` — `ConfigFacet`
- `facets/system_facet.py` — `SystemFacet`
- `stamp.py` — CLI tool (will be replaced, see Phase 6)

### Replace `PedalboardsFacet` with `pedalboards.py`:

Keep git for pedalboards (the repo is already there), but as direct function calls, not a class:

```python
# pedalboards.py

def init_pedalboards(path: Path) -> None:
    """Ensure pedalboards repo exists with factory and device branches."""
    ...

def list_pedalboard_items(path: Path) -> list[Item]:
    """Return Item list for each .pedalboard directory."""
    items = []
    for entry in sorted(path.iterdir()):
        if not entry.is_dir() or not entry.name.endswith(".pedalboard"):
            continue
        is_dirty = bool(git("status", "--porcelain", "--", str(entry), cwd=path, check=False).strip())
        stamp_tag = last_stamp(path, f"pedalboard/{entry.name}")
        stamp_time = parse_stamp_time(stamp_tag) if stamp_tag else None

        # Determine state and right column
        if stamp_time:
            right = human_time(stamp_time)
        elif not is_dirty:
            right = "factory"
        else:
            right = "?"

        label = entry.name
        dirty = is_dirty
        actions = [
            Action("Rollback to stamp", lambda n=entry.name: rollback_pedalboard(n, "stamp"),
                   confirm=f"Rollback {entry.name}\nto last stamp?"),
            Action("Rollback to factory", lambda n=entry.name: rollback_pedalboard(n, "factory"),
                   confirm=f"Rollback {entry.name}\nto factory?"),
        ]
        # Factory-only items don't get "Rollback to stamp"
        if not stamp_time:
            actions = [a for a in actions if a.label != "Rollback to stamp"]

        items.append(Item(name=entry.name, label=label, dirty=dirty, right=right, actions=actions))
    # sort: stamped by recency, then unstamped by mtime
    ...
    return items

def stamp_pedalboard(name: str) -> None:
    """Create a git tag for this pedalboard's current state."""
    ...

def rollback_pedalboard(name: str, target: Literal["stamp", "factory"]) -> None:
    """Restore pedalboard to last stamp or factory state."""
    ...

def factory_reset_pedalboard(name: str) -> None:
    """Same as rollback to factory — kept as explicit API for clarity."""
    rollback_pedalboard(name, "factory")
```

### Replace `PackagesFacet` with `packages.py`:

Keep the JSON stamp file pattern (it's not git, it's just a file). Keep `pacman -U` from cache for rollback.

```python
# packages.py

def list_package_items() -> list[Item]:
    """Return Item list for each tracked package."""
    installed = collect_versions()      # pacman -Q
    stamped = read_stamp_file()         # ~/.pistomp-recovery/packages.stamp
    factory = read_factory_file()        # /etc/pistomp/factory-packages.list
    available = check_updates()          # pacman -Qu
    items = []
    for pkg in PISTOMP_PACKAGES:
        inst = installed.get(pkg)
        stamp = stamped.get(pkg)
        fact = factory.get(pkg)
        avail = available.get(pkg)
        is_dirty = inst != stamp
        label = f"● {pkg}" if is_dirty else f"  {pkg}"
        right = f"↑{avail}" if avail else ""
        actions = []
        if avail:
            actions.append(Action(f"Update to {avail}", lambda p=pkg: install_package(p)))
        if not is_dirty:
            actions.append(Action("Stamp current version", lambda p=pkg: stamp_package(p)))
        if is_dirty and stamp:
            actions.append(Action("Rollback to stamp", lambda p=pkg: rollback_package(p, "stamp"),
                                  confirm=f"Rollback {pkg}\nto stamp?"))
        if fact:
            actions.append(Action("Rollback to factory", lambda p=pkg: rollback_package(p, "factory"),
                                  confirm=f"Rollback {pkg}\nto factory?"))
        items.append(Item(name=pkg, label=label, right=right, actions=actions))
    return items

def stamp_packages() -> None:
    """Write current pacman versions to stamp file."""
    ...

def rollback_package(name: str, target: str) -> None:
    """Rollback package to stamped or factory version via pacman -U."""
    ...
```

### Replace `ConfigFacet` and `SystemFacet` with `config.py` and `system.py`:

Config and system keep git repos with `factory`/`device` branches — same pattern as pedalboards, but without per-item operations. They use `git_util` directly.

```python
# config.py
from pistomp_recovery import git_util

CONFIG_DIR = Path("/home/pistomp/data/config")
CONFIG_REPO = Path("/home/pistomp/.pistomp-recovery/config.git")

def init_config() -> None:
    """Ensure config repo exists with factory and device branches."""
    if not git_util.is_repo(CONFIG_REPO):
        # Symlink config files into repo, commit, create factory branch
        ...
    git_util.git("checkout", git_util.DEVICE_BRANCH, cwd=CONFIG_REPO)

def list_config_items() -> list[Item]:
    """Return Item list for config files. Only dirty-check + rollback actions."""
    is_dirty = bool(git_util.git("status", "--porcelain", cwd=CONFIG_REPO, check=False).strip())
    stamp_tag = git_util.last_stamp(CONFIG_REPO, "config")
    stamp_time = parse_stamp_time(stamp_tag) if stamp_tag else None
    return [
        Item(
            name="config",
            label="● Config" if is_dirty else "  Config",
            right=human_time(stamp_time) if stamp_time else "never",
            actions=[
                Action("Rollback to stamp", lambda: rollback_config("stamp"),
                       confirm="Rollback config\nto last stamp?"),
                Action("Rollback to factory", lambda: rollback_config("factory"),
                       confirm="Reset config\nto factory?"),
            ],
        ),
    ]

def stamp_config() -> str:
    """Commit and tag current config state."""
    git_util.add_and_commit(CONFIG_REPO, "config stamp")
    return git_util.stamp(CONFIG_REPO, "config")

def rollback_config(target: str) -> None:
    """Rollback config to stamp or factory."""
    if target == "factory":
        git_util.factory_reset(CONFIG_REPO)
    else:
        tag = git_util.last_stamp(CONFIG_REPO, "config")
        git_util.rollback(CONFIG_REPO, tag)
```

```python
# system.py — same pattern as config.py but for system files
# /boot/config.txt, /etc/jackdrc, /var/lib/alsa/asound.state, etc.
```

### `git_util.py` stays:

The `git_util.py` module (init, add_and_commit, stamp, rollback, factory_reset, last_stamp, diff_summary, create_factory_branch) is kept as-is. It's ~100 lines of straightforward git wrappers. All three git-backed modules (pedalboards, config, system) call `git_util` directly. No `Facet` ABC needed.

### `__main__.py` changes:

Replace all facet references with direct function calls:

```python
# Before:
self._ped_facet = PedalboardsFacet()
...
self._ped_facet.init()
self._ped_facet.list_items()

# After:
pedalboard_items()  # calls init internally if needed
```

The `_show_pedalboards()`, `_show_packages()`, `_show_reset()` methods construct `Item` lists and pass them to `MenuScreen`.

---

## Phase 4: Simplify package manager and health check

**Goal:** Remove `UpdateState` enum and `PackageManager` class. Replace with simple functions.

### Replace `PackageManager` class with functions:

```python
# packages/installer.py

def download_packages(names: list[str]) -> bool:
    """pacman -Sw --noconfirm --needed. Returns True on success."""
    result = subprocess.run(["pacman", "-Sw", "--noconfirm", "--needed"] + names, ...)
    return result.returncode == 0

def install_packages(names: list[str]) -> bool:
    """pacman -S --noconfirm --needed. Returns True on success."""
    result = subprocess.run(["pacman", "-S", "--noconfirm", "--needed"] + names, ...)
    return result.returncode == 0

def install_from_cache(names: list[str]) -> bool:
    """Find cached .pkg.tar* and pacman -U. Returns True on success."""
    ...
```

### Replace health check with per-service checks, but don't start services:

The current `full_health_check()` *starts* services in dependency order, then checks them. This is wrong for two reasons:
1. If the audio stack is broken, starting it during an update flow is fragile.
2. The check conflates "package installed correctly" with "entire audio stack works."

**New design:** Recovery does not do health checks after package installation. Instead:

1. Recovery installs packages and stamps them.
2. User hits "Resume" to restart pi-stomp.
3. If pi-stomp starts successfully, it calls `pistomp-stamp` to confirm everything works.
4. If pi-stomp crashes 3× in 180s, systemd starts recovery again. The user can now roll back.

This means `health.py` is simplified to just `check_service_running(name)` for display purposes (showing which services are up on the system info screen), not for validating package installs.

```python
# packages/health.py (simplified)

def service_status(name: str) -> str:
    """Returns 'active', 'failed', 'inactive', etc."""
    result = subprocess.run(["systemctl", "is-active", name], capture_output=True, text=True)
    return result.stdout.strip()

def service_journal(name: str, lines: int = 10) -> str:
    """Returns recent journal lines for a service."""
    result = subprocess.run(["journalctl", "-u", name, "-n", str(lines), "--no-pager"], ...)
    return result.stdout.strip()
```

The `UpdatesScreen` progress flow becomes:
1. Download packages → show "Downloading..."
2. Install packages → show "Installing..."
3. Stamp → show "Saving snapshot..."
4. Done. Show "Update complete. Press Resume to restart."

No health check step. The user resumes pi-stomp, and pi-stomp itself validates the stack.

---

## Phase 5: Crash diagnostics — know what failed

**Goal:** When recovery starts due to a crash loop, show which service failed and why.

### Current crash detection:

```python
# service.py
def get_boot_mode() -> BootMode:
    result = subprocess.run(["systemctl", "is-failed", "mod-ala-pi-stomp"], ...)
    if result.stdout.strip() == "failed":
        return BootMode.CRASH_RECOVERY
    return BootMode.USER_RECOVERY
```

This only checks if pi-stomp failed. It doesn't say *why* or whether the dependency chain is broken.

### New crash diagnostics:

```python
# service.py

@dataclass
class CrashInfo:
    boot_mode: BootMode
    failed_service: str | None   # which service in the chain failed
    crash_log: str               # last journal lines of the failed service
    service_states: dict[str, str]  # {"jack": "active", "mod-host": "failed", ...}

def diagnose_crash() -> CrashInfo:
    """Determine why recovery was triggered."""
    # Check each service in the dependency chain
    chain = ["jack", "mod-host", "mod-ui", "mod-ala-pi-stomp"]
    states = {}
    failed_service = None
    for svc in chain:
        states[svc] = service_status(svc)
        if states[svc] == "failed" and failed_service is None:
            failed_service = svc

    # Get crash log from the failed service
    crash_log = ""
    if failed_service:
        crash_log = service_journal(failed_service, lines=10)

    boot_mode = BootMode.CRASH_RECOVERY if failed_service else BootMode.USER_RECOVERY
    return CrashInfo(boot_mode=boot_mode, failed_service=failed_service,
                     crash_log=crash_log, service_states=states)
```

### CrashScreen shows which service failed:

Instead of "App Crashed" with generic journal lines, the crash screen shows:

```
  jack: active
  mod-host: failed ←
  mod-ui: inactive
  pi-stomp: inactive

  [crash log lines]
  
  Resume    Recovery Menu
```

The user can immediately see "mod-host crashed" rather than just "something broke." This is the key structural improvement for knowing what failed.

### System info screen also gets service states:

```python
def get_system_info() -> dict[str, str]:
    info = {}
    info["kernel"] = ...
    info["uptime"] = ...
    info["temp"] = ...
    for svc in PISTOMP_SERVICES:
        info[svc] = service_status(svc)
    return info
```

---

## Phase 6: Wire up pi-stomp stamping

**Goal:** Make pi-stomp call `pistomp-stamp` after successful pedalboard load, so stamps represent actual known-good state.

### Current state:

pi-stomp does not call `pistomp-stamp` anywhere. The `/run/pistomp-healthy` stamp file is checked by `health.py` but never written by pi-stomp. The `pistomp-stamp` CLI exists but is unwired.

### New stamp protocol:

1. **pi-stomp calls `pistomp-stamp` after successful pedalboard load.** This is the only thing that should trigger a stamp, because pi-stomp running means the full stack (JACK → mod-host → mod-ui → pi-stomp) is healthy.

2. **pi-stomp writes `/run/pistomp-healthy` on startup.** This is the existing health stamp that recovery's (now-removed) health check was looking for. pi-stomp should write this file once it's fully initialized and handling requests.

3. **The `pistomp-stamp` CLI stays** but is simplified to just two operations:
   - `pistomp-stamp stamp` — writes current package versions to the stamp file, creates a git tag in the pedalboards repo for the current state.
   - `pistomp-stamp status` — shows dirty state (for debugging).

4. **Remove per-facet stamping.** The `pistomp-stamp -f config` and `pistomp-stamp -f system` subcommands are removed. Config and system don't need git tags — they get reset from factory files, not rolled back to stamps.

### pi-stomp integration (in ../pi-stomp):

In the pedalboard load handler (e.g., `modhandler.pedalboard_change()` or `mod.pedalboard_change()`), after a successful load:

```python
subprocess.run(["pistomp-stamp", "stamp"], check=False)
```

And during pi-stomp startup, after the event loop is running and pedalboards are loaded:

```python
Path("/run/pistomp-healthy").touch()
```

This requires adding `pistomp-stamp` as a dependency in pi-stomp's PKGBUILD, or just ensuring it's on the PATH.

### Impact on recovery:

With pi-stomp doing the stamping, recovery's role is purely:
- Show what changed since the last stamp
- Offer rollback to last stamp or factory
- Install updates
- Resume pi-stomp (which validates health by existing)

---

## Phase 7: Update the stamp CLI

**Goal:** Simplify `stamp.py` to match the new model.

### Current `stamp.py`:
- `pistomp-stamp stamp` — stamps all facets or a specific facet
- `pistomp-stamp snapshot` — commits without tagging
- `pistomp-stamp status` — shows dirty state

### New `stamp.py`:

```python
# stamp.py (simplified)

def cmd_stamp(args):
    """Stamp current state as known-good."""
    # Pedalboards: git add + commit + tag
    init_pedalboards(PEDALBOARDS_DIR)
    stamp_pedalboard_repo(PEDALBOARDS_DIR)
    # Packages: write current versions to stamp file
    stamp_packages()

def cmd_status(args):
    """Show dirty state."""
    # Pedalboards: git status --short
    # Packages: compare installed vs stamped versions
```

Remove `--facet` flag, `snapshot` subcommand, and per-facet dispatch. The stamp is always holistic: "the system was working when this stamp was made."

---

## File map after refactor

```
src/pistomp_recovery/
├── __main__.py          — Entry point, main loop (dirty flag, navigation, screen routing)
├── constants.py         — Paths, package list, PACKAGE_SERVICES map, LCD dims
├── util.py              — human_time() relative timestamp utility
├── stamp.py             — CLI: pistomp-stamp (stamp, status)
├── service.py           — systemd: boot mode, crash diagnostics, start/stop
├── git_util.py          — Git operations (unchanged, used by pedalboards.py)
├── pygame_init.py       — Idempotent pygame init (unchanged)
├── items.py             — Item and Action dataclasses
├── pedalboards.py       — Pedalboard operations (init, list_items, stamp, rollback, factory_reset)
├── packages.py          — Package operations (list_items, stamp, rollback, install, check_updates)
├── config.py            — Config reset (copy factory files)
├── system.py            — System reset (copy factory files)
├── hardware/
│   ├── encoder.py       — Rotary encoder GPIO input (unchanged)
│   └── lcd.py           — SPI ILI9341 driver (unchanged)
├── packages/
│   ├── installer.py     — Pacman wrappers (download, install, rollback from cache)
│   └── health.py        — Service status checks (simplified, no full_health_check)
├── emulator/
│   ├── bootstrap.py     — Emulator app (updated for new screens)
│   ├── controls.py      — FakeEncoder (unchanged)
│   ├── lcd_pygame.py    — Pygame LCD (unchanged)
│   └── window.py        — Emulator window (unchanged)
└── ui/
    ├── display.py        — Pygame surface ↔ SPI LCD bridge (add dirty-aware update)
    ├── colors.py         — Color constants (unchanged)
    ├── fonts/
    │   ├── __init__.py   — SafeFont, get_font() (unchanged)
    │   ├── DejaVuSans.ttf
    │   └── DejaVuSans-Bold.ttf
    ├── input.py          — Encoder + switch → InputEvent (unchanged)
    ├── screens/
    │   ├── __init__.py   — Screen base class (simplified)
    │   ├── menu_screen.py — Generic menu screen (LIST, DETAIL, CONFIRM, PROGRESS states)
    │   ├── crash.py       — Crash screen with service diagnostics
    │   ├── system_info.py — System info (unchanged structure)
    │   └── status.py      — Progress bar + status for update operations
    └── widgets/
        ├── misc.py        — Box, InputEvent (no Widget base class)
        ├── paint.py        — PaintContext (simplified, no Container integration)
        ├── menu.py         — Menu (standalone, no Container inheritance)
        ├── confirm_dialog.py — ConfirmDialog (standalone)
        └── text.py         — ProgressBar, StatusLine (standalone, no Widget inheritance)
```

**Deleted files:**
- `facets/base.py`
- `facets/config_facet.py`
- `facets/pedalboards_facet.py`
- `facets/packages_facet.py`
- `facets/system_facet.py`
- `ui/widgets/widget.py`
- `ui/widgets/container.py`
- `ui/widgets/panel.py`
- `ui/widgets/panel_stack.py`
- `ui/screens/main_menu.py` (replaced by `menu_screen.py` construction)
- `ui/screens/pedalboards_screen.py`
- `ui/screens/packages_screen.py`
- `ui/screens/reset_screen.py`
- `ui/screens/updates.py` (replaced by `menu_screen.py` with PROGRESS state)
- `packages/manager.py` (replaced by `packages/installer.py`)

---

## Estimated line counts

| Component | Before | After |
|---|---|---|
| Facets + git_util + stamp | ~750 | ~250 (pedalboards.py + packages.py + git_util.py + stamp.py) |
| Widget hierarchy | ~250 | ~0 (deleted) |
| Screens (pedalboards, packages, reset, updates, crash, main_menu) | ~650 | ~200 (menu_screen.py + crash.py + system_info.py) |
| Menu + confirm | ~200 | ~150 (simplified, standalone) |
| Health + manager | ~250 | ~50 (health.py simplified + installer.py) |
| Service + constants | ~120 | ~120 |
| __main__ | ~470 | ~300 |
| Other (colors, fonts, display, hardware, emulator) | ~350 | ~350 |
| **Total** | **~4,300** | **~1,420** |

---

## Implementation order

1. **Phase 1** — Flatten UI, add dirty flag. This is mechanical and testable via snapshot tests.
2. **Phase 2** — Generic `MenuScreen`. Requires Phase 1 first (standalone widgets). Testable via emulator.
3. **Phase 3** — Replace facets with functions. Can be done in parallel with Phase 2 since the UI only cares about `Item` objects.
4. **Phase 4** — Simplify package manager and health check. Depends on Phase 3.
5. **Phase 5** — Crash diagnostics. Independent, can be done anytime.
6. **Phase 6** — Wire up pi-stomp stamping. Requires changes in ../pi-stomp, can be done last.
7. **Phase 7** — Simplify stamp CLI. Depends on Phase 3 and Phase 6.

Phases 1-3 are the core refactor. Phases 4-5 are improvements. Phases 6-7 are cross-project integration.

---

## Open questions

1. **Should `pistomp-stamp` stamp everything at once, or should pedalboard stamps be per-pedalboard?** The current design stamps individual pedalboards when they're loaded. If pi-stomp calls `pistomp-stamp` after every pedalboard load, it stamps the pedalboards repo (tagging the current state of all pedalboards, not just the loaded one). Per-pedalboard tags are useful for "rollback just this pedalboard to its last-known-good." Recommendation: keep per-pedalboard stamping in `pistomp-stamp` but have pi-stomp call `pistomp-stamp stamp -f pedalboards -i {pedalboard_name}` after a successful load.

2. **Should the package stamp file be per-package or monolithic?** Current: monolithic (`packages.stamp` is a dict of all tracked package versions). This is fine — when pi-stomp stamps, it records all package versions as a snapshot of the full system state. No need for per-package timestamps.

3. **Config and system keep git repos with factory/device branches and stamping.** The original design was right — git provides rollback-to-stamp and rollback-to-factory for these files, which `cp -a` from factory doesn't (you lose the "undo my last config change" use case). Config and system each get a git repo with a `factory` branch (image-shipped state) and a `device` branch (working state). Stamps are git tags. `pistomp-stamp` commits and tags the current state on the `device` branch. Rollback to stamp = `git checkout {tag} -- .`. Rollback to factory = `git checkout factory -- .`.

4. **Factory state for pedalboards, config, and system is set up at image build time.** pistomp-arch needs a new build phase (e.g., `NN-recovery.sh`) that initializes the git repos, commits factory state, creates `factory` branches, and creates the `device` branch. Currently this is done by `PedalboardsFacet.init()` on first boot, which means the factory state depends on runtime git operations. Moving this to image build time makes the factory state deterministic and removes the need for runtime init.

5. **No "Stamp" action in recovery menus.** Stamping is pi-stomp's job — it calls `pistomp-stamp` after a successful pedalboard load because only pi-stomp knows the system is working. Recovery menus show "Rollback to stamp" and "Rollback to factory" but not "Stamp."