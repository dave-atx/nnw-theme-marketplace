from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HUGO = shutil.which("hugo")
SITE = "https://dave-atx.github.io/nnw-theme-marketplace/"
HOSTILE = '</script><script>alert("x")</script>'


def build_site(destination: Path, themes: dict[str, Any] | None = None) -> None:
    """Build the site, optionally replacing data/themes.json with the given catalog."""
    assert HUGO is not None
    command = [HUGO, "--destination", str(destination), "--minify", "--panicOnWarning"]
    if themes is not None:
        data = destination.parent / "data"
        data.mkdir()
        (data / "themes.json").write_text(json.dumps(themes))
        override = destination.parent / "override.toml"
        mounts = "".join(
            f'[[module.mounts]]\nsource = "{source}"\ntarget = "{target}"\n'
            for source, target in (
                (PROJECT_ROOT / "content", "content"),
                (PROJECT_ROOT / "layouts", "layouts"),
                (PROJECT_ROOT / "static", "static"),
                (PROJECT_ROOT / "assets", "assets"),
                (data, "data"),
            )
        )
        override.write_text(mounts)
        command += ["--config", f"hugo.toml,{override}"]
    result = subprocess.run(command, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AssertionError(f"hugo build failed:\n{result.stdout}\n{result.stderr}")


class HeadParser(HTMLParser):
    """Collect meta tags, the canonical link, and JSON-LD blocks from a page."""

    def __init__(self, html: str) -> None:
        super().__init__()
        self.meta: dict[str, str] = {}
        self.canonical: str | None = None
        self.json_ld: list[str] = []
        self._in_json_ld = False
        self.feed(html)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag == "meta" and ("property" in values or "name" in values):
            self.meta[values.get("property") or values["name"]] = values.get("content", "")
        elif tag == "link" and values.get("rel") == "canonical":
            self.canonical = values.get("href")
        elif tag == "script" and values.get("type") == "application/ld+json":
            self._in_json_ld = True
            self.json_ld.append("")

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in_json_ld = False

    def handle_data(self, data: str) -> None:
        if self._in_json_ld:
            self.json_ld[-1] += data


def json_ld(html: str) -> dict[str, Any]:
    blocks = HeadParser(html).json_ld
    if len(blocks) != 1:
        raise AssertionError(f"expected one JSON-LD block, found {len(blocks)}")
    return json.loads(blocks[0])


@unittest.skipUnless(HUGO, "hugo is not installed")
class SeoTests(unittest.TestCase):
    """Search and social metadata stay complete, absolute, and injection-safe."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.directory = tempfile.TemporaryDirectory()
        cls.public = Path(cls.directory.name) / "public"
        build_site(cls.public)
        cls.home = (cls.public / "index.html").read_text()
        cls.install = (cls.public / "install" / "index.html").read_text()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.directory.cleanup()

    def test_sitemap_lists_indexable_pages_only(self) -> None:
        sitemap = (self.public / "sitemap.xml").read_text()
        self.assertIn(f"<loc>{SITE}</loc>", sitemap)
        self.assertIn(f"<loc>{SITE}get-listed/</loc>", sitemap)
        self.assertNotIn("/install/", sitemap)

    def test_only_the_install_page_is_noindex(self) -> None:
        self.assertEqual(HeadParser(self.install).meta.get("robots"), "noindex")
        self.assertNotIn("robots", HeadParser(self.home).meta)

    def test_social_tags_use_absolute_urls_to_a_real_image(self) -> None:
        head = HeadParser(self.home)
        self.assertEqual(head.canonical, SITE)
        self.assertEqual(head.meta["og:url"], SITE)
        self.assertEqual(head.meta["og:title"], "NetNewsWire Themes")
        self.assertEqual(head.meta["og:description"], head.meta["description"])
        self.assertEqual(head.meta["twitter:card"], "summary_large_image")
        self.assertEqual(head.meta["og:image"], f"{SITE}og-image.png")
        self.assertEqual(head.meta["twitter:image"], head.meta["og:image"])
        self.assertTrue(head.meta["og:image:alt"])
        self.assertTrue((self.public / "og-image.png").is_file())

    def test_subpages_describe_themselves(self) -> None:
        head = HeadParser((self.public / "get-listed" / "index.html").read_text())
        self.assertEqual(head.canonical, f"{SITE}get-listed/")
        self.assertEqual(head.meta["og:url"], f"{SITE}get-listed/")
        self.assertEqual(head.meta["og:title"], "Get your theme listed · NetNewsWire Themes")

    def test_json_ld_lists_every_theme(self) -> None:
        themes = json.loads((PROJECT_ROOT / "data" / "themes.json").read_text())["themes"]
        graph = json_ld(self.home)["@graph"]
        items = graph[1]["mainEntity"]["itemListElement"]
        self.assertEqual([item["item"]["name"] for item in items], [t["name"] for t in themes])
        self.assertEqual([item["position"] for item in items], list(range(1, len(themes) + 1)))
        self.assertNotIn("application/ld+json", self.install)

    def test_json_ld_escapes_hostile_theme_fields(self) -> None:
        themes = json.loads((PROJECT_ROOT / "data" / "themes.json").read_text())
        theme = themes["themes"][0]
        theme["name"] = HOSTILE
        theme["description"] = HOSTILE
        theme["creator_name"] = HOSTILE
        with tempfile.TemporaryDirectory() as directory:
            public = Path(directory) / "public"
            build_site(public, themes)
            html = (public / "index.html").read_text()
        blocks = HeadParser(html).json_ld
        self.assertEqual(len(blocks), 1)
        self.assertNotIn("<", blocks[0])
        work = json_ld(html)["@graph"][1]["mainEntity"]["itemListElement"][0]["item"]
        self.assertEqual(work["name"], HOSTILE)
        self.assertEqual(work["description"], HOSTILE)
        self.assertEqual(work["author"]["name"], HOSTILE)


if __name__ == "__main__":
    unittest.main()
