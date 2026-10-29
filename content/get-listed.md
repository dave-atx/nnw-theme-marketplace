---
title: "Get your theme listed"
description: "Publish a valid NetNewsWire theme release and the marketplace will discover it automatically."
---

The marketplace finds themes on GitHub by itself, so there's no submission form. A listing isn't an endorsement by [NetNewsWire](https://netnewswire.com/) or this marketplace, and it doesn't mean anyone has reviewed the theme for security.

## Create a theme

New to theme authoring? Start with the [NetNewsWire theme template](https://github.com/dave-atx/netnewswire-theme-template). Choose **Use this template → Create a new repository** on GitHub, not **Fork**. It includes guided setup, a preview gallery, and automated checks and release builds. You can follow its instructions yourself or work with a coding agent.

## Listing requirements

1. Use a public, non-archived GitHub repository that is not a fork.
2. Add the GitHub topic `netnewswire-theme` or `netnewswire`.
3. Publish a non-draft, non-prerelease GitHub release.
4. Attach a ZIP named `Something.nnwtheme.zip` to the release. GitHub’s automatic “Source code” archives don't count.
5. Put a valid `.nnwtheme` package in that ZIP.

The package must contain these exact filenames:

```text
Something.nnwtheme/
├── Info.plist
├── stylesheet.css
└── template.html
```

`Info.plist` must provide `ThemeIdentifier`, `Name`, `CreatorHomePage`, `CreatorName`, and an integer `Version`. Keep `ThemeIdentifier` stable across releases: the marketplace uses it to join download counts across every version of the same theme.

## What appears on a card

| Card field | Source |
| --- | --- |
| Theme name and creator | `Name` and `CreatorName` in `Info.plist` |
| Theme home | `CreatorHomePage` in `Info.plist` |
| Author link | GitHub profile of the repository owner |
| Description | GitHub repository description |
| Version and updated date | Latest stable GitHub release |
| Stars | GitHub repository star count |
| Downloads | Sum of downloads for every valid release asset with the same `ThemeIdentifier`, including prereleases |
| Install button | Latest stable `*.nnwtheme.zip` release asset |

Update those sources and the catalog picks up the changes on its next refresh. It refreshes a few times a day.

## Add a good screenshot

The marketplace first looks in the repository for PNG, JPEG, or WebP files whose path contains `screenshot`, `preview`, or `demo`. Images under `screenshots/`, `images/`, `assets/`, or `docs/` win ties. Clear names such as these work well:

```text
screenshots/theme-preview.png
docs/assets/dark-screenshot.webp
```

If no repository image matches, the marketplace uses the first non-badge raster image embedded in the README. A 16:10 image works best; other aspect ratios are cropped from the top. If neither exists, the card gets a neutral placeholder.

## Releases and download totals

Each new stable release should attach a fresh `*.nnwtheme.zip` asset. The card installs the newest stable release while its download count includes valid assets from all releases. Renaming an asset doesn't reset the total as long as the package keeps the same `ThemeIdentifier`.

A broken latest release removes the theme until a valid stable release is available, so test the ZIP before publishing it.

## Several themes in one repository

One theme per repository is simplest. If your themes need to stay together, attach each theme's ZIP to the same release. They all get listed, with separate pages and download counts. To give each one its own description and screenshot, see [List several themes from one repository]({{< relref "several-themes.md" >}}).

## Curated galleries

The marketplace also keeps a small set of reviewed gallery files for established catalogs that can't meet the automatic rules. They currently cover the [PaiJi theme collection](https://paiji.github.io/NetNewsWire-themes-collection/) and themes from [Stuart Breckenridge's NetNewsWire theme page](https://stuartbreckenridge.net/projects/netnewswire-themes/).

These entries still point to public, non-archived GitHub repositories and must pass the same package validation. They may use a release asset published by a collection repository or a GitHub tag archive. GitHub doesn't count downloads for tag archives, so those cards say “Downloads unavailable.”

Each gallery is a TOML file in [`catalog/galleries/`](https://github.com/dave-atx/nnw-theme-marketplace/tree/main/catalog/galleries). It uses the same format a repository can host for its own themes, plus a source repository and pinned release or tag for each entry. Every entry is a reviewed change to this repository, and a comment in the file records why it's an exception.
