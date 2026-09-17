from __future__ import annotations

import argparse
import base64
import json
import os
import plistlib
import re
import shutil
import stat
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.parsers.expat
import zipfile
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any

API_ROOT = "https://api.github.com"
TOPICS = ("netnewswire", "netnewswire-theme")
REQUIRED_FILES = ("Info.plist", "template.html", "stylesheet.css")
REQUIRED_PLIST_FIELDS = {
    "ThemeIdentifier": str,
    "Name": str,
    "CreatorHomePage": str,
    "CreatorName": str,
    "Version": int,
}
MAX_ASSET_BYTES = 25 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
RETRY_STATUSES = frozenset({500, 502, 503, 504})
REQUEST_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 2.0
MIN_CATALOG_RETENTION = 0.75


class CatalogError(RuntimeError):
    """A recoverable problem with one repository, release, or archive.

    Callers record these as diagnostics and continue with the next candidate.
    """


class CatalogNotFound(CatalogError):
    """GitHub has no such repository, release, or tag."""


class CatalogAborted(RuntimeError):
    """A problem that invalidates the whole run, such as exhausted API quota.

    Aborting keeps a partial catalog from being written over a complete one.
    """


@dataclass(frozen=True)
class Theme:
    id: str
    name: str
    creator_name: str
    creator_url: str
    author_github_url: str
    repository: str
    repository_url: str
    description: str
    stars: int
    release: str
    released_at: str
    asset_name: str
    asset_url: str
    downloads: int | None
    downloads_last_7_days: int | None
    install_url: str
    screenshot_url: str | None


def _github_token() -> str | None:
    for variable in ("GITHUB_TOKEN", "GH_TOKEN"):
        if token := os.environ.get(variable):
            return token
    if shutil.which("gh"):
        result = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, check=False
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    return None


class GitHub:
    def __init__(self, token: str | None):
        self.token = token

    def request(self, url: str) -> urllib.request.Request:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "nnw-theme-marketplace",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return urllib.request.Request(url, headers=headers)

    @staticmethod
    def _check_rate_limit(error: urllib.error.HTTPError, url: str) -> None:
        """Abort the run when GitHub reports exhausted quota rather than a real 403."""
        if error.code not in (403, 429):
            return
        headers = error.headers or {}
        exhausted = headers.get("x-ratelimit-remaining") == "0"
        throttled = headers.get("retry-after") is not None
        if error.code == 403 and not exhausted and not throttled:
            return
        reset = headers.get("x-ratelimit-reset")
        when = ""
        if reset and reset.isdigit():
            when = f" until {datetime.fromtimestamp(int(reset), UTC).isoformat()}"
        raise CatalogAborted(f"GitHub API quota exhausted{when} (requesting {url})")

    def _open(self, request: urllib.request.Request, timeout: int, limit: int | None) -> bytes:
        url = request.full_url
        for attempt in range(1, REQUEST_ATTEMPTS + 1):
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    return response.read() if limit is None else response.read(limit)
            except urllib.error.HTTPError as error:
                self._check_rate_limit(error, url)
                if error.code == 404:
                    raise CatalogNotFound(f"GitHub returned 404 for {url}") from error
                retryable = error.code in RETRY_STATUSES
                if not retryable or attempt == REQUEST_ATTEMPTS:
                    raise CatalogError(f"GitHub returned {error.code} for {url}") from error
                reason: object = error.code
            except (urllib.error.URLError, TimeoutError) as error:
                if attempt == REQUEST_ATTEMPTS:
                    raise CatalogError(f"could not reach {url}: {error}") from error
                reason = error
            print(f"  retrying {url} after {reason} (attempt {attempt}/{REQUEST_ATTEMPTS})")
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)
        raise AssertionError("unreachable")

    def json(self, path: str) -> Any:
        url = path if path.startswith("https://") else f"{API_ROOT}{path}"
        payload = self._open(self.request(url), timeout=30, limit=None)
        try:
            return json.loads(payload)
        except ValueError as error:
            raise CatalogError(f"GitHub returned invalid JSON for {url}") from error

    def bytes(self, url: str) -> bytes:
        request = self.request(url)
        request.headers["Accept"] = "application/octet-stream"
        content = self._open(request, timeout=60, limit=MAX_ASSET_BYTES + 1)
        if len(content) > MAX_ASSET_BYTES:
            raise CatalogError("release asset exceeds the 25 MiB validation limit")
        return content


def discover_repositories(github: GitHub) -> list[dict[str, Any]]:
    repositories: dict[int, dict[str, Any]] = {}
    for topic in TOPICS:
        page = 1
        while True:
            query = urllib.parse.urlencode({"q": f"topic:{topic}", "per_page": 100, "page": page})
            payload = github.json(f"/search/repositories?{query}")
            for repository in payload["items"]:
                repositories[repository["id"]] = repository
            if len(payload["items"]) < 100:
                break
            page += 1
    return sorted(repositories.values(), key=lambda item: item["full_name"].lower())


def _theme_roots(archive: zipfile.ZipFile, asset_name: str) -> list[PurePosixPath]:
    names = [PurePosixPath(name) for name in archive.namelist() if not name.endswith("/")]
    total_size = sum(info.file_size for info in archive.infolist())
    if total_size > MAX_UNCOMPRESSED_BYTES:
        raise CatalogError("expanded archive exceeds the 50 MiB validation limit")
    if any(path.is_absolute() or ".." in path.parts for path in names):
        raise CatalogError("archive contains an unsafe path")
    if any(stat.S_ISLNK(info.external_attr >> 16) for info in archive.infolist()):
        raise CatalogError("archive contains a symbolic link")

    roots: set[PurePosixPath] = set()
    for path in names:
        for index, part in enumerate(path.parts):
            if part.lower().endswith(".nnwtheme"):
                roots.add(PurePosixPath(*path.parts[: index + 1]))
                break

    if not roots and asset_name.lower().endswith(".nnwtheme.zip"):
        present = {path.as_posix() for path in names}
        if all(required in present for required in REQUIRED_FILES):
            roots.add(PurePosixPath("."))
    return sorted(roots, key=str)


def _archive_path(root: PurePosixPath, filename: str) -> str:
    return filename if root == PurePosixPath(".") else str(root / filename)


def _theme_metadata(raw: bytes, info_path: str) -> dict[str, Any]:
    """Parse and validate one Info.plist.

    Archives come from untrusted repositories, so any parser failure has to
    surface as a CatalogError that callers can record and skip past. plistlib
    raises ExpatError for malformed XML and returns whatever type the file
    declares, neither of which is a CatalogError on its own.
    """
    try:
        metadata = plistlib.loads(raw)
    except plistlib.InvalidFileException:
        raise
    except (xml.parsers.expat.ExpatError, ValueError, TypeError, OverflowError) as error:
        raise CatalogError(f"{info_path}: could not be parsed: {error}") from error
    if not isinstance(metadata, dict):
        raise CatalogError(f"{info_path}: top level must be a dictionary")
    for field, field_type in REQUIRED_PLIST_FIELDS.items():
        value = metadata.get(field)
        if field_type is int and isinstance(value, bool):
            raise CatalogError(f"{info_path}: {field} must be an integer")
        if not isinstance(value, field_type) or (isinstance(value, str) and not value.strip()):
            raise CatalogError(f"{info_path}: invalid {field}")
    return metadata


def themes_in_asset(content: bytes, asset_name: str) -> list[dict[str, Any]]:
    with tempfile.SpooledTemporaryFile(max_size=MAX_ASSET_BYTES) as file:
        file.write(content)
        file.seek(0)
        try:
            with zipfile.ZipFile(file) as archive:
                themes: list[dict[str, Any]] = []
                archive_names = set(archive.namelist())
                for root in _theme_roots(archive, asset_name):
                    required_paths = [_archive_path(root, name) for name in REQUIRED_FILES]
                    if not all(path in archive_names for path in required_paths):
                        continue
                    info_path = _archive_path(root, "Info.plist")
                    themes.append(_theme_metadata(archive.read(info_path), info_path))
                return themes
        except (zipfile.BadZipFile, plistlib.InvalidFileException) as error:
            raise CatalogError(f"invalid theme archive: {error}") from error


def _screenshot(github: GitHub, repository: dict[str, Any]) -> str | None:
    """Pick a preview image, or None.

    A screenshot is presentation only, so every lookup failure here degrades to
    no image rather than costing the repository its listing.
    """
    branch = repository["default_branch"]
    try:
        tree = github.json(
            f"/repos/{repository['full_name']}/git/trees/{urllib.parse.quote(branch)}?recursive=1"
        )
    except CatalogError:
        return _readme_screenshot(github, repository)
    candidates: list[tuple[int, str]] = []
    for item in tree.get("tree", []):
        path = item.get("path", "")
        lower = path.lower()
        if item.get("type") != "blob" or not lower.endswith((".png", ".jpg", ".jpeg", ".webp")):
            continue
        if item.get("size", 0) > 5 * 1024 * 1024:
            continue
        score = 0
        if any(word in lower for word in ("screenshot", "preview", "demo")):
            score += 20
        if any(part in lower for part in ("screenshots/", "images/", "assets/", "docs/")):
            score += 8
        if any(word in lower for word in ("icon", "logo", "badge", "avatar")):
            score -= 20
        if score > 0:
            candidates.append((score, path))
    if candidates:
        path = max(candidates, key=lambda candidate: (candidate[0], candidate[1]))[1]
        quoted_path = urllib.parse.quote(path, safe="/")
        return f"https://raw.githubusercontent.com/{repository['full_name']}/{branch}/{quoted_path}"
    return _readme_screenshot(github, repository)


def _readme_screenshot(github: GitHub, repository: dict[str, Any]) -> str | None:
    try:
        payload = github.json(f"/repos/{repository['full_name']}/readme")
        readme = base64.b64decode(payload["content"]).decode("utf-8", errors="replace")
    except CatalogError, KeyError, ValueError:
        return None

    markdown_images = re.findall(r"!\[[^]]*]\(([^\s)]+)", readme)
    html_images = re.findall(r"<img\b[^>]*\bsrc=[\"']([^\"']+)", readme, re.IGNORECASE)
    for source in [*html_images, *markdown_images]:
        lower = source.lower()
        if not lower.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
            continue
        if any(host in lower for host in ("shields.io", "badge", "github.com/actions")):
            continue
        if source.startswith("https://"):
            return source
        if source.startswith(("http://", "data:", "//")):
            continue
        path = urllib.parse.quote(source.removeprefix("./"), safe="/")
        return (
            f"https://raw.githubusercontent.com/{repository['full_name']}/"
            f"{repository['default_branch']}/{path}"
        )
    return None


def _install_url(asset_url: str) -> str:
    encoded = urllib.parse.quote(asset_url, safe="")
    return f"netnewswire://theme/add?url={encoded}"


def _theme_record(
    metadata: dict[str, Any],
    repository: dict[str, Any],
    *,
    release: str,
    released_at: str,
    asset_name: str,
    asset_url: str,
    downloads: int | None,
    screenshot_url: str | None,
    display: dict[str, Any] | None = None,
) -> Theme:
    display = display or {}
    return Theme(
        id=metadata["ThemeIdentifier"],
        name=display.get("name", metadata["Name"]),
        creator_name=metadata["CreatorName"],
        creator_url=metadata["CreatorHomePage"],
        author_github_url=repository["owner"]["html_url"],
        repository=repository["full_name"],
        repository_url=repository["html_url"],
        description=display.get("description")
        or repository.get("description")
        or "A community NetNewsWire theme.",
        stars=repository["stargazers_count"],
        release=release,
        released_at=released_at,
        asset_name=asset_name,
        asset_url=asset_url,
        downloads=downloads,
        downloads_last_7_days=None,
        install_url=_install_url(asset_url),
        screenshot_url=display.get("screenshot_url", screenshot_url),
    )


def index_curated_item(github: GitHub, item: dict[str, Any]) -> tuple[list[Theme], list[str]]:
    source_repository = github.json(f"/repos/{item['source_repository']}")
    if source_repository["archived"]:
        return [], ["source repository is archived"]
    if source_repository["fork"]:
        return [], ["source repository is a fork"]

    package = item["package"]
    package_repository = package.get("repository", item["source_repository"])
    kind = package["kind"]
    if kind == "release_asset":
        tag = package["tag"]
        release = github.json(
            f"/repos/{package_repository}/releases/tags/{urllib.parse.quote(tag, safe='')}"
        )
        if release["draft"]:
            return [], ["configured release is a draft"]
        asset = next(
            (asset for asset in release["assets"] if asset["name"] == package["asset"]),
            None,
        )
        if asset is None:
            return [], [f"release {tag} has no {package['asset']} asset"]
        asset_name = asset["name"]
        asset_url = asset["browser_download_url"]
        downloads: int | None = asset["download_count"]
        released_at = release["published_at"]
    elif kind == "tag_archive":
        tag = package["tag"]
        commit = github.json(
            f"/repos/{package_repository}/commits/{urllib.parse.quote(tag, safe='')}"
        )
        asset_name = f"{package_repository.rsplit('/', 1)[-1]}-{tag}.zip"
        asset_url = (
            f"https://github.com/{package_repository}/archive/refs/tags/"
            f"{urllib.parse.quote(tag, safe='')}.zip"
        )
        downloads = None
        released_at = commit["commit"]["committer"]["date"]
    else:
        raise CatalogError(f"unknown curated package kind: {kind}")

    metadata_items = themes_in_asset(github.bytes(asset_url), asset_name)
    identifier = item.get("theme_identifier")
    if identifier:
        metadata_items = [
            metadata for metadata in metadata_items if metadata["ThemeIdentifier"] == identifier
        ]
    if not metadata_items:
        return [], [f"{asset_name}: no matching valid .nnwtheme package found"]
    if len(metadata_items) > 1 and not identifier:
        return [], [f"{asset_name}: contains multiple themes; theme_identifier is required"]

    screenshot_url = item.get("display", {}).get("screenshot_url")
    if not screenshot_url:
        screenshot_url = _screenshot(github, source_repository)
    themes = [
        _theme_record(
            metadata,
            source_repository,
            release=tag,
            released_at=released_at,
            asset_name=asset_name,
            asset_url=asset_url,
            downloads=downloads,
            screenshot_url=screenshot_url,
            display=item.get("display"),
        )
        for metadata in metadata_items
    ]
    return themes, []


def index_collections(github: GitHub, path: Path) -> tuple[list[Theme], list[dict[str, Any]]]:
    if not path.exists():
        return [], []
    catalog = json.loads(path.read_text())
    themes: list[Theme] = []
    diagnostics: list[dict[str, Any]] = []
    for collection in catalog.get("collections", []):
        for item in collection.get("items", []):
            label = f"{collection['name']}: {item['source_repository']}"
            try:
                found, errors = index_curated_item(github, item)
            except (CatalogError, KeyError, urllib.error.HTTPError) as error:
                found, errors = [], [str(error)]
            themes.extend(found)
            diagnostics.append({"repository": label, "themes": len(found), "errors": errors})
            _report(label, found, errors)
    return themes, diagnostics


def index_repository(
    github: GitHub, repository: dict[str, Any], asset_themes: dict[str, list[str]]
) -> tuple[list[Theme], list[str]]:
    full_name = repository["full_name"]
    try:
        latest = github.json(f"/repos/{full_name}/releases/latest")
    except CatalogNotFound:
        return [], ["no published release"]

    assets = [
        asset
        for asset in latest["assets"]
        if asset["name"].lower().endswith(".nnwtheme.zip") and asset.get("state") == "uploaded"
    ]
    if not assets:
        return [], ["latest release has no .nnwtheme.zip asset"]

    screenshot_url = _screenshot(github, repository)
    themes: list[Theme] = []
    errors: list[str] = []
    metadata_by_asset_id: dict[int, list[dict[str, Any]]] = {}
    for asset in assets:
        try:
            metadata_by_asset_id[asset["id"]] = themes_in_asset(
                github.bytes(asset["browser_download_url"]), asset["name"]
            )
        except CatalogError as error:
            errors.append(f"{asset['name']}: {error}")
            metadata_by_asset_id[asset["id"]] = []
        asset_themes[str(asset["id"])] = [
            metadata["ThemeIdentifier"] for metadata in metadata_by_asset_id[asset["id"]]
        ]

    releases = github.json(f"/repos/{full_name}/releases?per_page=100")
    downloads_by_theme: dict[str, int] = {}
    for release in releases:
        if release["draft"]:
            continue
        for asset in release["assets"]:
            if not asset["name"].lower().endswith(".nnwtheme.zip"):
                continue
            for identifier in _asset_identifiers(github, asset, asset_themes):
                downloads_by_theme[identifier] = (
                    downloads_by_theme.get(identifier, 0) + asset["download_count"]
                )

    for asset in assets:
        metadata_items = metadata_by_asset_id[asset["id"]]
        for metadata in metadata_items:
            themes.append(
                _theme_record(
                    metadata,
                    repository,
                    release=latest["tag_name"],
                    released_at=latest["published_at"],
                    asset_name=asset["name"],
                    asset_url=asset["browser_download_url"],
                    downloads=downloads_by_theme.get(metadata["ThemeIdentifier"], 0),
                    screenshot_url=screenshot_url,
                )
            )
        if not metadata_items:
            errors.append(f"{asset['name']}: no valid .nnwtheme package found")
    return themes, errors


def _asset_identifiers(
    github: GitHub, asset: dict[str, Any], asset_themes: dict[str, list[str]]
) -> list[str]:
    """Return the theme identifiers an uploaded asset contains.

    A release asset is immutable, so this mapping is cached across runs. Only
    successful validations are cached; a failed download must stay retryable
    instead of permanently recording the asset as empty.
    """
    key = str(asset["id"])
    if key in asset_themes:
        return asset_themes[key]
    try:
        metadata_items = themes_in_asset(github.bytes(asset["browser_download_url"]), asset["name"])
    except CatalogError:
        return []
    identifiers = [metadata["ThemeIdentifier"] for metadata in metadata_items]
    asset_themes[key] = identifiers
    return identifiers


def load_cache(path: Path) -> dict[str, Any]:
    """Read the rolling build cache, tolerating a missing or corrupt file.

    The cache is restored from an Actions cache entry that can be evicted or
    written by an older revision, so a bad file degrades to a cold start rather
    than failing the run.
    """
    cache: dict[str, Any] = {"snapshots": [], "assets": {}}
    if not path.exists():
        return cache
    try:
        stored = json.loads(path.read_text())
    except ValueError as error:
        print(f"Ignoring unreadable cache at {path}: {error}")
        return cache
    if not isinstance(stored, dict):
        return cache
    if isinstance(stored.get("snapshots"), list):
        cache["snapshots"] = stored["snapshots"]
    if isinstance(stored.get("assets"), dict):
        cache["assets"] = stored["assets"]
    return cache


def save_cache(path: Path, cache: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n")


def _captured_at(snapshot: dict[str, Any]) -> datetime:
    captured = datetime.fromisoformat(snapshot["captured_at"])
    return captured if captured.tzinfo else captured.replace(tzinfo=UTC)


def apply_download_history(
    themes: list[Theme], cache: dict[str, Any], now: datetime | None = None
) -> list[Theme]:
    now = now or datetime.now(UTC)
    snapshots = [snapshot for snapshot in cache.get("snapshots", []) if "captured_at" in snapshot]

    cutoff = now - timedelta(days=7)
    eligible = [snapshot for snapshot in snapshots if _captured_at(snapshot) <= cutoff]
    baseline = max(eligible, key=_captured_at, default=None)

    measured: list[Theme] = []
    for theme in themes:
        weekly_downloads = None
        if baseline is not None and theme.downloads is not None:
            previous = baseline.get("downloads", {}).get(theme.id)
            if previous is not None:
                weekly_downloads = max(0, theme.downloads - previous)
        measured.append(replace(theme, downloads_last_7_days=weekly_downloads))

    if not any(_captured_at(snapshot).date() == now.date() for snapshot in snapshots):
        snapshots.append(
            {
                "captured_at": now.isoformat(),
                "downloads": {
                    theme.id: theme.downloads for theme in themes if theme.downloads is not None
                },
            }
        )
    retention_cutoff = now - timedelta(days=15)
    cache["snapshots"] = sorted(
        (snapshot for snapshot in snapshots if _captured_at(snapshot) >= retention_cutoff),
        key=_captured_at,
    )
    return measured


def build_catalog(
    output: Path,
    collections: Path = Path("catalog/collections.json"),
    history: Path = Path(".cache/download-history.json"),
    *,
    allow_shrink: bool = False,
) -> dict[str, Any]:
    previous_count = _published_theme_count(output)
    cache = load_cache(history)
    asset_themes = cache["assets"]

    github = GitHub(_github_token())
    repositories = discover_repositories(github)
    themes: list[Theme] = []
    diagnostics: list[dict[str, Any]] = []
    for repository in repositories:
        if repository["archived"] or repository["fork"]:
            continue
        try:
            found, errors = index_repository(github, repository, asset_themes)
        except CatalogError as error:
            found, errors = [], [str(error)]
        themes.extend(found)
        diagnostics.append(
            {
                "repository": repository["full_name"],
                "themes": len(found),
                "errors": errors,
            }
        )
        _report(repository["full_name"], found, errors)

    curated_themes, curated_diagnostics = index_collections(github, collections)
    themes.extend(curated_themes)
    diagnostics.extend(curated_diagnostics)

    unique_themes: dict[str, Theme] = {}
    for theme in themes:
        if theme.id in unique_themes:
            print(f"Ignoring duplicate {theme.id} from {theme.repository}")
            continue
        unique_themes[theme.id] = theme

    if not allow_shrink and previous_count:
        floor = int(previous_count * MIN_CATALOG_RETENTION)
        if len(unique_themes) < floor:
            raise CatalogAborted(
                f"refusing to publish {len(unique_themes)} themes after {previous_count}; "
                f"rerun when GitHub is healthy or pass --allow-shrink"
            )

    measured_themes = apply_download_history(list(unique_themes.values()), cache)
    save_cache(history, cache)
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "themes": [
            asdict(theme)
            for theme in sorted(measured_themes, key=lambda item: item.name.casefold())
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {len(unique_themes)} themes to {output}")
    _report_failures(diagnostics)
    return payload


def _published_theme_count(output: Path) -> int:
    """Count the themes in the catalog this run would replace."""
    try:
        published = json.loads(output.read_text())
    except OSError, ValueError:
        return 0
    themes = published.get("themes") if isinstance(published, dict) else None
    return len(themes) if isinstance(themes, list) else 0


def _report(label: str, found: list[Theme], errors: list[str]) -> None:
    print(f"{label}: {len(found)} theme{'s' if len(found) != 1 else ''}")
    for error in errors:
        print(f"  {error}")


def _report_failures(diagnostics: list[dict[str, Any]]) -> None:
    failed = [entry for entry in diagnostics if entry["errors"]]
    if not failed:
        return
    print(f"\n{len(failed)} candidate(s) produced no listing:")
    for entry in failed:
        for error in entry["errors"]:
            print(f"  {entry['repository']}: {error}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the NetNewsWire theme catalog")
    parser.add_argument("--output", type=Path, default=Path("data/themes.json"))
    parser.add_argument("--collections", type=Path, default=Path("catalog/collections.json"))
    parser.add_argument("--history", type=Path, default=Path(".cache/download-history.json"))
    parser.add_argument(
        "--allow-shrink",
        action="store_true",
        help="publish even if far fewer themes qualified than in the current catalog",
    )
    args = parser.parse_args()
    try:
        build_catalog(args.output, args.collections, args.history, allow_shrink=args.allow_shrink)
    except CatalogAborted as error:
        raise SystemExit(f"Catalog build aborted: {error}") from error


if __name__ == "__main__":
    main()
