# 同人游戏雷达 · Doujin Game Radar — Desktop

[中文](README.md) · **English**

> Cross-platform (Windows / macOS) desktop app: **Tauri 2 + SvelteKit**; packaged builds **embed the data pipeline** (no Python required) — data, covers and favorites never leave your machine.

## Download

- **Windows**: grab `doujin-game-radar-windows-installer` from the latest ["Desktop Build (Windows)"](https://github.com/Faintimi/dlsite-tracker/actions/workflows/desktop-release.yml) run (or the Release page)
- **macOS / build it yourself**: run `bash scripts/build-sidecar.sh` at the repository root first (builds the embedded pipeline), then `npm install && npm run tauri build` (requirements below)

## Features (v0.1)

- Browse ~9k works: virtualized grid / cover wall / bottom info bar / compact list / strip (five view modes)
- Filters: keyword, genre intersection, year range, sales / price / rating, favorites & collections, followed makers only
- Sorting: sales / rating / release date / price / title
- Collections (multi-membership) and maker following; right-click quick menu; hover detail card
- **Discover** (computed locally in real time): rising dark horses (sprinting / high-hype), taste-matched new releases and hidden gems; a dedicated editor builds a three-level profile (love / like / show less) from visually selected favorite works, explainable collection analysis and human-oriented semantic groups; hovering for 2 seconds or opening marks a work as seen, with confirmed “Not interested” feedback
- **Followed updates**: detects releases from followed makers within the last 14 calendar days, with a summary banner, sidebar unread count, and a cover list grouped by maker; opening the list clears unread status while NEW labels remain for the full two-week window; “Check now” starts a quick data update and detects additions after reload
- **First run**: "Initialize data" on the empty state sets everything up on your machine (fetches the hot ranking in ~5–10 minutes) — no Python install, no repository clone
- **One-click update**: "更新数据 ▾" → quick hot update / full maintenance / deeper import / import last N years; live banner + auto-refresh when done (packaged builds use the embedded pipeline — no extra dependencies)

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
- **Embedded mode** (packaged builds / regular users): the app ships a single-file `radar-pipeline` binary (built with PyInstaller via `scripts/build-sidecar.sh`). On first run, "Initialize data" on the empty state writes the config, creates the database and fetches the hot ranking (~5–10 minutes, network-dependent) in the app data directory; every button (update / import / genre ranking) then calls it — **no Python install, no repository clone**.

On first launch the app **auto-discovers and binds** the data file: it walks up from the executable's directory, scans one level under `~/code`, `~/Code`, `~/Projects`, `~/Documents`, `~/Desktop` and your home directory for `<project>/out/works.json`, and also checks the embedded mode's app data directory (`<app data dir>/pipeline/out/works.json`), then remembers the path. Manual selection is only needed when discovery fails.
