# Doujin Game Finder (macOS desktop app)

This directory contains the source of the companion macOS desktop app: it reads data files exported by the "dlsite-tracker" pipeline (or your own CSV / JSON / saved HTML) and lets you browse & filter games locally.

**The app itself never uses the network and collects nothing** — all crawling is done by the pipeline (see the repository's root `README.md`). The in-app "Start update" button merely launches the pipeline scripts on your machine; network activity happens entirely inside the pipeline.

[中文](README.md) · **English**

## Build & run

```bash
bash scripts/build-app.sh                     # build with swiftc (needs only Xcode Command Line Tools)
open "app/dist/同人游戏筛选器.app"             # launch
```

- If Gatekeeper blocks the first launch: right-click → Open in Finder (the build is ad-hoc signed)
- Build output goes to `app/dist/` and is **not tracked**

## Usage

1. Open the app → "Select data file" → choose the pipeline export `out/works.json` (press ⌘⇧G in the file dialog to paste a path directly)
2. **"Start update" menu**: **"Quick hot update"** (~2–4 min: ranking / listing / popularity-order pages → enrich → sales → export) and **"Full maintenance"** (adds genre pages / covers / import resume); plus last 1/3/5/7 years, "Custom start year…" and "Fetch older…". The app **auto-reloads** when finished; the data file must be the pipeline project's `out/works.json` (the app derives the project directory from that path and launches the corresponding script)
3. **"Progressive import" switch** (sidebar): ON = start / resume in background (last one or three years), OFF = graceful pause (checkpoint kept, can be resumed anytime); "Cancel import task…" available while running (double confirmation); when the import finishes it auto-exports and **auto-reloads** — start it and forget it; your new works will be there when you come back
4. Covers appear automatically: `image_path` in `works.json` is a relative path (`covers/<RJ>.jpg`, resolved against the data file's directory)
5. After the pipeline runs, click "Update" to re-read — no need to re-select the file. "Update" actually means "export locally first (fully offline), then re-read", so it is always in sync with the database; falls back to re-read-only outside a pipeline project layout
6. Sidebar filters: rating / sales / price ranges (both ends inclusive; blank = no limit); genres support **multi-select include** (intersection) and **exclusion** (exclusion wins); release year **multi-select**; **content badges**: voice / music / video (all must match)
7. Sorting: sales / rating / price / **release date (new→old)** / **daily · weekly · monthly top ranks** (current rank ascending, 1 = hottest; unranked last) / title
8. Top banner: one-click update status first (`update-progress.json`: running / done / interrupted); otherwise progressive-import progress (`import-progress.json`: imported / excluded / skipped); auto-refreshes every 30 s while running
9. **View modes**: large cards / two-column / compact list / adaptive grid / cover wall (⌘1–⌘5, remembered); the "Personalization" panel toggles badges / discount badge + strikethrough original price / review counts
10. **Favorites & makers**: heart = add to "My favorites"; right-click = add to a collection (create new, multi-collection supported); sidebar "Collections" section manages collections and followed makers; click a maker name → all their works (follow, or open their DLsite maker page)
11. **Double-click a card** to open the work page; hover highlights
12. **Auto-sync on launch**: if the data file is newer than the local cache (e.g. after the nightly update), the app syncs & re-reads automatically — always up to date on open
13. **Sidebar**: always visible, fixed width; toggling expands/shrinks the window outward (content stays put; if there is not enough room on the left it expands left first, then right); smooth animation
14. **Card info**: genre / work form / content badges shown on three aligned rows (large cards labeled; medium cards show up to 5 genres + N); colored capsules for form & badges; compact data row (dates as MM-DD, rating without "/5"); wraps instead of truncating on narrow cards

## Data format notes

The app reads the exported `works[]` array; `category` and `form` are `" | "`-separated; unknown fields are ignored.

Rank-based sorting uses `rank_day_current` / `rank_week_current` / `rank_month_current` (**lower is hotter**, 1 = top of the chart) and `rank_trend_current` (official popularity order).

## Maintenance

- `app/DoujinGameFinder.swift` is the source of truth; build check: `bash scripts/build-app.sh`
- The repository contains no personal data; the app writes no logs and uploads nothing
