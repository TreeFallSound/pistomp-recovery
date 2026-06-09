from __future__ import annotations

import argparse
import sys

from pistomp_recovery.facets.base import Facet
from pistomp_recovery.facets.config_facet import ConfigFacet
from pistomp_recovery.facets.packages_facet import PackagesFacet
from pistomp_recovery.facets.pedalboards_facet import PedalboardsFacet
from pistomp_recovery.facets.system_facet import SystemFacet

FACETS: dict[str, Facet] = {
    "config": ConfigFacet(),
    "pedalboards": PedalboardsFacet(),
    "packages": PackagesFacet(),
    "system": SystemFacet(),
}


def main(args: list[str] | None = None) -> None:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="pistomp facet stamp utility"
    )
    parser.add_argument(
        "command",
        choices=["stamp", "snapshot", "status"],
        help="Action to perform",
    )
    parser.add_argument(
        "--facet",
        "-f",
        choices=list(FACETS.keys()),
        default=None,
        help="Which facet to operate on (default: all)",
    )
    parser.add_argument(
        "--message",
        "-m",
        default=None,
        help="Commit message",
    )

    parsed: argparse.Namespace = parser.parse_args(args)
    facets_to_run: list[str] = [parsed.facet] if parsed.facet else list(FACETS.keys())

    for facet_name in facets_to_run:
        facet: Facet = FACETS[facet_name]
        try:
            facet.init()
            if parsed.command == "stamp":
                tag: str = facet.stamp(message=parsed.message)
                print(f"stamped {facet_name}: {tag}")
            elif parsed.command == "snapshot":
                sha: str = facet.snapshot(message=parsed.message)
                print(f"snapshot {facet_name}: {sha}")
            elif parsed.command == "status":
                status: str = facet.status()
                print(f"{facet_name}: {status or 'clean'}")
        except Exception as e:
            print(f"error on {facet_name}: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
