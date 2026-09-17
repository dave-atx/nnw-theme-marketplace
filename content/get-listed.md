---
title: "Get your theme listed"
description: "Publish a valid NetNewsWire theme release and the marketplace will discover it automatically."
---

The marketplace primarily indexes community themes on GitHub automatically. There is no submission form. A listing is not an endorsement by NetNewsWire or this marketplace, and it does not mean that a theme has received a security review.

## Listing requirements

1. Use a public, non-archived GitHub repository that is not a fork.
2. Add the GitHub topic `netnewswire-theme` or `netnewswire`.
3. Publish a non-draft, non-prerelease GitHub release.
4. Attach a ZIP named `Something.nnwtheme.zip` to the release. GitHub’s automatic “Source code” archives do not qualify.
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

Update those sources and the catalog will pick up the changes during its next refresh.

## Add a good screenshot

The marketplace first looks in the repository for PNG, JPEG, or WebP files whose path contains `screenshot`, `preview`, or `demo`. Images under `screenshots/`, `images/`, `assets/`, or `docs/` receive preference. Clear names such as these work well:

```text
screenshots/theme-preview.png
docs/assets/dark-screenshot.webp
```

If no repository image matches, the marketplace uses the first non-badge raster image embedded in the README. A 16:10 image works best; other aspect ratios are cropped from the top. If neither source exists, the card receives a neutral placeholder.

## Releases and download totals

Each new stable release should attach a fresh `*.nnwtheme.zip` asset. The card installs the newest stable release while its download count includes valid assets from all releases. Renaming an asset does not reset the total as long as the package keeps the same `ThemeIdentifier`.

The catalog refreshes automatically. A broken latest release removes the theme until a valid stable release is available, so test the ZIP before publishing it.

## Curated collections

The marketplace also has a small, source-controlled collection manifest for established catalogs that cannot meet the automatic rules. It currently covers the [PaiJi theme collection](https://paiji.github.io/NetNewsWire-themes-collection/) and themes from [Stuart Breckenridge's NetNewsWire theme page](https://stuartbreckenridge.net/projects/netnewswire-themes/).

Manifest entries still point to public, non-archived GitHub repositories and must pass the same package validation. They may use a release asset published by a collection repository or a GitHub tag archive. GitHub does not publish download counts for tag archives, so those cards say “Downloads unavailable” rather than showing a misleading zero.

The manifest records the source repository, exact release or tag, asset name where applicable, and optional display copy or screenshot. Changes are reviewed as marketplace source changes, keeping each exception explicit and auditable.
