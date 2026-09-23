# 同人游戏雷达 · Doujin Game Radar — Desktop

[中文](README.md) · **English**

> Cross-platform (Windows / macOS) desktop app: **Tauri 2 + SvelteKit**; data comes from the Python pipeline at the repository root — covers and favorites never leave your machine.

## Download

- **Windows**: grab `doujin-game-radar-windows-installer` from the latest ["Desktop Build (Windows)"](https://github.com/Faintimi/dlsite-tracker/actions/workflows/desktop-release.yml) run (or the Release page)
- **macOS / build it yourself**: `npm install && npm run tauri build` (requirements below)

## Features (v0.1)

- Browse ~9k works: virtualized grid / cover wall / bottom info bar / compact list / strip (five view modes)
- Filters: keyword, genre intersection, year range, sales / price / rating, favorites & collections, followed makers only
- Sorting: sales / rating / release date / price / title
- Collections (multi-membership) and maker following; right-click quick menu; hover detail card
- **One-click update**: "更新数据 ▾" → quick hot update / full maintenance / deeper import / import last N years; live banner + auto-refresh when done (requires Python ≥ 3.9 + this repo's pipeline)

## Requirements

| Dependency | Notes |
| --- | --- |
| Node.js | LTS (with npm) |
| Rust | Stable toolchain via [rustup](https://rustup.rs) |
| System WebView | macOS: WKWebView (built in); Windows: WebView2 (usually preinstalled on Win10+) |
| Python ≥ 3.9 | Only for the in-app update feature (pipeline lives in this repo) |

## Commands

```bash
npm install          # install dependencies
npm run tauri dev    # dev mode (hot reload)
npm run tauri build  # build packages (macOS: .app/.dmg; Windows: NSIS)
npm run check        # svelte-check type checking
```

## Relation to the data pipeline

The app reads the pipeline's exported `out/works.json` (schema v2) and the neighbouring `covers/`; collection and maintenance stay with `dlsite_tracker` at the repository root (see the root README). The "Update" button merely launches the repository's fixed task chains on your machine (`scripts/*.sh` / `python -m dlsite_tracker task …`).
