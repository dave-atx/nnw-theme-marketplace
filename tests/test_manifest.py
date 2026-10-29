from __future__ import annotations

import unittest

from marketplace.manifest import (
    MAX_DESCRIPTION_CHARS,
    MAX_MANIFEST_BYTES,
    Gallery,
    GalleryTheme,
    ManifestError,
    Package,
    parse_gallery,
)

HOSTED = """
version = 1

[gallery]
name = "Daisy"
homepage = "https://example.org/daisy"

[[theme]]
id = "org.example.daisy"
description = \"\"\"
  Editorial serif theme
  with a house style.
\"\"\"
screenshot = "screenshots/daisy.png"

[[theme]]
id = "org.example.daisy-sans"
name = "Daisy Sans"
"""

CURATED = """
version = 1

[gallery]
name = "Example collection"
homepage = "https://example.org/collection"

[[theme]]
id = "org.example.reader"
source = "example/reader"
screenshot = "https://example.org/reader.png"

[theme.package]
repository = "example/collection"
tag = "1.0.0"
asset = "Reader.nnwtheme.zip"

[[theme]]
id = "org.example.archive"
source = "example/archive"

[theme.package]
tag = "v1"
"""


def hosted(body: str, version: int = 1) -> bytes:
    return f"version = {version}\n{body}".encode()


def curated(theme: str, package: str = 'tag = "v1"') -> bytes:
    return (
        'version = 1\n[gallery]\nname = "G"\nhomepage = "https://example.org"\n'
        f'[[theme]]\nid = "org.example.reader"\nsource = "example/reader"\n{theme}\n'
        f"[theme.package]\n{package}\n"
    ).encode()


class HostedManifestTests(unittest.TestCase):
    def test_reads_card_copy_for_each_theme(self) -> None:
        gallery = parse_gallery(HOSTED.encode(), curated=False)
        self.assertEqual(
            gallery,
            Gallery(
                name="Daisy",
                homepage="https://example.org/daisy",
                themes=(
                    GalleryTheme(
                        id="org.example.daisy",
                        description="Editorial serif theme with a house style.",
                        screenshot="screenshots/daisy.png",
                    ),
                    GalleryTheme(id="org.example.daisy-sans", name="Daisy Sans"),
                ),
            ),
        )

    def test_gallery_table_is_optional(self) -> None:
        gallery = parse_gallery(hosted('[[theme]]\nid = "org.example.a"'), curated=False)
        self.assertIsNone(gallery.name)
        self.assertEqual([theme.id for theme in gallery.themes], ["org.example.a"])

    def test_rejects_source_and_package(self) -> None:
        for extra in ('source = "other/repo"', 'package = { tag = "v1" }'):
            with self.subTest(extra=extra), self.assertRaisesRegex(ManifestError, "unknown key"):
                parse_gallery(hosted(f'[[theme]]\nid = "org.example.a"\n{extra}'), curated=False)

    def test_rejects_screenshot_urls_and_unsafe_paths(self) -> None:
        for path in (
            "https://example.org/a.png",
            "/screenshots/a.png",
            "../a.png",
            "screenshots/../../a.png",
            "./a.png",
            "screenshots//a.png",
            "screenshots\\\\a.png",
            "screenshots/a.gif",
            "screenshots/a.svg",
        ):
            body = f'[[theme]]\nid = "org.example.a"\nscreenshot = "{path}"'
            with self.subTest(path=path), self.assertRaisesRegex(ManifestError, "relative path"):
                parse_gallery(hosted(body), curated=False)

    def test_accepts_nested_image_paths_in_any_case(self) -> None:
        body = '[[theme]]\nid = "org.example.a"\nscreenshot = "docs/Shots/A.WebP"'
        [theme] = parse_gallery(hosted(body), curated=False).themes
        self.assertEqual(theme.screenshot, "docs/Shots/A.WebP")


class ManifestValidationTests(unittest.TestCase):
    def test_rejects_oversized_file_before_parsing(self) -> None:
        raw = b"#" * (MAX_MANIFEST_BYTES + 1)
        with self.assertRaisesRegex(ManifestError, "KiB limit"):
            parse_gallery(raw, curated=False)

    def test_rejects_invalid_toml_and_encoding(self) -> None:
        for raw in (b"version = ", b"version = 1\n[[theme]\n", b"\xff\xfe"):
            with self.subTest(raw=raw), self.assertRaises(ManifestError):
                parse_gallery(raw, curated=False)

    def test_survives_deep_nesting(self) -> None:
        """tomllib recurses per nesting level; a file under the size cap can still overflow."""
        raw = b"version = 1\nx = " + b"[" * 8000 + b"]" * 8000
        self.assertLessEqual(len(raw), MAX_MANIFEST_BYTES)
        with self.assertRaisesRegex(ManifestError, "not valid TOML"):
            parse_gallery(raw, curated=False)

    def test_requires_version_one(self) -> None:
        body = '[[theme]]\nid = "org.example.a"'
        for raw in (body.encode(), hosted(body, 2), hosted(body).replace(b"1", b"true", 1)):
            with self.subTest(raw=raw), self.assertRaisesRegex(ManifestError, "version"):
                parse_gallery(raw, curated=False)

    def test_rejects_unknown_keys_to_surface_typos(self) -> None:
        for body in (
            'descripton = "x"\n[[theme]]\nid = "org.example.a"',
            '[[theme]]\nid = "org.example.a"\ndescripton = "x"',
            '[gallery]\nhomepge = "https://example.org"\n[[theme]]\nid = "org.example.a"',
        ):
            with self.subTest(body=body), self.assertRaisesRegex(ManifestError, "unknown key"):
                parse_gallery(hosted(body), curated=False)

    def test_unquoted_dotted_identifier_tables_are_rejected(self) -> None:
        """The [themes.com.example.a] mistake must fail rather than nest quietly."""
        with self.assertRaisesRegex(ManifestError, "unknown key themes"):
            parse_gallery(hosted('[themes.org.example.a]\ndescription = "x"'), curated=False)

    def test_requires_theme_entries_with_ids(self) -> None:
        cases = {
            "": "no \\[\\[theme\\]\\]",
            'theme = "x"': "array",
            '[[theme]]\nname = "A"': "id is required",
            '[[theme]]\nid = ""': "non-empty",
            '[[theme]]\nid = "org example"': "no whitespace",
            "[[theme]]\nid = 7": "must be a string",
        }
        for body, message in cases.items():
            with self.subTest(body=body), self.assertRaisesRegex(ManifestError, message):
                parse_gallery(hosted(body), curated=False)

    def test_rejects_duplicate_identifiers(self) -> None:
        body = '[[theme]]\nid = "org.example.a"\n[[theme]]\nid = "org.example.a"'
        with self.assertRaisesRegex(ManifestError, "more than once"):
            parse_gallery(hosted(body), curated=False)

    def test_caps_and_cleans_card_copy(self) -> None:
        long = "x" * (MAX_DESCRIPTION_CHARS + 1)
        cases = {
            f'description = "{long}"': "longer than",
            'description = "   "': "blank",
            'description = "a\\u0007b"': "control character",
            "description = 3": "must be a string",
        }
        for line, message in cases.items():
            body = f'[[theme]]\nid = "org.example.a"\n{line}'
            with self.subTest(line=line), self.assertRaisesRegex(ManifestError, message):
                parse_gallery(hosted(body), curated=False)

    def test_homepage_must_be_https(self) -> None:
        for url in ("http://example.org", "javascript:alert(1)", "https://user@example.org"):
            body = f'[gallery]\nhomepage = "{url}"\n[[theme]]\nid = "org.example.a"'
            with self.subTest(url=url), self.assertRaisesRegex(ManifestError, "https URL"):
                parse_gallery(hosted(body), curated=False)


class CuratedManifestTests(unittest.TestCase):
    def test_reads_sources_and_pinned_packages(self) -> None:
        gallery = parse_gallery(CURATED.encode(), curated=True)
        self.assertEqual(
            [(theme.source, theme.package, theme.package_repository) for theme in gallery.themes],
            [
                (
                    "example/reader",
                    Package(
                        tag="1.0.0", asset="Reader.nnwtheme.zip", repository="example/collection"
                    ),
                    "example/collection",
                ),
                ("example/archive", Package(tag="v1"), "example/archive"),
            ],
        )
        self.assertEqual(gallery.themes[0].screenshot, "https://example.org/reader.png")

    def test_requires_gallery_name_and_homepage(self) -> None:
        raw = CURATED.replace('name = "Example collection"\n', "").encode()
        with self.assertRaisesRegex(ManifestError, "name and homepage"):
            parse_gallery(raw, curated=True)

    def test_requires_source_and_tag(self) -> None:
        without_source = CURATED.replace('source = "example/archive"\n', "").encode()
        with self.assertRaisesRegex(ManifestError, "source is required"):
            parse_gallery(without_source, curated=True)
        with self.assertRaisesRegex(ManifestError, "needs a tag"):
            parse_gallery(curated("", 'asset = "A.zip"'), curated=True)

    def test_validates_repositories_and_assets(self) -> None:
        cases = {
            ("", 'tag = "v1"\nrepository = "not a repo"'): "no whitespace",
            ("", 'tag = "v1"\nrepository = "example"'): "owner/name",
            ("", 'tag = "v1"\nasset = "../A.zip"'): "file name",
            ("", 'tag = "v1"\nkind = "tag_archive"'): "unknown key kind",
            ('screenshot = "images/a.png"', 'tag = "v1"'): "https URL",
        }
        for (theme, package), message in cases.items():
            with self.subTest(package=package), self.assertRaisesRegex(ManifestError, message):
                parse_gallery(curated(theme, package), curated=True)


if __name__ == "__main__":
    unittest.main()
