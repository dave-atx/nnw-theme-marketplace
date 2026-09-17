from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HUGO = shutil.which("hugo")


def build_feed(feed_content_modified: str | None) -> list[dict[str, Any]]:
    """Render the JSON Feed, optionally overriding the feedContentModified stamp."""
    assert HUGO is not None
    with tempfile.TemporaryDirectory() as directory:
        destination = Path(directory) / "public"
        command = [HUGO, "--destination", str(destination), "--panicOnWarning"]
        if feed_content_modified is not None:
            override = Path(directory) / "override.toml"
            override.write_text(f'[params]\nfeedContentModified = "{feed_content_modified}"\n')
            command += ["--config", f"hugo.toml,{override}"]
        result = subprocess.run(
            command, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False
        )
        if result.returncode != 0:
            raise AssertionError(f"hugo build failed:\n{result.stdout}\n{result.stderr}")
        return json.loads((destination / "feed.json").read_text())["items"]


@unittest.skipUnless(HUGO, "hugo is not installed")
class FeedDateTests(unittest.TestCase):
    """date_modified tracks template changes but must never precede date_published."""

    def test_uses_the_stamp_when_it_is_newer_than_the_release(self) -> None:
        items = build_feed("2099-01-01T00:00:00Z")
        self.assertTrue(items)
        for item in items:
            self.assertEqual(item["date_modified"], "2099-01-01T00:00:00Z")

    def test_falls_back_to_the_release_date_when_the_stamp_is_older(self) -> None:
        items = build_feed("2000-01-01T00:00:00Z")
        self.assertTrue(items)
        for item in items:
            self.assertEqual(item["date_modified"], item["date_published"])

    def test_never_reports_a_modification_before_publication(self) -> None:
        for stamp in (None, "2000-01-01T00:00:00Z", "2099-01-01T00:00:00Z"):
            with self.subTest(stamp=stamp):
                for item in build_feed(stamp):
                    self.assertGreaterEqual(item["date_modified"], item["date_published"])


if __name__ == "__main__":
    unittest.main()
