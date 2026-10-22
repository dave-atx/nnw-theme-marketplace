from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from test_seo import SITE, HeadParser, build_site

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HUGO = shutil.which("hugo")


class ScriptCounter(HTMLParser):
    """Count script elements, which ignores text that only looks like a tag."""

    def __init__(self, html: str) -> None:
        super().__init__()
        self.count = 0
        self.feed(html)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.count += tag == "script"


def theme(base: dict[str, Any], identifier: str, name: str, **fields: Any) -> dict[str, Any]:
    return {**base, "id": identifier, "name": name, "release_history": [], **fields}


@unittest.skipUnless(HUGO, "hugo is not installed")
class ThemePageTests(unittest.TestCase):
    """Each theme gets an indexable page at a stable, name-based path."""

    @classmethod
    def setUpClass(cls) -> None:
        catalog = json.loads((PROJECT_ROOT / "data" / "themes.json").read_text())
        base = catalog["themes"][0]
        catalog["themes"] = [
            theme(base, "org.example.ringo", "Ringo", release_notes="Fixed <b>bold</b> text"),
            theme(base, "org.example.one.default", "Default"),
            theme(base, "org.example.two.default", "Default"),
            theme(base, "org.example.symbols", "<script>"),
        ]
        cls.directory = tempfile.TemporaryDirectory()
        cls.public = Path(cls.directory.name) / "public"
        build_site(cls.public, catalog)
        cls.home = (cls.public / "index.html").read_text()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.directory.cleanup()

    def page(self, slug: str) -> str:
        return (self.public / "themes" / slug / "index.html").read_text()

    def test_uses_the_name_and_falls_back_to_the_identifier(self) -> None:
        for slug in ("ringo", "org.example.one.default", "org.example.two.default", "script"):
            with self.subTest(slug=slug):
                self.assertTrue((self.public / "themes" / slug / "index.html").is_file())

    def test_describes_the_theme_for_search(self) -> None:
        head = HeadParser(self.page("ringo"))
        self.assertEqual(head.canonical, f"{SITE}themes/ringo/")
        self.assertEqual(head.meta["og:title"], "Ringo · NetNewsWire Themes")
        self.assertTrue(head.meta["description"].startswith("Ringo, a NetNewsWire theme by "))

    def test_escapes_untrusted_names_and_notes(self) -> None:
        page = self.page("script")
        self.assertIn("<h1>&lt;script></h1>", page)
        self.assertEqual(ScriptCounter(page).count, 1)
        ringo = self.page("ringo")
        self.assertIn("Fixed", ringo)
        self.assertNotIn("<b>bold</b>", ringo)

    def test_home_links_to_theme_pages_under_the_project_path(self) -> None:
        self.assertIn("href=/nnw-theme-marketplace/themes/ringo/>Ringo</a></h3>", self.home)

    def test_sitemap_lists_theme_pages_but_not_the_section(self) -> None:
        sitemap = (self.public / "sitemap.xml").read_text()
        self.assertIn(f"<loc>{SITE}themes/ringo/</loc>", sitemap)
        self.assertNotIn(f"<loc>{SITE}themes/</loc>", sitemap)
        self.assertFalse((self.public / "themes" / "index.html").exists())

    def test_feed_items_link_to_theme_pages(self) -> None:
        items = json.loads((self.public / "feed.json").read_text())["items"]
        urls = {item["url"] for item in items}
        self.assertIn(f"{SITE}themes/ringo/", urls)


if __name__ == "__main__":
    unittest.main()
