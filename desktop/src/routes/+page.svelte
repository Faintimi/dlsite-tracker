<script lang="ts">
  import { onMount, untrack } from "svelte";
  import { LogicalPosition, LogicalSize } from "@tauri-apps/api/dpi";
  import { currentMonitor as currentWindowMonitor, getCurrentWindow } from "@tauri-apps/api/window";
  import { openUrl } from "@tauri-apps/plugin-opener";
  import {
    getDataPath,
    loadWorks,
    pickDataFile,
    runExport,
    bootstrapPipeline,
    dataFileStamp,
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
  import DiscoveryFeedbackDialog from "$lib/DiscoveryFeedbackDialog.svelte";
  import HoverPanel from "$lib/HoverPanel.svelte";
  import UpdateBanner from "$lib/UpdateBanner.svelte";
  import ConfirmDialog from "$lib/ConfirmDialog.svelte";
  import PromptDialog from "$lib/PromptDialog.svelte";
  import YearPickerDialog from "$lib/YearPickerDialog.svelte";
  import Sidebar from "$lib/Sidebar.svelte";
  import TasteEditor from "$lib/TasteEditor.svelte";
  import TagChip from "$lib/TagChip.svelte";
  import { CONTENT_FLAG_TAGS } from "$lib/tag";
  import { matchingGenreCandidates } from "$lib/genreCatalog";
  import { DEFAULT_COLLECTION_NAME, library } from "$lib/library.svelte";
  import { prefs } from "$lib/prefs.svelte";
  import { ICONS, categoriesOf } from "$lib/ui";
  import CompactRow from "$lib/CompactRow.svelte";
  import CoverTile from "$lib/CoverTile.svelte";
  import Discover from "$lib/Discover.svelte";
  import FollowUpdates from "$lib/FollowUpdates.svelte";
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

  function releaseTimestamp(value: string): number {
    const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
    if (match) return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3])).getTime();
    const stamp = Date.parse(value);
    return Number.isFinite(stamp) ? stamp : 0;
  }

  let status = $state<Status>("empty");
  let errorMessage = $state("");
  let initializing = $state(false);
  let initProgressObserved = false;
  let data = $state<LoadedData | null>(null);
  let syncing = $state(false);
  let updateStarting = $state(false);
  let updateLaunchToken = 0;
  let lastError = $state("");
  let lastDataStamp = "";
  let loadedAt = $state("");
  let updateError = $state("");

  let view = $state<ViewMode>(normalizeView(prefs.data.displayMode));
  /** 主区模式：浏览（列表）/ 发现（口味匹配与黑马信号） */
  let mode = $state<"browse" | "discover" | "followUpdates">("browse");
  let discoverReturnMode = $state<"browse" | "followUpdates">("browse");
  let followUpdatesVisited = $state(false);
  let returnToFollowUpdates = $state(false);
  let manualRefreshCount = $state(0);
  let sort = $state<SortKey>("sales");
  let filter = $state<FilterState>(emptyFilter());
  const activeContentFlags = $derived(CONTENT_FLAG_TAGS.filter(({ key }) => filter.flags[key]));
  let viewFilter = $state<ViewFilter>({ kind: "all" });
  let importYears = $state("1");

  let showPersonalization = $state(false);
  let cardMenu = $state<{ x: number; y: number; work: WorkView; discovery: boolean } | null>(null);
  let displayMenu = $state<{ x: number; y: number } | null>(null);
  let updateMenu = $state<{ x: number; y: number } | null>(null);

  let progress = $state<UpdateState | null>(null);
  let importInfo = $state<ImportProgress | null>(null);
  let genreInfo = $state<GenreProgress | null>(null);
  let coverage = $state<ImportCoverage | null>(null);
  let lastProgressToken = "";
  let lastGenreDoneTs = 0;
  let lastImportPhase = "";
  let progressReady = $state(false);
  let coverRecoveryAttempted = $state(false);

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
  let genreImportRequest = $state<{ id: string; name: string; source?: "chip" } | null>(null);
  let pendingCategoryImport = $state<{ id: string; name: string } | null>(null);
  let categoryImportReady = $state<{ id: string; name: string } | null>(null);
  let categoryMenu = $state<{ name: string; x: number; y: number; selectedId?: string } | null>(null);
  let genrePreferenceSaving = $state(false);
  let joinDailyRequest = $state<{ id: string; name: string } | null>(null);
  let yearDialog = $state<{ mode: "update" | "deeper" } | null>(null);
  let yearValue = $state(new Date().getFullYear() - 5);
  let deeperValue = $state(7);
  let dislikeRequest = $state<WorkView | null>(null);
  let tasteEditorOpen = $state(false);

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
  /** 发现系统：已关注作者的 key 集合（用于口味得分加分） */
  const followedMakers = $derived(new Set(library.data.makers.map((maker) => maker.key)));
  const recentFollowedWorks = $derived.by(() => {
    const now = new Date();
    const end = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1).getTime() - 1;
    const start = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 13).getTime();
    return works
      .filter((work) => {
        if (!followedMakers.has(makerKeyOf(work.maker, work.maker_id))) return false;
        const released = releaseTimestamp(work.regist_date);
        return released >= start && released <= end;
      })
      .sort((a, b) => releaseTimestamp(b.regist_date) - releaseTimestamp(a.regist_date));
  });
  const unreadFollowUpdateIds = $derived(library.unreadFollowUpdateIds());
  const unreadFollowUpdates = $derived(
    recentFollowedWorks.filter((work) => unreadFollowUpdateIds.has(work.id)),
  );
  const unreadFollowMakerCount = $derived(
    new Set(unreadFollowUpdates.map((work) => makerKeyOf(work.maker, work.maker_id))).size,
  );
  const seenIds = $derived(library.seenIds());
  const dismissedIds = $derived(library.dismissedIds());
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
    if (progress && isRunning(progress)) {
      const text = updateSummary(progress, importInfo);
      if (text) return { icon: ICONS.refresh, text };
    }
    if (importInfo?.running) {
      const text = importSummary(importInfo);
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
    const items: { label: string; action: () => void; danger?: boolean; divider?: boolean }[] = [];
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
    if (cardMenu?.discovery) {
      items.push({
        label: "不感兴趣…",
        danger: true,
        divider: true,
        action: () => (dislikeRequest = target),
      });
    }
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
  const pipelineBusy = $derived(initializing || updateStarting || isRunning(progress) || genreJobActive);
  const categoryImportBusy = $derived(pipelineBusy || syncing || importInfo?.running === true || pendingCategoryImport !== null || genrePreferenceSaving);
  const categoryMenuItems = $derived.by(() => {
    const menu = categoryMenu;
    if (!menu) return [];
    const candidates = matchingGenreCandidates(menu.name, genreCatalog, genres);
    const items: { label: string; action: () => void; disabled?: boolean; divider?: boolean }[] = [];
    if (candidates.length === 0) {
      return [{ label: "官方人气榜目录未找到此分类", action: () => {}, disabled: true }];
    }
    if (candidates.length > 1 && !menu.selectedId) {
      items.push({ label: "请选择对应的官方分类 ID", action: () => {}, disabled: true });
      for (const candidate of candidates) {
        items.push({
          label: `${candidate.name}（ID ${candidate.id}）`,
          action: () => { categoryMenu = { ...menu, selectedId: candidate.id }; },
        });
      }
      return items;
    }
    const candidate = candidates.find((entry) => entry.id === menu.selectedId) ?? candidates[0];
    const imported = genres.find((entry) => entry.id === candidate.id && (entry.depth ?? 0) > 0);
    if (imported) {
      items.push({
        label: `查看「${candidate.name}」人气榜`,
        action: () => { filter.genreFocus = candidate.id; categoryImportReady = null; },
      });
      items.push({
        label: imported.watched ? "取消每日刷新" : "加入每日刷新",
        action: () => void (imported.watched ? handleGenreUnwatch(candidate.id) : handleGenreWatch(candidate.id)),
        disabled: categoryImportBusy,
      });
    } else {
      items.push({
        label: `导入「${candidate.name}」人气榜（前 200 名）…`,
        action: () => { genreImportRequest = { ...candidate, source: "chip" }; },
        disabled: categoryImportBusy,
      });
    }
    if (categoryImportBusy) {
      items.push({ label: "当前有任务进行中，请完成后再试", action: () => {}, disabled: true, divider: true });
    }
    return items;
  });

  function openCategoryMenu(name: string, event: MouseEvent) {
    event.preventDefault();
    event.stopPropagation();
    hideHover();
    cardMenu = null;
    categoryMenu = { name, x: event.clientX, y: event.clientY };
  }

  // 旧版首次初始化可能遗留“作品已富化但封面阶段从未启动”的全空状态。
  // 新版启动后自动修复一次；这是数据管道不变量，不向用户暴露补救按钮。
  $effect(() => {
    if (
      !progressReady ||
      coverRecoveryAttempted ||
      status !== "ready" ||
      works.length === 0 ||
      works.some((work) => Boolean(work.image_path)) ||
      isRunning(progress) ||
      genreJobActive
    ) {
      return;
    }
    coverRecoveryAttempted = true;
    void startUpdate("covers")
      .then(() => pollProgress())
      .catch((error) => {
        updateError = `自动补齐封面失败：${String(error)}`;
      });
  });

  let followScanSignature = "";
  $effect(() => {
    if (!library.loaded || status !== "ready") return;
    const signature = `${[...followedMakers].sort().join(",")}|${recentFollowedWorks.map((work) => work.id).join(",")}`;
    if (signature === followScanSignature) return;
    followScanSignature = signature;
    library.checkFollowUpdates(recentFollowedWorks.map((work) => work.id));
  });

  $effect(() => {
    const el = scroller;
    if (!el) return;
    // 发现／关注更新会卸载浏览列表；返回时恢复虚拟列表的真实滚动位置。
    el.scrollTop = untrack(() => scrollTop);
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
    void filter.forms;
    void filter.selectedYears;
    void filter.flags;
    void filter.genreFocus;
    void sort;
    void view;
    void viewFilter;
    hideHover();
    cardMenu = null;
    // 只追踪上方筛选项；容器重建本身不应触发回到顶部。
    untrack(() => scroller?.scrollTo({ top: 0 }));
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
      if (path) {
        await reload();
        lastDataStamp = (await dataFileStamp()) ?? "";
      }
    } catch (error) {
      status = "error";
      errorMessage = String(error);
    }
  }

  /** 首次使用：一键初始化内嵌管道（本机抓取热榜，约 5–10 分钟）。
   *  进度与完成后刷新由 pollProgress（2 秒轮询）接管。 */
  async function initPipeline() {
    if (initializing || status === "ready") return;
    initializing = true;
    initProgressObserved = false;
    try {
      await bootstrapPipeline();
      console.info("[radar] 已开始初始化（内嵌管道）");
    } catch (error) {
      initializing = false;
      updateError = String(error);
    }
  }

  async function reload(options: { quiet?: boolean; keepScroll?: boolean } = {}) {
    const hadData = data !== null;
    if (!options.quiet && !hadData) status = "loading";
    if (!options.quiet) errorMessage = "";
    try {
      // 先让「加载中」渲染一帧，再做读文件与解析的重活
      await new Promise((resolve) => setTimeout(resolve, 0));
      data = await loadWorks();
      console.info(`[radar] 已加载 ${data.works.length} 件作品（${data.path}）`);
      if (!options.keepScroll) {
        // 虚拟列表的逻辑位置与真实滚动容器必须一起归零。
        // 只改 scrollTop 状态会把行渲染在顶部，却让容器停在旧位置，出现空白列表。
        scroller?.scrollTo({ top: 0 });
        scrollTop = 0;
      } else if (scroller) {
        scrollTop = scroller.scrollTop;
      }
      loadedAt = new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
      lastError = "";
      status = "ready";
    } catch (error) {
      if (options.quiet) {
        // 静默重载（数据可能正在写入）：不打断当前界面，下次轮询再试
        console.warn("[radar] 静默重载失败：", error);
        return;
      }
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
    if (syncing || pipelineBusy || status === "loading") return;
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
    manualRefreshCount += 1;
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
    categoryMenu = null;
  }

  function openWork(url: string) {
    if (url) void openUrl(url);
  }

  function openMenu(work: WorkView, event: MouseEvent) {
    event.preventDefault();
    event.stopPropagation();
    hideHover();
    categoryMenu = null;
    cardMenu = { x: event.clientX, y: event.clientY, work, discovery: false };
  }

  function openDiscoveryMenu(work: WorkView, event: MouseEvent) {
    event.preventDefault();
    event.stopPropagation();
    hideHover();
    cardMenu = { x: event.clientX, y: event.clientY, work, discovery: true };
  }

  function matchedTaste(work: WorkView): string[] {
    const categories = new Set(categoriesOf(work));
    return Object.entries(prefs.data.tasteProfile)
      .filter(([name, level]) => level !== "less" && categories.has(name))
      .map(([name]) => name);
  }

  function dismissDiscovery(adjustTaste: boolean) {
    const work = dislikeRequest;
    dislikeRequest = null;
    if (!work) return;
    const matched = matchedTaste(work);
    library.dismiss(work.id);
    if (adjustTaste && matched.length > 0) {
      const remove = new Set(matched);
      prefs.replaceTasteProfile(
        Object.fromEntries(
          Object.entries(prefs.data.tasteProfile).filter(([name]) => !remove.has(name)),
        ),
      );
    }
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
      // 数据文件被更新（抓取中途导出 / 命令行导出）→ 静默重载并保持滚动位置
      const stamp = await dataFileStamp().catch(() => null);
      if (stamp && stamp !== lastDataStamp) {
        lastDataStamp = stamp;
        void reload({ quiet: true, keepScroll: true });
      }
      const next = await readProgress();
      progressReady = true;
      const state = next.state;
      if (isRunning(state)) updateStarting = false;
      if (state?.years === "bootstrap" && isRunning(state)) {
        initProgressObserved = true;
        if (!data) initializing = true;
      }
      const progressToken = state ? `${state.updated_ts ?? 0}:${state.phase ?? ""}:${state.years ?? ""}` : "";
      if (state && progressToken !== lastProgressToken) {
        const previous = progress?.phase;
        lastProgressToken = progressToken;
        if (state.phase === "done" && (initProgressObserved || (previous && ACTIVE_PHASES.has(previous)))) {
          if (initializing) initializing = false;
          initProgressObserved = false;
          void reload({ keepScroll: true }); // 更新完成 → 自动刷新数据（保持浏览位置）
        } else if (state.phase === "failed" && initializing && initProgressObserved) {
          initializing = false;
          initProgressObserved = false;
          updateError = state.detail || "初始化失败；详见数据目录日志";
        }
      }
      progress = state;
      const imported = next.importProgress;
      if (imported) {
        const phase = imported.phase ?? "";
        if (phase === "done" && lastImportPhase === "enrich") {
          void reload({ keepScroll: true }); // 渐进导入完成 → 自动刷新
        }
        lastImportPhase = phase;
      }
      importInfo = imported;
      const genre = next.genreProgress;
      if (
        pendingCategoryImport?.id === genre?.genre_id &&
        (genre?.phase === "failed" || genre?.phase === "busy")
      ) {
        pendingCategoryImport = null;
        updateError = genre.detail || genre.error || "分类人气榜导入未完成";
      }
      if (genre && genre.done && !isStale(genre.updated_ts, 6) && (genre.updated_ts ?? 0) !== lastGenreDoneTs) {
        if (lastGenreDoneTs !== 0 || genreInfo !== null) {
          const refreshed = reload({ keepScroll: true }); // 分类抓取完成 → 自动刷新
          const id = genre.genre_id ?? "";
          const name = pendingCategoryImport?.name || genre.genre_name || genreNameById(id);
          if (pendingCategoryImport?.id === id) {
            pendingCategoryImport = null;
            if (genre.error) updateError = genre.error;
            else void refreshed.then(() => {
              if (data?.file.genres?.some((entry) => entry.id === id && (entry.depth ?? 0) > 0)) {
                categoryImportReady = { id, name };
              } else {
                updateError = `「${name}」导入已结束，但新榜单尚未出现在数据文件中；请稍后点「更新」重读`;
              }
            });
          } else if (id && !genre.error) {
            joinDailyRequest = { id, name };
          }
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
    return genres.find((entry) => entry.id === id)?.name ?? genreCatalog.find((entry) => entry.id === id)?.name ?? id;
  }

  async function runUpdate(kind: "quick" | "daily" | "covers" | "update-all", range?: string) {
    if (pipelineBusy || syncing || status !== "ready") return;
    updateStarting = true;
    const launchToken = ++updateLaunchToken;
    try {
      await startUpdate(kind, range);
      await pollProgress();
    } catch (error) {
      updateStarting = false;
      window.alert(String(error));
    } finally {
      // 子进程先启动、随后才写进度；保持忙碌态直到观察到活动阶段。
      // 极端启动失败且未留下进度时，超时恢复按钮以便重试。
      setTimeout(() => {
        if (launchToken === updateLaunchToken) updateStarting = false;
      }, 30000);
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
    filter.forms = filter.forms.includes(name)
      ? filter.forms.filter((item) => item !== name)
      : [...filter.forms, name];
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
    returnToFollowUpdates = false;
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

  async function confirmGenreImport() {
    const request = genreImportRequest;
    genreImportRequest = null;
    if (!request) return;
    if (request.source === "chip" && (pipelineBusy || syncing || importInfo?.running || genrePreferenceSaving)) {
      updateError = "当前有任务进行中，请完成后再导入分类人气榜";
      return;
    }
    if (request.source === "chip") {
      pendingCategoryImport = { id: request.id, name: request.name };
      categoryImportReady = null;
    }
    try {
      await startGenreImport(request.id, false);
      await pollProgress();
    } catch (error) {
      if (request.source === "chip") pendingCategoryImport = null;
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
  async function setGenreWatched(id: string, watched: boolean) {
    if (genrePreferenceSaving) return;
    genrePreferenceSaving = true;
    try {
      if (watched) await watchGenre(id);
      else await unwatchGenre(id);
      await runExport();
      await reload({ quiet: true, keepScroll: true });
    } catch (error) {
      updateError = String(error);
    } finally {
      genrePreferenceSaving = false;
    }
  }

  async function handleGenreWatch(id: string) {
    await setGenreWatched(id, true);
  }

  async function handleGenreUnwatch(id: string) {
    await setGenreWatched(id, false);
  }

  async function handleGenreRemove(id: string) {
    if (genrePreferenceSaving || syncing || pipelineBusy || importInfo?.running) {
      updateError = "当前有任务进行中，请完成后再移除分类人气榜";
      return;
    }
    genrePreferenceSaving = true;
    let removed = false;
    try {
      await removeGenre(id);
      removed = true;
      await runExport();
      if (filter.genreFocus === id) filter.genreFocus = "";
      await reload({ keepScroll: true });
    } catch (error) {
      updateError = removed
        ? `分类已从本地库移除，但界面同步失败：${String(error)}。请点击「更新」重试。`
        : String(error);
    } finally {
      genrePreferenceSaving = false;
    }
  }

  function clearAllFilters() {
    filter = emptyFilter();
  }

  function openFollowUpdates() {
    followUpdatesVisited = true;
    returnToFollowUpdates = false;
    mode = "followUpdates";
    library.markFollowUpdatesRead(recentFollowedWorks.map((work) => work.id));
  }

  function toggleDiscover() {
    if (mode === "discover") {
      if (discoverReturnMode === "followUpdates") openFollowUpdates();
      else mode = "browse";
    } else {
      discoverReturnMode = mode;
      mode = "discover";
    }
  }

  function openMakerFromFollowUpdates(work: WorkView) {
    showMaker(work);
    returnToFollowUpdates = true;
    mode = "browse";
  }

  async function refreshFollowUpdates() {
    library.checkFollowUpdates(recentFollowedWorks.map((work) => work.id), true);
    await runUpdate("quick");
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
      active={mode !== "discover"}
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
      followUpdatesSelected={mode === "followUpdates"}
      followUpdatesUnread={unreadFollowUpdates.length}
      onOpenFollowUpdates={openFollowUpdates}
      onOpenBrowse={() => {
        returnToFollowUpdates = false;
        mode = "browse";
      }}
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
          class="btn"
          class:active={prefs.data.hideImages}
          aria-pressed={prefs.data.hideImages}
          title="隐藏所有作品图片；下次打开应用仍保持当前选择"
          onclick={() => prefs.set("hideImages", !prefs.data.hideImages)}
        >{prefs.data.hideImages ? "显示图片" : "隐藏图片"}</button>
        <button
          class="btn with-icon"
          class:active={mode === "discover"}
          disabled={status !== "ready"}
          title="发现：黑马新锐 / 合口味新作 / 遗珠（本地计算，点口味即时生效）"
          onclick={toggleDiscover}
        >
          {@html ICONS.flame}{mode === "discover" ? "返回浏览" : "发现"}
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
        <button class="btn with-icon" onclick={openUpdateMenu} disabled={status !== "ready" || pipelineBusy || syncing}>
          {@html ICONS.tray}开始更新数据 ▾
        </button>
        <button
          class="btn primary with-icon"
          onclick={() => void refreshData()}
          disabled={status !== "ready" || syncing || pipelineBusy}
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
    {:else if unreadFollowUpdates.length > 0 && mode !== "followUpdates"}
      <button class="follow-banner" onclick={openFollowUpdates}>
        <span class="follow-banner-icon">{@html ICONS.flame}</span>
        <span>{unreadFollowMakerCount} 位关注作者发布了 {unreadFollowUpdates.length} 部近两周新作</span>
        <span class="spacer"></span>
        <span class="follow-banner-link">查看更新</span>
      </button>
    {/if}

    {#if categoryImportReady && mode === "browse"}
      <div class="category-ready" role="status">
        <span>「{categoryImportReady.name}」人气榜已导入</span>
        <span class="spacer"></span>
        <button class="link" onclick={() => {
          filter.genreFocus = categoryImportReady?.id ?? "";
          categoryImportReady = null;
        }}>查看榜单</button>
        <button class="link" aria-label="关闭导入完成提示" onclick={() => (categoryImportReady = null)}>×</button>
      </div>
    {/if}

    {#if mode === "discover" && status === "ready" && data}
      <Discover
        resetScrollToken={manualRefreshCount}
        works={data.works}
        tasteProfile={prefs.data.tasteProfile}
        {followedMakers}
        {seenIds}
        {dismissedIds}
        onEditTaste={() => (tasteEditorOpen = true)}
        onopen={(game) => openWork(game.url)}
        onhover={enterHover}
        onleave={leaveHover}
        onseen={(game) => library.markSeen(game.id)}
        oncontext={openDiscoveryMenu}
      />
    {/if}
    {#if followUpdatesVisited && status === "ready" && data}
      <FollowUpdates
        active={mode === "followUpdates"}
        resetScrollToken={manualRefreshCount}
        works={recentFollowedWorks}
        unreadIds={unreadFollowUpdateIds}
        lastCheckedAt={library.data.follow_updates.last_checked_at}
        refreshing={syncing || isRunning(progress)}
        onrefresh={() => void refreshFollowUpdates()}
        onopen={(work) => openWork(work.url)}
        onmaker={openMakerFromFollowUpdates}
      />
    {/if}
    {#if mode === "browse" || status !== "ready" || !data}
      {#if viewFilter.kind !== "all"}
      <div class="strip">
        <span class="strip-icon">{@html ICONS.filterCircle}</span>
        <span class="strip-title">{viewFilterTitle(viewFilter, collectionNameOf)}</span>
        <span class="strip-count">· 命中 {filtered.length} 部</span>
        <span class="spacer"></span>
        {#if returnToFollowUpdates}
          <button class="link" onclick={openFollowUpdates}>返回关注更新</button>
        {/if}
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
        <span class="strip-title">分类人气榜：「{activeGenre.name}」按官方人气名次</span>
        <span class="spacer"></span>
        <button class="link" onclick={() => (filter.genreFocus = "")}>返回全部作品</button>
      </div>
    {/if}

    {#if status === "ready" && data}
      {#if filter.genres.length > 0 || filter.excludeGenres.length > 0 || filter.forms.length > 0 || activeContentFlags.length > 0}
        <div class="active-filter-groups" aria-label="当前筛选条件">
          {#if filter.genres.length > 0}
            <div class="active-filter-group" aria-label="包含分类，全部满足">
              <span class="active-filter-label" title="所选分类取交集">分类</span>
              {#each filter.genres as name (name)}
                <TagChip
                  kind="category"
                  text={name}
                  context="filter"
                  removable
                  title={`移除包含分类「${name}」`}
                  ariaLabel={`移除包含分类「${name}」`}
                  onclick={() => (filter.genres = filter.genres.filter((item) => item !== name))}
                />
              {/each}
            </div>
          {/if}
          {#if filter.excludeGenres.length > 0}
            <div class="active-filter-group" aria-label="排除分类">
              <span class="active-filter-label">排除分类</span>
              {#each filter.excludeGenres as name (name)}
                <TagChip
                  kind="excluded"
                  text={name}
                  context="filter"
                  removable
                  title={`移除排除分类「${name}」`}
                  ariaLabel={`移除排除分类「${name}」`}
                  onclick={() => (filter.excludeGenres = filter.excludeGenres.filter((item) => item !== name))}
                />
              {/each}
            </div>
          {/if}
          {#if filter.forms.length > 0}
            <div class="active-filter-group" aria-label="作品形式，符合任一即可">
              <span class="active-filter-label" title="所选形式取并集">作品形式</span>
              {#each filter.forms as name (name)}
                <TagChip
                  kind="form"
                  text={name}
                  context="filter"
                  removable
                  title={`移除作品形式「${name}」`}
                  ariaLabel={`移除作品形式「${name}」`}
                  onclick={() => (filter.forms = filter.forms.filter((item) => item !== name))}
                />
              {/each}
            </div>
          {/if}
          {#if activeContentFlags.length > 0}
            <div class="active-filter-group" aria-label="内容标志，全部满足">
              <span class="active-filter-label" title="所选标志取交集">内容标志</span>
              {#each activeContentFlags as flag (flag.key)}
                <TagChip
                  kind={flag.key}
                  text={flag.label}
                  context="filter"
                  removable
                  title={`移除内容标志「${flag.label}」`}
                  ariaLabel={`移除内容标志「${flag.label}」`}
                  onclick={() => (filter.flags = { ...filter.flags, [flag.key]: false })}
                />
              {/each}
            </div>
          {/if}
        </div>
      {/if}
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
                      oncatmenu={openCategoryMenu}
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
                      oncatmenu={openCategoryMenu}
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
        {#if initializing}
          <p>正在初始化数据…</p>
          <p class="hint">
            {progress?.detail || "首次抓取热榜约 5–10 分钟（视网络）；全部在本机进行，不会上传"}
          </p>
        {:else}
          <p>
            还没有数据。首次使用可一键初始化：应用会在本机抓取 DLsite 热榜（约 5–10 分钟，视网络），无需安装 Python。
          </p>
          <p class="hint">
            已有数据文件？选择数据管道导出的 <code>works.json</code> 即可（封面在旁边的 <code>covers/</code>）；本地仓库的 <code>out/works.json</code> 启动时会自动查找
          </p>
          <button class="btn primary with-icon" onclick={() => void initPipeline()}>
            {@html ICONS.tray}初始化数据（抓取热榜）
          </button>
          <button class="btn" onclick={pick}>选择数据文件</button>
        {/if}
      </div>
    {/if}
    {/if}
  </div>
</div>

{#if hoverWork}
  <HoverPanel game={hoverWork} x={hoverX} y={hoverY} {genres} />
{/if}

{#if tasteEditorOpen}
  <TasteEditor
    works={data?.works ?? []}
    collections={library.data.collections}
    profile={prefs.data.tasteProfile}
    collectionIds={prefs.data.tasteCollectionIds}
    exemplarIds={prefs.data.tasteExemplarIds}
    onboarded={prefs.data.tasteOnboarded}
    onsave={(value) => {
      prefs.replaceTasteProfile(value.profile);
      prefs.set("tasteCollectionIds", value.collectionIds);
      prefs.set("tasteExemplarIds", value.exemplarIds);
      prefs.set("tasteOnboarded", true);
      tasteEditorOpen = false;
    }}
    oncancel={() => (tasteEditorOpen = false)}
  />
{/if}

{#if cardMenu}
  <ContextMenu x={cardMenu.x} y={cardMenu.y} items={menuItems} onclose={() => (cardMenu = null)} />
{/if}

{#if categoryMenu}
  <ContextMenu x={categoryMenu.x} y={categoryMenu.y} items={categoryMenuItems} onclose={() => (categoryMenu = null)} />
{/if}

{#if dislikeRequest}
  <DiscoveryFeedbackDialog
    title={dislikeRequest.title}
    tasteNames={matchedTaste(dislikeRequest)}
    onhide={() => dismissDiscovery(false)}
    onlearn={() => dismissDiscovery(true)}
    oncancel={() => (dislikeRequest = null)}
  />
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
    title="导入分类人气榜"
    message={`「${genreImportRequest.name}」尚未导入人气数据。现在抓取并入库？（含榜上新作品，约 1–3 分钟；进度见顶部横幅）`}
    confirmLabel="开始导入（前 200 名）"
    danger={false}
    onconfirm={() => void confirmGenreImport()}
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

  .category-ready {
    display: flex;
    align-items: center;
    gap: 12px;
    flex: none;
    padding: 8px 22px;
    border-bottom: 1px solid var(--border);
    background: color-mix(in srgb, var(--accent) 8%, var(--panel));
    color: var(--text);
    font-size: 12px;
  }

  .follow-banner {
    width: 100%;
    flex: none;
    display: flex;
    align-items: center;
    gap: 8px;
    border: 0;
    border-bottom: 1px solid var(--border);
    background: color-mix(in srgb, var(--accent) 10%, transparent);
    color: var(--text);
    padding: 9px 22px;
    font: inherit;
    font-size: 12px;
    text-align: left;
    cursor: pointer;
  }

  .follow-banner-icon,
  .follow-banner-link {
    color: var(--accent);
  }

  .follow-banner-icon {
    display: inline-flex;
  }

  .follow-banner-link {
    font-weight: 650;
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

  .active-filter-groups {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px 18px;
    padding: 10px 22px 0;
  }

  .active-filter-group {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 6px;
    max-width: 100%;
  }

  .active-filter-label {
    color: var(--muted);
    font-size: 12px;
    white-space: nowrap;
    margin-right: 1px;
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
