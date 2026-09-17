# Contributing

Thanks for helping improve the marketplace.

## Theme listings

Most themes should not require a pull request. Follow the public
[listing requirements](https://dave-atx.github.io/nnw-theme-marketplace/get-listed/)
and the scheduled indexer will discover the repository.

The collection manifest is reserved for established catalogs or notable theme
sources that cannot use the automatic release convention. A manifest change
must explain why automatic discovery is insufficient and must point to a
public, non-archived source repository. Curated packages receive the same
validation as automatic listings.

## Code and documentation

Open an issue for substantial behavior or policy changes before investing in a
large implementation. Small fixes can go directly to a pull request.

Use Python 3.14 through `uv`. After editing Python, lint and format everything:

```sh
uv run ruff check --fix .
uv run ruff format .
```

Before opening a pull request, run:

```sh
uv run ruff check .
uv run ruff format --check .
uv run python -m unittest discover -s tests -v
hugo --panicOnWarning
```

Do not commit `public/`, `.cache/`, credentials, local URLs, or browser-test
artifacts. `data/themes.json` is generated and intentionally committed;
download history is runtime state and intentionally ignored.

By contributing, you agree that your contribution is licensed under the
Apache License 2.0.
