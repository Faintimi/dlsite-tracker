# 同人游戏雷达 · Doujin Game Radar — 桌面版

**中文** · [English](README_EN.md)

> 跨平台（Windows / macOS）桌面应用：**Tauri 2 + SvelteKit**；数据来自仓库根目录的 Python 管道，封面与收藏只存在本机。

## 获取

- **Windows**：GitHub → Actions → 「Desktop Build (Windows)」最近一次运行的 Artifacts（`doujin-game-radar-windows-installer`）下载安装包；或见 Release 页附件
- **macOS / 自行构建**：`npm install && npm run tauri build`（依赖见下表）

## 功能（v0.1）

- 浏览 ~9k 作品：虚拟滚动网格 / 封面墙 / 底部信息栏 / 紧凑列表 / 横条（五种视图）
- 筛选：关键词、分类交集、年份范围、销量 / 价格 / 评分、收藏状态与收藏夹、仅关注作者
- 排序：销量 / 评分 / 发售日 / 价格 / 名称
- 收藏夹（多归属）与制作者关注；右键菜单快捷操作；悬停详情卡
- **一键更新**：「更新数据 ▾」→ 立即更新热榜（快）/ 完整维护 / 继续抓更早 / 导入最近 N 年；进度横幅 + 完成后自动刷新（需 Python ≥ 3.9 + 本仓库管道）

## 构建环境

| 依赖 | 说明 |
| --- | --- |
| Node.js | LTS（含 npm） |
| Rust | 稳定版（rustup） |
| 系统 WebView | macOS：WKWebView；Windows：WebView2（Win10+ 一般自带） |
| Python ≥ 3.9 | 仅「更新数据」功能需要（管道同仓库） |

## 常用命令

```bash
npm install          # 安装依赖
npm run tauri dev    # 开发模式（热更新，自动打开窗口）
npm run tauri build  # 打包（macOS：.app/.dmg；Windows：NSIS）
npm run check        # svelte-check 类型检查
```

## 与数据管道的关系

应用读取管道导出的 `out/works.json`（schema v2）与同目录 `covers/`；采集与维护始终由根目录 `dlsite_tracker` 完成（用法见仓库根 README）。「更新数据」按钮只是在本机启动仓库内的固定任务链（`scripts/*.sh` / `python -m dlsite_tracker task …`）。
