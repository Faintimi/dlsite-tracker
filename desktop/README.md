# 同人游戏雷达 · Doujin Game Radar — 桌面版

**中文** · [English](README_EN.md)

> 跨平台（Windows / macOS）桌面应用：**Tauri 2 + SvelteKit**；**打包版内置数据管道**（无需安装 Python），数据、封面与收藏只存在本机。

## 获取

- **Windows**：GitHub → Actions → 「Desktop Build (Windows)」最近一次运行的 Artifacts（`doujin-game-radar-windows-installer`）下载安装包；或见 Release 页附件
- **macOS / 自行构建**：在仓库根执行 `bash scripts/build-sidecar.sh`（生成内嵌管道），再 `npm install && npm run tauri build`（依赖见下表）

## 功能（v0.1）

- 浏览 ~9k 作品：虚拟滚动网格 / 封面墙 / 底部信息栏 / 紧凑列表 / 横条（五种视图）
- 筛选：关键词、分类交集、年份范围、销量 / 价格 / 评分、收藏状态与收藏夹、仅关注作者
- 排序：销量 / 评分 / 发售日 / 价格 / 名称
- 收藏夹（多归属）与制作者关注；右键菜单快捷操作；悬停详情卡
- **发现**（本机实时计算）：黑马新锐（冲刺中 / 高期待・心愿单信号）+ 合你口味的新作 + 遗珠老作挖掘；口味手动勾选分类，每条推荐附可解释理由
- **首次使用**：空状态页「初始化数据」一键搭建（本机抓取热榜，约 5–10 分钟），无需安装 Python / 克隆仓库
- **一键更新**：「更新数据 ▾」→ 立即更新热榜（快）/ 完整维护 / 继续抓更早 / 导入最近 N 年；进度横幅 + 完成后自动刷新（打包版用内置管道，无额外依赖）

## 构建环境

| 依赖 | 说明 |
| --- | --- |
| Node.js | LTS（含 npm） |
| Rust | 稳定版（rustup） |
| 系统 WebView | macOS：WKWebView；Windows：WebView2（Win10+ 一般自带） |
| Python ≥ 3.9 | 构建内嵌管道与「仓库模式」需要；打包版运行时不依赖 |

## 常用命令

```bash
npm install          # 安装依赖
npm run tauri dev    # 开发模式（热更新，自动打开窗口；数据走「仓库 + 系统 Python」）
bash ../scripts/build-sidecar.sh  # 构建内嵌管道（打包前必须执行一次；产物不入库）
npm run tauri build  # 打包（macOS：.app/.dmg；Windows：NSIS；含内嵌管道）
npm run check        # svelte-check 类型检查
```

## 与数据管道的关系

应用读取管道导出的 `out/works.json`（schema v3）与同目录 `covers/`；采集与维护始终由根目录 `dlsite_tracker` 完成（用法见仓库根 README）。「更新数据」按钮只是在本机启动固定任务链。

**两种管道模式**（自动判定）：

- **仓库模式**（开发 / 自用）：数据目录是一份完整仓库（含 `dlsite_tracker/` 包）时，走系统 Python 与 `scripts/*.sh`（需 Python ≥ 3.9）；
- **内嵌模式**（打包版 / 普通用户）：应用随包携带 `radar-pipeline` 单文件管道（PyInstaller 构建，见 `scripts/build-sidecar.sh`）。首次使用在空状态页点「初始化数据」，自动在应用数据目录完成配置、建库并抓取热榜（约 5–10 分钟，视网络）；之后所有按钮（更新 / 导入 / 分类人气）都调用它——**无需安装 Python、无需克隆仓库**。

首次启动时应用会**自动查找并绑定**数据文件：沿可执行文件所在目录向上查找、扫描 `~/code`、`~/Code`、`~/Projects`、`~/Documents`、`~/Desktop` 与主目录下的一层子目录（找 `<项目>/out/works.json`），以及内嵌模式的应用数据目录（`<应用数据目录>/pipeline/out/works.json`）；找到后记住路径，下次直接使用。仅在自动查找失败时，才需要在空状态页手动选择一次。
