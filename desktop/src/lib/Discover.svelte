<script lang="ts">
  import type { WorkView } from "$lib/api";
  import type { TasteLevel } from "$lib/prefs.svelte";
  import { ICONS } from "$lib/ui";
  import {
    DISCOVERY,
    buildDiscovery,
    buildTasteContext,
    weightedShuffle,
    type DiscoveryItem,
    type TasteContext,
  } from "$lib/discovery";
  import DiscoverCard from "./DiscoverCard.svelte";

  let {
    active = true,
    resetScrollToken = 0,
    works,
    tasteProfile,
    followedMakers,
    seenIds,
    dismissedIds,
    onEditTaste,
    onopen,
    onhover,
    onleave,
    onseen,
    oncontext,
  }: {
    active?: boolean;
    resetScrollToken?: number;
    works: WorkView[];
    tasteProfile: Record<string, TasteLevel>;
    followedMakers: Set<string>;
    seenIds: Set<string>;
    dismissedIds: Set<string>;
    onEditTaste: () => void;
    onopen?: (game: WorkView) => void;
    onhover?: (game: WorkView, event: MouseEvent) => void;
    onleave?: () => void;
    onseen?: (game: WorkView) => void;
    oncontext?: (game: WorkView, event: MouseEvent) => void;
  } = $props();

  const expanded = $state<Record<string, boolean>>({});
  let discoverEl: HTMLDivElement | null = $state(null);
  let savedScrollTop = 0;
  $effect(() => {
    if (active && discoverEl) discoverEl.scrollTop = savedScrollTop;
  });
  // 首屏铺满：每区显示数＝网格列数 ×2 行，避免末行留下空位（随窗口宽度自适应）。
  // 网格宽 = 发现页宽 − 页面内边距 36（18×2）− 分区内边距 28（14×2）。
  let discoverW = $state(0);
  const GRID_MIN = 158; // 与 .d-grid 的 minmax 保持一致
  const GRID_GAP = 12;
  const previewCount = $derived(
    discoverW === 0
      ? DISCOVERY.sectionPreview
      : Math.max(1, Math.floor((Math.max(0, discoverW - 64) + GRID_GAP) / (GRID_MIN + GRID_GAP))) * 2,
  );

  const ctx: TasteContext = $derived(buildTasteContext(works, tasteProfile, followedMakers));
  const result = $derived(buildDiscovery(works, ctx, seenIds, dismissedIds));
  const tasteCounts = $derived({
    love: Object.values(tasteProfile).filter((level) => level === "love").length,
    like: Object.values(tasteProfile).filter((level) => level === "like").length,
    less: Object.values(tasteProfile).filter((level) => level === "less").length,
  });
  const positiveTasteCount = $derived(tasteCounts.love + tasteCounts.like);

  // 遗珠区（与其它分区不同）：随机分批探索——每批 DISCOVERY.sectionPreview 部，
  // 「换一批」出下一批，轮完后重新洗牌。加权随机：口味分越高越容易靠前，但全池都会轮到。
  let oldOrder = $state<DiscoveryItem[]>([]);
  let oldBatch = $state(0);
  let oldSig = ""; // 新作品集合/口味变化才重洗，单个「看过」不打断探索
  $effect(() => {
    const sig = `${works.map((work) => work.id).join(",")}|${JSON.stringify(tasteProfile)}|${[...followedMakers].sort().join(",")}`;
    if (sig !== oldSig) {
      if (oldSig) {
        for (const key of Object.keys(expanded)) delete expanded[key];
        savedScrollTop = 0;
        discoverEl?.scrollTo({ top: 0 });
      }
      oldSig = sig;
      oldOrder = weightedShuffle(result.old);
      oldBatch = 0;
    } else {
      const available = new Set(result.old.map((item) => item.game.id));
      if (oldOrder.some((item) => !available.has(item.game.id))) {
        oldOrder = oldOrder.filter((item) => available.has(item.game.id));
      }
    }
  });
  $effect(() => {
    void resetScrollToken;
    savedScrollTop = 0;
    discoverEl?.scrollTo({ top: 0 });
  });
  const oldTotal = $derived(Math.max(1, Math.ceil(oldOrder.length / previewCount)));
  const oldBatchSafe = $derived(Math.min(oldBatch, oldTotal - 1));
  const oldVisible = $derived(
    oldOrder.slice(oldBatchSafe * previewCount, (oldBatchSafe + 1) * previewCount),
  );

  function nextOldBatch() {
    if (oldBatchSafe + 1 >= oldTotal) {
      oldOrder = weightedShuffle(result.old);
      oldBatch = 0;
    } else {
      oldBatch = oldBatchSafe + 1;
    }
  }

  interface Section {
    key: "sprint" | "hype" | "fresh" | "old";
    title: string;
    note: string;
    empty: string;
    items: DiscoveryItem[];
  }

  const sections = $derived<Section[]>([
    {
      key: "sprint",
      title: "黑马新锐 · 冲刺中",
      note: `${DISCOVERY.newWindowDays} 天内发售 · 按销量增量排序（窗口见卡片）`,
      empty: "暂无——多在应用里跑几次「更新」积累销量快照后自然出现",
      items: result.sprint,
    },
    {
      key: "hype",
      title: "黑马新锐 · 高期待",
      note: `心愿单 ≥ ${DISCOVERY.hypeWishMin} 且销量未爆的新作`,
      empty: "暂无符合「高期待未爆」的作品",
      items: result.hype,
    },
    {
      key: "fresh",
      title: "合你口味的新作",
      note: `近 ${DISCOVERY.freshWindowDays} 天发售 ∩ 口味匹配`,
      empty: positiveTasteCount === 0 ? "先建立你的口味画像" : "近期没有匹配口味的新作",
      items: result.fresh,
    },
    {
      key: "old",
      title: "遗珠 · 老作挖掘",
      note: `${DISCOVERY.oldMinDays} 天前发售 · 口味匹配 · 每批随机 ${previewCount} 部（可「换一批」）`,
      empty: positiveTasteCount === 0 ? "先建立你的口味画像" : "没有匹配口味的遗珠候选",
      items: result.old,
    },
  ]);

  function toggleExpand(key: string) {
    expanded[key] = !expanded[key];
  }

  function shown(section: Section): DiscoveryItem[] {
    return expanded[section.key]
      ? section.items
      : section.items.slice(0, previewCount);
  }
</script>

<div
  class="discover"
  class:inactive={!active}
  bind:this={discoverEl}
  bind:clientWidth={discoverW}
  onscroll={(event) => { if (active) savedScrollTop = event.currentTarget.scrollTop; }}
>
  <div class="d-head">
    <span class="d-head-icon">{@html ICONS.flame}</span>
    <div class="d-head-text">
      <div class="d-head-title">发现</div>
      <div class="d-head-sub">口味匹配与黑马信号全部在本机实时计算；改口味立即生效</div>
    </div>
  </div>

  <div class="taste-bar">
    <span class="taste-label">我的口味</span>
    {#if Object.keys(tasteProfile).length === 0}
      <span class="taste-hint">从喜欢的作品与收藏开始，建立更懂你的口味画像</span>
    {:else}
      {#if tasteCounts.love > 0}<span class="taste-stat love">很喜欢 {tasteCounts.love}</span>{/if}
      {#if tasteCounts.like > 0}<span class="taste-stat like">喜欢 {tasteCounts.like}</span>{/if}
      {#if tasteCounts.less > 0}<span class="taste-stat less">少推荐 {tasteCounts.less}</span>{/if}
    {/if}
    <span class="spacer"></span>
    <button class="link" onclick={onEditTaste}>{Object.keys(tasteProfile).length === 0 ? "开始设置" : "编辑口味"}</button>
  </div>

  {#each sections as section (section.key)}
    <section class="d-sec">
      <div class="d-sec-head">
        <span class="d-sec-title">{section.title}</span>
        <span class="d-sec-count">{section.items.length} 部</span>
        <span class="spacer"></span>
        {#if section.key !== "old" && section.items.length > previewCount}
          <button class="link" onclick={() => toggleExpand(section.key)}>
            {expanded[section.key] ? "收起" : `查看全部（${section.items.length}）`}
          </button>
        {/if}
      </div>
      <div class="d-sec-note">{section.note}</div>
      {#if section.items.length === 0}
        <div class="d-sec-empty">{section.empty}</div>
      {:else if section.key === "old"}
        <div class="d-grid" role="list">
          {#each oldVisible as item (item.game.id)}
            <DiscoverCard
              {item}
              {onopen}
              {onhover}
              {onleave}
              {onseen}
              {oncontext}
              seen={seenIds.has(item.game.id)}
            />
          {/each}
        </div>
        {#if oldOrder.length > previewCount}
          <div class="d-batch">
            <span class="d-batch-info">
              第 {oldBatchSafe + 1} / {oldTotal} 批 · 共 {oldOrder.length} 部候选
            </span>
            <span class="spacer"></span>
            <button class="d-batch-btn" onclick={nextOldBatch}>
              {oldBatchSafe + 1 >= oldTotal ? "重新洗牌 ↻" : "换一批 ↻"}
            </button>
          </div>
        {/if}
      {:else}
        <div class="d-grid" role="list">
          {#each shown(section) as item (item.game.id)}
            <DiscoverCard
              {item}
              {onopen}
              {onhover}
              {onleave}
              {onseen}
              {oncontext}
              seen={seenIds.has(item.game.id)}
            />
          {/each}
        </div>
      {/if}
    </section>
  {/each}
</div>

<style>
  .discover {
    flex: 1;
    overflow-y: auto;
    padding: 14px 18px 28px;
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
  .discover.inactive { display: none; }

  .d-head {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .d-head-icon {
    display: flex;
    color: var(--accent);
  }

  .d-head-title {
    font-size: 17px;
    font-weight: 650;
  }

  .d-head-sub {
    font-size: 12px;
    color: var(--muted);
    margin-top: 1px;
  }

  .taste-bar {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
    background: var(--panel);
    border-radius: 11px;
    padding: 9px 12px;
  }

  .taste-label {
    font-size: 12.5px;
    font-weight: 650;
    margin-right: 2px;
  }

  .taste-hint {
    font-size: 12px;
    color: var(--muted);
  }

  .spacer {
    flex: 1;
  }

  .taste-stat {
    border-radius: 999px;
    padding: 3px 9px;
    color: #fff;
    font-size: 11.5px;
  }

  .taste-stat.love {
    background: #d94a65;
  }

  .taste-stat.like {
    background: var(--accent);
  }

  .taste-stat.less {
    background: #737782;
  }

  .d-sec {
    background: var(--panel);
    border-radius: 12px;
    padding: 12px 14px 14px;
  }

  .d-sec-head {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .d-sec-title {
    font-size: 13.5px;
    font-weight: 650;
  }

  .d-sec-count {
    font-size: 11.5px;
    color: var(--muted);
  }

  .d-sec-note {
    font-size: 11.5px;
    color: var(--muted);
    margin: 2px 0 10px;
  }

  .d-sec-empty {
    font-size: 12px;
    color: var(--muted);
    padding: 8px 0 4px;
  }

  .d-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(158px, 1fr));
    gap: 14px 12px;
  }

  .link {
    background: none;
    border: none;
    color: var(--accent);
    font-size: 12px;
    cursor: pointer;
    padding: 0;
  }

  .link:hover {
    text-decoration: underline;
  }

  .d-batch {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 12px;
  }

  .d-batch-info {
    font-size: 11.5px;
    color: var(--muted);
  }

  .d-batch-btn {
    border: 1px solid var(--border);
    background: transparent;
    color: var(--accent);
    border-radius: 8px;
    padding: 4px 14px;
    font-size: 12px;
    cursor: pointer;
  }

  .d-batch-btn:hover {
    border-color: var(--accent);
  }
</style>
