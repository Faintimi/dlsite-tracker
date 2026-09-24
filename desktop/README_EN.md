# 同人游戏雷达 · Doujin Game Radar — Desktop

[中文](README.md) · **English**

> Cross-platform (Windows / macOS) desktop app: **Tauri 2 + SvelteKit**; packaged builds **embed the data pipeline** (no Python required) — data, covers and favorites never leave your machine.

DLsite remains the source for product information and purchases. Radar organizes public product data into a longer-term personal discovery workflow: spot potential hits from sales changes and wishlist signals, intersect independent filters, explore older works through your own taste profile, and catch new releases from followed creators. Reasons and source signals are visible, while collections and taste preferences stay local; purchases and downloads remain on the official store. The feature list describes the current source tree; consult each release's notes for what a published installer includes.

## Download

- **Windows**: grab `doujin-game-radar-windows-installer` from the latest ["Desktop Build (Windows)"](https://github.com/Faintimi/dlsite-tracker/actions/workflows/desktop-release.yml) run (or the Release page)
- **macOS / build it yourself**: run `bash scripts/build-sidecar.sh` at the repository root first (builds the embedded pipeline), then `npm install && npm run tauri build` (requirements below)

## Features

- Browse works imported into your local library: virtualized grid / cover wall / bottom info bar / compact list / strip (five view modes)
- In public, use “隐藏图片” in the toolbar to replace every work cover with a neutral placeholder; use “显示图片” to restore them. Your choice is saved locally for the next launch and does not alter cover files.
- Filters: keyword, genre intersection, year range, sales / price / rating, favorites & collections, followed makers only
- Sorting: sales / rating / release date / price / title
- Collections (multi-membership) and maker following; right-click quick menu; hover detail card
- Card ratings have a new top tier at a precise score of 4.70 or above: the number still reads 5, but this tier is pink instead of the ordinary 5-point gold; scores above 4.0 through 4.5 use orange-red gold. Hover details show the official two-decimal score. Normal updates automatically populate precise scores for older works through the existing batch API.
- Following is a separate collapsible sidebar section alongside Collections: collapsed on first use, remembers its state, and keeps the unread new-release count visible in its header
- **Discover** (computed locally in real time): rising dark horses (sprinting / high-hype), taste-matched new releases and hidden gems; a dedicated editor builds a three-level profile (love / like / show less) from visually selected favorite works, explainable collection analysis and human-oriented semantic groups; hovering for 2 seconds or opening marks a work as seen, with confirmed “Not interested” feedback
- **Followed updates**: detects releases from followed makers within the last 14 calendar days, with a summary banner, sidebar unread count, and a cover list grouped by maker; opening the list clears unread status while NEW labels remain for the full two-week window; “Check now” starts a quick data update and detects additions after reload
- **Navigation**: Discover returns to the page you came from; entering Discover again starts at the top with default sections and a fresh hidden-gem batch. A maker opened from Followed updates has a return link. Reselecting a collection or using the toolbar's manual Refresh starts at the top; background reloads preserve your place in the work list. A new launch still starts in Browse.
- **Genre-ranking shortcut**: left-click a genre chip on a work card to filter, or right-click it to manage that genre's official ranking. A new ranking imports the top 200 after confirmation and offers a View action on completion without leaving the current page; an imported ranking can be opened or added to/removed from daily refresh. Only exact official name-to-ID matches are used; duplicate names require a choice, and missing names are never guessed.
- **First run**: "Initialize data" on the empty state sets everything up on your machine (fetches the hot ranking in ~5–10 minutes) — no Python install, no repository clone
- **One-click update**: "更新数据 ▾" → quick hot update / full maintenance / deeper import / import last N years; live banner + auto-refresh when done (packaged builds use the embedded pipeline — no extra dependencies)
- **Coordinated tasks**: a running progressive import yields at a work/page boundary for a hot-ranking update, then continues in the same process from its checkpoint. Windows and macOS use the same file locks to prevent duplicate imports and concurrent database writes. If it cannot yield safely within two minutes, the update asks you to retry later.

## Requirements

| Dependency | Notes |
| --- | --- |
| Node.js | LTS (with npm) |
| Rust | Stable toolchain via [rustup](https://rustup.rs) |
| System WebView | macOS: WKWebView (built in); Windows: WebView2 (usually preinstalled on Win10+) |
| Python ≥ 3.9 | Needed to build the embedded pipeline and for "repository mode"; not required at runtime in packaged builds |

## Commands

```bash
npm install          # install dependencies
npm run tauri dev    # dev mode (hot reload; uses "repository + system Python")
bash ../scripts/build-sidecar.sh  # build the embedded pipeline (required once before packaging; artifacts are not committed)
npm run tauri build  # build packages (macOS: .app/.dmg; Windows: NSIS; embeds the pipeline)
npm run check        # svelte-check type checking
```

## Relation to the data pipeline

The app reads the pipeline's exported `out/works.json` (schema v3) and the neighbouring `covers/`; collection and maintenance stay with `dlsite_tracker` at the repository root (see the root README). The "Update" button merely launches the fixed task chains on your machine.

**Two pipeline modes** (auto-detected):

- **Repository mode** (development / power users): when the data directory is a full repository (containing the `dlsite_tracker/` package), the app runs system Python and `scripts/*.sh` (requires Python ≥ 3.9);
- **Embedded mode** (packaged builds / regular users): the app ships a single-file `radar-pipeline` binary (built with PyInstaller via `scripts/build-sidecar.sh`). On first run, "Initialize data" on the empty state writes the config, creates the database, enriches the hot ranking, downloads covers, and performs the final export (~5–10 minutes, network-dependent) in the app data directory; every update chain completes covers for newly added works and automatically repairs the zero-cover state left by older builds — **no Python install, no repository clone, and no extra console window on Windows**.

On first launch the app **auto-discovers and binds** the data file: it walks up from the executable's directory, scans one level under `~/code`, `~/Code`, `~/Projects`, `~/Documents`, `~/Desktop` and your home directory for `<project>/out/works.json`, and also checks the embedded mode's app data directory (`<app data dir>/pipeline/out/works.json`), then remembers the path. Manual selection is only needed when discovery fails.
