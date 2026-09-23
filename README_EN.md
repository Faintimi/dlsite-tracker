# Doujin Game Radar · 同人游戏雷达

> **A cross-platform desktop browser & filter for DLsite doujin games (Windows / macOS)**, backed by a robots-compliant daily data pipeline: sales / hot rankings / genre popularity refreshed every day — with genre-intersection filters, favorites and maker tracking. **All data and cover images stay on your machine.**
>
> *跨平台（Windows / macOS）的 DLsite 同人游戏浏览与筛选应用：每日自动更新销量 / 热榜 / 分类人气，支持分类交集筛选、收藏夹与制作者追踪——数据与封面全部只存在你本机。*

[中文](README.md) · **English**

- **Local-first**: no account, no telemetry, no cloud; neither the app nor the pipeline sends any data anywhere
- **Compliant crawling**: only public pages and the site's own public APIs, strict robots compliance (`Crawl-delay: 10`), public metadata only
- **Unofficial project**: not affiliated with DLsite; the store contains adult content — intended for adult users

## What it does

The pipeline collects public DLsite product metadata (title / circle / price / rating / review count / sales / genres / rankings …) into a local SQLite database, and exports it as JSON / CSV plus cover thumbnails. Companion desktop apps (Windows / macOS, plus a native macOS app) read the export and provide browsing, filtering, favorites and one-click updates. **The apps never use the network** — all crawling happens inside the pipeline.

## Highlights

- **Daily maintenance** (default 23:30): hot rankings / on-ranking sales / genre popularity / official popularity order
- **Two-tier one-click update in the app**: "Quick hot update" (~1–2 min) and "Full maintenance" (adds genre pages, covers, import resume); the list **auto-refreshes** when done
- **Filters**: keyword, genre intersection, release year, sales / price / rating, favorites & collections, followed makers only
- **Sorting**: sales / rating / price / release date / title
- **Favorites** (a work can belong to multiple collections), **maker following**, **hover detail card**, **right-click quick menu**, five view modes (grid / cover wall / bottom info bar / compact list / strip)
- Live progress banner during updates; list auto-refreshes when finished

## Quick start

Requirements: **macOS / Windows / Linux + Python ≥ 3.9** (standard library only, zero third-party dependencies — no `pip install` needed).

```bash
git clone https://github.com/Faintimi/dlsite-tracker.git
cd dlsite-tracker
cp config.example.ini config.ini          # local config (not tracked; includes rate-limit notes)

python3 -m dlsite_tracker init            # initialize data dir + database
python3 -m dlsite_tracker update          # daily update (hot mode)
python3 -m dlsite_tracker import-recent --dry-run --years 1   # estimate a 1-year import (offline)
python3 -m dlsite_tracker import-recent --years 1             # progressive import (resumable, pausable)
python3 -m dlsite_tracker export          # export out/works.json + works.csv
python3 -m dlsite_tracker --help          # all commands
```

One-shot chains (same as the app buttons):

```bash
bash scripts/quick-update.sh              # quick hot update (~2–4 min)
bash scripts/update-all.sh 1              # import last year → sales → covers → export
bash scripts/install-schedule.sh          # daily 23:30 maintenance (launchd, no sudo; uninstall: uninstall-schedule.sh)
```

> Note: because of polite rate limiting (≥10 s per page), the first full import takes some patience; afterwards only fast incremental updates run.

## Desktop apps

Two UIs to choose from (both read the same `out/works.json`; favorites and settings are stored per app, so they never interfere):

### Cross-platform desktop (Windows / macOS, recommended)

- **Windows**: download the latest `doujin-game-radar-windows-installer` artifact from [Actions "Desktop Build (Windows)"](https://github.com/Faintimi/dlsite-tracker/actions/workflows/desktop-release.yml) (or the Release page)
- **Build it yourself** (macOS / Windows):

```bash
cd desktop
npm install
npm run tauri build        # output: src-tauri/target/release/bundle/ (.app/.dmg on macOS, NSIS on Windows)
```

- First launch: click **Open data file…** and pick the exported `out/works.json` — it is remembered afterwards
- **Update ▾**: quick hot update / full maintenance / deeper import / import last N years; a live banner shows progress and the list auto-refreshes when done (requires Python ≥ 3.9 + this repo's pipeline)
- Features: filters (genre intersection / year / sales / price / rating / favorites / followed makers), sorting, five view modes, hover detail card, collections and a right-click menu
- See [`desktop/README.md`](desktop/README.md) / [`desktop/README_EN.md`](desktop/README_EN.md)

### Native macOS app (SwiftUI)

```bash
bash scripts/build-app.sh                 # build (needs only Xcode Command Line Tools)
open "app/dist/同人游戏筛选器.app"
```

In the app: "Select data file" → choose the exported `out/works.json`. See [`app/README.md`](app/README.md) / [`app/README_EN.md`](app/README_EN.md).

## Privacy & security

- No login, no cookies, no tokens; no user content is ever collected
- Crawling is limited to public pages / public site APIs, strictly following robots (`Crawl-delay: 10`)
- All data and covers are written only to local `data/` and `out/` (git-ignored, never committed)
- The apps are offline; "Update" merely launches this repository's fixed task chains on your machine (`scripts/*.sh` / `python -m dlsite_tracker task …`)
- This repository contains code and docs only — no personal data, no store content

## Data sources & compliance

| Source | Purpose | Constraint |
| --- | --- | --- |
| Sitemap | full / incremental discovery | public entrypoint provided for crawlers |
| `product.json` | per-work details (title / circle / price / rating / genres …) | public JSON |
| `product/info/ajax` (batched, 80 per request) | sales / wishlist count / type / release date | public site API; rate-limited |
| Ranking / listing / genre-popularity / popularity-order pages | rank & sales snapshots | ≥10 s between pages |

- Please read DLsite's terms of use and robots rules before using this project; for personal study & research use only
- You are responsible for compliance if you redistribute the outputs at scale or use them commercially

## License

[MIT](LICENSE) © 2026 Faintimi · Unofficial project, not affiliated with DLsite
