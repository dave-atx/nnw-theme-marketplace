---
title: "List several themes from one repository"
description: "Give each theme in a multi-theme repository its own description and screenshot with an nnw-marketplace.toml file."
---

Most themes should live in a repository of their own. The [usual listing rules]({{< relref "get-listed.md" >}}) need no extra files, and each theme gets its own stars, description, and screenshot from its repository.

Sometimes themes belong together. They might be variants built from one stylesheet, or a set that's always released as a group. The marketplace lists every valid `*.nnwtheme.zip` attached to a repository's latest stable release, so a single release can already list several themes. Each one gets its own page and download count, joined by its `ThemeIdentifier`.

What they share by default is the repository's description and screenshot, so the cards look the same apart from their names. To give each theme its own card, add an `nnw-marketplace.toml` file to the repository root.

## Example

```toml
[[theme]]
id = "com.example.lantern"
description = "A warm serif theme with generous margins for long reads."
screenshot = "screenshots/lantern.png"

[[theme]]
id = "com.example.lantern-sans"
description = """
  Lantern's layout and colors with a sans-serif font stack,
  for readers who prefer it on screen.
"""
screenshot = "screenshots/lantern-sans.png"
```

The marketplace reads the file **as of your latest stable release's tag**, not from your default branch. Commit changes to the file, then publish a release, and the cards update on the next catalog refresh. Edits you haven't released yet don't show up.

## Fields

| Field | Required | Meaning |
| --- | --- | --- |
| `[[theme]]` `id` | Yes | The theme's `ThemeIdentifier` from its `Info.plist`. |
| `[[theme]]` `name` | No | The name shown on the card instead of the `Info.plist` `Name`. Up to 80 characters. |
| `[[theme]]` `description` | No | The card description, instead of the repository description. Up to 300 characters. Line breaks and repeated spaces become single spaces. |
| `[[theme]]` `screenshot` | No | Path to a PNG, JPEG, or WebP image in the repository, such as `screenshots/lantern.png`. 5 MB at most. |

Add one `[[theme]]` table for each theme you want to describe. A theme the file doesn't mention keeps the repository's description and screenshot.

## Rules

- **The file can only describe themes your release ships.** It can't add a theme, point at another repository, or pin an older release. An `id` that isn't in the latest release is ignored.
- **Screenshots are paths, not URLs.** Write them relative to the repository root, without a leading `/` or `./`. The image must exist at the release's tag. If it doesn't, that card falls back to the repository's usual screenshot.
- **Mistakes don't remove your listing.** If the file is invalid (bad TOML, an unknown field, a value that's too long), the marketplace ignores the whole file and your themes list as they would without it. Fix the file and publish a new release.
- **Put the identifier in `id`, not in a table header.** Write `[[theme]]` followed by `id = "com.example.lantern"`. A header like `[themes.com.example.lantern]` is rejected, because TOML reads each dot as another nested table.
- The file must be smaller than 16 KB and describe at most 50 themes.

## Check your file

Any TOML parser can check the syntax. With Python 3.11 or newer:

```sh
python3 -c 'import sys, tomllib; tomllib.load(open(sys.argv[1], "rb")); print("ok")' nnw-marketplace.toml
```

That catches syntax errors but not the rules above. If a card doesn't change after a release, look for your repository in the [catalog build logs](https://github.com/dave-atx/nnw-theme-marketplace/actions/workflows/pages.yml). Every problem the marketplace finds with the file is listed there.

## Curated galleries use the same format

A few established galleries can't meet the automatic rules. Their authors publish no release ZIPs, or a mirror repository packages the themes for them. The marketplace keeps a file in this same format for each of those in its own repository, under [`catalog/galleries/`](https://github.com/dave-atx/nnw-theme-marketplace/tree/main/catalog/galleries). Those files are reviewed changes to the marketplace, so they may also name a `source` repository and pin a `[theme.package]`, which a hosted file can't do. They're also a good set of examples.
