# NetNewsWire Theme Marketplace

An independent, community-run catalog of themes for
[NetNewsWire](https://netnewswire.com/). Browse the marketplace at
[dave-atx.github.io/nnw-theme-marketplace](https://dave-atx.github.io/nnw-theme-marketplace/)
or subscribe to its
[JSON Feed](https://dave-atx.github.io/nnw-theme-marketplace/feed.json) in
NetNewsWire.

This project is not affiliated with or endorsed by NetNewsWire. Listings are
not security reviews. Check a theme's source and author before installing it.

## How themes are listed

The catalog searches public, non-archived GitHub repositories with the
`netnewswire` or `netnewswire-theme` topic. A repository qualifies when its
latest stable release contains a valid `*.nnwtheme.zip` asset. The indexer
validates the archive and required `Info.plist`, `template.html`, and
`stylesheet.css` files before publishing a listing.

Established catalogs that do not follow that release convention can be
declared in [`catalog/collections.json`](catalog/collections.json). Curated
entries use the same package validation and can select either a release asset
or a GitHub tag archive. See the site's
[listing guide](https://dave-atx.github.io/nnw-theme-marketplace/get-listed/)
for complete requirements and metadata rules.

Cards combine package metadata with GitHub repository details, stars, release
downloads, screenshots, and release dates. Lifetime download counts include
all valid release assets with the same stable `ThemeIdentifier`. GitHub does
not provide counts for tag archives, so those listings say that downloads are
unavailable.

## Local development

Requirements:

- [uv](https://docs.astral.sh/uv/)
- Python 3.14
- Hugo Extended 0.166.0 or newer
- `playwright-cli` with an installed Chromium browser for UI checks

Install the locked environment, refresh the catalog, and start Hugo:

```sh
uv sync --locked
uv run build-catalog
hugo server
```

Run the same checks used in CI:

```sh
uv run ruff check .
uv run ruff format --check .
uv run python -m unittest discover -s tests -v
hugo --panicOnWarning
```

After changing Python, run Ruff before any other validation:

```sh
uv run ruff check --fix .
uv run ruff format .
```

Set `GITHUB_TOKEN` or `GH_TOKEN` when refreshing the catalog to avoid GitHub's
anonymous API limit. When GitHub CLI is installed and authenticated, the
indexer uses its token automatically.

## Download trends

GitHub reports lifetime asset downloads but not historical counts. The indexer
derives seven-day activity from daily snapshots in
`.cache/download-history.json`. Git ignores this file; GitHub Actions carries
it between builds using a daily cache key. A new or evicted cache produces a
seven-day warm-up message rather than an invented trend.

## Deployment

[`pages.yml`](.github/workflows/pages.yml) validates pull requests and deploys
the site to GitHub Pages after every push to `main`, every manual run, and on a
30-minute schedule. Scheduled builds refresh GitHub metadata and retain trend
history in the Actions cache without committing generated state.

See [`docs/architecture.md`](docs/architecture.md) for the data flow,
repository layout, trust boundaries, and maintenance notes.

## License

Licensed under the [Apache License 2.0](LICENSE).
