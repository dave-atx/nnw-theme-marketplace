from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from collections.abc import Sequence
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from marketplace.preview import (
    SAMPLE_WEEKLY_DOWNLOADS,
    with_weekly_downloads,
    write_data_overlay,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HUGO = shutil.which("hugo")
CATALOG: dict[str, Any] = json.loads((PROJECT_ROOT / "data" / "themes.json").read_text())


class HomepageParser(HTMLParser):
    """Collect the Trending section, its card links and names, and theme card anchors."""

    def __init__(self) -> None:
        super().__init__()
        self.has_trending = False
        self.trending_links: list[str] = []
        self.trending_names: list[str] = []
        self.card_ids: set[str] = set()
        self._in_trend_card = False
        self._in_name = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        if tag == "section" and "trending" in classes:
            self.has_trending = True
        elif tag == "a" and "trend-card" in classes:
            self._in_trend_card = True
            self.trending_links.append(attributes.get("href") or "")
        elif tag == "strong" and self._in_trend_card:
            self._in_name = True
        elif tag == "article" and "theme-card" in classes and attributes.get("id"):
            self.card_ids.add(attributes["id"] or "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._in_trend_card = False
        elif tag == "strong":
            self._in_name = False

    def handle_data(self, data: str) -> None:
        if self._in_name:
            self.trending_names.append(data.strip())


def render_homepage(counts: Sequence[int | None]) -> HomepageParser:
    """Build the site with the given weekly counts and parse its homepage."""
    assert HUGO is not None
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        overlay = write_data_overlay(root / "overlay", with_weekly_downloads(CATALOG, counts))
        destination = root / "public"
        command = [
            HUGO,
            "--destination",
            str(destination),
            "--config",
            f"hugo.toml,{overlay}",
            "--panicOnWarning",
        ]
        result = subprocess.run(
            command, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False
        )
        if result.returncode != 0:
            raise AssertionError(f"hugo build failed:\n{result.stdout}\n{result.stderr}")
        parser = HomepageParser()
        parser.feed((destination / "index.html").read_text())
        return parser


def expected_names(counts: Sequence[int | None]) -> list[str]:
    ranked = sorted(
        (count, theme["name"])
        for theme, count in zip(CATALOG["themes"], counts, strict=False)
        if count
    )
    return [name for _, name in reversed(ranked)][:3]


@unittest.skipUnless(HUGO, "hugo is not installed")
class TrendingSectionTests(unittest.TestCase):
    """The homepage shows up to three themes with the most downloads in the last week."""

    def test_sample_counts_exercise_sorting_filtering_and_the_limit(self) -> None:
        nonzero = [count for count in SAMPLE_WEEKLY_DOWNLOADS if count]
        self.assertGreater(len(nonzero), 3)
        self.assertIn(0, SAMPLE_WEEKLY_DOWNLOADS)
        self.assertNotEqual(nonzero[:3], sorted(nonzero, reverse=True)[:3])
        self.assertLessEqual(len(SAMPLE_WEEKLY_DOWNLOADS), len(CATALOG["themes"]))

    def test_shows_the_top_three_themes_by_weekly_downloads(self) -> None:
        page = render_homepage(SAMPLE_WEEKLY_DOWNLOADS)
        self.assertTrue(page.has_trending)
        self.assertEqual(page.trending_names, expected_names(SAMPLE_WEEKLY_DOWNLOADS))

    def test_trending_cards_link_to_theme_cards(self) -> None:
        page = render_homepage(SAMPLE_WEEKLY_DOWNLOADS)
        self.assertEqual(len(page.trending_links), 3)
        for link in page.trending_links:
            with self.subTest(link=link):
                self.assertTrue(link.startswith("#"))
                self.assertIn(link.removeprefix("#"), page.card_ids)

    def test_shows_fewer_cards_when_fewer_themes_moved(self) -> None:
        counts = (0, 5)
        page = render_homepage(counts)
        self.assertTrue(page.has_trending)
        self.assertEqual(page.trending_names, expected_names(counts))
        self.assertEqual(len(page.trending_names), 1)

    def test_hidden_without_weekly_downloads(self) -> None:
        for counts in ((), (0, 0, 0, 0)):
            with self.subTest(counts=counts):
                page = render_homepage(counts)
                self.assertFalse(page.has_trending)
                self.assertEqual(page.trending_links, [])


if __name__ == "__main__":
    unittest.main()
