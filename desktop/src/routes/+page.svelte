<script lang="ts">
  import { onMount } from "svelte";
  import { LogicalPosition, LogicalSize } from "@tauri-apps/api/dpi";
  import { currentMonitor as currentWindowMonitor, getCurrentWindow } from "@tauri-apps/api/window";
  import { openUrl } from "@tauri-apps/plugin-opener";
  import {
    getDataPath,
    loadWorks,
    pickDataFile,
    runExport,
    type LoadedData,
    type WorkView,
  } from "$lib/api";
  import {
    applyFilters,
    emptyFilter,
    makerKeyOf,
    SORT_OPTIONS,
    viewFilterTitle,
    type FilterState,
    type SortKey,
    type ViewFilter,
  } from "$lib/filter";
  import ContextMenu from "$lib/ContextMenu.svelte";
  import HoverPanel from "$lib/HoverPanel.svelte";
  import UpdateBanner from "$lib/UpdateBanner.svelte";
  import ConfirmDialog from "$lib/ConfirmDialog.svelte";
  import PromptDialog from "$lib/PromptDialog.svelte";
  import YearPickerDialog from "$lib/YearPickerDialog.svelte";
  import Sidebar from "$lib/Sidebar.svelte";
  import { DEFAULT_COLLECTION_NAME, library } from "$lib/library.svelte";
  import { prefs } from "$lib/prefs.svelte";
  import { ICONS, categoriesOf } from "$lib/ui";
  import CompactRow from "$lib/CompactRow.svelte";
  import CoverTile from "$lib/CoverTile.svelte";
  import LargeRow from "$lib/LargeRow.svelte";
  import MediumCard from "$lib/MediumCard.svelte";
  import {
    ACTIVE_PHASES,
    cancelImport,
    genreSummary,
    importSummary,
    importSwitch,
    isRunning,
    isStale,
    readProgress,
    removeGenre,
    startGenreImport,
    startUpdate,
    unwatchGenre,
    updateSummary,
    watchGenre,
    type GenreProgress,
    type ImportCoverage,
    type ImportProgress,
    type UpdateState,
  } from "$lib/pipeline";

  type Status = "empty" | "loading" | "ready" | "error";
  type ViewMode = "largeCards" | "twoColumn" | "compact" | "adaptiveGrid" | "coverWall";

  interface ViewCfg {
    label: string;
    shortcut: string;
    icon: string;
    kind: "list" | "grid";
    itemH: number;
    minW: number;
    maxW?: number;
    maxCols?: number;
    gap: number;
  }

  // 显示模式（严格对齐 macOS DisplayMode：名称 / 快捷键 ⌘1–5 / 图标）
  const VIEWS: Record<ViewMode, ViewCfg> = {
    largeCards: {
      label: "大卡列表",
      shortcut: "1",
      icon: ICONS.modeLarge,
      kind: "list",
      itemH: 194,
      minW: 0,
      gap: 10,
    },
    twoColumn: {
      label: "双列卡片",
      shortcut: "2",
      icon: ICONS.modeTwo,
      kind: "grid",
      itemH: 226,
      minW: 296,
      maxCols: 2,
      gap: 12,
    },
    compact: {
      label: "紧凑列表",
      shortcut: "3",
      icon: ICONS.modeCompact,
      kind: "list",
      itemH: 78,
      minW: 0,
      gap: 6,
    },
    adaptiveGrid: {
      label: "自适应网格",
      shortcut: "4",
      icon: ICONS.modeGrid,
      kind: "grid",
      itemH: 226,
      minW: 296,
      maxCols: 4,
      gap: 12,
    },
    coverWall: {
      label: "封面墙",
      shortcut: "5",
      icon: ICONS.modeWall,
      kind: "grid",
      itemH: 196,
      minW: 150,
      maxW: 230,
      gap: 14,
    },
  };
  const VIEW_ORDER: ViewMode[] = ["largeCards", "twoColumn", "compact", "adaptiveGrid", "coverWall"];

  function normalizeView(value: string): ViewMode {
    return (VIEW_ORDER as string[]).includes(value) ? (value as ViewMode) : "largeCards";
  }

  let status = $state<Status>("empty");
  let errorMessage = $state("");
  let data = $state<LoadedData | null>(null);
  let syncing = $state(false);
  let lastError = $state("");
  let loadedAt = $state("");
  let updateError = $state("");

  let view = $state<ViewMode>(normalizeView(prefs.data.displayMode));
  let sort = $state<SortKey>("sales");
  let filter = $state<FilterState>(emptyFilter());
  let viewFilter = $state<ViewFilter>({ kind: "all" });
  let importYears = $state("1");

  let showPersonalization = $state(false);
  let cardMenu = $state<{ x: number; y: number; work: WorkView } | null>(null);
  let displayMenu = $state<{ x: number; y: number } | null>(null);
  let updateMenu = $state<{ x: number; y: number } | null>(null);

  let progress = $state<UpdateState | null>(null);
  let importInfo = $state<ImportProgress | null>(null);
  let genreInfo = $state<GenreProgress | null>(null);
  let coverage = $state<ImportCoverage | null>(null);
  let lastProgressTs = 0;
  let lastGenreDoneTs = 0;
  let lastImportPhase = "";

  let scroller: HTMLDivElement | null = $state(null);
  let viewportW = $state(1200);
  let viewportH = $state(800);
  let scrollTop = $state(0);

  let hoverWork = $state<WorkView | null>(null);
  let hoverX = $state(0);
  let hoverY = $state(0);
  let hoverTimer: ReturnType<typeof setTimeout> | null = null;

  // 对话框：收藏夹 / 分类导入 / 加入每日刷新 / 年份选择
  let collectionPrompt = $state<{ workId: string } | null>(null);
  let collectionName = $state("");
  let genreImportRequest = $state<{ id: string; name: string } | null>(null);
  let joinDailyRequest = $state<{ id: string; name: string } | null>(null);
  let yearDialog = $state<{ mode: "update" | "deeper" } | null>(null);
  let yearValue = $state(new Date().getFullYear() - 5);
  let deeperValue = $state(7);

  const works = $derived(data?.works ?? []);

  /** 测量用「最宽内容」卡片：长标题 + 最长 9 个分类 + 三形式 + 全徽章 + 全数据行 + 折扣价 */
  const measureWork = $derived.by((): WorkView | null => {
    const base = works[0];
    if (!base) return null;
    const top = [...new Set(works.flatMap((work) => categoriesOf(work)))]
      .sort((a, b) => b.length - a.length)
      .slice(0, 9);
    return {
      ...base,
      title: base.title.length >= 32 ? base.title : `${base.title} ${base.title}`,
      category: (top.length > 0 ? top : categoriesOf(base)).join(" | "),
      form: "模拟/角色扮演/音声",
      sales: base.sales ?? 123456,
      rating: base.rating ?? 4.75,
      rating_count: base.rating_count ?? 123456,
      regist_date: base.regist_date || "2020-01-01",
      price: base.price ?? 1000,
      official_price: (base.price ?? 1000) + 1000,
      discount_rate: base.discount_rate ?? 50,
      rank_day_current: base.rank_day_current ?? 1,
      rank_week_current: base.rank_week_current ?? 2,
      rank_month_current: base.rank_month_current ?? 3,
      rank_trend_current: base.rank_trend_current ?? 4,
      voice: true,
      music: true,
      video: true,
    };
  });
  const activeCollectionId = $derived(viewFilter.kind === "collection" ? viewFilter.id : "");
  const activeMaker = $derived(viewFilter.kind === "maker" ? viewFilter : null);
  const collectionNameOf = $derived(
    activeCollectionId
      ? (library.data.collections.find((item) => item.id === activeCollectionId)?.name ?? "已删除")
      : "",
  );
  const favoriteIds = $derived.by(() => {
    if (activeCollectionId) return library.idsIn(activeCollectionId);
    return new Set<string>();
  });
  const filtered = $derived(applyFilters(works, filter, sort, { viewFilter, favoriteIds }));
  const genres = $derived(data?.file.genres ?? []);
  const genreCatalog = $derived(data?.file.genre_catalog ?? []);
  const activeGenre = $derived(genres.find((entry) => entry.id === filter.genreFocus) ?? null);

  const cfg = $derived(VIEWS[view]);
  const usable = $derived(Math.max(0, viewportW - 44));
  const cols = $derived.by(() => {
    if (cfg.kind === "list") return 1;
    const count = Math.max(1, Math.floor((usable + cfg.gap) / (cfg.minW + cfg.gap)));
    return cfg.maxCols ? Math.min(cfg.maxCols, count) : count;
  });
  const cellW = $derived(
    cfg.kind === "list"
      ? 0
      : Math.min(cfg.maxW ?? Number.POSITIVE_INFINITY, (usable - (cols - 1) * cfg.gap) / cols),
  );

  // 行高：按「最宽内容卡片」实测高度取最大值（macOS 网格行高随内容自适应；
  // 固定行高会裁掉部分卡片的价格/心/打开行，实测可将行高撑到足够）
  let measureEl = $state<HTMLDivElement | null>(null);
  let measuredH = $state(0);
  const itemH = $derived(Math.max(cfg.itemH, Math.ceil(measuredH)));
  const rowH = $derived(itemH + cfg.gap);
  const totalRows = $derived(Math.ceil(filtered.length / cols));
  const totalHeight = $derived(totalRows * rowH);
  const firstRow = $derived(Math.max(0, Math.floor(scrollTop / rowH) - 1));
  const lastRow = $derived(Math.min(totalRows, Math.ceil((scrollTop + viewportH) / rowH) + 1));
  const rows = $derived.by(() => {
    const out: { key: number; top: number; items: WorkView[] }[] = [];
    for (let r = firstRow; r < lastRow; r++) {
      out.push({ key: r, top: r * rowH, items: filtered.slice(r * cols, (r + 1) * cols) });
    }
    return out;
  });

  // 顶部横幅（对齐 macOS library.banner 的优先级：进行中优先于已结束）
  const banner = $derived.by((): { icon: string; text: string } | null => {
    if (genreInfo?.running) {
      const text = genreSummary(genreInfo);
      if (text) return { icon: ICONS.refresh, text };
    }
    if (importInfo?.running) {
      const text = importSummary(importInfo);
      if (text) return { icon: ICONS.refresh, text };
    }
    if (progress && isRunning(progress)) {
      const text = updateSummary(progress, importInfo);
      if (text) return { icon: ICONS.refresh, text };
    }
    if (genreInfo && !isStale(genreInfo.updated_ts, 6)) {
      const text = genreSummary(genreInfo);
      if (text) return { icon: phaseIcon(genreInfo.phase), text };
    }
    if (progress && !isStale(progress.updated_ts, 48)) {
      const text = updateSummary(progress, importInfo);
      if (text) return { icon: phaseIcon(progress.phase), text };
    }
    if (importInfo) {
      const text = importSummary(importInfo);
      if (text) return { icon: ICONS.hourglass, text };
    }
    return null;
  });

  function phaseIcon(phase: string | undefined): string {
    switch (phase) {
      case "done":
        return ICONS.check;
      case "failed":
        return ICONS.warn;
      case "busy":
        return ICONS.hourglass;
      default:
        return ICONS.refresh;
    }
  }

  const statusText = $derived.by(() => {
    switch (status) {
      case "loading":
        return "正在解析数据…";
      case "ready":
        if (lastError) return "更新失败；仍显示上次导入的作品";
        if (syncing) return "正在同步本地数据…";
        return `已更新 ${works.length} 部作品${loadedAt ? ` · ${loadedAt}` : ""}`;
      case "error":
        return "无法加载数据";
      default:
        return "请选择数据文件开始使用";
    }
  });

  // 作品右键菜单（对齐 macOS GameContextMenu：打开作品页 / 收藏夹 / 关注制作者）
  const menuItems = $derived.by(() => {
    const target = cardMenu?.work;
    const items: { label: string; action: () => void; danger?: boolean }[] = [];
    if (!target) return items;
    const key = makerKeyOf(target.maker, target.maker_id);
    items.push({ label: "打开作品页", action: () => openWork(target.url) });
    items.push({
      label: library.isFavorited(target.id) ? "移出我的收藏" : `加入「${DEFAULT_COLLECTION_NAME}」`,
      action: () => library.toggleFavorite(target.id),
    });
    for (const collection of library.data.collections) {
      if (collection.name === DEFAULT_COLLECTION_NAME) continue;
      const inside = collection.work_ids.includes(target.id);
      items.push({
        label: `${inside ? "✓ " : "　"}${collection.name}`,
        action: () => library.toggleIn(target.id, collection.id),
      });
    }
    items.push({
      label: "新建收藏夹并加入…",
      action: () => {
        collectionName = "";
        collectionPrompt = { workId: target.id };
      },
    });
    items.push({
      label: library.isFollowing(key)
        ? `取消关注「${target.maker || "制作者未知"}」`
        : `关注制作者「${target.maker || "制作者未知"}」`,
      action: () => library.toggleFollow(key, target.maker, target.maker_id ?? ""),
    });
    return items;
  });

  const displayMenuItems = $derived(
    VIEW_ORDER.map((mode) => ({
      label: `${view === mode ? "✓ " : "　"}${VIEWS[mode].label}（⌘${VIEWS[mode].shortcut}）`,
      action: () => setView(mode),
    })),
  );

  const updateMenuItems = $derived.by(() => {
    const items: { label: string; action: () => void; disabled?: boolean; divider?: boolean }[] = [];
    items.push({ label: "立即更新热榜（快）", action: () => void runUpdate("quick") });
    items.push({ label: "完整维护（同每日计划）", action: () => void runUpdate("daily") });
    items.push({ label: "最近一年", divider: true, action: () => void runUpdate("update-all", "1") });
    items.push({ label: "最近三年", action: () => void runUpdate("update-all", "3") });
    items.push({ label: "最近五年", action: () => void runUpdate("update-all", "5") });
    items.push({ label: "最近七年", action: () => void runUpdate("update-all", "7") });
    items.push({
      label: "自定义年份至今…",
      divider: true,
      action: () => {
        yearValue = new Date().getFullYear() - 5;
        yearDialog = { mode: "update" };
      },
    });
    items.push({
      label: "继续抓更早…",
      disabled: coverage === null,
      action: () => {
        if (!coverage) return;
        const covered = coverage.covered_years ?? 3;
        deeperValue = Math.min(Math.max(Math.floor(covered) + 1, 2), 29);
        yearDialog = { mode: "deeper" };
      },
    });
    return items;
  });

  const deeperOptions = $derived.by(() => {
    const covered = coverage?.covered_years ?? 3;
    const base = Math.min(Math.max(Math.floor(covered) + 1, 2), 29);
    const out: { value: number; label: string }[] = [];
    for (let years = base; years <= Math.min(base + 8, 30); years++) {
      out.push({ value: years, label: `最近 ${years} 年` });
    }
    return out;
  });

  const yearPickChoices = $derived.by(() => {
    const current = new Date().getFullYear();
    const out: { value: number; label: string }[] = [];
    for (let year = current; year >= 2006; year--) {
      out.push({ value: year, label: `${year} 年` });
    }
    return out;
  });

  const genreJobActive = $derived(genreInfo?.running === true);

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

  // 实测「最宽内容卡片」高度（视图 / 列宽 / 主题变化时自动重测）
  $effect(() => {
    const el = measureEl;
    if (!el) return;
    const observer = new ResizeObserver(() => {
      measuredH = el.offsetHeight;
    });
    observer.observe(el);
    measuredH = el.offsetHeight;
    return () => observer.disconnect();
  });

  // 筛选 / 排序 / 视图 / 视图范围变化时：回到顶部并收起浮窗与菜单
  $effect(() => {
    void filter.keyword;
    void filter.ratingLow;
    void filter.ratingHigh;
    void filter.includeUnrated;
    void filter.salesLow;
    void filter.salesHigh;
    void filter.priceLow;
    void filter.priceHigh;
    void filter.genres;
    void filter.excludeGenres;
    void filter.form;
    void filter.selectedYears;
    void filter.flags;
    void filter.genreFocus;
    void sort;
    void view;
    void viewFilter;
    hideHover();
    cardMenu = null;
    scroller?.scrollTo({ top: 0 });
    scrollTop = 0;
  });

  onMount(() => {
    void library.load();
    void bootstrap();
    const timer = setInterval(() => {
      void pollProgress();
    }, 2000);
    void pollProgress();
    return () => clearInterval(timer);
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
    const hadData = data !== null;
    if (!hadData) status = "loading";
    errorMessage = "";
    try {
      // 先让「加载中」渲染一帧，再做读文件与解析的重活
      await new Promise((resolve) => setTimeout(resolve, 0));
      data = await loadWorks();
      console.info(`[radar] 已加载 ${data.works.length} 件作品（${data.path}）`);
      scrollTop = 0;
      loadedAt = new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
      lastError = "";
      status = "ready";
    } catch (error) {
      console.error("[radar] 数据加载失败：", error);
      if (hadData) {
        // 对齐 macOS：保留上次导入的作品，仅提示失败
        lastError = String(error);
        updateError = String(error);
        status = "ready";
      } else {
        status = "error";
        errorMessage = String(error);
      }
    }
  }

  /** 更新（对齐 macOS）：先本地同步导出（纯本机、不联网），再重读文件。 */
  async function refreshData() {
    if (!data) {
      await pick();
      return;
    }
    syncing = true;
    try {
      const result = await runExport();
      console.info(`[radar] 本地同步导出：${result}`);
    } catch (error) {
      syncing = false;
      updateError = String(error);
      return;
    }
    await reload();
    syncing = false;
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
    cardMenu = null;
  }

  function openWork(url: string) {
    if (url) void openUrl(url);
  }

  function openMenu(work: WorkView, event: MouseEvent) {
    event.preventDefault();
    event.stopPropagation();
    hideHover();
    cardMenu = { x: event.clientX, y: event.clientY, work };
  }

  function openDisplayMenu(event: MouseEvent) {
    // 关键：阻止事件继续冒泡到 window，否则菜单挂载瞬间会被同一击关闭
    event.stopPropagation();
    if (displayMenu) {
      displayMenu = null;
      return;
    }
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    displayMenu = { x: rect.left, y: rect.bottom + 6 };
  }

  function openUpdateMenu(event: MouseEvent) {
    event.stopPropagation();
    if (updateMenu) {
      updateMenu = null;
      return;
    }
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    updateMenu = { x: Math.max(8, rect.right - 250), y: rect.bottom + 6 };
  }

  /** 个性化弹层：点击外部关闭（对齐 macOS popover 行为）。 */
  function onWindowClick(event: MouseEvent) {
    if (!showPersonalization) return;
    const target = event.target as HTMLElement | null;
    if (target?.closest(".popover") || target?.closest(".personalization-trigger")) return;
    showPersonalization = false;
  }

  // P21：悬停 0.5 秒显示浮窗
  function enterHover(work: WorkView, event: MouseEvent) {
    cancelHoverTimer();
    const x = event.clientX;
    const y = event.clientY;
    hoverTimer = setTimeout(() => {
      hoverX = x;
      hoverY = y;
      hoverWork = work;
    }, 500);
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

  async function pollProgress() {
    try {
      const next = await readProgress();
      const state = next.state;
      if (state && (state.updated_ts ?? 0) !== lastProgressTs) {
        const previous = progress?.phase;
        lastProgressTs = state.updated_ts ?? 0;
        if (state.phase === "done" && previous && ACTIVE_PHASES.has(previous)) {
          void reload(); // 更新完成 → 自动刷新数据
        }
      }
      progress = state;
      const imported = next.importProgress;
      if (imported) {
        const phase = imported.phase ?? "";
        if (phase === "done" && lastImportPhase === "enrich") {
          void reload(); // 渐进导入完成 → 自动刷新
        }
        lastImportPhase = phase;
      }
      importInfo = imported;
      const genre = next.genreProgress;
      if (genre && genre.done && !isStale(genre.updated_ts, 6) && (genre.updated_ts ?? 0) !== lastGenreDoneTs) {
        if (lastGenreDoneTs !== 0 || genreInfo !== null) {
          void reload(); // 分类抓取完成 → 自动刷新
          const id = genre.genre_id ?? "";
          const name = genre.genre_name ?? genreNameById(id);
          if (id) joinDailyRequest = { id, name };
        }
        lastGenreDoneTs = genre.updated_ts ?? 0;
      } else if (genre?.done) {
        lastGenreDoneTs = genre.updated_ts ?? lastGenreDoneTs;
      }
      genreInfo = genre;
      coverage = next.importCoverage;
    } catch {
      // 轮询失败不打扰（文件可能暂不可读；下次再试）
    }
  }

  function genreNameById(id: string): string {
    return genres.find((entry) => entry.id === id)?.name ?? id;
  }

  async function runUpdate(kind: "quick" | "daily" | "update-all", range?: string) {
    if (isRunning(progress) || genreJobActive) {
      window.alert("已有更新在运行中，进度见顶部横幅。");
      return;
    }
    try {
      await startUpdate(kind, range);
      await pollProgress();
    } catch (error) {
      window.alert(String(error));
    }
  }

  function setView(mode: ViewMode) {
    view = mode;
    prefs.set("displayMode", mode);
  }

  function onKeydown(event: KeyboardEvent) {
    if (event.metaKey || event.ctrlKey) {
      const index = Number(event.key);
      if (Number.isInteger(index) && index >= 1 && index <= VIEW_ORDER.length) {
        event.preventDefault();
        setView(VIEW_ORDER[index - 1]);
        return;
      }
    }
    if (event.key === "Escape") {
      hideHover();
      cardMenu = null;
      displayMenu = null;
      updateMenu = null;
      showPersonalization = false;
    }
  }

  /** 侧栏开关（对齐 macOS P16.1）：窗口向外扩展 / 缩回——关闭时右缘与内容不动。 */
  async function toggleSidebar() {
    const next = !prefs.data.sidebarVisible;
    prefs.set("sidebarVisible", next);
    try {
      const window_ = getCurrentWindow();
      const size = await window_.outerSize();
      const position = await window_.outerPosition();
      const scale = await window_.scaleFactor();
      const delta = 280 * scale;
      if (!next) {
        const targetWidth = Math.max(600 * scale, size.width - delta);
        const right = position.x + size.width;
        await window_.setSize(
          new LogicalSize(Math.round(targetWidth / scale), Math.round(size.height / scale)),
        );
        await window_.setPosition(
          new LogicalPosition(Math.round((right - targetWidth) / scale), Math.round(position.y / scale)),
        );
      } else {
        const monitor = await currentWindowMonitor();
        const screenMinX = monitor?.workArea.position.x ?? 0;
        const leftRoom = Math.max(0, position.x - screenMinX);
        const leftPart = Math.min(delta, leftRoom);
        await window_.setPosition(
          new LogicalPosition(
            Math.round((position.x - leftPart) / scale),
            Math.round(position.y / scale),
          ),
        );
        await window_.setSize(
          new LogicalSize(Math.round((size.width + delta) / scale), Math.round(size.height / scale)),
        );
      }
    } catch (error) {
      console.error("[radar] 侧栏窗口联动失败：", error);
    }
  }

  // ChipFilter（对齐 macOS）：分类/形式/标志芯片点击 → 筛选或取消
  function chipCategory(name: string) {
    if (filter.genres.includes(name)) {
      filter.genres = filter.genres.filter((item) => item !== name);
    } else {
      filter.genres = [...filter.genres, name];
      filter.excludeGenres = filter.excludeGenres.filter((item) => item !== name);
    }
  }

  function chipForm(name: string) {
    filter.form = filter.form === name ? "" : name;
  }

  function chipBadge(key: "voice" | "music" | "video") {
    filter.flags = { ...filter.flags, [key]: !filter.flags[key] };
  }

  // RankDisplay（对齐 macOS）：分类人气态显示该分类名次；官方人气排序显示全站名次
  function rankTextFor(work: WorkView): string | null {
    if (filter.genreFocus) {
      const position = work.genre_pos?.[filter.genreFocus];
      return typeof position === "number" ? `#${position}` : null;
    }
    if (sort === "trend" && typeof work.rank_trend_current === "number") {
      return `#${work.rank_trend_current}`;
    }
    return null;
  }

  function showMaker(work: WorkView) {
    viewFilter = {
      kind: "maker",
      key: makerKeyOf(work.maker, work.maker_id),
      name: work.maker || "制作者未知",
      makerId: work.maker_id ?? "",
    };
  }

  async function handleImportToggle(on: boolean) {
    try {
      await importSwitch(on, importYears);
      await pollProgress();
    } catch (error) {
      window.alert(String(error));
    }
  }

  async function handleGenreImport(id: string, name: string) {
    genreImportRequest = { id, name };
  }

  async function confirmGenreImport(id: string) {
    genreImportRequest = null;
    try {
      await startGenreImport(id, false);
      await pollProgress();
    } catch (error) {
      window.alert(String(error));
    }
  }

  async function handleGenreMore() {
    if (!filter.genreFocus || genreJobActive) return;
    try {
      await startGenreImport(filter.genreFocus, true);
      await pollProgress();
    } catch (error) {
      window.alert(String(error));
    }
  }

  /** 加入每日刷新 → 导出 + 重载（侧栏「每日刷新」计数随之更新）。 */
  async function handleGenreWatch(id: string) {
    try {
      await watchGenre(id);
      await refreshData();
    } catch (error) {
      updateError = String(error);
    }
  }

  async function handleGenreUnwatch(id: string) {
    try {
      await unwatchGenre(id);
      await refreshData();
    } catch (error) {
      updateError = String(error);
    }
  }

  async function handleGenreRemove(id: string) {
    try {
      await removeGenre(id);
      await refreshData();
    } catch (error) {
      updateError = String(error);
    }
  }

  function clearAllFilters() {
    filter = emptyFilter();
  }

  function submitCollection(value: string) {
    if (collectionPrompt) {
      library.createCollection(value, collectionPrompt.workId);
      collectionPrompt = null;
    }
  }
</script>

<svelte:head>
  <title>同人游戏雷达 · Doujin Game Radar</title>
</svelte:head>

<svelte:window onkeydown={onKeydown} onclick={onWindowClick} />

<div class="app">
  {#if prefs.data.sidebarVisible}
    <Sidebar
      bind:filter
      bind:viewFilter
      bind:importYears
      {works}
      {genres}
      {genreCatalog}
      collections={library.data.collections}
      makers={library.data.makers}
      importProgress={importInfo}
      genreProgress={genreInfo}
      onCreateCollection={(name) => library.createCollection(name)}
      onRenameCollection={(id, name) => library.renameCollection(id, name)}
      onDeleteCollection={(id) => {
        if (viewFilter.kind === "collection" && viewFilter.id === id) viewFilter = { kind: "all" };
        library.deleteCollection(id);
      }}
      onGenreImport={(id, name) => void handleGenreImport(id, name)}
      onGenreWatch={(id) => void handleGenreWatch(id)}
      onGenreUnwatch={(id) => void handleGenreUnwatch(id)}
      onGenreRemove={(id) => void handleGenreRemove(id)}
      onClearFilters={clearAllFilters}
      onImportToggle={(on) => void handleImportToggle(on)}
      onCancelImport={() => void cancelImport().then(() => pollProgress())}
      onCancelFollow={(maker) => library.toggleFollow(maker.key, maker.name, maker.maker_id)}
    />
  {/if}

  <div class="main">
    <header class="header">
      <div class="brand">
        <div class="brand-line">
          <div class="brand-title">同人游戏雷达</div>
          <button
            class="info-btn"
            title="数据来自你导入的文件。「更新」重读同一文件；「开始更新数据」运行本地管道（导入 → 销量 → 封面 → 导出），完成后自动刷新。收藏与偏好保存在本机。"
          >
            {@html ICONS.info}
          </button>
        </div>
        <div class="brand-sub">{statusText}</div>
      </div>
      <div class="actions">
        <button
          class="icon-btn"
          title={prefs.data.sidebarVisible ? "收起筛选侧栏（窗口同步缩回）" : "展开筛选侧栏（窗口同步扩展）"}
          onclick={() => void toggleSidebar()}
        >
          {@html ICONS.sidebar}
        </button>
        <button class="btn with-icon" title="显示形式（⌘1–⌘5，记住选择）" onclick={openDisplayMenu}>
          {@html VIEWS[view].icon}
          {VIEWS[view].label}
        </button>
        <button
          class="btn with-icon personalization-trigger"
          class:active={showPersonalization}
          onclick={(event) => {
            event.stopPropagation();
            showPersonalization = !showPersonalization;
          }}
        >
          {@html ICONS.slider}个性化
        </button>
        <button class="btn with-icon" onclick={openUpdateMenu}>
          {@html ICONS.tray}开始更新数据 ▾
        </button>
        <button
          class="btn primary with-icon"
          onclick={() => void refreshData()}
          disabled={status === "loading" || syncing}
        >
          {@html ICONS.refresh}更新
        </button>
      </div>
    </header>

    {#if showPersonalization}
      <div class="popover">
        <div class="pop-title">个性化显示</div>
        <div class="pop-divider"></div>
        <label class="pop-check">
          <input
            type="checkbox"
            checked={prefs.data.showBadges}
            onchange={(event) => prefs.set("showBadges", event.currentTarget.checked)}
          />
          徽章（配音 / 音乐 / 动画）
        </label>
        <label class="pop-check">
          <input
            type="checkbox"
            checked={prefs.data.showDiscount}
            onchange={(event) => prefs.set("showDiscount", event.currentTarget.checked)}
          />
          折扣角标与原价划线
        </label>
        <label class="pop-check">
          <input
            type="checkbox"
            checked={prefs.data.showRatingCount}
            onchange={(event) => prefs.set("showRatingCount", event.currentTarget.checked)}
          />
          评价人数
        </label>
        <div class="pop-note">偏好保存在本机，立即生效。</div>
      </div>
    {/if}

    {#if banner}
      <div class="banner-wrap">
        <UpdateBanner icon={banner.icon} text={banner.text} />
      </div>
    {/if}

    {#if viewFilter.kind !== "all"}
      <div class="strip">
        <span class="strip-icon">{@html ICONS.filterCircle}</span>
        <span class="strip-title">{viewFilterTitle(viewFilter, collectionNameOf)}</span>
        <span class="strip-count">· 命中 {filtered.length} 部</span>
        <span class="spacer"></span>
        {#if activeMaker}
          {#if activeMaker.makerId}
            <button
              class="link with-icon"
              title="打开该作者主页（网页端，包含未在本机入库的作品）"
              onclick={() =>
                openWork(
                  `https://www.dlsite.com/maniax/circle/profile/=/maker_id/${activeMaker.makerId}.html`,
                )}
            >
              {@html ICONS.external}在 DLsite 查看全量作品
            </button>
          {/if}
          <button
            class="link"
            onclick={() => library.toggleFollow(activeMaker.key, activeMaker.name, activeMaker.makerId)}
          >
            {library.isFollowing(activeMaker.key) ? "取消关注" : "关注此作者"}
          </button>
        {/if}
        <button class="link" onclick={() => (viewFilter = { kind: "all" })}>返回全部作品</button>
      </div>
    {/if}

    {#if activeGenre}
      <div class="strip">
        <span class="strip-icon">{@html ICONS.chartBarFill}</span>
        <span class="strip-title">分类人气：「{activeGenre.name}」按官方人气名次</span>
        <span class="spacer"></span>
        <button class="link" onclick={() => (filter.genreFocus = "")}>返回全部作品</button>
      </div>
    {/if}

    {#if status === "ready" && data}
      <div class="count-row">
        <span class="count-text">找到 {filtered.length} 部作品</span>
        <span class="spacer"></span>
        <select class="sort-select" bind:value={sort} aria-label="排序">
          {#each SORT_OPTIONS as option (option.key)}
            <option value={option.key}>{option.label}</option>
          {/each}
        </select>
      </div>
      <div class="scroller" bind:this={scroller} onscroll={onScroll}>
        <div class="canvas" style="height: {totalHeight + 22}px">
          {#if measureWork}
            <div
              class="measure"
              style="width: {cfg.kind === 'list' ? usable : cellW}px"
              bind:this={measureEl}
              aria-hidden="true"
            >
              {#if view === "largeCards"}
                <LargeRow
                  game={measureWork}
                  showBadges
                  showDiscount
                  showRatingCount
                  rankText="#88"
                  onopen={() => {}}
                />
              {:else if view === "compact"}
                <CompactRow
                  game={measureWork}
                  showBadges
                  showDiscount
                  showRatingCount
                  rankText="#88"
                  onopen={() => {}}
                />
              {:else if view === "coverWall"}
                <CoverTile game={measureWork} showBadges />
              {:else}
                <MediumCard
                  game={measureWork}
                  showBadges
                  showDiscount
                  showRatingCount
                  rankText="#88"
                  onopen={() => {}}
                />
              {/if}
            </div>
          {/if}
          {#each rows as row (row.key)}
            <div class="grid-row" style="top: {row.top}px; gap: {cfg.gap}px">
              {#each row.items as w (w.id)}
                <div
                  class="cell"
                  role="listitem"
                  style="height: {itemH}px; {cfg.kind === 'list' ? 'flex:1;' : `width:${cellW}px;`}"
                  ondblclick={() => openWork(w.url)}
                  oncontextmenu={(event) => openMenu(w, event)}
                  onmouseenter={(event) => enterHover(w, event)}
                  onmouseleave={leaveHover}
                >
                  {#if view === "largeCards"}
                    <LargeRow
                      game={w}
                      showBadges={prefs.data.showBadges}
                      showDiscount={prefs.data.showDiscount}
                      showRatingCount={prefs.data.showRatingCount}
                      rankText={rankTextFor(w)}
                      oncats={chipCategory}
                      onform={chipForm}
                      onbadge={chipBadge}
                      onmaker={() => showMaker(w)}
                      onopen={() => openWork(w.url)}
                    />
                  {:else if view === "compact"}
                    <CompactRow
                      game={w}
                      showBadges={prefs.data.showBadges}
                      showDiscount={prefs.data.showDiscount}
                      showRatingCount={prefs.data.showRatingCount}
                      rankText={rankTextFor(w)}
                      onbadge={chipBadge}
                      onmaker={() => showMaker(w)}
                      onopen={() => openWork(w.url)}
                    />
                  {:else if view === "coverWall"}
                    <CoverTile game={w} showBadges={prefs.data.showBadges} onbadge={chipBadge} />
                  {:else}
                    <MediumCard
                      game={w}
                      showBadges={prefs.data.showBadges}
                      showDiscount={prefs.data.showDiscount}
                      showRatingCount={prefs.data.showRatingCount}
                      rankText={rankTextFor(w)}
                      oncats={chipCategory}
                      onform={chipForm}
                      onbadge={chipBadge}
                      onmaker={() => showMaker(w)}
                      onopen={() => openWork(w.url)}
                    />
                  {/if}
                </div>
              {/each}
            </div>
          {/each}
          {#if filtered.length === 0}
            <div class="empty-state">
              <span class="empty-icon">{@html ICONS.stackSlash}</span>
              <span>当前条件没有匹配的作品，请调整筛选区间或收藏夹。</span>
            </div>
          {/if}
        </div>
        {#if activeGenre}
          <div class="genre-footer">
            <div class="gf-divider"></div>
            <div class="gf-row">
              {#if typeof activeGenre.count === "number"}
                <span class="gf-text">
                  「{activeGenre.name}」已加载名次 {Math.min(activeGenre.depth ?? 0, activeGenre.count)}/{activeGenre.count}
                </span>
              {:else}
                <span class="gf-text">「{activeGenre.name}」已加载名次 {activeGenre.depth ?? 0}</span>
              {/if}
              {#if activeGenre.seen_at}
                <span class="gf-date">数据 {String(activeGenre.seen_at).slice(0, 10)}</span>
              {/if}
              <span class="spacer"></span>
              {#if genreJobActive}
                <span class="gf-progress"><span class="spin"></span>正在导入…</span>
              {:else if typeof activeGenre.count === "number" && (activeGenre.depth ?? 0) >= activeGenre.count}
                <span class="gf-date">已到末尾</span>
              {:else}
                <button
                  class="btn small with-icon"
                  title="现抓下一段人气名次；榜上不在库的作品会顺带入库"
                  onclick={() => void handleGenreMore()}
                >
                  {@html ICONS.plus}载入更多（下一 100 名，含新作品入库）
                </button>
              {/if}
            </div>
          </div>
        {/if}
      </div>
    {:else if status === "loading"}
      <div class="center">
        <span class="empty-icon">{@html ICONS.stackSlash}</span>
        <p>正在解析数据…（约 9k 作品）</p>
      </div>
    {:else if status === "error"}
      <div class="center">
        <h1>无法加载数据</h1>
        <p class="error">{errorMessage}</p>
        <button class="btn" onclick={pick}>选择数据文件</button>
      </div>
    {:else}
      <div class="center">
        <h1>同人游戏雷达 · Doujin Game Radar</h1>
        <p>未自动找到数据文件；请选择由数据管道导出的 <code>works.json</code></p>
        <p class="hint">
          启动时会自动查找常见位置（本地仓库的 <code>out/works.json</code>）；封面在其旁边的 <code>covers/</code> 目录，数据全部留在本机
        </p>
        <button class="btn primary" onclick={pick}>选择数据文件</button>
      </div>
    {/if}
  </div>
</div>

{#if hoverWork}
  <HoverPanel game={hoverWork} x={hoverX} y={hoverY} {genres} />
{/if}

{#if cardMenu}
  <ContextMenu x={cardMenu.x} y={cardMenu.y} items={menuItems} onclose={() => (cardMenu = null)} />
{/if}

{#if displayMenu}
  <ContextMenu
    x={displayMenu.x}
    y={displayMenu.y}
    items={displayMenuItems}
    onclose={() => (displayMenu = null)}
  />
{/if}

{#if updateMenu}
  <ContextMenu
    x={updateMenu.x}
    y={updateMenu.y}
    items={updateMenuItems}
    onclose={() => (updateMenu = null)}
  />
{/if}

{#if collectionPrompt}
  <PromptDialog
    title="新建收藏夹"
    label="收藏夹名称"
    placeholder="收藏夹名称"
    bind:value={collectionName}
    onsubmit={(value) => void submitCollection(value)}
    oncancel={() => (collectionPrompt = null)}
  />
{/if}

{#if genreImportRequest}
  <ConfirmDialog
    title="导入分类人气"
    message={`「${genreImportRequest.name}」尚未导入人气数据。现在抓取并入库？（含榜上新作品，约 1–3 分钟；进度见顶部横幅）`}
    confirmLabel="开始导入（前 200 名）"
    danger={false}
    onconfirm={() => void confirmGenreImport(genreImportRequest?.id ?? "")}
    oncancel={() => (genreImportRequest = null)}
  />
{/if}

{#if joinDailyRequest}
  <ConfirmDialog
    title="加入每日刷新？"
    message={`「${joinDailyRequest.name}」已导入。是否加入每日自动刷新列表？（写入配置 genre_rank_ids）`}
    confirmLabel="加入"
    cancelLabel="不用"
    danger={false}
    onconfirm={() => {
      const request = joinDailyRequest;
      joinDailyRequest = null;
      if (request) void watchGenre(request.id);
    }}
    oncancel={() => (joinDailyRequest = null)}
  />
{/if}

{#if yearDialog?.mode === "update"}
  <YearPickerDialog
    title="自定义更新范围"
    message={`更新将导入 ${yearValue} 年至今的作品（导入 → 销量 → 封面 → 导出）。`}
    options={yearPickChoices}
    bind:value={yearValue}
    confirmLabel="开始更新"
    onsubmit={(year) => {
      yearDialog = null;
      void runUpdate("update-all", `since:${year}`);
    }}
    oncancel={() => (yearDialog = null)}
  />
{/if}

{#if yearDialog?.mode === "deeper"}
  <YearPickerDialog
    title="继续抓更早"
    message={coverage
      ? `已覆盖 ${coverage.covered_years !== undefined ? `≈${coverage.covered_years.toFixed(1)} 年` : "（年限未知）"}（约第 ${coverage.page ?? 0} 页）；新任务将跳过这一段，从覆盖点继续往更早抓。`
      : "还没有已覆盖记录（完成过一次目录遍历导入后可用）。"}
    options={deeperOptions}
    bind:value={deeperValue}
    confirmLabel="开始更新"
    confirmDisabled={coverage === null}
    onsubmit={(years) => {
      yearDialog = null;
      void runUpdate("update-all", `deeper:${years}`);
    }}
    oncancel={() => (yearDialog = null)}
  />
{/if}

{#if updateError}
  <ConfirmDialog
    title="无法更新"
    message={updateError}
    confirmLabel="知道了"
    hideCancel
    onconfirm={() => (updateError = "")}
    oncancel={() => (updateError = "")}
  />
{/if}

<style>
  .app {
    display: flex;
    height: 100vh;
  }

  .main {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }

  .header {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 18px 22px 14px;
    flex-wrap: wrap;
  }

  .brand {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .brand-line {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .info-btn {
    appearance: none;
    border: 0;
    background: transparent;
    color: var(--muted);
    padding: 0;
    display: inline-flex;
    cursor: default;
  }

  .info-btn:hover {
    color: var(--accent);
  }

  .brand-title {
    font-size: 25px;
    font-weight: 700;
    line-height: 30px;
  }

  .brand-sub {
    font-size: 12px;
    color: var(--muted);
  }

  .actions {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }

  .icon-btn {
    appearance: none;
    border: 1px solid var(--border);
    background: var(--panel);
    color: var(--text);
    border-radius: 8px;
    padding: 6px 9px;
    display: inline-flex;
    align-items: center;
    cursor: pointer;
  }

  .icon-btn:hover {
    border-color: var(--accent);
  }

  .btn.with-icon,
  .link.with-icon {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }

  .btn.active {
    border-color: var(--accent);
    color: var(--accent);
    font-weight: 600;
  }

  .btn.small {
    padding: 4px 10px;
    font-size: 12px;
  }

  .link {
    appearance: none;
    border: 0;
    background: transparent;
    color: var(--accent);
    font: inherit;
    font-size: 12px;
    padding: 2px 0;
    cursor: pointer;
  }

  .popover {
    position: fixed;
    top: 62px;
    right: 22px;
    z-index: 150;
    width: 250px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 14px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 10px;
    box-shadow: 0 10px 30px rgb(0 0 0 / 25%);
  }

  .pop-title {
    font-size: 13px;
    font-weight: 600;
  }

  .pop-divider {
    border-top: 1px solid var(--border);
    margin: 2px 0;
  }

  .pop-check {
    display: flex;
    align-items: center;
    gap: 7px;
    font-size: 12.5px;
    cursor: pointer;
  }

  .pop-note {
    font-size: 11px;
    color: var(--muted);
  }

  .banner-wrap {
    border-bottom: 1px solid var(--border);
  }

  .strip {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 22px;
    background: color-mix(in srgb, var(--accent) 7%, transparent);
    border-bottom: 1px solid var(--border);
  }

  .strip-icon {
    display: inline-flex;
    color: var(--muted);
  }

  .strip-title {
    font-size: 13px;
    font-weight: 600;
  }

  .strip-count {
    font-size: 12px;
    color: var(--muted);
  }

  .spacer {
    flex: 1;
  }

  .count-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 13px 22px;
  }

  .count-text {
    font-size: 13.5px;
    color: var(--muted);
  }

  .sort-select {
    width: 205px;
    border: 1px solid var(--border);
    background: var(--panel);
    color: var(--text);
    border-radius: 8px;
    padding: 5px 8px;
    font-size: 12.5px;
    font-family: inherit;
  }

  .scroller {
    flex: 1;
    overflow-y: auto;
    overscroll-behavior: contain;
  }

  .canvas {
    position: relative;
  }

  .measure {
    position: absolute;
    left: -20000px;
    top: 0;
    visibility: hidden;
    pointer-events: none;
  }

  .grid-row {
    position: absolute;
    left: 22px;
    right: 22px;
    display: flex;
    align-items: stretch;
  }

  .cell {
    position: relative;
    min-width: 0;
  }

  .empty-state {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    min-height: 370px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 14px;
    color: var(--muted);
    font-size: 13px;
  }

  .empty-icon {
    display: inline-flex;
    color: var(--muted);
    opacity: 0.7;
  }

  .genre-footer {
    padding-bottom: 18px;
  }

  .gf-divider {
    border-top: 1px solid var(--border);
    margin: 0 22px;
  }

  .gf-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 22px 0;
  }

  .gf-text {
    font-size: 12px;
    color: var(--muted);
  }

  .gf-date {
    font-size: 12px;
    color: var(--muted);
    opacity: 0.8;
  }

  .gf-progress {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: var(--muted);
  }

  .spin {
    width: 12px;
    height: 12px;
    border: 2px solid color-mix(in srgb, var(--accent) 30%, transparent);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.9s linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
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
