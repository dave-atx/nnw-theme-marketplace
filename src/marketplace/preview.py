from __future__ import annotations

import contextlib
import copy
import json
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

# Weekly counts assigned to the catalog's first themes, in catalog order. The
# pattern is out of order, includes a zero, and has more than three nonzero
# entries, so rendering exercises sorting, filtering, and the three-card limit.
SAMPLE_WEEKLY_DOWNLOADS: tuple[int, ...] = (12, 0, 48, 7, 30)


def with_weekly_downloads(catalog: dict[str, Any], counts: Sequence[int | None]) -> dict[str, Any]:
    """Return a copy of the catalog whose first themes carry the given weekly counts."""
    patched = copy.deepcopy(catalog)
    for index, theme in enumerate(patched["themes"]):
        theme["downloads_last_7_days"] = counts[index] if index < len(counts) else None
    return patched


def write_data_overlay(directory: Path, catalog: dict[str, Any]) -> Path:
    """Write a Hugo config that mounts the catalog ahead of the committed data directory."""
    data = directory / "data"
    data.mkdir(parents=True, exist_ok=True)
    (data / "themes.json").write_text(json.dumps(catalog, indent=2) + "\n")
    config = directory / "overlay.toml"
    config.write_text(
        "[[module.mounts]]\n"
        f"source = {json.dumps(str(data.resolve()))}\n"
        'target = "data"\n'
        "\n"
        "[[module.mounts]]\n"
        'source = "data"\n'
        'target = "data"\n'
    )
    return config


def main() -> None:
    """Serve the site with sample weekly downloads so the Trending section renders."""
    hugo = shutil.which("hugo")
    if hugo is None:
        raise SystemExit("hugo is not installed")
    catalog = json.loads(Path("data/themes.json").read_text())
    with tempfile.TemporaryDirectory() as directory:
        overlay = write_data_overlay(
            Path(directory), with_weekly_downloads(catalog, SAMPLE_WEEKLY_DOWNLOADS)
        )
        command = [hugo, "server", "--config", f"hugo.toml,{overlay}", *sys.argv[1:]]
        with contextlib.suppress(KeyboardInterrupt):
            subprocess.run(command, check=False)


if __name__ == "__main__":
    main()
