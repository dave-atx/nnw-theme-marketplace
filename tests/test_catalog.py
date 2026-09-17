from __future__ import annotations

import io
import json
import plistlib
import struct
import tempfile
import unittest
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest import mock

from marketplace.catalog import (
    MAX_UNCOMPRESSED_BYTES,
    CatalogAborted,
    CatalogError,
    Theme,
    _screenshot,
    apply_download_history,
    build_catalog,
    load_cache,
    themes_in_asset,
)

METADATA = {
    "ThemeIdentifier": "org.example.Reader",
    "Name": "Reader",
    "CreatorHomePage": "https://example.org/reader",
    "CreatorName": "Example",
    "Version": 3,
}


def theme_archive(prefix: str = "Reader.nnwtheme/", **files: bytes | str) -> bytes:
    contents: dict[str, bytes | str] = {
        "Info.plist": plistlib.dumps(METADATA),
        "template.html": "<article></article>",
        "stylesheet.css": "article {}",
    }
    contents.update(files)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, data in contents.items():
            archive.writestr(f"{prefix}{name}", data)
    return output.getvalue()


def plist_with(**overrides: Any) -> bytes:
    metadata = METADATA | overrides
    return plistlib.dumps(metadata)


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

    def test_rejects_absolute_path(self) -> None:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("/etc/passwd", "root")
        with self.assertRaisesRegex(CatalogError, "unsafe path"):
            themes_in_asset(output.getvalue(), "Reader.nnwtheme.zip")

    def test_rejects_symbolic_link(self) -> None:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            info = zipfile.ZipInfo("Reader.nnwtheme/stylesheet.css")
            info.create_system = 3
            info.external_attr = (0o120777 << 16) | 0o600
            archive.writestr(info, "/etc/passwd")
        with self.assertRaisesRegex(CatalogError, "symbolic link"):
            themes_in_asset(output.getvalue(), "Reader.nnwtheme.zip")

    def test_rejects_oversized_expansion(self) -> None:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("Reader.nnwtheme/stylesheet.css", b"\0" * (MAX_UNCOMPRESSED_BYTES + 1))
        with self.assertRaisesRegex(CatalogError, "50 MiB"):
            themes_in_asset(output.getvalue(), "Reader.nnwtheme.zip")

    def test_requires_exact_theme_files(self) -> None:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("Reader.nnwtheme/info.plist", plistlib.dumps(METADATA))
            archive.writestr("Reader.nnwtheme/template.html", "")
            archive.writestr("Reader.nnwtheme/stylesheet.css", "")
        self.assertEqual(themes_in_asset(output.getvalue(), "Reader.nnwtheme.zip"), [])

    def test_rejects_corrupt_zip(self) -> None:
        with self.assertRaisesRegex(CatalogError, "invalid theme archive"):
            themes_in_asset(b"not a zip file", "Reader.nnwtheme.zip")


class PlistValidationTests(unittest.TestCase):
    """Every rejection here has to be a CatalogError so one bad repository is skipped."""

    def parse(self, plist: bytes) -> list[dict[str, Any]]:
        return themes_in_asset(theme_archive(**{"Info.plist": plist}), "Reader.nnwtheme.zip")

    def test_rejects_malformed_xml(self) -> None:
        with self.assertRaisesRegex(CatalogError, "could not be parsed"):
            self.parse(b"<?xml version='1.0'?><plist><dict><key>a</key>")

    def test_rejects_non_dictionary_root(self) -> None:
        with self.assertRaisesRegex(CatalogError, "must be a dictionary"):
            self.parse(b"<?xml version='1.0'?><plist version='1.0'><array/></plist>")

    def test_rejects_truncated_binary_plist(self) -> None:
        with self.assertRaises(CatalogError):
            self.parse(b"bplist00" + struct.pack(">Q", 2**63))

    def test_rejects_unparseable_bytes(self) -> None:
        with self.assertRaises(CatalogError):
            self.parse(b"hello world")

    def test_rejects_missing_field(self) -> None:
        metadata = {key: value for key, value in METADATA.items() if key != "CreatorName"}
        with self.assertRaisesRegex(CatalogError, "invalid CreatorName"):
            self.parse(plistlib.dumps(metadata))

    def test_rejects_blank_string_field(self) -> None:
        with self.assertRaisesRegex(CatalogError, "invalid Name"):
            self.parse(plist_with(Name="   "))

    def test_rejects_wrong_type_field(self) -> None:
        with self.assertRaisesRegex(CatalogError, "invalid Version"):
            self.parse(plist_with(Version="3"))

    def test_rejects_boolean_version(self) -> None:
        """bool is a subclass of int, so it needs an explicit guard."""
        with self.assertRaisesRegex(CatalogError, "Version must be an integer"):
            self.parse(plist_with(Version=True))


class UnreachableGitHub:
    """Stands in for GitHub when every request fails."""

    def json(self, path: str) -> Any:
        raise CatalogError(f"could not reach {path}")


class ScreenshotTests(unittest.TestCase):
    def test_missing_tree_and_readme_costs_only_the_screenshot(self) -> None:
        repository = {"full_name": "example/reader", "default_branch": "main"}
        self.assertIsNone(_screenshot(UnreachableGitHub(), repository))


class CacheTests(unittest.TestCase):
    def test_missing_file_starts_cold(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = load_cache(Path(directory) / "absent.json")
        self.assertEqual(cache, {"snapshots": [], "assets": {}})

    def test_corrupt_file_starts_cold_instead_of_failing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache.json"
            path.write_text("{ not json")
            cache = load_cache(path)
        self.assertEqual(cache, {"snapshots": [], "assets": {}})

    def test_reads_snapshots_and_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache.json"
            path.write_text(json.dumps({"snapshots": [{"captured_at": "x"}], "assets": {"1": []}}))
            cache = load_cache(path)
        self.assertEqual(cache["snapshots"], [{"captured_at": "x"}])
        self.assertEqual(cache["assets"], {"1": []})


class ShrinkGuardTests(unittest.TestCase):
    """A partial outage must not replace a complete catalog with an empty one."""

    def build(self, directory: str, published: int, **kwargs: Any) -> dict[str, Any]:
        output = Path(directory) / "themes.json"
        output.write_text(json.dumps({"themes": [{"id": str(n)} for n in range(published)]}))
        with (
            mock.patch("marketplace.catalog._github_token", return_value=None),
            mock.patch("marketplace.catalog.discover_repositories", return_value=[]),
            mock.patch("marketplace.catalog.index_collections", return_value=([], [])),
        ):
            return build_catalog(
                output,
                Path(directory) / "collections.json",
                Path(directory) / "cache.json",
                **kwargs,
            )

    def test_refuses_to_publish_a_collapsed_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(CatalogAborted, "refusing to publish"):
                self.build(directory, published=17)
            published = json.loads((Path(directory) / "themes.json").read_text())
        self.assertEqual(len(published["themes"]), 17, "the existing catalog must survive")

    def test_allow_shrink_overrides_the_guard(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            payload = self.build(directory, published=17, allow_shrink=True)
        self.assertEqual(payload["themes"], [])

    def test_first_ever_build_has_no_floor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            payload = self.build(directory, published=0)
        self.assertEqual(payload["themes"], [])


class DownloadHistoryTests(unittest.TestCase):
    def theme(self, downloads: int | None, identifier: str = "org.example.Reader") -> Theme:
        return Theme(
            id=identifier,
            name="Reader",
            creator_name="Example",
            creator_url="https://example.org",
            author_github_url="https://github.com/example",
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
        cache: dict[str, Any] = {"snapshots": [], "assets": {}}
        initial = apply_download_history([self.theme(100)], cache, datetime(2026, 1, 1, tzinfo=UTC))
        current = apply_download_history([self.theme(127)], cache, datetime(2026, 1, 8, tzinfo=UTC))

        self.assertIsNone(initial[0].downloads_last_7_days)
        self.assertEqual(current[0].downloads_last_7_days, 27)

    def test_records_one_snapshot_per_day(self) -> None:
        cache: dict[str, Any] = {"snapshots": [], "assets": {}}
        apply_download_history([self.theme(100)], cache, datetime(2026, 1, 1, 1, tzinfo=UTC))
        apply_download_history([self.theme(120)], cache, datetime(2026, 1, 1, 23, tzinfo=UTC))
        self.assertEqual(len(cache["snapshots"]), 1)
        self.assertEqual(cache["snapshots"][0]["downloads"]["org.example.Reader"], 100)

    def test_clamps_negative_deltas(self) -> None:
        """A deleted release can lower a lifetime total; never report a negative trend."""
        cache: dict[str, Any] = {"snapshots": [], "assets": {}}
        apply_download_history([self.theme(100)], cache, datetime(2026, 1, 1, tzinfo=UTC))
        current = apply_download_history([self.theme(40)], cache, datetime(2026, 1, 8, tzinfo=UTC))
        self.assertEqual(current[0].downloads_last_7_days, 0)

    def test_ignores_baseline_younger_than_seven_days(self) -> None:
        cache: dict[str, Any] = {"snapshots": [], "assets": {}}
        apply_download_history([self.theme(100)], cache, datetime(2026, 1, 1, tzinfo=UTC))
        current = apply_download_history([self.theme(127)], cache, datetime(2026, 1, 5, tzinfo=UTC))
        self.assertIsNone(current[0].downloads_last_7_days)

    def test_leaves_untracked_downloads_unmeasured(self) -> None:
        cache: dict[str, Any] = {"snapshots": [], "assets": {}}
        apply_download_history([self.theme(None)], cache, datetime(2026, 1, 1, tzinfo=UTC))
        current = apply_download_history(
            [self.theme(None)], cache, datetime(2026, 1, 8, tzinfo=UTC)
        )
        self.assertIsNone(current[0].downloads_last_7_days)
        self.assertEqual(cache["snapshots"][0]["downloads"], {})

    def test_reports_nothing_for_a_theme_absent_from_the_baseline(self) -> None:
        cache: dict[str, Any] = {"snapshots": [], "assets": {}}
        apply_download_history([self.theme(100)], cache, datetime(2026, 1, 1, tzinfo=UTC))
        current = apply_download_history(
            [self.theme(50, "org.example.Newcomer")], cache, datetime(2026, 1, 8, tzinfo=UTC)
        )
        self.assertIsNone(current[0].downloads_last_7_days)

    def test_discards_snapshots_older_than_retention(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=UTC)
        cache: dict[str, Any] = {"snapshots": [], "assets": {}}
        for day in range(0, 40, 5):
            apply_download_history([self.theme(100 + day)], cache, start + timedelta(days=day))
        oldest = datetime.fromisoformat(cache["snapshots"][0]["captured_at"])
        self.assertGreaterEqual(oldest, start + timedelta(days=35) - timedelta(days=15))
        self.assertEqual(
            cache["snapshots"], sorted(cache["snapshots"], key=lambda item: item["captured_at"])
        )

    def test_tolerates_naive_timestamps_from_an_older_cache(self) -> None:
        cache: dict[str, Any] = {
            "snapshots": [
                {"captured_at": "2026-01-01T00:00:00", "downloads": {"org.example.Reader": 100}}
            ],
            "assets": {},
        }
        current = apply_download_history([self.theme(127)], cache, datetime(2026, 1, 8, tzinfo=UTC))
        self.assertEqual(current[0].downloads_last_7_days, 27)


if __name__ == "__main__":
    unittest.main()
