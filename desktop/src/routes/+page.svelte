<script lang="ts">
  import { onMount } from "svelte";
  import { openUrl } from "@tauri-apps/plugin-opener";
  import {
    getDataPath,
    loadWorks,
    pickDataFile,
    type LoadedData,
    type WorkView,
  } from "$lib/api";

  // 网格布局常量（需与样式中的卡片尺寸保持一致）
  const CARD_W = 172;
  const CARD_H = 314;
  const GAP = 14;
  const ROW_H = CARD_H + GAP;

  type Status = "empty" | "loading" | "ready" | "error";

  let status = $state<Status>("empty");
  let errorMessage = $state("");
  let data = $state<LoadedData | null>(null);

  let scroller: HTMLDivElement | null = $state(null);
  let viewportW = $state(1200);
  let viewportH = $state(800);
  let scrollTop = $state(0);

  const works = $derived(data?.works ?? []);
  const cols = $derived(Math.max(1, Math.floor((viewportW + GAP) / (CARD_W + GAP))));
  const totalRows = $derived(Math.ceil(works.length / cols));
  const totalHeight = $derived(totalRows * ROW_H);
  const firstRow = $derived(Math.max(0, Math.floor(scrollTop / ROW_H) - 1));
  const lastRow = $derived(
    Math.min(totalRows, Math.ceil((scrollTop + viewportH) / ROW_H) + 1),
  );
  // 虚拟滚动：只渲染可视行（前后各多渲染一行）
  const rows = $derived.by(() => {
    const out: { key: number; top: number; items: WorkView[] }[] = [];
    for (let r = firstRow; r < lastRow; r++) {
      out.push({ key: r, top: r * ROW_H, items: works.slice(r * cols, (r + 1) * cols) });
    }
    return out;
  });
  const generatedAt = $derived(
    data
      ? new Date(data.file.generated_at).toLocaleString("zh-CN", { hour12: false })
      : "",
  );

  $effect(() => {
    const el = scroller;
    if (!el) return;
    const observer = new ResizeObserver(() => {
      viewportW = el.clientWidth;
      viewportH = el.clientHeight;
    });
    observer.observe(el);
    viewportW = el.clientWidth;
    viewportH = el.clientHeight;
    return () => observer.disconnect();
  });

  onMount(() => {
    void bootstrap();
  });

  async function bootstrap() {
    try {
      const path = await getDataPath();
      if (path) await reload();
    } catch (error) {
      status = "error";
      errorMessage = String(error);
    }
  }

  async function reload() {
    status = "loading";
    errorMessage = "";
    try {
      // 先让“加载中”渲染一帧，再做读文件与解析的重活
      await new Promise((resolve) => setTimeout(resolve, 0));
      data = await loadWorks();
      console.info(`[radar] 已加载 ${data.works.length} 件作品（${data.path}）`);
      scrollTop = 0;
      status = "ready";
    } catch (error) {
      console.error("[radar] 数据加载失败：", error);
      status = "error";
      errorMessage = String(error);
    }
  }

  async function pick() {
    try {
      const picked = await pickDataFile();
      if (picked) await reload();
    } catch (error) {
      status = "error";
      errorMessage = String(error);
    }
  }

  function onScroll(event: Event) {
    scrollTop = (event.currentTarget as HTMLDivElement).scrollTop;
  }

  function openWork(url: string) {
    if (url) void openUrl(url);
  }

  function fmtNum(n: number | null | undefined): string {
    return typeof n === "number" && Number.isFinite(n) ? n.toLocaleString("ja-JP") : "—";
  }

  function fmtRating(n: number | null | undefined): string {
    return typeof n === "number" && Number.isFinite(n) ? n.toFixed(1) : "—";
  }

  function fmtPrice(w: WorkView): string {
    return typeof w.price === "number" ? `¥${w.price.toLocaleString("ja-JP")}` : "—";
  }
</script>

<svelte:head>
  <title>同人游戏雷达 · Doujin Game Radar</title>
</svelte:head>

<div class="app">
  <header class="toolbar">
    <div class="brand">同人游戏雷达<span class="tag">桌面版</span></div>
    <div class="actions">
      <button class="btn" onclick={pick}>打开数据文件…</button>
      <button class="btn" onclick={() => reload()} disabled={status === "loading" || status === "empty"}>
        重新加载
      </button>
    </div>
    <div class="meta">
      {#if status === "ready" && data}
        {works.length.toLocaleString("ja-JP")} 件作品 · 导出时间 {generatedAt}
      {:else if status === "loading"}
        正在加载…
      {/if}
    </div>
  </header>

  {#if status === "ready" && data}
    <div class="scroller" bind:this={scroller} onscroll={onScroll}>
      <div class="canvas" style="height: {totalHeight}px">
        {#each rows as row (row.key)}
          <div class="grid-row" style="top: {row.top}px">
            {#each row.items as w (w.id)}
              <button class="card" onclick={() => openWork(w.url)} title={w.title}>
                <div class="cover">
                  {#if w._cover}
                    <img src={w._cover} alt="" loading="lazy" decoding="async" />
                  {:else}
                    <span class="no-cover">无封面</span>
                  {/if}
                </div>
                <div class="info">
                  <div class="title">{w.title}</div>
                  <div class="maker">{w.maker}</div>
                  <div class="stats">
                    <span>销量 {fmtNum(w.sales)}</span>
                    <span>★ {fmtRating(w.rating)}</span>
                    <span class="price">{fmtPrice(w)}</span>
                  </div>
                </div>
              </button>
            {/each}
          </div>
        {/each}
      </div>
    </div>
  {:else if status === "loading"}
    <div class="center">
      <p>正在解析数据…（约 9k 作品）</p>
    </div>
  {:else if status === "error"}
    <div class="center">
      <h1>无法加载数据</h1>
      <p class="error">{errorMessage}</p>
      <button class="btn" onclick={pick}>打开数据文件…</button>
    </div>
  {:else}
    <div class="center">
      <h1>同人游戏雷达 · Doujin Game Radar</h1>
      <p>选择由数据管道导出的 <code>works.json</code> 开始浏览</p>
      <p class="hint">
        通常位于仓库的 <code>out/works.json</code>；封面在其旁边的 <code>covers/</code> 目录，数据全部留在本机
      </p>
      <button class="btn primary" onclick={pick}>打开数据文件…</button>
    </div>
  {/if}
</div>

<style>
  .app {
    display: flex;
    flex-direction: column;
    height: 100vh;
  }

  .toolbar {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 16px;
    background: var(--panel);
    border-bottom: 1px solid var(--border);
    flex: none;
  }

  .brand {
    font-size: 15px;
    font-weight: 700;
  }

  .tag {
    margin-left: 6px;
    padding: 1px 7px;
    border: 1px solid var(--border);
    border-radius: 999px;
    font-size: 11px;
    font-weight: 400;
    color: var(--muted);
    vertical-align: 1px;
  }

  .actions {
    display: flex;
    gap: 8px;
  }

  .meta {
    margin-left: auto;
    font-size: 12px;
    color: var(--muted);
    white-space: nowrap;
  }

  .scroller {
    flex: 1;
    overflow-y: auto;
    overscroll-behavior: contain;
  }

  .canvas {
    position: relative;
  }

  .grid-row {
    position: absolute;
    left: 0;
    right: 0;
    display: flex;
    justify-content: center;
    gap: 14px;
  }

  .card {
    width: 172px;
    height: 314px;
    padding: 0;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--panel);
    overflow: hidden;
    display: flex;
    flex-direction: column;
    text-align: left;
    cursor: pointer;
    color: inherit;
    font: inherit;
    transition:
      transform 0.12s ease,
      box-shadow 0.12s ease,
      border-color 0.12s ease;
  }

  .card:hover {
    transform: translateY(-2px);
    border-color: var(--accent);
    box-shadow: 0 6px 18px rgb(0 0 0 / 18%);
  }

  .cover {
    height: 240px;
    flex: none;
    background: var(--coverbg);
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .cover img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }

  .no-cover {
    color: var(--muted);
    font-size: 12px;
  }

  .info {
    flex: 1;
    min-width: 0;
    padding: 8px 10px;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .title {
    font-size: 13px;
    line-height: 17px;
    height: 34px;
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
  }

  .maker {
    font-size: 12px;
    color: var(--muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .stats {
    margin-top: auto;
    display: flex;
    justify-content: space-between;
    gap: 6px;
    font-size: 11px;
    color: var(--muted);
  }

  .stats .price {
    color: var(--accent);
    font-weight: 600;
  }

  .center {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 24px;
    text-align: center;
  }

  .center h1 {
    font-size: 22px;
    margin: 0 0 4px;
  }

  .center p {
    margin: 0;
    color: var(--muted);
  }

  .center .error {
    color: #d64545;
    max-width: 560px;
    word-break: break-all;
  }

  .hint {
    font-size: 12px;
  }

  .center code {
    background: var(--codebg);
    border-radius: 6px;
    padding: 1px 6px;
    font-size: 12px;
  }
</style>
