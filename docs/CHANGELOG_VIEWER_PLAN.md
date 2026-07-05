# Plan: Changelog viewer on the pre-install screen

## Problem

When the user is about to install a package update, the pre-install
screen (`app.py:_show_package_detail`) currently shows:

1. A version line (`old → new`).
2. A `---` separator.
3. The package description (from `apt-cache show`).
4. A `---` separator.
5. The `Install` button.

There is no way to see *what's in the update* before committing. The
crash screen has a nice pattern for the journal — a 6-line textarea on
the screen with a click-through to a fullscreen `LogViewScreen` for
the last 100 lines. We want the same affordance for changelogs.

## Constraints

- **No `.deb` pre-download.** Downloading the new version's `.deb` just
  to read the changelog, then downloading it again as part of the
  install, wastes 22+ MB on a 3G/satellite link. Users will not expect
  a silent download before they click Install.
- **No fallbacks.** If we can't get a changelog, show "No changelog
  available." — not a degraded description or an empty screen. The
  change to the install flow should be invisible to users when the
  source is unavailable.
- **One way of doing things.** If `apt-get changelog` works against
  the repo, the recovery service calls it and that's it. No custom
  pool-URL fetcher, no `.deb`-inspector, no per-package special case.
- The UI change lives in `pistomp-recovery`. The plumbing change to
  make `apt-get changelog` actually work lives in `pi-gen-pistomp`.

## Why the current state doesn't work

`apt-get changelog <pkg>` on a Debian system constructs a URL based on
the package's `Source:`/`Version:` and downloads a `.changes` file from
the repository, then concatenates the result with the installed
package's local `changelog.Debian.gz`.

The pi-stomp OTA repo at `https://sastraxi.github.io/pi-gen-pistomp/`
is built with `reprepro` using `reprepro includedeb`, which copies a
`.deb` into `pool/` and updates `dists/trixie/main/binary-arm64/Packages`
— but never publishes the corresponding `.changes` file. The repo is
also configured with `[trusted=yes]` on the client side, which is
incompatible with the `Acquire::Changelogs` URL pattern that assumes
the repo can be authenticated.

Empirically on a real device running `apt-get changelog` (apt 3.0.3):

- **`pistomp-recovery`**: works, but only because apt falls back to
  `store:///usr/share/doc/pistomp-recovery/changelog.Debian.gz` (the
  installed `.deb`'s bundled changelog). The user sees the *installed*
  version's changelog, not the *new* version's. Worthless for the
  stated use case.
- **`lcd-splash`**: "Changelog unavailable" — its `.deb` was built
  with `dpkg-deb --build`, not `dpkg-buildpackage`, so there's no
  `changelog.Debian.gz` to fall back to.
- **`cabsim-lv2` (installed `1.1.1-4`, candidate `1.1.1-5`)**:
  "Changelog unavailable" — the new version's `.changes` is not in
  `pool/`, only the old version's `changelog.Debian.gz` is on disk,
  and apt's "installed == candidate" check decides not to read the
  local file because there *is* a candidate.

So the headline finding is: the feature is half-built today. We need
to finish it on both sides.

## Approach

Sign the reprepro repo with a project-owned GPG key, switch the
publish step from `reprepro includedeb` to `reprepro include` (which
also publishes the `.changes` file at the canonical `pool/` URL), and
migrate the apt source line from `[trusted=yes]` to
`[signed-by=…]`. This is exactly the "GPG signing (future)" plan
already documented at `pi-gen-pistomp/docs/OTA.md:149-156` — we just
need to execute it.

The recovery service then makes a one-line change: `apt-cache show`
→ `apt-get changelog`. No new dependencies, no new backends, no
fallback paths.

The two `dpkg-deb --build` packages (`lcd-splash`,
`libfluidsynth2-compat`) need to be migrated to `dpkg-buildpackage` so
they emit `.changes` files. The 17 already-`dpkg-buildpackage`
packages are already producing `.changes` files at build time —
they're just being thrown away. We need to preserve and upload them.

## UI shape (pistomp-recovery)

After all changes, the pre-install screen looks like:

```
┌────────────────────────────────────┐  ← header: "pi-stomp", ← Back
│ 3.0-16 → 3.0-17                    │  ← version line
│ ---                                │  ← separator
│  * The thing this update does.     │  ← description (capped at 6 lines)
│  * Another thing.                  │
│  * A third.                        │
│  ...                               │  ← ellipsis if truncated
│ ---                                │  ← separator
│ Install | Changelog                │  ← actions row
└────────────────────────────────────┘
```

- The first `---` separator (currently between the version line and
  the description) is **removed**. There's nothing above it to divide
  from — the version line is the title-ish row, and an immediate `---`
  makes the description look orphaned.
- `Changelog` is a new target on the same row as `Install`, separated
  by ` | `. It is **disabled** when the backend returned no
  changelog lines.
- Clicking `Changelog` pushes a `LogViewScreen` titled "Changelog"
  with the new entries.
- The description is capped at 6 lines (matching the crash log
  textarea's 6-line height). If the description is longer, the
  truncated last visible line is replaced with `...` and the rest is
  available in a future "Description" viewer if we ever add one (not
  in scope for this plan).

The `LogViewScreen` header title is parameterized from "Crash Log"
(default) to "Changelog" (new) so the same widget is reused.

---

# pi-gen-pistomp changes

## 1. Generate the GPG key (one-time, human-driven)

**On a secure machine:**

```bash
gpg --batch --quick-generate-key \
    "pi-Stomp Archive <pistomp-archive@noreply.github.com>" \
    ed25519 default 0
gpg --armor --output pistomp-archive-keyring.gpg --export <KEYID>
gpg --armor --output pistomp-archive-secret.asc \
    --export-secret-keys <KEYID>
```

**Storage:**

- Commit `pistomp-archive-keyring.gpg` to the repo at
  `stage2/05-pistomp/files/pistomp-archive-keyring.gpg` (matches the
  pattern of `stage0/00-configure-apt/files/raspberrypi-archive-keyring.pgp`).
- Store `pistomp-archive-secret.asc` as a GitHub Actions secret named
  `PISTOMP_APT_SIGNING_KEY` at the organization or repo level,
  whichever the runner can read.

**Note on key rotation:** A future rotation should publish a
*transition* keyring (containing both old and new public keys) as a
one-off `.deb` whose `postinst` replaces the existing keyring; the
old key can be revoked one release window later. The small scale of
this project probably doesn't justify the formal procedure — treat the
key as evergreen, document the revocation procedure, rotate manually
if the key is ever compromised.

## 2. `stage2/00-dummy-packages/01-run.sh` — switch the apt source to `signed-by=`

**File:** `stage2/00-dummy-packages/01-run.sh:15,22`

**Change** line 15 (primary repo):

```diff
-echo "deb [arch=${APT_REPO_ARCH} trusted=yes] ${APT_REPO_URL} ${APT_REPO_SUITE} ${APT_REPO_COMPONENT}" \
+echo "deb [arch=${APT_REPO_ARCH} signed-by=/usr/share/keyrings/pistomp-archive-keyring.gpg] ${APT_REPO_URL} ${APT_REPO_SUITE} ${APT_REPO_COMPONENT}" \
     > /etc/apt/sources.list.d/pistomp.list
```

**Leave line 22 unchanged.** The local override at
`file:/pistomp-cache/apt-repo` is a `file://` source only reachable
from inside the build chroot; it doesn't need signing. Its
`trusted=yes` is appropriate for the build-time local mount.

The cleanup step in `stage2/05-pistomp/05-run.sh` only removes
`pistomp-local.list` and the bind-mount — it does not touch
`pistomp.list` content, so no change there.

## 3. `stage2/05-pistomp/01-run.sh` — install the keyring

**File:** `stage2/05-pistomp/01-run.sh`

**Add** a single `install` line near the top, before the service-file
copies:

```bash
# Public key for the pi-stomp OTA apt repo. Pairs with [signed-by=...] in pistomp.list.
install -m 644 files/pistomp-archive-keyring.gpg \
    ${ROOTFS_DIR}/usr/share/keyrings/pistomp-archive-keyring.gpg
```

No `apt-key add` is needed (deprecated since apt 2.4). The
`[signed-by=…]` source-line argument references the keyring path
directly.

## 4. `scripts/setup-apt-repo.sh` — sign the local override too (for dev parity)

**File:** `scripts/setup-apt-repo.sh:33-42`

The hand-rolled `Release` file should be GPG-signed so that the local
override behaves identically to the production repo (and so
`apt-get changelog` works against the local override during image
builds and local package development).

**Option A (preferred):** replace the `dpkg-scanpackages` body with
a `reprepro` invocation that uses the same `conf/distributions` as
production. The `conf/distributions` is currently templated in
`publish-apt-repo.yml:37-45`; lift it into a real `conf/distributions`
file and use it in both places. This unifies the dev override and
production publish.

**Option B (minimal change):** keep `dpkg-scanpackages` and add a
gpg-sign step at the end of `setup-apt-repo.sh`:

```bash
gpg --batch --yes --default-key "${PISTOMP_APT_KEYID:-$(gpg --list-secret-keys --with-colons | awk -F: '/^sec/ {print $5; exit}')}" \
    --detach-sign --armor \
    --output "${REPO_DIR}/dists/${APT_REPO_SUITE}/Release.gpg" \
    "${REPO_DIR}/dists/${APT_REPO_SUITE}/Release"
gpg --batch --yes --default-key "${PISTOMP_APT_KEYID:-...}" \
    --clearsign --output "${REPO_DIR}/dists/${APT_REPO_SUITE}/InRelease" \
    "${REPO_DIR}/dists/${APT_REPO_SUITE}/Release"
```

The `pistomp-local.list` source line stays `[trusted=yes]` (file://
mount, no auth needed).

## 5. `conf/distributions` — add `SignWith:`

**File:** currently templated in `.github/workflows/publish-apt-repo.yml:37-45`

**Change:** add `SignWith: yes` to the printf'd `conf/distributions`:

```diff
           printf '%s\n' \
             "Origin: pistomp" \
             "Label: pistomp" \
             "Suite: trixie" \
             "Codename: trixie" \
             "Architectures: arm64" \
             "Components: main" \
             "Description: pi-Stomp custom packages" \
+            "SignWith: yes" \
             > conf/distributions
```

`SignWith: yes` means "use the gpg default key in the runner's
keyring," which is what the import step (next section) sets up. Pin
a specific keyid with `SignWith: ABCDEF…` if you want the keyid
visible in the workflow definition (not necessary — the secret
controls the key, not the workflow).

## 6. `.github/workflows/publish-apt-repo.yml` — key import + `include` instead of `includedeb`

**Three changes to the file:**

### (a) Add a "Import signing key" step before "Add packages to repo"

```yaml
      - name: Import signing key
        env:
          PISTOMP_APT_SIGNING_KEY: ${{ secrets.PISTOMP_APT_SIGNING_KEY }}
        run: |
          set -euo pipefail
          GNUPGHOME="$(mktemp -d)"
          export GNUPGHOME
          echo "${PISTOMP_APT_SIGNING_KEY}" | gpg --batch --import
          # Pass GNUPGHOME to subsequent steps so reprepro picks it up.
          echo "GNUPGHOME=${GNUPGHOME}" >> "${GITHUB_ENV}"
```

The keyring lives in a `mktemp -d` so the secret is never persisted
to the runner filesystem.

### (b) Bump the install step to also install `gnupg`

**File:** `.github/workflows/publish-apt-repo.yml:52-53`

```diff
       - name: Install reprepro + gnupg
-        run: sudo apt-get update -qq && sudo apt-get install -y -qq reprepro
+        run: sudo apt-get update -qq && sudo apt-get install -y -qq reprepro gnupg
```

### (c) Switch `includedeb` to `include`

**File:** `.github/workflows/publish-apt-repo.yml:76-84`

`reprepro include` consumes a `.changes` file (verifying the embedded
`.deb` SHA256 matches the actual `.deb`), then places the `.changes`
at the canonical `pool/<component>/<first-letter>/<source>/<source>_<source-version>_<arch>.changes`
URL — which is exactly the URL `apt-get changelog` constructs.

```yaml
      - name: Add packages to repo (refuses duplicate name+version)
        working-directory: repo
        run: |
          shopt -s nullglob
          # Use `reprepro include` (not `includedeb`) so the .changes file is
          # also placed under pool/ at the canonical URL apt-get changelog
          # constructs: pool/<component>/<first-letter>/<source>/<source>_<source-version>_<arch>.changes
          for changes in incoming/*.changes; do
            deb="${changes%.changes}.deb"
            [ -f "$deb" ] || { echo "::warning::no .deb for $changes"; continue; }
            reprepro -b . include trixie "$changes" || {
              echo "::warning::reprepro refused $changes (duplicate name+version, or missing Section/Priority in debian/control)."
            }
          done
```

The previous `includedeb` flow is removed. If a package's build
process doesn't produce a `.changes` file (only true for the two
`dpkg-deb --build` packages before they're migrated — see §9 and
§10), the publish step will warn and skip it. Once §9 and §10 land,
every package has a `.changes` and the loop covers them all.

## 7. `scripts/build-common.sh` — also move `.changes` files into the cache

**File:** `scripts/build-common.sh:26-29` (`move_to_cache`)

`dpkg-buildpackage` writes the `.deb` *and* the `.changes` file in
the source tree's parent directory. Currently only the `.deb` is
moved into `CACHE_DIR`; the `.changes` is left behind and lost.

```diff
 move_to_cache() {
     local search_dir="${1:-$(dirname "${UPSTREAM_DIR}")}"
     find "${search_dir}" -maxdepth 1 -name "${PKG}_*.deb" -exec mv {} "${CACHE_DIR}/" \;
+    # dpkg-buildpackage also emits a .changes file in the source's parent dir.
+    # Publish it too so reprepro `include` (not just `includedeb`) can ingest
+    # the upload and place the .changes in pool/ — that's the file apt-get
+    # changelog fetches.
+    find "${search_dir}" -maxdepth 1 -name "${PKG}_*.changes" -exec mv {} "${CACHE_DIR}/" \;
+    find "${search_dir}" -maxdepth 1 -name "${PKG}_*.buildinfo" -exec mv {} "${CACHE_DIR}/" \; 2>/dev/null || true
     echo "==> Built ${PKG} → ${CACHE_DIR}"
 }
```

The `.buildinfo` is part of the same upload bundle; harmless to
preserve.

## 8. `.github/workflows/build-deb.yml` — upload the `.changes` as a release asset

**File:** `.github/workflows/build-deb.yml:171-202` ("Assemble
release assets" step)

Add the `.changes` (and `.buildinfo`) to the release's `files` list,
alongside the `.deb` and `.built-sha`:

```diff
           files="$deb"
           sidecar="$CACHE/${PKG}.built-sha"
           if [ -f "$sidecar" ]; then
             echo "sidecar present: $sidecar"
             files="${files}"$'\n'"${sidecar}"
           else
             echo "no .built-sha sidecar for ${PKG} (not git-backed) — skipping"
           fi
+          # The .changes file is what reprepro `include` consumes to publish a
+          # changelog endpoint. Upload it alongside the .deb.
+          changes=$(ls "$CACHE/${PKG}_"*"_arm64.changes" 2>/dev/null | head -1)
+          if [ -n "$changes" ]; then
+            echo "changes present: $changes"
+            files="${files}"$'\n'"${changes}"
+          else
+            echo "::warning::no .changes for ${PKG} (binary-only build?) — apt-get changelog will be unavailable for this package"
+          fi
+          buildinfo=$(ls "$CACHE/${PKG}_"*"_arm64.buildinfo" 2>/dev/null | head -1)
+          if [ -n "$buildinfo" ]; then
+            echo "buildinfo present: $buildinfo"
+            files="${files}"$'\n'"${buildinfo}"
+          fi
```

The warning is a CI signal for the two `dpkg-deb --build` packages —
once they're migrated (§9, §10), the warning disappears.

## 9. Migrate `lcd-splash` to `dpkg-buildpackage`

**Files to change:** `debpkgs/lcd-splash/build.sh` and
`debpkgs/lcd-splash/debian/`.

The package's `debian/changelog` already exists. The `debian/control`
file needs a `Source:` stanza added and `Build-Depends:` moved to
the source stanza. A new `debian/rules` replaces the inline `gcc`
invocation.

**`debpkgs/lcd-splash/debian/control` (rewrite):**

```
Source: lcd-splash
Section: misc
Priority: optional
Maintainer: pistomp <pistomp@example.com>
Build-Depends: debhelper-compat (= 13), lg-pistomp
Standards-Version: 4.6.2

Package: lcd-splash
Architecture: arm64
Depends: lg-pistomp
Description: Fast ILI9341 LCD boot splash for pi-Stomp
 Drives the 320x240 SPI LCD directly (spidev + lgpio) with no
 Python/interpreter overhead. Displays a pre-converted RGB565 image
 with optional text overlay.
```

(Keep the `Build-Depends: lg-pistomp` even though it duplicates the
Depends — the Source stanza is for build-time, the binary stanza is
for runtime. `dpkg-buildpackage` enforces the source stanza at build
time; `lg-pistomp` is already in `CACHE_DIR` by the time this runs.)

**`debpkgs/lcd-splash/debian/rules` (new file, mode 0755):**

```makefile
#!/usr/bin/make -f
export DH_VERBOSE=1

PKG = lcd-splash
SRC_DIR = $(CURDIR)/src
LG_EXTRACT = /tmp/lg-pistomp-extract

%:
	dh $@

override_dh_auto_configure:
	# Generate font.h from Terminus Bold 22px console font.
	# Same apt-cache + wget + dpkg-deb dance as the old build.sh, but
	# without a postinst TTY requirement.
	FONT=/usr/share/consolefonts/Lat15-TerminusBold22x11.psf.gz
	if [ ! -f "$$FONT" ]; then \
	    CSL_EXTRACT=/tmp/console-setup-linux-extract; \
	    mkdir -p "$$CSL_EXTRACT"; \
	    CSL_URL=$$(apt-cache show console-setup-linux \
	        | awk '/^Filename:/ { print "http://deb.debian.org/debian/" $$2; exit }'); \
	    wget -nv -O /tmp/console-setup-linux.deb "$$CSL_URL"; \
	    dpkg-deb -x /tmp/console-setup-linux.deb "$$CSL_EXTRACT"; \
	    FONT="$$CSL_EXTRACT/usr/share/consolefonts/Lat15-TerminusBold22x11.psf.gz"; \
	fi
	python3 $(SRC_DIR)/gen-font-h.py "$$FONT" > $(SRC_DIR)/font.h
	# Extract lg-pistomp headers/library. The .deb is in CACHE_DIR because
	# build-deb.yml installs it as a build dep before build.sh runs.
	mkdir -p $(LG_EXTRACT)
	dpkg-deb -x $(CACHE_DIR)/lg-pistomp_*_arm64.deb $(LG_EXTRACT)

override_dh_auto_build:
	gcc -O2 -Wall -Wextra \
	    -I$(LG_EXTRACT)/usr/include \
	    -L$(LG_EXTRACT)/usr/lib \
	    -o $(SRC_DIR)/lcd-splash $(SRC_DIR)/lcd-splash.c \
	    -I$(SRC_DIR) \
	    -llgpio

override_dh_auto_install:
	# Place the compiled binary, the RGB565 splash image, and DEBIAN/md5sums.
	install -Dm 755 $(SRC_DIR)/lcd-splash \
	    debian/$(PKG)/usr/bin/lcd-splash
	install -Dm 644 $(ROOT_DIR)/stage2/05-pistomp/files/splash.rgb565 \
	    debian/$(PKG)/usr/share/pistomp/splash.rgb565
	# Generate md5sums so dpkg --verify can detect post-install modifications.
	find debian/$(PKG) -type f ! -path '*/DEBIAN/*' -exec md5sum {} \; \
	    | sed 's|debian/$(PKG)/||' > debian/$(PKG)/DEBIAN/md5sums

override_dh_dwz:
	# No DWARF in this binary
```

**`debpkgs/lcd-splash/build.sh` (rewrite):**

```bash
#!/bin/bash
# Build lcd-splash .deb for arm64 Debian Trixie — builds from C source.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
source "${ROOT_DIR}/scripts/build-common.sh"

PKG="lcd-splash"
UPSTREAM_DIR="${WORKDIR}/${PKG}-src"

cache_check

# The build actually runs out of debpkgs/lcd-splash (no upstream git clone);
# symlink so debian/rules can use the standard dh layout.
[ ! -d "${UPSTREAM_DIR}" ] && ln -s "${SCRIPT_DIR}" "${UPSTREAM_DIR}"

cd "${UPSTREAM_DIR}"
dpkg-buildpackage -b -us -uc
move_to_cache
```

The symlink approach is cleaner than restructuring; the existing
`src/` directory lives alongside `debian/`, which is the standard
`dpkg-buildpackage` source layout.

**`debian/source/format`** (new file, mode 0644): `3.0 (native)` —
lcd-splash doesn't have an upstream tarball; it's a native package
whose source is the git tree itself.

**After this lands**, the build produces
`debpkgs/lcd-splash/../lcd-splash_<version>_arm64.deb` and
`lcd-splash_<version>_arm64.changes` (and `.buildinfo`). `move_to_cache`
(after §7) carries both into `CACHE_DIR`, and `build-deb.yml` (after
§8) uploads the `.changes` as a release asset. The next publish run
ingests it via `reprepro include` and `apt-get changelog lcd-splash`
works.

## 10. Migrate `libfluidsynth2-compat` to `dpkg-buildpackage`

**Files to change:** `debpkgs/libfluidsynth2-compat/build.sh` and
`debpkgs/libfluidsynth2-compat/debian/`.

`libfluidsynth2-compat` is simpler — it's a symlink shim with no
compilation. The only thing in the `.deb` is the `postinst` that
creates the symlink, plus the control file. Migration is mostly
cosmetic.

**`debpkgs/libfluidsynth2-compat/debian/control` (rewrite):**

```
Source: libfluidsynth2-compat
Section: libs
Priority: optional
Maintainer: pistomp <pistomp@example.com>
Build-Depends: debhelper-compat (= 13)
Standards-Version: 4.6.2

Package: libfluidsynth2-compat
Architecture: arm64
Depends: fluidsynth-headless
Description: FluidSynth .so.2 compatibility shim for prebuilt LV2 plugins
 Creates a libfluidsynth.so.2 symlink pointing to the real .so.3 library
 (shipped by fluidsynth-headless) so that prebuilt LV2 plugins compiled
 against libfluidsynth.so.2 can load on Trixie.
```

**`debpkgs/libfluidsynth2-compat/debian/rules` (new file, mode 0755):**

```makefile
#!/usr/bin/make -f
%:
	dh $@

override_dh_auto_configure:
	true

override_dh_auto_build:
	true

override_dh_auto_install:
	true

override_dh_dwz:
	# No DWARF
```

**`debian/source/format`** (new file, mode 0644): `3.0 (native)`.

The existing `debian/postinst` (the symlink-creator) is left
unchanged; `dh` will install it automatically as the binary's
`postinst`.

**`debpkgs/libfluidsynth2-compat/build.sh` (rewrite):**

```bash
#!/bin/bash
# Build libfluidsynth2-compat .deb — symlink shim, no compilation.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
source "${ROOT_DIR}/scripts/build-common.sh"

PKG="libfluidsynth2-compat"
UPSTREAM_DIR="${WORKDIR}/${PKG}-src"

cache_check

# Same symlink trick as lcd-splash — dpkg-buildpackage wants a source tree
# layout, and our source *is* debpkgs/libfluidsynth2-compat.
[ ! -d "${UPSTREAM_DIR}" ] && ln -s "${SCRIPT_DIR}" "${UPSTREAM_DIR}"

cd "${UPSTREAM_DIR}"
dpkg-buildpackage -b -us -uc
move_to_cache
```

## 11. `docs/OTA.md` — rewrite the "GPG signing (future)" section

**File:** `docs/OTA.md:149-156`

The "future" is now. Replace that section with:

```markdown
## GPG signing

The repo is signed with a project-owned GPG key (not `trusted=yes`).
The public half is shipped on the image at
`/usr/share/keyrings/pistomp-archive-keyring.gpg`; the source line at
`/etc/apt/sources.list.d/pistomp.list` uses `signed-by=…` to enforce
it. The private half is the `PISTOMP_APT_SIGNING_KEY` GitHub Actions
secret, imported into a throwaway `GNUPGHOME` by `publish-apt-repo.yml`
before reprepro runs.

`SignWith: yes` in `conf/distributions` tells reprepro to sign
`dists/trixie/Release` and write `dists/trixie/InRelease` (clearsigned)
and `dists/trixie/Release.gpg` (detached). The publish step also uses
`reprepro include` (not `includedeb`) so the `.changes` file is placed
at the canonical `pool/` URL — that's the file `apt-get changelog
<pkg>` fetches.

### Rotating the signing key

1. Generate a new key. Publish a transition keyring .deb (containing
   both old and new public keys) to the same repo; its `postinst`
   replaces `/usr/share/keyrings/pistomp-archive-keyring.gpg` with a
   file that includes both.
2. Update the `PISTOMP_APT_SIGNING_KEY` secret to contain *both* keys.
3. After one release window (when all devices have the transition
   keyring), generate a revocation certificate for the old key and
   republish the keyring .deb with only the new key.

For this project's scale, treat the key as evergreen and only
formally rotate if it's compromised.
```

## 12. `docs/OTA.md` — update the "Upgrading a pre-OTA device" snippet

**File:** `docs/OTA.md:131-147`

The snippet writes `[arch=arm64 trusted=yes]` to `pistomp.list`. After
this work ships, the snippet needs the keyring to be installed first
(so that `apt-get update` succeeds when it tries to verify the signed
`InRelease`).

```bash
ssh pistomp@pistomp.local
# Install the keyring (re-downloaded by the device's existing OTA machinery
# — see pi-gen-pistomp/docs/OTA.md "Rotating the signing key" for the
# initial keyring ship).
sudo apt-get update  # apt will fail to verify signed InRelease until
                     # the keyring is on the device; install it from the
                     # pre-built keyring .deb on the image.
echo "deb [arch=arm64 signed-by=/usr/share/keyrings/pistomp-archive-keyring.gpg] https://sastraxi.github.io/pi-gen-pistomp trixie main" \
  | sudo tee /etc/apt/sources.list.d/pistomp.list
sudo apt-get update
sudo apt-get install --only-upgrade pistomp-recovery
```

(The first `apt-get update` will fail until the keyring is on the
device — this is the migration story for pre-keying images. The
workaround is to ship a one-off `pistomp-archive-keyring` .deb that
has a `postinst` rewriting `pistomp.list`; this is the standard
Debian "archive keyring package" pattern, similar to
`apt.postgresql.org`. For pre-OTA devices, the keyring can be
extracted from a freshly-flashed image and scp'd in by hand.)

## 13. Cross-cutting concerns

**Existing deployed devices (pre-signed):** They will reject
`apt-get update` after the first signed release, because their
`pistomp.list` is `[trusted=yes]` but apt's behavior on a trusted
source is to skip *all* signature verification (per apt's docs), and
reprepro now writes a `Release.gpg` that is unverifiable-by-omission.
Actually, the `[trusted=yes]` flag still allows signature *errors* to
pass — that's its whole point. So existing devices will continue to
work; they just won't be verifying anything. The story for moving
them to `signed-by=…` is the `pistomp-archive-keyring` .deb shipped
in §12.

**Image build:** no change. `apt-get update` already runs after
writing `pistomp.list`; with the signed setup, it now actually
verifies. Behaviour is unchanged, security improves.

**Pre-migration of `lcd-splash` and `libfluidsynth2-compat`:** Until
§9 and §10 land, those two packages won't have a `.changes` file in
`pool/`, so `apt-get changelog` against them will continue to fail
with "Changelog unavailable." The pre-flight warning in
`publish-apt-repo.yml:80-83` (the `::warning::no .deb for $changes`
and `::warning::no .changes` lines) will surface this in CI until
the migration is complete. After both migrations land, the warnings
disappear for every package.

**Idempotency:** `SignWith: yes` is idempotent. `reprepro include`
with a duplicate `name+version` is a no-op (warning, not an error).
The `git add -A pool/ dists/ conf/` step already handles re-runs
correctly.

**Pool size:** Adding `.changes` files adds ~2-5 KB per package per
version. With 19 packages × ~2 versions per year, this is ~100 KB
over the lifetime of the repo. Not a concern.

---

# pistomp-recovery changes

## 14. `src/pistomp_recovery/items.py` — add `PackageDetail`

**New dataclass** to carry both the description and the changelog
from a single backend call:

```python
@dataclass(frozen=True)
class PackageDetail:
    """Pre-install detail for a single package.

    ``description`` is the multi-line package description (used as the
    scrolling body of the pre-install screen). ``changelog`` is the
    list of lines from the *new* version's changelog that are newer
    than the currently-installed version — empty when the backend
    has no changelog (e.g. pacman) or the new version's changelog
    could not be fetched.
    """

    description: tuple[str, ...]
    changelog: tuple[str, ...] = ()
```

`description` is a tuple (not a list) so the dataclass is hashable +
immutable like the other items in this file.

## 15. `src/pistomp_recovery/packages/manager.py` — `AptManager.package_detail` swaps `apt-cache show` for `apt-get changelog`

**File:** `src/pistomp_recovery/packages/manager.py:430-450`

Replace the existing method:

```python
    def package_detail(self, name: str) -> PackageDetail:
        # `apt-get changelog` fetches the new version's .changes file
        # from the repo and concatenates with
        # /usr/share/doc/<pkg>/changelog.Debian.gz from the installed
        # .deb. Requires the repo to be GPG-signed with `.changes`
        # files published in pool/ — see pi-gen-pistomp's
        # docs/OTA.md "GPG signing". Returns an empty PackageDetail
        # if apt can't fetch or parse the changelog; the UI shows
        # "No changelog available" in that case.
        result: subprocess.CompletedProcess[str] = subprocess.run(
            ["apt-get", "changelog", name],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            logger.debug("apt-get changelog %s failed: %s", name, result.stderr.strip())
            return PackageDetail(description=())

        # apt-get changelog output is RFC822-ish stanzas (newest first):
        #
        #   <package> (<version>) <suite>; urgency=<level>
        #
        #     * first changelog bullet
        #     * second changelog bullet
        #
        #    -- Maintainer <email>  Date
        #   <package> (<version>) <suite>; urgency=<level>
        #   ...
        #
        # Keep the stanzas as-is. The UI wraps to 38 cols and renders
        # the full text in a LogViewScreen.
        lines = [line for line in result.stdout.split("\n") if not line.startswith("Get:")]

        # Separate description from changelog. The description is the
        # contents of `apt-cache show <pkg> Description: ...` — fetched
        # separately, since apt-get changelog only produces changelog
        # text. Description fetches are local-only and don't need
        # network (apt-cache reads the .deb metadata cache).
        desc = self._apt_cache_description(name)
        return PackageDetail(description=desc, changelog=tuple(lines))

    def _apt_cache_description(self, name: str) -> tuple[str, ...]:
        result: subprocess.CompletedProcess[str] = subprocess.run(
            ["apt-cache", "show", "--no-all-versions", name],
            capture_output=True,
            text=True,
            check=False,
        )
        lines: list[str] = []
        in_desc = False
        for line in result.stdout.split("\n"):
            if line.startswith("Description"):
                in_desc = True
                short = line.split(":", 1)[1].strip()
                if short:
                    lines.append(short)
            elif in_desc:
                if not line.startswith(" "):
                    break
                stripped = line[1:]
                lines.append("" if stripped == "." else stripped)
        return tuple(lines)
```

Why this is the right shape: the description and the changelog are
fetched via two different apt commands (`apt-cache show` for
description, `apt-get changelog` for changelog). The pre-install
screen already handles them as separate visual elements (description
scrolls in the menu, changelog pushes a `LogViewScreen`), so a
`PackageDetail` with both is the natural shape. `description=()`
(empty tuple) is the "no description available" state, and
`changelog=()` is the "no changelog available" state — both safe
defaults that the UI handles.

`apt-get changelog` exit codes: returns 0 on success, 100 if the
package isn't known to apt, 1 if the changelog couldn't be fetched
(for any reason). The `returncode != 0` check covers all failure
modes; we log at debug level because the UI doesn't care *why* it
failed.

**Update the `PackageManager` protocol at the same location** to
reflect the new return type:

```python
    def package_detail(self, name: str) -> PackageDetail:
        """Return description and new-version changelog for a package.

        ``description`` is shown as the body of the pre-install screen
        (wrapped to 38 cols). ``changelog`` is shown when the user
        clicks the "Changelog" target on that screen; empty when the
        package manager has no changelog (e.g. pacman) or the new
        version's changelog could not be fetched.

        Runs on a background thread; no UI side effects.
        """
        ...
```

## 16. `src/pistomp_recovery/packages/manager.py` — `PacmanManager.package_detail` returns empty changelog

**File:** `src/pistomp_recovery/packages/manager.py:212-219`

Replace the existing method (the description part stays; add the new
return type):

```python
    def package_detail(self, name: str) -> PackageDetail:
        result: subprocess.CompletedProcess[str] = subprocess.run(
            ["pacman", "-Si", name], capture_output=True, text=True, check=False
        )
        for line in result.stdout.split("\n"):
            if line.startswith("Description"):
                return PackageDetail(description=(line.split(":", 1)[1].strip(),))
        return PackageDetail(description=())
```

Pacman has no Debian-style changelog concept; `changelog=()` is the
right answer and the UI will disable the Changelog target.

## 17. `src/pistomp_recovery/backends.py` — `DataBackend.package_detail` protocol

**File:** `src/pistomp_recovery/backends.py:126-132`

Update the protocol method's return type from `list[str]` to
`PackageDetail`:

```python
    def package_detail(self, name: str) -> PackageDetail:
        """Return description and new-version changelog for a package.

        ``description`` is the package's short description (used as the
        pre-install screen body). ``changelog`` is the new-version
        changelog; empty when the backend has no changelog or the
        new version's changelog could not be fetched.

        The description is rendered as plain text (the UI wraps to 38
        cols and caps at 6 lines). The changelog is opened in a
        fullscreen viewer when the user clicks the "Changelog" target.

        Called from a background thread; no UI side effects.
        """
        ...
```

Add the import at the top:

```python
from pistomp_recovery.items import Item, PackageDetail
```

## 18. `src/pistomp_recovery/backends_real.py` — `RealDataBackend.package_detail` returns `PackageDetail`

**File:** `src/pistomp_recovery/backends_real.py:151-152`

```python
    def package_detail(self, name: str) -> PackageDetail:
        return self._manager.package_detail(name)
```

No further change — the return type is now whatever
`self._manager.package_detail(name)` returns, which is `PackageDetail`.

## 19. `src/pistomp_recovery/emulator/backends.py` — `EmulatorDataBackend.package_detail` returns a sample `PackageDetail`

**File:** `src/pistomp_recovery/emulator/backends.py:314-321`

```python
    def package_detail(self, name: str) -> PackageDetail:
        return PackageDetail(
            description=(
                f"Custom pi-stomp package: {name}.",
                "",
                "Install this update to get the latest version.",
                "On the device, package details from apt-cache",
                "would appear here.",
            ),
            changelog=(
                f"{name} (1.0.0-1) trixie; urgency=medium",
                "",
                "  * Initial release.",
                "",
                " -- pi-gen-pistomp <noreply@github.com>  Mon, 01 Jan 2026 00:00:00 +0000",
            ),
        )
```

The sample changelog is the smallest valid RFC822 stanza so the
LogViewScreen renders it sensibly in the emulator.

## 20. `src/pistomp_recovery/ui/screens/log_view.py` — parameterize the title

**File:** `src/pistomp_recovery/ui/screens/log_view.py:17-37`

Add a `title: str = "Crash Log"` parameter to `__init__`, default
preserves current behavior:

```python
class LogViewScreen(Screen):
    """Fullscreen text viewer with vertical and horizontal scrolling.

    Used for the crash log and the pre-install changelog. Nav encoder
    selects lines. Tweak1 scrolls all lines horizontally. LONG_CLICK
    or navigating to and clicking the back icon exits.
    """

    def __init__(
        self,
        surface: pygame.Surface,
        lines: list[str],
        on_back: Callable[[], None],
        title: str = "Crash Log",
    ) -> None:
        super().__init__(surface)
        self._lines: list[str] = lines
        self._on_back: Callable[[], None] | None = on_back
        self._header: Header = Header(title, ICON_BACK)
        self._scroll: int = max(0, len(lines) - self._content_lines())
        self._hscroll: int = 0
        self._sel: int = len(lines) - 1 if lines else 0
        self._on_header: bool = False
```

Crash log call sites in `app.py:131-138` continue to work
unchanged.

## 21. `src/pistomp_recovery/app.py` — `_show_package_detail` UI change

**File:** `src/pistomp_recovery/app.py:549-590`

The new method:

```python
    def _show_package_detail(self, item: Item, mode: str, domain: str) -> None:
        """Push a detail screen showing the description and Install/Changelog targets."""
        name = item.name
        old_ver = item.label.removeprefix(name).strip()
        new_ver = item.right.lstrip("↑")

        menu = self._push_menu(
            name,
            [],
            back=True,
            mode=mode,
            domain=domain,
            reload_callback=lambda: self._refresh_domain(mode, domain),
        )
        menu.set_progress(name, 0.0, "Loading...", done=False)
        self._mark_dirty(None)

        # Capture these in the closure for the worker thread.
        def _run() -> None:
            detail = self._backends.data.package_detail(name)

            def show_changelog() -> None:
                # detail.changelog is empty when the backend couldn't
                # fetch one; this target is disabled in that case so
                # this branch is only reachable when there's content.
                if not detail.changelog:
                    return
                log_screen = LogViewScreen(
                    self.surface,
                    list(detail.changelog),
                    on_back=self.pop_screen,
                    title="Changelog",
                )
                self.push_screen(log_screen)

            rows: list[Row] = [Row(prefix=f"{old_ver} → {new_ver}")]
            for line in _wrap_description(detail.description):
                rows.append(Row(prefix=line))
            rows.append(Row(prefix="---", separator=True))
            rows.append(
                Row(
                    (
                        Target("Install", lambda: self._install_packages([name])),
                        Target(
                            "Changelog",
                            show_changelog,
                            enabled=bool(detail.changelog),
                        ),
                    )
                )
            )
            menu.set_rows(rows)
            menu.clear_progress()
            self._mark_dirty(None)

        threading.Thread(target=_run, daemon=True).start)
```

### Description capping

A new module-level helper above the class:

```python
_MAX_DESCRIPTION_LINES: int = 6
_DESCRIPTION_COLS: int = 38


def _wrap_description(description: tuple[str, ...]) -> list[str]:
    """Wrap the description to LCD width and cap at _MAX_DESCRIPTION_LINES.

    If the wrapped output is longer than the cap, the last visible line
    is replaced with "..." so the user sees they can scroll for more —
    except on this screen, where we don't yet have a way to view the
    full description. The cap is conservative: it ensures the
    Install/Changelog row is always on-screen regardless of how long
    the description is. (A future "Description" viewer would lift
    this cap.)
    """
    wrapped: list[str] = []
    for line in description:
        # textwrap.wrap(line, width) returns [] for the empty string;
        # the existing pre-install screen preserved that as a single
        # empty row.
        pieces = textwrap.wrap(line, _DESCRIPTION_COLS) or [""]
        wrapped.extend(pieces)
    if len(wrapped) > _MAX_DESCRIPTION_LINES:
        return wrapped[: _MAX_DESCRIPTION_LINES - 1] + ["..."]
    return wrapped
```

(Keep the existing `textwrap.wrap(line, 38) or [""]` semantics — the
`or [""]` is what makes an empty source line render as a blank row,
preserving the "Description:" paragraph break from `apt-cache show`.)

### Targets layout

- `Install` and `Changelog` share one row, separated by ` | ` (the
  default `Row` rendering — see `ui/screens/menu_screen.py:19`).
- `Changelog` is `enabled=bool(detail.changelog)`. When the backend
  returned no changelog (pacman, or apt-get changelog failed), the
  Changelog target renders dimmed and the encoder skips it.
- `Install` is always enabled. There is no scenario where we want to
  disable it on this screen.

## 22. `tests/conftest.py` — `FakeDataBackend.package_detail` returns `PackageDetail`

**File:** `tests/conftest.py:248-249`

```python
    def package_detail(self, name: str) -> PackageDetail:
        return PackageDetail(description=(), changelog=())
```

The default "no detail" state. Tests that want a specific description
or changelog can override.

## 23. Tests — new test file `tests/test_changelog_viewer.py`

A new test file covering the pre-install changelog feature end-to-end
with the existing `FakeDataBackend`:

```python
# pyright: reportPrivateUsage=false
"""Tests for the pre-install changelog viewer."""

from __future__ import annotations

from typing import Callable

from pistomp_recovery.items import PackageDetail, PackageUpdate, Row, Target
from pistomp_recovery.service import BootMode, CrashInfo
from pistomp_recovery.ui.screens.log_view import LogViewScreen
from pistomp_recovery.ui.widgets.misc import InputEvent
from tests.conftest import (
    AppHarness,
    FakeDataBackend,
    FakeDisplayBackend,
    FakeInputBackend,
)


def test_pre_install_removes_first_separator(
    recovery_app: AppHarness,
    fake_data: FakeDataBackend,
    snapshot: Callable[..., None],
) -> None:
    """The first --- separator (above the description) is gone."""
    fake_data._package_detail_override = PackageDetail(
        description=("A one-line description.",),
        changelog=(),
    )
    fake_data.set_updates("system", [PackageUpdate("a", "0.1", "0.2")])
    harness = recovery_app
    harness.app._show_domain("updates", "system")
    harness.inject()
    harness.select("a 0.1")
    harness.drain()
    snapshot("pre_install")
    # First --- must be gone: the version row is followed directly by
    # the description.
    menu = harness._menu()
    assert menu is not None
    rows = menu._rows
    assert rows[0].prefix == "0.1 → 0.2"
    assert not rows[0].separator
    assert "---" not in rows[0].prefix
    # And the first description row is at index 1.
    assert rows[1].prefix == "A one-line description."
    # Bottom: --- then Install | Changelog.
    assert rows[-2].prefix == "---" and rows[-2].separator
    last_targets = [t.label for t in rows[-1].targets]
    assert last_targets == ["Install", "Changelog"]


def test_pre_install_caps_description_at_six_lines(
    recovery_app: AppHarness,
    fake_data: FakeDataBackend,
) -> None:
    """Long descriptions are truncated with ... to keep Install on-screen."""
    long_desc = tuple(f"line {i}" for i in range(20))
    fake_data._package_detail_override = PackageDetail(
        description=long_desc, changelog=()
    )
    fake_data.set_updates("system", [PackageUpdate("a", "0.1", "0.2")])
    harness = recovery_app
    harness.app._show_domain("updates", "system")
    harness.inject()
    harness.select("a 0.1")
    harness.drain()

    menu = harness._menu()
    assert menu is not None
    # version row + 5 description lines + "..." + "---" + Install|Changelog
    # = 1 + 5 + 1 + 1 + 1 = 9 rows.
    assert len(menu._rows) == 9
    assert menu._rows[5].prefix == "..."
    # The bottom two rows are still --- and Install|Changelog.
    assert menu._rows[-2].prefix == "---" and menu._rows[-2].separator
    labels = [t.label for t in menu._rows[-1].targets]
    assert labels == ["Install", "Changelog"]


def test_changelog_target_disabled_when_no_changelog(
    recovery_app: AppHarness,
    fake_data: FakeDataBackend,
) -> None:
    """When the backend returned no changelog, Changelog is disabled."""
    fake_data._package_detail_override = PackageDetail(
        description=("desc",), changelog=()
    )
    fake_data.set_updates("system", [PackageUpdate("a", "0.1", "0.2")])
    harness = recovery_app
    harness.app._show_domain("updates", "system")
    harness.inject()
    harness.select("a 0.1")
    harness.drain()

    menu = harness._menu()
    assert menu is not None
    install = next(t for t in menu._rows[-1].targets if t.label == "Install")
    changelog = next(t for t in menu._rows[-1].targets if t.label == "Changelog")
    assert install.enabled
    assert not changelog.enabled
    # Encoder skips the disabled target, so nav_labels() has no "Changelog".
    assert "Changelog" not in harness.nav_labels()


def test_changelog_target_enabled_when_changelog_present(
    recovery_app: AppHarness,
    fake_data: FakeDataBackend,
) -> None:
    fake_data._package_detail_override = PackageDetail(
        description=("desc",),
        changelog=(
            "a (0.2) trixie; urgency=medium",
            "",
            "  * The new thing.",
            "",
            " -- Author <a@b.c>  Mon, 01 Jan 2026 00:00:00 +0000",
        ),
    )
    fake_data.set_updates("system", [PackageUpdate("a", "0.1", "0.2")])
    harness = recovery_app
    harness.app._show_domain("updates", "system")
    harness.inject()
    harness.select("a 0.1")
    harness.drain()

    assert "Changelog" in harness.nav_labels()


def test_clicking_changelog_pushes_log_view_screen(
    recovery_app: AppHarness,
    fake_data: FakeDataBackend,
) -> None:
    """Selecting Changelog pushes a LogViewScreen titled 'Changelog'."""
    changelog_lines = (
        "a (0.2) trixie; urgency=medium",
        "",
        "  * First bullet.",
        "  * Second bullet.",
        "",
        " -- Author <a@b.c>  Mon, 01 Jan 2026 00:00:00 +0000",
    )
    fake_data._package_detail_override = PackageDetail(
        description=("desc",), changelog=changelog_lines
    )
    fake_data.set_updates("system", [PackageUpdate("a", "0.1", "0.2")])
    harness = recovery_app
    harness.app._show_domain("updates", "system")
    harness.inject()
    harness.select("a 0.1")
    harness.drain()

    harness.select("Changelog")
    screen = harness.app.current_screen()
    assert isinstance(screen, LogViewScreen)
    # Title comes from the LogViewScreen's parameterized header.
    assert screen._header.title == "Changelog"
    # And the lines are the changelog verbatim.
    assert screen._lines == list(changelog_lines)


def test_log_view_screen_back_from_changelog(
    recovery_app: AppHarness,
    fake_data: FakeDataBackend,
) -> None:
    """LONG_CLICK on the changelog viewer returns to the pre-install screen."""
    fake_data._package_detail_override = PackageDetail(
        description=("desc",),
        changelog=("a (0.2) trixie; urgency=medium", "  * body"),
    )
    fake_data.set_updates("system", [PackageUpdate("a", "0.1", "0.2")])
    harness = recovery_app
    harness.app._show_domain("updates", "system")
    harness.inject()
    harness.select("a 0.1")
    harness.drain()
    harness.select("Changelog")
    assert isinstance(harness.app.current_screen(), LogViewScreen)

    harness.long_press()  # LONG_CLICK on the back affordance
    # We're back on the pre-install menu, with Install still present.
    menu = harness._menu()
    assert menu is not None
    labels = [t.label for t in menu._rows[-1].targets]
    assert "Install" in labels and "Changelog" in labels
```

The `FakeDataBackend` needs a small extension to support overriding
`package_detail` per test:

```python
# in tests/conftest.py, inside FakeDataBackend
def package_detail(self, name: str) -> PackageDetail:
    override = getattr(self, "_package_detail_override", None)
    if override is not None:
        return override
    return PackageDetail(description=(), changelog=())
```

This is the only conftest change.

## 24. Backwards compatibility

**Existing tests:** the change to `package_detail`'s return type
breaks compilation of the `FakeDataBackend.package_detail` and
`EmulatorDataBackend.package_detail` until both are updated
(§19, §22). The other test file using `package_detail` indirectly
(`tests/test_screens.py:60`) only waits for the loading thread to
finish via `harness.drain()` and never inspects the result, so it
will continue to pass.

**Existing behaviour on devices without the new feature:** Before
`pi-gen-pistomp` ships the signed repo + `.changes` files, devices
running `apt-get changelog <pkg>` will get "Changelog unavailable" and
the new code (§15) returns `PackageDetail(description=..., changelog=())`.
The pre-install screen will render with the Changelog target disabled,
and the user can still install. **No regression** — the worst case is
"same UI as today, no changelog option."

**Pre-OTA devices (pre-`pistomp.list`-baked-in):** Same — they'll
have the old `[trusted=yes]` source line. The first time they
`apt-get update` after the repo becomes signed, apt will try to
verify `InRelease` against the keyring (which isn't on the device)
and fail. The `pistomp-archive-keyring` migration .deb (§12) is the
fix; without it, those devices can't `apt-get update` until
re-flashed.

---

# Execution order

1. **Generate the GPG key**, commit the public half to
   `stage2/05-pistomp/files/pistomp-archive-keyring.gpg`, store the
   private half as `PISTOMP_APT_SIGNING_KEY` secret. (Human-only,
   ~5 min.)
2. **`scripts/build-common.sh`** (§7) — preserve `.changes` files in
   `CACHE_DIR`. One PR. Required by step 3.
3. **`.github/workflows/build-deb.yml`** (§8) — upload `.changes` as
   a release asset. One PR. Required by step 4.
4. **`.github/workflows/publish-apt-repo.yml`** (§6) — import the
   key, switch `includedeb` → `include`, install `gnupg` on the
   runner. One PR. After this lands, new releases will publish
   `.changes` to `pool/`. The next step (§5) makes the repo
   actually *signed*.
5. **`stage2/00-dummy-packages/01-run.sh` + `stage2/05-pistomp/01-run.sh`**
   (§2, §3) — switch to `signed-by=…`, install the keyring. One PR.
   After this lands, the next image build's `apt-get update` will
   verify signatures. (Existing devices don't get this until
   reflashed — see §12.)
6. **`scripts/setup-apt-repo.sh`** (§4) — sign the local override
   too, for dev parity. One PR.
7. **`debpkgs/lcd-splash/`** (§9) — migrate to `dpkg-buildpackage`.
   One PR per package, or one combined PR.
8. **`debpkgs/libfluidsynth2-compat/`** (§10) — migrate to
   `dpkg-buildpackage`. One PR per package, or one combined PR.
9. **`pistomp-recovery/src/...`** (§14–§22) — `PackageDetail`
   dataclass, `AptManager.package_detail` change, `LogViewScreen`
   title parameter, `_show_package_detail` UI change,
   `backends.py`/`backends_real.py`/`emulator/backends.py`/
   `conftest.py` updates. One PR in `pistomp-recovery`.
10. **`tests/test_changelog_viewer.py`** (§23) — new tests. Bundled
    with step 9.
11. **`docs/OTA.md`** (§11) — rewrite the "GPG signing" section.
    Bundled with step 5.
12. **`pistomp-archive-keyring` .deb** (mentioned in §12) — one-off
    migration package for pre-OTA devices. Independent PR; can ship
    any time after step 1.

After step 8 lands, every package has a `.changes` in `pool/`, the
repo is signed, and `apt-get changelog <pkg>` works against it from
any device with the keyring on disk. Step 9 wires the recovery
service to use it. Step 12 is the only "user-facing migration" step
the rest of the fleet needs to do.

# Why the recovery-side change is so small

`apt-get changelog` does everything we want:

- Fetches the new version's `.changes` from `pool/` over HTTPS.
- Verifies the GPG signature (assumes the repo is signed per §5).
- Concatenates the new stanza with the installed version's
  `changelog.Debian.gz` (if present) to produce a full history.
- Stops on first parse error or network failure with a non-zero
  return code.

So the recovery service's job is to call this command, parse the
output into lines, and ship those lines to a `LogViewScreen`. No
custom URL construction, no `.deb` inspection, no fallback paths.
The same call works for any package in any repo, including
upstream Debian packages (apt's URL pattern is hardcoded for the
major origins).
