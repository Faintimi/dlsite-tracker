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
  import {
    activeFilterCount,
    applyFilters,
    emptyFilter,
    SORT_OPTIONS,
    yearOf,
    type FilterState,
    type SortKey,
  } from "$lib/filter";
  import FilterPanel from "$lib/FilterPanel.svelte";
  import HoverCard from "$lib/HoverCard.svelte";

  type Status = "empty" | "loading" | "ready" | "error";
  type ViewMode = "grid" | "wall" | "info" | "compact" | "strip";

  interface ViewCfg {
    label: string;
    kind: "grid" | "list";
    itemW: number;
    itemH: number;
    gap: number;
  }

  // 视图配置：卡片尺寸需与样式中的对应类保持一致
  const VIEWS: Record<ViewMode, ViewCfg> = {
    grid: { label: "网格卡", kind: "grid", itemW: 172, itemH: 314, gap: 14 },
    wall: { label: "封面墙", kind: "grid", itemW: 200, itemH: 280, gap: 14 },
    info: { label: "底部信息栏", kind: "grid", itemW: 200, itemH: 280, gap: 14 },
    compact: { label: "紧凑列表", kind: "list", itemW: 0, itemH: 56, gap: 6 },
    strip: { label: "横条", kind: "list", itemW: 0, itemH: 128, gap: 8 },
  };
  const VIEW_ORDER: ViewMode[] = ["grid", "wall", "info", "compact", "strip"];

  let status = $state<Status>("empty");
  let errorMessage = $state("");
  let data = $state<LoadedData | null>(null);

  let view = $state<ViewMode>("grid");
  let sort = $state<SortKey>("sales");
  let filter = $state<FilterState>(emptyFilter());
  let showFilters = $state(false);

  let scroller: HTMLDivElement | null = $state(null);
  let viewportW = $state(1200);
  let viewportH = $state(800);
  let scrollTop = $state(0);

  let hoverWork = $state<WorkView | null>(null);
  let hoverX = $state(0);
  let hoverY = $state(0);
  let hoverTimer: ReturnType<typeof setTimeout> | null = null;
  // 底部信息栏视图当前展示的作品（悬停更新；未悬停时展示第一件）
  let barWork = $state<WorkView | null>(null);

  const works = $derived(data?.works ?? []);
  const filtered = $derived(applyFilters(works, filter, sort));
  const barTarget = $derived(barWork ?? filtered[0] ?? null);
  const years = $derived.by(() => {
    const set = new Set<number>();
    for (const work of works) {
      const year = yearOf(work);
      if (year !== null) set.add(year);
    }
    return [...set].sort((a, b) => b - a);
  });
  const genres = $derived(data?.file.genres ?? []);
  const activeCount = $derived(activeFilterCount(filter));

  const cfg = $derived(VIEWS[view]);
  const cols = $derived(
    cfg.kind === "grid"
      ? Math.max(1, Math.floor((viewportW + cfg.gap) / (cfg.itemW + cfg.gap)))
      : 1,
  );
  const rowH = $derived(cfg.itemH + cfg.gap);
  const totalRows = $derived(Math.ceil(filtered.length / cols));
  const totalHeight = $derived(totalRows * rowH);
  const firstRow = $derived(Math.max(0, Math.floor(scrollTop / rowH) - 1));
  const lastRow = $derived(
    Math.min(totalRows, Math.ceil((scrollTop + viewportH) / rowH) + 1),
  );
  // 虚拟滚动：只渲染可视行（前后各多渲染一行）
  const rows = $derived.by(() => {
    const out: { key: number; top: number; items: WorkView[] }[] = [];
    for (let r = firstRow; r < lastRow; r++) {
      out.push({
        key: r,
        top: r * rowH,
        items: filtered.slice(r * cols, (r + 1) * cols),
      });
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

  // 筛选 / 排序 / 视图变化时：回到顶部并收起悬停卡
  $effect(() => {
    void filter.keyword;
    void filter.genres;
    void filter.yearFrom;
    void filter.yearTo;
    void filter.salesMin;
    void filter.priceMax;
    void filter.ratingMin;
    void sort;
    void view;
    hideHover();
    barWork = null;
    scroller?.scrollTo({ top: 0 });
    scrollTop = 0;
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
    hideHover();
  }

  function openWork(url: string) {
    if (url) void openUrl(url);
  }

  function enterHover(work: WorkView, event: MouseEvent) {
    cancelHoverTimer();
    if (view === "info") {
      barWork = work;
      return;
    }
    const x = event.clientX;
    const y = event.clientY;
    hoverTimer = setTimeout(() => {
      hoverX = x;
      hoverY = y;
      hoverWork = work;
    }, 320);
  }

  function leaveHover() {
    cancelHoverTimer();
    hoverWork = null;
  }

  function cancelHoverTimer() {
    if (hoverTimer !== null) {
      clearTimeout(hoverTimer);
      hoverTimer = null;
    }
  }

  function hideHover() {
    cancelHoverTimer();
    hoverWork = null;
  }

  function resetFilter() {
    filter = emptyFilter();
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

  function fmtDate(w: WorkView): string {
    return w.regist_date ? w.regist_date.slice(0, 10) : "—";
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
    {#if status === "ready" && data}
      <div class="actions views">
        {#each VIEW_ORDER as v (v)}
          <button class="btn view-btn" class:active={view === v} onclick={() => (view = v)}>
            {VIEWS[v].label}
          </button>
        {/each}
      </div>
      <select class="select" bind:value={sort}>
        {#each SORT_OPTIONS as option (option.key)}
          <option value={option.key}>{option.label}</option>
        {/each}
      </select>
      <button class="btn" class:active={showFilters} onclick={() => (showFilters = !showFilters)}>
        筛选{activeCount > 0 ? `（${activeCount}）` : ""}
      </button>
    {/if}
    <div class="meta">
      {#if status === "ready" && data}
        {filtered.length.toLocaleString("ja-JP")} / {works.length.toLocaleString("ja-JP")} 件 · 导出 {generatedAt}
      {:else if status === "loading"}
        正在加载…
      {/if}
    </div>
  </header>

  {#if status === "ready" && data}
    {#if showFilters}
      <FilterPanel bind:filter {genres} {years} onreset={resetFilter} />
    {/if}
    <div class="scroller" bind:this={scroller} onscroll={onScroll}>
      <div class="canvas" style="height: {totalHeight}px">
        {#each rows as row (row.key)}
          <div class="grid-row {cfg.kind}" style="top: {row.top}px">
            {#each row.items as w (w.id)}
              {#if view === "grid" || view === "wall" || view === "info"}
                <button
                  class="card {view}"
                  onclick={() => openWork(w.url)}
                  onmouseenter={(event) => enterHover(w, event)}
                  onmouseleave={leaveHover}
                >
                  <div class="cover">
                    {#if w._cover}
                      <img src={w._cover} alt="" loading="lazy" decoding="async" />
                    {:else}
                      <span class="no-cover">无封面</span>
                    {/if}
                  </div>
                  {#if view === "grid"}
                    <div class="info">
                      <div class="title">{w.title}</div>
                      <div class="maker">{w.maker}</div>
                      <div class="stats">
                        <span>销量 {fmtNum(w.sales)}</span>
                        <span>★ {fmtRating(w.rating)}</span>
                        <span class="price">{fmtPrice(w)}</span>
                      </div>
                    </div>
                  {/if}
                </button>
              {:else if view === "compact"}
                <button
                  class="row-item compact"
                  onclick={() => openWork(w.url)}
                  onmouseenter={(event) => enterHover(w, event)}
                  onmouseleave={leaveHover}
                >
                  <div class="thumb sm">
                    {#if w._cover}<img src={w._cover} alt="" loading="lazy" decoding="async" />{/if}
                  </div>
                  <div class="row-main">
                    <div class="row-title">{w.title}</div>
                    <div class="row-sub">{w.maker} · {w.id}</div>
                  </div>
                  <div class="row-num">销量 {fmtNum(w.sales)}</div>
                  <div class="row-num">★ {fmtRating(w.rating)}</div>
                  <div class="row-num price">{fmtPrice(w)}</div>
                  <div class="row-date">{fmtDate(w)}</div>
                </button>
              {:else}
                <button
                  class="row-item strip"
                  onclick={() => openWork(w.url)}
                  onmouseenter={(event) => enterHover(w, event)}
                  onmouseleave={leaveHover}
                >
                  <div class="thumb lg">
                    {#if w._cover}<img src={w._cover} alt="" loading="lazy" decoding="async" />{/if}
                  </div>
                  <div class="row-main">
                    <div class="row-title">{w.title}</div>
                    <div class="row-sub">{w.maker} · {w.id}</div>
                    <div class="row-cats">{w.category}</div>
                    <div class="row-stats">
                      <span>销量 {fmtNum(w.sales)}</span>
                      <span>★ {fmtRating(w.rating)}</span>
                      <span class="price">{fmtPrice(w)}</span>
                      <span>{fmtDate(w)}</span>
                    </div>
                  </div>
                </button>
              {/if}
            {/each}
          </div>
        {/each}
        {#if filtered.length === 0}
          <div class="no-result">没有符合条件的作品（试着放宽筛选条件）</div>
        {/if}
      </div>
    </div>
    {#if view === "info" && barTarget}
      <footer class="bottom-bar">
        <div class="bar-thumb">
          {#if barTarget._cover}<img src={barTarget._cover} alt="" decoding="async" />{/if}
        </div>
        <div class="bar-main">
          <div class="bar-title">{barTarget.title}</div>
          <div class="bar-sub">{barTarget.maker} · {barTarget.id} · 发售 {fmtDate(barTarget)}</div>
          <div class="bar-stats">
            <span>销量 {fmtNum(barTarget.sales)}</span>
            <span>★ {fmtRating(barTarget.rating)}（{fmtNum(barTarget.rating_count)} 评）</span>
            <span class="price">{fmtPrice(barTarget)}</span>
          </div>
          <div class="bar-cats">{barTarget.category}</div>
        </div>
        <button class="btn" onclick={() => barTarget && openWork(barTarget.url)}>
          打开 DLsite ↗
        </button>
      </footer>
    {/if}
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

{#if hoverWork}
  <HoverCard work={hoverWork} x={hoverX} y={hoverY} />
{/if}

<style>
  .app {
    display: flex;
    flex-direction: column;
    height: 100vh;
  }

  .toolbar {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 10px 12px;
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

  /* ===== 视图切换 / 排序 / 筛选按钮 ===== */
  .btn.active {
    border-color: var(--accent);
    color: var(--accent);
    font-weight: 600;
  }

  .views {
    gap: 6px;
  }

  .view-btn {
    padding: 6px 10px;
  }

  .select {
    border: 1px solid var(--border);
    background: var(--panel);
    color: var(--text);
    border-radius: 8px;
    padding: 6px 8px;
    font-size: 13px;
    font-family: inherit;
  }

  /* ===== 封面墙 ===== */
  .card.wall {
    width: 200px;
    height: 280px;
  }

  .card.wall .cover {
    height: 100%;
  }

  /* ===== 列表式视图（紧凑列表 / 横条） ===== */
  .grid-row.list {
    padding: 0 12px;
  }

  .row-item {
    width: 100%;
    padding: 0;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--panel);
    overflow: hidden;
    display: flex;
    align-items: center;
    gap: 12px;
    text-align: left;
    cursor: pointer;
    color: inherit;
    font: inherit;
    transition:
      border-color 0.12s ease,
      box-shadow 0.12s ease;
  }

  .row-item:hover {
    border-color: var(--accent);
    box-shadow: 0 4px 14px rgb(0 0 0 / 15%);
  }

  .row-item.compact {
    height: 56px;
  }

  .row-item.strip {
    height: 128px;
    align-items: stretch;
  }

  .thumb {
    flex: none;
    background: var(--coverbg);
    overflow: hidden;
  }

  .thumb.sm {
    width: 40px;
    height: 54px;
    border-radius: 6px;
    margin-left: 8px;
  }

  .thumb.lg {
    width: 88px;
    height: 126px;
    border-radius: 8px;
    margin: 1px 0 1px 1px;
  }

  .thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }

  .row-main {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .row-item.strip .row-main {
    padding: 8px 0;
    justify-content: center;
  }

  .row-title {
    font-size: 13px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .row-sub {
    font-size: 12px;
    color: var(--muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .row-cats {
    font-size: 11px;
    color: var(--muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .row-stats {
    display: flex;
    gap: 14px;
    font-size: 11px;
    color: var(--muted);
  }

  .row-stats .price {
    color: var(--accent);
    font-weight: 600;
  }

  .row-num {
    flex: none;
    width: 110px;
    text-align: right;
    font-size: 12px;
    color: var(--muted);
  }

  .row-num.price {
    color: var(--accent);
    font-weight: 600;
  }

  .row-date {
    flex: none;
    width: 88px;
    text-align: right;
    font-size: 11px;
    color: var(--muted);
    padding-right: 10px;
  }

  .no-result {
    position: absolute;
    top: 40px;
    left: 0;
    right: 0;
    text-align: center;
    color: var(--muted);
  }

  /* ===== 底部信息栏视图 ===== */
  .bottom-bar {
    flex: none;
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 10px 16px;
    background: var(--panel);
    border-top: 1px solid var(--border);
  }

  .bar-thumb {
    flex: none;
    width: 66px;
    height: 92px;
    border-radius: 8px;
    background: var(--coverbg);
    overflow: hidden;
  }

  .bar-thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }

  .bar-main {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 3px;
  }

  .bar-title {
    font-size: 14px;
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .bar-sub {
    font-size: 12px;
    color: var(--muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .bar-stats {
    display: flex;
    flex-wrap: wrap;
    gap: 4px 14px;
    font-size: 12px;
    color: var(--muted);
  }

  .bar-stats .price {
    color: var(--accent);
    font-weight: 600;
  }

  .bar-cats {
    font-size: 11px;
    color: var(--muted);
    line-height: 16px;
    max-height: 32px;
    overflow: hidden;
  }
</style>
