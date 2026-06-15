# pi-stomp stamping integration (Phase 6)

**Status:** Not yet implemented. This document describes the changes needed in `../pi-stomp`.

## Changes required

### 1. `modalapi/mod.py` — call `pistomp-stamp` after successful pedalboard load

In `pedalboard_change()`, after the POST to `pedalboard/load_bundle/` succeeds and `set_current_pedalboard()` is called:

```python
import subprocess
subprocess.run(["pistomp-stamp", "stamp"], check=False)
```

This should be added around line 758 in `modalapi/mod.py`:

```python
# After set_current_pedalboard()
self.set_current_pedalboard(self.pedalboard_list[self.selected_pedalboard_index])
self.bot_encoder_mode = BotEncoderMode.DEFAULT
# NEW:
try:
    subprocess.run(["pistomp-stamp", "stamp"], check=False)
except Exception:
    logging.debug("pistomp-stamp failed", exc_info=True)
```

### 2. Write `/run/pistomp-healthy` on startup

In `modalapistomp.py` or the main app entry point, after the event loop is running and the first pedalboard is loaded:

```python
from pathlib import Path
Path("/run/pistomp-healthy").touch()
```

This tells recovery (and the old health check) that pi-stomp is fully initialized and handling requests.

### 3. Add `pistomp-recovery` as a dependency

In `pi-stomp`'s PKGBUILD, add `pistomp-recovery` to `depends` (or at least ensure `pistomp-stamp` is on `PATH`). Since `pistomp-recovery` is already installed on the image, this is just ensuring the dependency chain is explicit.

## Rationale

- Stamping is **pi-stomp's job** because only pi-stomp knows the system is working (JACK → mod-host → mod-ui → pi-stomp all up).
- Recovery should **not** stamp on the user's behalf — the whole point of a stamp is "I know this works."
- Recovery's role is purely rollback + install + resume. Health validation happens by pi-stomp successfully starting.
