"""Gallery manifests: TOML files that describe one or more themes.

The same format is read from two places with different trust. A theme
repository may commit `nnw-marketplace.toml` to give each theme in its latest
stable release its own card copy. That hosted file is untrusted: it may only
describe themes its own release already ships. Files under `catalog/galleries/`
are reviewed policy for galleries that can't meet the automatic rules, so they
may also name a source repository and pin a package.
"""

from __future__ import annotations

import re
import tomllib
import urllib.parse
from dataclasses import dataclass, replace
from typing import Any

HOSTED_FILENAME = "nnw-marketplace.toml"
FORMAT_VERSION = 1
MAX_MANIFEST_BYTES = 16 * 1024
MAX_THEMES = 50
MAX_NAME_CHARS = 80
MAX_DESCRIPTION_CHARS = 300
MAX_FIELD_CHARS = 255
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
REPOSITORY_PATTERN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?/[A-Za-z0-9._-]+")
CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")

TOP_LEVEL_KEYS = frozenset({"version", "gallery", "theme"})
GALLERY_KEYS = frozenset({"name", "homepage"})
HOSTED_THEME_KEYS = frozenset({"id", "name", "description", "screenshot"})
CURATED_THEME_KEYS = HOSTED_THEME_KEYS | {"source", "package"}
PACKAGE_KEYS = frozenset({"repository", "tag", "asset"})


class ManifestError(ValueError):
    """A manifest that can't be used as written."""


@dataclass(frozen=True)
class Package:
    """A pinned package. Without an asset it is GitHub's archive of the tag."""

    tag: str
    asset: str | None = None
    repository: str | None = None


@dataclass(frozen=True)
class GalleryTheme:
    id: str
    name: str | None = None
    description: str | None = None
    screenshot: str | None = None
    source: str | None = None
    package: Package | None = None

    @property
    def package_repository(self) -> str:
        assert self.source is not None and self.package is not None
        return self.package.repository or self.source


@dataclass(frozen=True)
class Gallery:
    name: str | None
    homepage: str | None
    themes: tuple[GalleryTheme, ...]


def parse_gallery(raw: bytes, *, curated: bool) -> Gallery:
    """Parse and validate one manifest.

    Hosted manifests arrive from untrusted repositories, so every parser
    failure becomes a ManifestError. tomllib has no depth limit of its own;
    the size cap keeps its recursion bounded, and RecursionError is caught in
    case a pathological file still reaches it.
    """
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ManifestError(f"exceeds the {MAX_MANIFEST_BYTES // 1024} KiB limit")
    try:
        document = tomllib.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise ManifestError("is not UTF-8 text") from error
    except (tomllib.TOMLDecodeError, RecursionError) as error:
        raise ManifestError(f"is not valid TOML: {error}") from error

    _check_keys(document, TOP_LEVEL_KEYS, "top level")
    version = document.get("version")
    if type(version) is not int or version != FORMAT_VERSION:
        raise ManifestError(f"version must be {FORMAT_VERSION}")

    gallery = document.get("gallery", {})
    if not isinstance(gallery, dict):
        raise ManifestError("[gallery] must be a table")
    _check_keys(gallery, GALLERY_KEYS, "[gallery]")
    name = _text(gallery, "name", "[gallery]", MAX_NAME_CHARS)
    homepage = _https_url(gallery, "homepage", "[gallery]")
    if curated and (name is None or homepage is None):
        raise ManifestError("[gallery] needs a name and homepage")

    entries = document.get("theme", [])
    if not isinstance(entries, list) or not all(isinstance(entry, dict) for entry in entries):
        raise ManifestError("theme must be an array of [[theme]] tables")
    if not entries:
        raise ManifestError("lists no [[theme]] entries")
    if len(entries) > MAX_THEMES:
        raise ManifestError(f"lists more than {MAX_THEMES} themes")

    themes = tuple(
        _theme(entry, f"[[theme]] {index}", curated=curated)
        for index, entry in enumerate(entries, start=1)
    )
    seen: set[str] = set()
    for theme in themes:
        if theme.id in seen:
            raise ManifestError(f"lists {theme.id} more than once")
        seen.add(theme.id)
    return Gallery(name=name, homepage=homepage, themes=themes)


def _theme(entry: dict[str, Any], label: str, *, curated: bool) -> GalleryTheme:
    _check_keys(entry, CURATED_THEME_KEYS if curated else HOSTED_THEME_KEYS, label)
    identifier = _token(entry, "id", label)
    if identifier is None:
        raise ManifestError(f"{label}: id is required")
    label = f"{label} ({identifier})"
    theme = GalleryTheme(
        id=identifier,
        name=_text(entry, "name", label, MAX_NAME_CHARS),
        description=_text(entry, "description", label, MAX_DESCRIPTION_CHARS),
        screenshot=(
            _https_url(entry, "screenshot", label)
            if curated
            else _image_path(entry, "screenshot", label)
        ),
    )
    if not curated:
        return theme

    source = _repository(entry, "source", label)
    if source is None:
        raise ManifestError(f"{label}: source is required")
    package = entry.get("package")
    if not isinstance(package, dict):
        raise ManifestError(f"{label}: package must be a table")
    _check_keys(package, PACKAGE_KEYS, f"{label} package")
    tag = _token(package, "tag", f"{label} package")
    if tag is None:
        raise ManifestError(f"{label}: package needs a tag")
    asset = _token(package, "asset", f"{label} package")
    if asset is not None and "/" in asset:
        raise ManifestError(f"{label}: package asset must be a file name")
    return replace(
        theme,
        source=source,
        package=Package(
            tag=tag,
            asset=asset,
            repository=_repository(package, "repository", f"{label} package"),
        ),
    )


def _check_keys(table: dict[str, Any], allowed: frozenset[str], label: str) -> None:
    unknown = sorted(set(table) - allowed)
    if unknown:
        raise ManifestError(f"{label}: unknown key {', '.join(unknown)}")


def _string(table: dict[str, Any], key: str, label: str, limit: int) -> str | None:
    if key not in table:
        return None
    value = table[key]
    if not isinstance(value, str):
        raise ManifestError(f"{label}: {key} must be a string")
    if len(value) > limit:
        raise ManifestError(f"{label}: {key} is longer than {limit} characters")
    return value


def _text(table: dict[str, Any], key: str, label: str, limit: int) -> str | None:
    """Card copy. Whitespace runs collapse so multi-line TOML strings read as prose."""
    value = _string(table, key, label, limit * 2)
    if value is None:
        return None
    text = " ".join(value.split())
    if not text:
        raise ManifestError(f"{label}: {key} is blank")
    if len(text) > limit:
        raise ManifestError(f"{label}: {key} is longer than {limit} characters")
    if CONTROL_CHARACTERS.search(text):
        raise ManifestError(f"{label}: {key} contains a control character")
    return text


def _token(table: dict[str, Any], key: str, label: str) -> str | None:
    value = _string(table, key, label, MAX_FIELD_CHARS)
    if value is None:
        return None
    if not value or any(character.isspace() for character in value):
        raise ManifestError(f"{label}: {key} must be non-empty with no whitespace")
    if CONTROL_CHARACTERS.search(value):
        raise ManifestError(f"{label}: {key} contains a control character")
    return value


def _repository(table: dict[str, Any], key: str, label: str) -> str | None:
    value = _token(table, key, label)
    if value is not None and not REPOSITORY_PATTERN.fullmatch(value):
        raise ManifestError(f"{label}: {key} must be a GitHub owner/name")
    return value


def _https_url(table: dict[str, Any], key: str, label: str) -> str | None:
    value = _token(table, key, label)
    if value is None:
        return None
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ManifestError(f"{label}: {key} must be an https URL")
    return value


def _image_path(table: dict[str, Any], key: str, label: str) -> str | None:
    """A repository-relative image path. Hosted manifests never supply URLs."""
    value = _token(table, key, label)
    if value is None:
        return None
    # An empty part catches a leading slash and doubled slashes.
    if (
        "\\" in value
        or any(part in ("", ".", "..") for part in value.split("/"))
        or not value.lower().endswith(IMAGE_SUFFIXES)
    ):
        raise ManifestError(
            f"{label}: {key} must be a relative path to a PNG, JPEG, or WebP file in the repository"
        )
    return value
