# Doujin Game Radar · 同人游戏雷达

> **A local-first browser & filter for DLsite doujin games on macOS**, backed by a robots-compliant daily data pipeline: sales / hot rankings / genre popularity refreshed every day — with genre-intersection filters, favorites and maker tracking. **All data and cover images stay on your machine.**
>
> *macOS 上的 DLsite 同人游戏浏览与筛选应用：每日自动更新销量 / 热榜 / 分类人气，支持分类交集筛选、收藏夹与制作者追踪——数据与封面全部只存在你本机。*

[中文](README.md) · **English**

- **Local-first**: no account, no telemetry, no cloud; neither the app nor the pipeline sends any data anywhere
- **Compliant crawling**: only public pages and the site's own public APIs, strict robots compliance (`Crawl-delay: 10`), public metadata only
- **Unofficial project**: not affiliated with DLsite; the store contains adult content — intended for adult users

## What it does

The pipeline collects public DLsite product metadata (title / circle / price / rating / review count / sales / genres / rankings …) into a local SQLite database, and exports it as JSON / CSV plus cover thumbnails. A companion macOS app reads the export and provides browsing, filtering, favorites and one-click updates. **The app itself never uses the network** — all crawling happens inside the pipeline.

## Highlights

- **Daily maintenance** (default 23:30): hot rankings / on-ranking sales / genre popularity / official popularity order
- **Two-tier one-click update in the app**: "Quick hot update" (~2–4 min) and "Full maintenance" (adds genre pages, covers, import resume)
- **Filters**: genre multi-select with **intersection** (all must match), genre exclusion, rating / sales / price / work form / release year / content badges (voice · music · video)
- **Sorting**: sales / rating / price / release date (new→old) / daily·weekly·monthly rank / official popularity
- **Favorites** (a work can belong to multiple collections), **maker following**, **hover detail popover**, five view modes (⌘1–⌘5)
- Live progress banner during updates; auto-reload when finished

## Quick start

Requirements: **macOS + Python ≥ 3.9** (standard library only, zero third-party dependencies — no `pip install` needed).

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

## Desktop app (macOS)

```bash
bash scripts/build-app.sh                 # build (needs only Xcode Command Line Tools)
open "app/dist/同人游戏筛选器.app"
```

In the app: "Select data file" → choose the exported `out/works.json`. Press "Update" to re-read after the pipeline runs (it exports locally first, then re-reads). See [`app/README.md`](app/README.md) (Chinese) / [`app/README_EN.md`](app/README_EN.md) for details.

## Privacy & security

- No login, no cookies, no tokens; no user content is ever collected
- Crawling is limited to public pages / public site APIs, strictly following robots (`Crawl-delay: 10`)
- All data and covers are written only to local `data/` and `out/` (git-ignored, never committed)
- The app is offline; "Start update" merely launches this repository's scripts on your machine
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
