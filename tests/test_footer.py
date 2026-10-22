from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from test_seo import build_site

HUGO = shutil.which("hugo")


@unittest.skipUnless(HUGO, "hugo is not installed")
class CatalogUpdatedTests(unittest.TestCase):
    """The footer's update time is rendered in UTC and rewritten in the browser's zone."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.directory = tempfile.TemporaryDirectory()
        public = Path(cls.directory.name) / "public"
        build_site(public, {"generated_at": "2026-01-02T03:04:05+02:00", "themes": []})
        cls.pages = {
            "home": (public / "index.html").read_text(),
            "install": (public / "install" / "index.html").read_text(),
        }

    @classmethod
    def tearDownClass(cls) -> None:
        cls.directory.cleanup()

    def test_marks_up_the_utc_instant_with_a_utc_fallback(self) -> None:
        for name, html in self.pages.items():
            with self.subTest(page=name):
                self.assertIn(
                    "<time datetime=2026-01-02T01:04:05Z data-local-time>"
                    "January 2, 2026 at 1:04 AM UTC</time>",
                    html,
                )

    def test_every_page_loads_the_local_time_script(self) -> None:
        for name, html in self.pages.items():
            with self.subTest(page=name):
                self.assertIn("/js/local-time.min.", html)


if __name__ == "__main__":
    unittest.main()
