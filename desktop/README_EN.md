# 同人游戏雷达 · Doujin Game Radar — Desktop

[中文](README.md) · **English**

> Cross-platform (Windows / macOS) desktop UI: **Tauri 2 + SvelteKit** frontend, backed by the Python data pipeline at the repository root.

## Status

🚧 **Work in progress (scaffold stage)**: a runnable development environment and project structure are in place; browsing, filtering, favorites and one-click updates land milestone by milestone.

## Requirements

| Dependency | Notes |
| --- | --- |
| Node.js | LTS (with npm) |
| Rust | Stable toolchain via [rustup](https://rustup.rs) |
| System WebView | macOS: WKWebView (built in); Windows: WebView2 (usually preinstalled on Win10+) |

## Commands

```bash
npm install          # install frontend dependencies
npm run tauri dev    # dev mode (hot reload, opens the app window)
npm run tauri build  # build packages (macOS: .app/.dmg; Windows: NSIS/MSI)
npm run check        # svelte-check type checking
```

## Relation to the data pipeline

The app reads exported work data as JSON (`works.json`) produced by the Python pipeline at the repository root;
data collection and maintenance stay with `dlsite_tracker` (see the root README).
