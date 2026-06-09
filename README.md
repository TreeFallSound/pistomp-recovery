pistomp-recovery
==================

Package update and recovery service for pi-Stomp.

Runs as an exclusive LCD service alongside mod-ala-pi-stomp. Activates via:
  - systemd OnFailure when the main app crashes 3+ times in 180 seconds
  - User selecting "Recovery" from the System Menu

Architecture
------------
- Facets: git-backed versioned config directories (etckeeper model)
  - config: /home/pistomp/data/config/ (default_config.yml, settings.yml)
  - pedalboards: /home/pistomp/data/.pedalboards/ (git repo)
  - packages: pacman package version manifests
  - system: /boot/config.txt, /etc/jackdrc, ALSA state
- Package management: pacman-based update/rollback with GitHub Releases hosting
- Health checks: verify JACK → mod-host → mod-ui → pi-stomp after updates
- LCD UI: pygame-based widget library for 320x240 ILI9341 display

CLI
---
- `pistomp-recovery` — main service (started by systemd)
- `pistomp-stamp stamp -f <facet>` — stamp a facet as known-good
- `pistomp-stamp snapshot -f <facet>` — take a snapshot without stamping
- `pistomp-stamp status -f <facet>` — show facet status

Development
-----------
    uv sync
    uv run python -m pistomp_recovery --log DEBUG --force-menu
    