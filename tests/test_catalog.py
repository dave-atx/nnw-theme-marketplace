from __future__ import annotations

import io
import plistlib
import tempfile
import unittest
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from marketplace.catalog import (
    CatalogError,
    Theme,
    apply_download_history,
    themes_in_asset,
)

METADATA = {
    "ThemeIdentifier": "org.example.Reader",
    "Name": "Reader",
    "CreatorHomePage": "https://example.org/reader",
    "CreatorName": "Example",
    "Version": 3,
}


def theme_archive(prefix: str = "Reader.nnwtheme/") -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(f"{prefix}Info.plist", plistlib.dumps(METADATA))
        archive.writestr(f"{prefix}template.html", "<article></article>")
        archive.writestr(f"{prefix}stylesheet.css", "article {}")
    return output.getvalue()


class ThemeArchiveTests(unittest.TestCase):
    def test_reads_theme_package(self) -> None:
        self.assertEqual(themes_in_asset(theme_archive(), "Reader.nnwtheme.zip"), [METADATA])

    def test_reads_flat_archive_with_conventional_asset_name(self) -> None:
        self.assertEqual(
            themes_in_asset(theme_archive(prefix=""), "Reader.nnwtheme.zip"),
            [METADATA],
        )

    def test_rejects_parent_path(self) -> None:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("../Reader.nnwtheme/Info.plist", plistlib.dumps(METADATA))
        with self.assertRaisesRegex(CatalogError, "unsafe path"):
            themes_in_asset(output.getvalue(), "Reader.nnwtheme.zip")

    def test_requires_exact_theme_files(self) -> None:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("Reader.nnwtheme/info.plist", plistlib.dumps(METADATA))
            archive.writestr("Reader.nnwtheme/template.html", "")
            archive.writestr("Reader.nnwtheme/stylesheet.css", "")
        self.assertEqual(themes_in_asset(output.getvalue(), "Reader.nnwtheme.zip"), [])


class DownloadHistoryTests(unittest.TestCase):
    def theme(self, downloads: int) -> Theme:
        return Theme(
            id="org.example.Reader",
            name="Reader",
            creator_name="Example",
            creator_url="https://example.org",
            author_github_url="https://github.com/example",
            version=1,
            repository="example/reader",
            repository_url="https://github.com/example/reader",
            description="Example theme",
            stars=1,
            release="v1",
            released_at="2026-01-01T00:00:00+00:00",
            asset_name="Reader.nnwtheme.zip",
            asset_url="https://example.org/Reader.nnwtheme.zip",
            downloads=downloads,
            downloads_last_7_days=None,
            install_url="netnewswire://theme/add?url=example",
            screenshot_url=None,
        )

    def test_calculates_downloads_from_seven_day_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            history = Path(directory) / "history.json"
            initial, _ = apply_download_history(
                [self.theme(100)], history, datetime(2026, 1, 1, tzinfo=UTC)
            )
            current, _ = apply_download_history(
                [self.theme(127)], history, datetime(2026, 1, 8, tzinfo=UTC)
            )

        self.assertIsNone(initial[0].downloads_last_7_days)
        self.assertEqual(current[0].downloads_last_7_days, 27)


if __name__ == "__main__":
    unittest.main()
