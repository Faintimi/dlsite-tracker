# Doujin Game Radar · 同人游戏雷达

> **Go beyond the current charts to find works that fit you.** Doujin Game Radar turns public DLsite product information into a personal discovery workspace for Windows and macOS: follow new releases and changing popularity, combine filters, build a taste profile, and organize favorite works and creators. Your library, covers, and preferences stay on your machine.
>
> *不只浏览热榜，更要找到适合自己的作品：发现黑马、建立口味、关注作者，在本机整理自己的游戏库。*

[中文](README.md) · **English**

- **Local-first**: no DLsite account required; the library, covers, collections, and taste preferences remain local, with no telemetry or cloud sync. The update pipeline does request public product information from DLsite.
- **Respect the source**: the pipeline observes robots rules and polite rate limits, reading public product metadata only; purchases and downloads remain on the official store.
- **Unofficial project**: not affiliated with DLsite; the store contains adult content — intended for adult users.

## Why use Radar?

DLsite is the source for product information and purchases. Radar complements it with a cross-work, over-time workflow centered on your own interests. It does not handle transactions or pass off local inferences as official conclusions. Instead of starting over with each search or chart, you can carry these jobs forward in one persistent workspace:

| Common starting point | What Radar adds |
| --- | --- |
| Check today's charts and look for the next breakout | Discover combines changes between local sales snapshots and wishlist signals to surface rising and high-interest works. Each candidate has a reason; these suggestions are not official rankings. |
| Search a genre, then try to narrow the results | Intersect genres and independently combine work formats, voice/music/video flags, year, sales, rating, price, and exclusions. Remove an active filter directly from the results view. |
| Finish a work you like and look for unseen similar works | Build a three-level taste profile (love / like / show less) from favorite works, collections, and semantic themes. Hidden gems appear in batches; seen and dismissed feedback remains local. |
| Remember creators you like and watch for new releases | Followed Updates groups works released in the past 14 days by creator, with unread indicators and an on-demand check. |
| Browse repeatedly and want a lasting personal library | Use multiple collections, genre-popularity lists, and five viewing modes. Daily maintenance and progressive import show progress and resume from checkpoints; covers are filled in as tasks run. |

Precise ratings are another example: cards retain an easy-to-scan star score, while hover details show the official two-decimal rating; works at 4.70 or above have a distinct color tier. “Sales change” is calculated from public snapshots taken at different times, not live transactions. Taste matches are local suggestions, not official evaluations.

## How it works

The bundled pipeline fetches public product metadata from DLsite pages and APIs, stores it in local SQLite, and exports JSON / CSV plus cover thumbnails. The desktop interface reads local exports. When you request an update, the local pipeline fetches fresh public data and the interface reloads after completion. There is no account sync, and the app does not replace official product pages. Initial import and subsequent backfills depend on network conditions, catalog size, and site rate limits.

## Try the desktop app first

Packaged Windows / macOS builds include the pipeline: **no Python or repository clone is needed at runtime**. Download your platform's build from [Releases](https://github.com/Faintimi/dlsite-tracker/releases), then choose “初始化数据” (Initialize data) on first launch. Imported works appear progressively and their covers follow. Builds are also available through [Actions artifacts](https://github.com/Faintimi/dlsite-tracker/actions/workflows/desktop-release.yml). The feature overview above describes the current source tree; see each release's notes for what a published installer includes. See the [desktop guide](desktop/README_EN.md) for details.

## Command line / developer quick start

Running the pipeline separately requires **macOS / Windows / Linux + Python ≥ 3.9** (standard library only, no `pip install`). Packaged desktop users can skip this section.

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
bash scripts/quick-update.sh              # quick hot update (initial precise-rating backfill takes longer)
bash scripts/update-all.sh 1              # import last year → sales → covers → export
bash scripts/install-schedule.sh          # macOS: daily 23:30 maintenance (launchd, no sudo; uninstall: uninstall-schedule.sh)
```

> Note: because of polite rate limiting (≥10 s per page), the first full import takes some patience; afterwards only fast incremental updates run.

## Desktop apps

Two UIs to choose from (both read the same `out/works.json`; favorites and settings are stored per app, so they never interfere):

### Cross-platform desktop (Windows / macOS, recommended)

- **Windows**: download the latest `doujin-game-radar-windows-installer` artifact from [Actions "Desktop Build (Windows)"](https://github.com/Faintimi/dlsite-tracker/actions/workflows/desktop-release.yml) (or the Release page)
- **Build it yourself** (macOS / Windows):

```bash
bash scripts/build-sidecar.sh   # create the embedded pipeline before packaging
cd desktop
npm install
npm run tauri build        # output: src-tauri/target/release/bundle/ (.app/.dmg on macOS, NSIS on Windows)
```

- First launch: choose **Initialize data** to build the local library without installing Python; an existing `out/works.json` can also be selected manually
- **Update ▾**: quick hot update / full maintenance / deeper import / import last N years; a live banner shows progress and the list auto-refreshes when done (packaged builds use the embedded pipeline)
- Features: filters (genre intersection / year / sales / price / rating / favorites / followed makers), sorting, five view modes, hover detail card, collections and a right-click menu
- See [`desktop/README.md`](desktop/README.md) / [`desktop/README_EN.md`](desktop/README_EN.md)

### Native macOS app (SwiftUI)

```bash
bash scripts/build-app.sh                 # build (needs only Xcode Command Line Tools)
open "app/dist/同人游戏筛选器.app"
```

In the app: "Select data file" → choose the exported `out/works.json`. It reads the same export, but new Discover, taste, and Followed Updates features are in the cross-platform desktop app. See [`app/README.md`](app/README.md) / [`app/README_EN.md`](app/README_EN.md).

## Privacy & security

- No login, no cookies, no tokens; no user content is ever collected
- Crawling is limited to public pages / public site APIs, strictly following robots (`Crawl-delay: 10`)
- Data and covers are written to local `data/` and `out/` (git-ignored, never committed); desktop collections and taste preferences are local too
- The desktop interface reads local data; “Update” starts a local pipeline that requests public metadata from DLsite without uploading your collections or taste profile
- This repository contains code and docs only — no personal data, no store content

## Data sources & compliance

| Source | Purpose | Constraint |
| --- | --- | --- |
| Sitemap | full / incremental discovery | public entrypoint provided for crawlers |
| `product.json` | per-work details (title / circle / price / rating / genres …) | public JSON |
| `product/info/ajax` (batched, 80 per request) | sales / wishlist count / precise rating / type / release date | public site API; rate-limited |
| Ranking / listing / genre-popularity / popularity-order pages | rank & sales snapshots | ≥10 s between pages |

- Please read DLsite's terms of use and robots rules before using this project; for personal study & research use only
- You are responsible for compliance if you redistribute the outputs at scale or use them commercially

## License

[MIT](LICENSE) © 2026 Faintimi · Unofficial project, not affiliated with DLsite
