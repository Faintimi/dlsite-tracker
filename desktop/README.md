# 同人游戏雷达 · Doujin Game Radar — 桌面版

**中文** · [English](README_EN.md)

> 跨平台（Windows / macOS）桌面界面：**Tauri 2 + SvelteKit** 前端，数据层复用仓库根目录的 Python 管道。

## 状态

🚧 **开发中（脚手架阶段）**：可运行的开发环境与工程结构已就绪；浏览、筛选、收藏与一键更新等功能按里程碑逐步实现。

## 开发环境

| 依赖 | 说明 |
| --- | --- |
| Node.js | LTS 版本（含 npm） |
| Rust | 通过 [rustup](https://rustup.rs) 安装稳定版 |
| 系统 WebView | macOS 自带 WKWebView；Windows 需 WebView2（Win10+ 一般自带） |

## 常用命令

```bash
npm install          # 安装前端依赖
npm run tauri dev    # 开发模式（热更新，自动打开应用窗口）
npm run tauri build  # 打包（macOS：.app/.dmg；Windows：NSIS/MSI）
npm run check        # svelte-check 类型检查
```

## 与数据管道的关系

应用读取由仓库根目录 Python 管道导出的 JSON 数据（`works.json`）展示作品；
数据采集与维护继续使用根目录的 `dlsite_tracker`（详见仓库根 README）。
