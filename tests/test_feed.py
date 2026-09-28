from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

from test_seo import build_site

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


@unittest.skipUnless(HUGO, "hugo is not installed")
class ReleaseNotesFeedTests(unittest.TestCase):
    """Release notes render as Markdown, with untrusted HTML and links neutralized."""

    def render(self, notes: str | None) -> str:
        themes = json.loads((PROJECT_ROOT / "data" / "themes.json").read_text())
        theme = themes["themes"][0]
        theme["release_notes"] = notes
        with tempfile.TemporaryDirectory() as directory:
            public = Path(directory) / "public"
            build_site(public, themes)
            items = json.loads((public / "feed.json").read_text())["items"]
        return next(item for item in items if item["id"] == theme["asset_url"])["content_html"]

    def test_renders_markdown_notes_before_the_install_links(self) -> None:
        content = self.render("### Bug Fixes\n- Wrap the opening paragraph")
        self.assertIn("<h3", content)
        self.assertIn("<li>Wrap the opening paragraph</li>", content)
        self.assertLess(content.index("Wrap the opening"), content.index("Install "))

    def test_drops_raw_html_and_script_links(self) -> None:
        content = self.render(
            '<script>alert(1)</script>\n\n<img src=x onerror="alert(2)">\n\n'
            "[click](javascript:alert(3))"
        )
        self.assertNotIn("<script", content)
        self.assertNotIn("onerror", content)
        self.assertNotIn("javascript:", content)
        self.assertIn("click", content)

    def test_omits_notes_when_absent(self) -> None:
        self.assertNotIn("<h", self.render(None).split("Install ")[0])


@unittest.skipUnless(HUGO, "hugo is not installed")
class ReleaseHistoryFeedTests(unittest.TestCase):
    """Earlier releases become their own items, keeping the id they had when current."""

    def test_emits_an_item_per_earlier_release(self) -> None:
        themes = json.loads((PROJECT_ROOT / "data" / "themes.json").read_text())
        theme = themes["themes"][0]
        theme["release_history"] = [
            {
                "release": "v0.9",
                "released_at": "2001-01-01T00:00:00Z",
                "asset_name": "Old.nnwtheme.zip",
                "asset_url": "https://github.com/example/reader/old.zip",
                "release_notes": "- The first cut",
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            public = Path(directory) / "public"
            build_site(public, themes)
            items = json.loads((public / "feed.json").read_text())["items"]
        ids = [item["id"] for item in items]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn(theme["asset_url"], ids)
        past = items[-1]
        self.assertEqual(past["id"], "https://github.com/example/reader/old.zip")
        self.assertEqual(past["title"], f"{theme['name']} v0.9")
        self.assertEqual(past["date_published"], "2001-01-01T00:00:00Z")
        self.assertIn("<li>The first cut</li>", past["content_html"])
        self.assertEqual(past["attachments"][0]["title"], "Old.nnwtheme.zip")


if __name__ == "__main__":
    unittest.main()
