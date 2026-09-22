# 同人游戏雷达 · Doujin Game Radar

**中文** · [English](README_EN.md)

> **macOS 上的 DLsite 同人游戏浏览与筛选应用** + 配套的合规数据管道：每日自动更新销量 / 热榜 / 分类人气，浏览时支持分类交集筛选、收藏夹与制作者追踪——**数据与封面全部只存在你本机**。
>
> *A local-first browser & filter for DLsite doujin games on macOS, backed by a robots-compliant daily data pipeline. All data stays on your machine.*

- **本地优先**：无账号、无遥测、无云端；应用与管道都不向你之外发送任何数据
- **合规采集**：只访问公开页面与站点自身接口，严格遵守 robots（`Crawl-delay: 10`），只取公开商品元数据
- **非官方项目**：与 DLsite 无关联；商店含成人向内容，本项目面向成年用户

## 它做什么

管道在本机采集 DLsite 的公开商品元数据（名称 / 社团 / 价格 / 评分 / 评价数 / 销量 / 分类 / 排行榜 等），存入本机 SQLite，并导出为 JSON / CSV 与封面缩略图；配套的 macOS 应用读取导出文件，提供浏览、筛选、收藏与一键更新。**应用自身不联网**——联网行为全部发生在管道里。

## 功能亮点

- **每日自动维护**（默认 23:30）：热榜名次 / 在榜销量 / 分类人气 / 官方人气序
- **应用内一键更新双档**：「立即更新热榜（快）」约 2–4 分钟；「完整维护（同夜间计划）」包含分类人气、封面与导入续传
- **筛选**：分类多选取交集、分类排除、评分 / 销量 / 价格 / 作品形式 / 发售年份 / 内容标志（配音·音乐·动画）
- **排序**：销量 / 评分 / 价格 / 发售时间（新→旧）/ 日·周·月热度 / 官方人气
- **收藏夹**（一个作品可属于多个）、**制作者关注**、**悬停详情浮窗**、五种显示形式（⌘1–⌘5）
- 顶部横幅实时显示更新 / 导入进度，完成后自动刷新

## 快速开始

环境要求：**macOS + Python ≥ 3.9**（仅标准库，零第三方依赖；无需 `pip install`）。

```bash
git clone https://github.com/Faintimi/dlsite-tracker.git
cd dlsite-tracker
cp config.example.ini config.ini          # 本地配置（不入库；含节流参数说明）

python3 -m dlsite_tracker init            # 初始化数据目录与数据库
python3 -m dlsite_tracker update          # 每日更新（热榜模式）
python3 -m dlsite_tracker import-recent --dry-run --years 1   # 试算「最近一年」导入规模（不联网）
python3 -m dlsite_tracker import-recent --years 1             # 渐进导入（断点续传，可随时暂停）
python3 -m dlsite_tracker export          # 导出 out/works.json + works.csv
python3 -m dlsite_tracker --help          # 查看全部命令
```

一键链（与应用按钮同款）：

```bash
bash scripts/quick-update.sh              # 快版热榜更新（约 2–4 分钟）
bash scripts/update-all.sh 1              # 导入最近一年 → 销量 → 封面 → 导出
bash scripts/install-schedule.sh          # 每日 23:30 自动维护（launchd，无需 sudo；卸载：uninstall-schedule.sh）
```

> 提示：由于严格遵循站点礼貌限速（页面 ≥10 秒/页），首次全量建立数据需要一些耐心；之后每天只做增量维护，很快。

## 桌面应用（macOS）

```bash
bash scripts/build-app.sh                 # 构建（仅需 Xcode Command Line Tools）
open "app/dist/同人游戏筛选器.app"
```

应用内「选择数据文件」→ 选择导出的 `out/works.json` 即可使用；数据更新后点「更新」重读（先本地同步导出、再重读）。详细说明见 [`app/README.md`](app/README.md) / [`app/README_EN.md`](app/README_EN.md)。

## 隐私与安全

- 不登录、不使用账号 / Cookie / 令牌；不抓取任何用户内容
- 采集仅限公开页面与站点公开接口，严格遵循 robots（含 `Crawl-delay: 10`）
- 所有数据与封面只写在本机 `data/` 与 `out/`（均已 gitignore，不入库）
- 应用自身不联网；「开始更新数据」只是在本机启动本仓库的固定脚本
- 本仓库只包含代码与文档，不含任何个人数据或商品内容

## 数据来源与合规

| 来源 | 用途 | 约束 |
| --- | --- | --- |
| Sitemap | 全量 / 增量发现作品 | 官方提供给爬虫的公开入口 |
| `product.json` | 单作品详情（名称 / 社团 / 价格 / 评分 / 分类…） | 公开 JSON |
| `product/info/ajax`（批量 80 件/请求） | 销量 / 收藏数 / 类型 / 上架日 | 站内公开接口；节流限速 |
| 榜单页 / 列表页 / 分类人气 / 人气序 | 名次与销量快照 | 每页 ≥10 秒间隔 |

- 请在使用前阅读 DLsite 的使用条款与 robots 规则；本项目仅供个人学习与研究使用
- 输出数据的大规模再分发、商业用途请自行评估合规性

## License

[MIT](LICENSE) © 2026 Faintimi · 非官方项目，与 DLsite 无关联

## English quick notes

- **What**: a local-first DLsite doujin-game browser for macOS (SwiftUI app), backed by a robots-compliant daily data pipeline (Python standard library, zero dependencies).
- **Quick start**: `python3 -m dlsite_tracker update` → `bash scripts/build-app.sh` → open the app and select `out/works.json`.
- **Privacy**: no accounts, no telemetry, nothing leaves your machine. Unofficial project — obey DLsite's terms & robots.
