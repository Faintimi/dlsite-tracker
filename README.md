# 同人游戏雷达 · Doujin Game Radar

**中文** · [English](README_EN.md)

> **不只浏览热榜，更要找到适合自己的作品。** 同人游戏雷达把 DLsite 的公开商品信息整理成 Windows / macOS 上的私人探索工作台：追踪新作与热度变化、组合筛选、建立口味、收藏与关注作者。作品数据、封面和个人偏好保存在本机。
>
> *A local-first discovery workspace for DLsite doujin games: find emerging works, explore your taste, and keep up with creators on Windows and macOS.*

- **本地优先**：不要求 DLsite 账号；作品库、封面、收藏与口味偏好保存在本机，无遥测或云端同步。更新时，数据管道会向 DLsite 请求公开商品信息。
- **尊重来源**：管道遵守 robots 与礼貌限速，只读取公开商品元数据；作品购买与下载仍在官方商店完成。
- **非官方项目**：与 DLsite 无关联；商店含成人向内容，本项目面向成年用户。

## 为什么要用雷达？

DLsite 是作品信息与购买的来源；雷达补充的是跨作品、跨时间、围绕你自己口味的探索流程。它不参与交易，也不把本机推测包装成官方结论。相比从单次搜索或榜单开始、逐部查看，雷达把下列任务串进一个可持续使用的工作台：

| 常见起点 | 雷达进一步帮你做什么 |
| --- | --- |
| 看当下热榜，想找下一部黑马 | 「发现」结合本地销量快照变化与心愿单信号，分出冲刺中、高期待的新作；候选附理由，不把推测当成官方排名。 |
| 搜索一个分类，想继续缩小范围 | 分类可交集筛选，并与作品形式、配音／音乐／动画标志、年份、销量、评分、价格、排除条件独立组合；已选条件可直接点掉。 |
| 看完一部喜欢的作品，想找没看过的同好作 | 从喜欢的作品、收藏夹与语义主题建立「很喜欢／喜欢／少推荐」口味；遗珠分批探索，看过与不感兴趣的反馈留在本机。 |
| 记住几个喜欢的作者，想跟进新作 | 关注更新集中展示近 14 天发布的作品，提供未读提示、按作者分组与一键检查。 |
| 反复浏览，希望积累成自己的作品库 | 多收藏夹、分类人气榜、五种浏览视图；每日维护与渐进导入支持进度显示和断点续传，封面随任务补齐。 |

精确评分也是一个例子：卡片保持易扫读的星级，悬停详情显示官方两位小数；精确分达到 4.70 的作品有独立颜色档位。这里的“销量变化”来自本机不同时间的公开数据快照，并非实时成交数据；口味匹配也是本机计算的建议，不是官方评价。

## 它如何工作

内置管道从 DLsite 公开页面及接口读取商品元数据，写入本机 SQLite，再导出 JSON / CSV 与封面缩略图。桌面界面读取本地导出文件；点击更新时，由本机管道联网维护数据，完成后界面自动重载。没有账号同步，也不代替官方作品页。首次建库与后续补齐所需时间取决于网络、作品数量及站点限速。

## 先体验桌面版

Windows / macOS 打包版内置数据管道，**使用时不需要 Python，也不需要克隆仓库**。从 [Release](https://github.com/Faintimi/dlsite-tracker/releases) 下载对应版本，首次打开点「初始化数据」即可开始；更新过程会逐步显示已导入作品，封面随后补齐。也可从 [Actions 构建产物](https://github.com/Faintimi/dlsite-tracker/actions/workflows/desktop-release.yml) 获取构建。上方功能介绍对应当前源码，已发布安装包的功能以各版本说明为准。具体操作见 [桌面版说明](desktop/README.md)。

## 命令行 / 开发者快速开始

以下是单独运行数据管道的方式，需要 **macOS / Windows / Linux + Python ≥ 3.9**（仅标准库，无需 `pip install`）；桌面打包版不需要这些步骤。

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
bash scripts/quick-update.sh              # 快版热榜更新（首次补齐精确评分时会更久）
bash scripts/update-all.sh 1              # 导入最近一年 → 销量 → 封面 → 导出
bash scripts/install-schedule.sh          # macOS：每日 23:30 自动维护（launchd，无需 sudo；卸载：uninstall-schedule.sh）
```

> 提示：由于严格遵循站点礼貌限速（页面 ≥10 秒/页），首次全量建立数据需要一些耐心；之后每天只做增量维护，很快。

## 桌面应用

两套界面任选（读取同一份 `out/works.json`；收藏与设置分别保存在各自应用目录，互不影响）：

### 跨平台桌面版（Windows / macOS，推荐）

- **Windows 直接下载**：见 [Actions「Desktop Build (Windows)」](https://github.com/Faintimi/dlsite-tracker/actions/workflows/desktop-release.yml) 最新一次运行的 Artifacts（`doujin-game-radar-windows-installer`），或 Release 页附件
- **自行构建**（macOS / Windows 均可）：

```bash
bash scripts/build-sidecar.sh   # 先生成内嵌管道（打包前必须执行一次）
cd desktop
npm install
npm run tauri build        # 产物：src-tauri/target/release/bundle/（macOS：.app/.dmg；Windows：NSIS）
```

- 首次打开：点**「初始化数据」**一键搭建（内置数据管道，本机抓取热榜约 5–10 分钟、视网络，无需安装 Python）；已有数据文件时可用「选择数据文件」直接打开管道导出的 `out/works.json`
- **「更新数据 ▾」**：立即更新热榜（快）/ 完整维护 / 继续抓更早（续深）/ 导入最近 N 年；顶部横幅实时显示进度，完成后列表自动刷新（打包版用内置管道，无额外依赖）
- 功能：筛选（分类交集 / 年份 / 销量 / 价格 / 评分 / 收藏 / 关注作者）、排序、五种视图、悬停详情卡、收藏夹与右键菜单
- 说明见 [`desktop/README.md`](desktop/README.md) / [`desktop/README_EN.md`](desktop/README_EN.md)

### macOS 原生版（SwiftUI）

```bash
bash scripts/build-app.sh                 # 构建（仅需 Xcode Command Line Tools）
open "app/dist/同人游戏筛选器.app"
```

应用内「选择数据文件」→ 选择导出的 `out/works.json`。此版读取同一份导出文件，但新发现、口味与关注更新等功能以跨平台桌面版为准。说明见 [`app/README.md`](app/README.md) / [`app/README_EN.md`](app/README_EN.md)。

## 隐私与安全

- 不登录、不使用账号 / Cookie / 令牌；不抓取任何用户内容
- 采集仅限公开页面与站点公开接口，严格遵循 robots（含 `Crawl-delay: 10`）
- 数据与封面写在本机 `data/` 与 `out/`（均已 gitignore，不入库）；桌面收藏与口味偏好也保存在本机
- 桌面界面读取本地数据；点击「更新数据」会在本机启动管道，管道向 DLsite 请求公开元数据，不上传收藏与口味偏好
- 本仓库只包含代码与文档，不含任何个人数据或商品内容

## 数据来源与合规

| 来源 | 用途 | 约束 |
| --- | --- | --- |
| Sitemap | 全量 / 增量发现作品 | 官方提供给爬虫的公开入口 |
| `product.json` | 单作品详情（名称 / 社团 / 价格 / 评分 / 分类…） | 公开 JSON |
| `product/info/ajax`（批量 80 件/请求） | 销量 / 心愿单数 / 精确评分 / 类型 / 上架日 | 站内公开接口；节流限速 |
| 榜单页 / 列表页 / 分类人气 / 人气序 | 名次与销量快照 | 每页 ≥10 秒间隔 |

- 请在使用前阅读 DLsite 的使用条款与 robots 规则；本项目仅供个人学习与研究使用
- 输出数据的大规模再分发、商业用途请自行评估合规性

## License

[MIT](LICENSE) © 2026 Faintimi · 非官方项目，与 DLsite 无关联

## English quick notes

- **What**: local-first DLsite doujin-game browsers (cross-platform desktop app for Windows/macOS + a native macOS app), backed by a robots-compliant daily data pipeline (Python standard library, zero dependencies).
- **Quick start**: packaged Windows/macOS builds include the pipeline and initialize locally without Python; developers can run `python3 -m dlsite_tracker update` and export `out/works.json`.
- **Privacy**: no account or telemetry; library and preferences stay local. The update pipeline requests public metadata from DLsite. Unofficial project — obey DLsite's terms & robots.
