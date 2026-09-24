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
| `src/marketplace/preview.py` | Sample weekly downloads mounted over `data/` for Trending tests and local preview |
| `catalog/collections.json` | Reviewed exceptions for established catalogs and tag-based themes |
| `catalog/` | Source-controlled catalog policy; runtime history must not be stored here |
| `.cache/download-history.json` | Ignored build cache: rolling download snapshots plus the release-asset to theme-identifier map, restored through Actions cache |
| `data/themes.json` | Generated Hugo input, kept in Git so Hugo can run without network access |
| `layouts/` | Hugo HTML and JSON Feed templates |
| `assets/` | Hugo-managed CSS and JavaScript |
| `static/` | Files copied directly to the published site, including feed and browser icons |
| `content/` | Standalone documentation and install-route content |
| `tests/` | Python archive-validation and trend-calculation tests, plus Hugo render tests for the feed and Trending section |
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

## Feed dates

Each feed item's `date_published` is its release date. `date_modified` is the
later of that release date and the `feedContentModified` site parameter.

That parameter is maintained by hand and records when the JSON Feed template
last changed the rendered `content_html`. Editing the template changes every
item's content without changing any release date, and nothing can derive that
fact automatically, so bump `feedContentModified` in `hugo.toml` whenever you
change what `index.jsonfeed.json` renders. Taking the later of the two dates
keeps an item from reporting a modification that precedes its publication.

## Trend history

GitHub exposes current lifetime download totals only. Each UTC day, the first
scheduled build stores the current numeric totals in the ignored history file.
The generator compares current totals with the newest snapshot at least seven
days old and clamps negative deltas to zero. It keeps 15 days of snapshots.

Actions cache entries are immutable, so the workflow uses a new key per UTC
day and restores the newest prior key by prefix. Later builds on the same day
restore the exact cache entry. If history disappears, weekly values remain
unknown until a complete baseline exists and the Trending section stays hidden.

The committed `data/themes.json` therefore carries no weekly counts, so
`marketplace.preview` copies it with sample counts into a temporary data
directory that a Hugo module mount places ahead of `data/`. The Trending render
tests and `uv run preview-trending` both use this overlay; neither commits a
second catalog that could drift from the generated one.

The same cache file stores which theme identifiers each release asset contains.
A release asset is immutable, so that mapping is computed once and reused,
which keeps lifetime download totals from re-downloading and re-validating
every historical asset on every scheduled build. Only successful validations
are cached, so a failed download stays retryable. Because the day's first build
is the one that writes the cache, assets first seen later in a day are resolved
again until the next day's first build.

## Failure handling

Repository metadata and theme archives are untrusted, so any one candidate can
fail without ending the run: parse and validation failures raise `CatalogError`,
which the per-candidate loops record as a diagnostic and print to the build log.

Two conditions are fatal instead. Exhausted GitHub API quota raises
`CatalogAborted`, because continuing would turn every remaining repository into
a spurious "no themes" result. And the generator refuses to write a catalog
holding less than 75% of the themes the committed one lists, so a partial
outage cannot replace a complete site with an empty one. `--allow-shrink`
overrides that guard when listings really did go away.

Transient HTTP failures and connection errors are retried with backoff before
they become a `CatalogError`.

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
