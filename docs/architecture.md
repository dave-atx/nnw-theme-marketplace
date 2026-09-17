# Architecture

## System overview

The marketplace is a static Hugo site backed by a Python catalog generator.
There is no application server or database.

1. `marketplace.catalog` discovers GitHub repositories by topic and reads the
   explicit collection manifest.
2. It downloads candidate theme archives, validates their structure and plist
   metadata, enriches them with GitHub metadata, and writes `data/themes.json`.
3. Hugo renders the home page, listing guide, install handoff page, and JSON
   Feed into `public/`.
4. GitHub Actions uploads that directory as a Pages artifact and deploys it.

The scheduled workflow repeats this process every 30 minutes. GitHub Pages
serves only static output.

## Repository layout

| Path | Purpose |
| --- | --- |
| `src/marketplace/catalog.py` | GitHub discovery, archive validation, metadata enrichment, and trend calculation |
| `catalog/collections.json` | Reviewed exceptions for established catalogs and tag-based themes |
| `catalog/` | Source-controlled catalog policy; runtime history must not be stored here |
| `.cache/download-history.json` | Ignored rolling download snapshots restored through Actions cache |
| `data/themes.json` | Generated Hugo input, kept in Git so Hugo can run without network access |
| `layouts/` | Hugo HTML and JSON Feed templates |
| `assets/` | Hugo-managed CSS and JavaScript |
| `static/` | Files copied directly to the published site, including feed and browser icons |
| `content/` | Standalone documentation and install-route content |
| `tests/` | Python archive-validation and trend-calculation tests |
| `.github/workflows/pages.yml` | CI, scheduled catalog refresh, and Pages deployment |

## Discovery and validation

Automatic discovery searches for both `netnewswire` and `netnewswire-theme`
topics. Duplicate repositories are merged by GitHub repository ID. Archived
repositories and forks are ignored.

An automatic listing uses the latest non-draft, non-prerelease release and
requires an uploaded filename ending in `.nnwtheme.zip`. Download totals scan
all non-draft releases, including prereleases, and join valid assets by
`ThemeIdentifier`.

The collection manifest handles known sources that cannot satisfy automatic
discovery. A manifest entry identifies its source repository and either:

- an exact release tag and asset, optionally hosted by a collection repository;
- an exact GitHub tag archive.

Both paths use the same archive validator. The validator limits compressed and
expanded sizes, rejects path traversal and symbolic links, requires exact
case-sensitive filenames, and validates required plist values and types.

## Presentation data

Theme package metadata is authoritative for the theme identifier, name,
creator, creator home page, and version. GitHub supplies the repository URL,
owner profile, stars, release date, and download counts. Repository images and
README images are inspected for a screenshot. Curated entries may override
display names, descriptions, and screenshots without changing package
identity.

The JSON Feed embeds screenshots in each item's HTML. Its install link opens a
same-site HTTP page because NetNewsWire does not consistently make custom URL
schemes clickable in feed content. That page requires a click or tap before
navigating to the catalogued `netnewswire://` install URL. It accepts only a
theme identifier present in the generated catalog.

## Trend history

GitHub exposes current lifetime download totals only. Each UTC day, the first
scheduled build stores the current numeric totals in the ignored history file.
The generator compares current totals with the newest snapshot at least seven
days old and clamps negative deltas to zero. It keeps 15 days of snapshots.

Actions cache entries are immutable, so the workflow uses a new key per UTC
day and restores the newest prior key by prefix. Later builds on the same day
restore the exact cache entry. If history disappears, weekly values remain
unknown until a complete baseline exists.

## CI and deployment

Every workflow run installs the locked `uv` environment, checks all Python with
Ruff, runs unit tests, and performs a warning-strict Hugo build. Pull requests
use the checked-in catalog and never deploy. Pushes to `main`, scheduled runs,
and manual runs refresh the catalog, restore trend history, upload the Pages
artifact, and deploy it.

The configured base URL includes the GitHub project path. Internal links must
use Hugo's `relURL` or `absURL` helpers; root-relative links will point at the
wrong site on project Pages.

## Trust boundaries

Repository metadata, plist values, descriptions, images, and archives are
untrusted community input. Keep archive validation ahead of metadata use and
escape values through Hugo's contextual template handling. Do not execute
theme contents. Install redirects must resolve through the generated theme map
instead of accepting an arbitrary target URL from a query parameter.
