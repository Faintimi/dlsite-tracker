<script lang="ts">
  import type { GenreEntry, WorkView } from "$lib/api";
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
    works,
    genres,
    taste,
    followedMakers,
    onTasteChange,
    onopen,
    onhover,
    onleave,
  }: {
    works: WorkView[];
    genres: GenreEntry[];
    taste: string[];
    followedMakers: Set<string>;
    onTasteChange: (next: string[]) => void;
    onopen?: (game: WorkView) => void;
    onhover?: (game: WorkView, event: MouseEvent) => void;
    onleave?: () => void;
  } = $props();

  let editing = $state(false);
  let query = $state("");
  const expanded = $state<Record<string, boolean>>({});
  // 「未看过」记录在下一步（M3）接入本地文件；先以空集合运行
  const seen = new Set<string>();

  const ctx: TasteContext = $derived(buildTasteContext(works, taste, followedMakers));
  const result = $derived(buildDiscovery(works, ctx, seen));

  // 遗珠区（与其它分区不同）：随机分批探索——每批 DISCOVERY.sectionPreview 部，
  // 「换一批」出下一批，轮完后重新洗牌。加权随机：口味分越高越容易靠前，但全池都会轮到。
  let oldOrder = $state<DiscoveryItem[]>([]);
  let oldBatch = $state(0);
  let oldSig = ""; // 非响应式签名：仅当数据/口味变动时重洗，避免轮询重算时跳批
  $effect(() => {
    const sig = `${works.length}|${result.old.length}|${result.old[0]?.game.id ?? ""}|${taste.join(",")}`;
    if (sig !== oldSig) {
      oldSig = sig;
      oldOrder = weightedShuffle(result.old);
      oldBatch = 0;
    }
  });
  const oldTotal = $derived(Math.max(1, Math.ceil(oldOrder.length / DISCOVERY.sectionPreview)));
  const oldVisible = $derived(
    oldOrder.slice(oldBatch * DISCOVERY.sectionPreview, (oldBatch + 1) * DISCOVERY.sectionPreview),
  );

  function nextOldBatch() {
    if (oldBatch + 1 >= oldTotal) {
      oldOrder = weightedShuffle(result.old);
      oldBatch = 0;
    } else {
      oldBatch += 1;
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
      empty: taste.length === 0 ? "先在下方勾选口味分类" : "近期没有匹配口味的新作",
      items: result.fresh,
    },
    {
      key: "old",
      title: "遗珠 · 老作挖掘",
      note: `${DISCOVERY.oldMinDays} 天前发售 · 口味匹配 · 每批随机 ${DISCOVERY.sectionPreview} 部（可「换一批」）`,
      empty: taste.length === 0 ? "先在下方勾选口味分类" : "没有匹配口味的遗珠候选",
      items: result.old,
    },
  ]);

  const candidateGenres = $derived(
    genres
      .filter((entry) => (entry.count ?? 0) > 0)
      .sort((a, b) => (b.count ?? 0) - (a.count ?? 0))
      .filter((entry) => !query.trim() || entry.name.includes(query.trim()))
      .slice(0, 120),
  );

  function toggleTaste(name: string) {
    onTasteChange(
      taste.includes(name) ? taste.filter((item) => item !== name) : [...taste, name],
    );
  }

  function toggleExpand(key: string) {
    expanded[key] = !expanded[key];
  }

  function shown(section: Section): DiscoveryItem[] {
    return expanded[section.key]
      ? section.items
      : section.items.slice(0, DISCOVERY.sectionPreview);
  }
</script>

<div class="discover">
  <div class="d-head">
    <span class="d-head-icon">{@html ICONS.flame}</span>
    <div class="d-head-text">
      <div class="d-head-title">发现</div>
      <div class="d-head-sub">口味匹配与黑马信号全部在本机实时计算；改口味立即生效</div>
    </div>
  </div>

  <div class="taste-bar">
    <span class="taste-label">我的口味</span>
    {#if taste.length === 0}
      <span class="taste-hint">选几个你喜欢的分类，下面的分区就会开始工作</span>
    {:else}
      {#each taste as name (name)}
        <button class="chip on" title="点击移除" onclick={() => toggleTaste(name)}>{name} ×</button>
      {/each}
    {/if}
    <span class="spacer"></span>
    <button class="link" onclick={() => (editing = !editing)}>
      {editing ? "收起分类" : "＋ 编辑口味"}
    </button>
  </div>

  {#if editing || taste.length === 0}
    <div class="picker">
      <input class="picker-search" type="text" placeholder="搜索分类…" bind:value={query} />
      <div class="picker-grid">
        {#each candidateGenres as entry (entry.id)}
          <button
            class="chip"
            class:on={taste.includes(entry.name)}
            onclick={() => toggleTaste(entry.name)}
          >
            {entry.name}<span class="chip-count">{entry.count ?? 0}</span>
          </button>
        {/each}
      </div>
    </div>
  {/if}

  {#each sections as section (section.key)}
    <section class="d-sec">
      <div class="d-sec-head">
        <span class="d-sec-title">{section.title}</span>
        <span class="d-sec-count">{section.items.length} 部</span>
        <span class="spacer"></span>
        {#if section.key !== "old" && section.items.length > DISCOVERY.sectionPreview}
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
            <DiscoverCard {item} {onopen} {onhover} {onleave} />
          {/each}
        </div>
        {#if oldOrder.length > DISCOVERY.sectionPreview}
          <div class="d-batch">
            <span class="d-batch-info">
              第 {oldBatch + 1} / {oldTotal} 批 · 共 {oldOrder.length} 部候选
            </span>
            <span class="spacer"></span>
            <button class="d-batch-btn" onclick={nextOldBatch}>
              {oldBatch + 1 >= oldTotal ? "重新洗牌 ↻" : "换一批 ↻"}
            </button>
          </div>
        {/if}
      {:else}
        <div class="d-grid" role="list">
          {#each shown(section) as item (item.game.id)}
            <DiscoverCard {item} {onopen} {onhover} {onleave} />
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

  .chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    border: 1px solid var(--border);
    background: transparent;
    border-radius: 999px;
    padding: 3px 10px;
    font-size: 12px;
    color: var(--muted);
    cursor: pointer;
  }

  .chip:hover {
    border-color: var(--accent);
    color: var(--accent);
  }

  .chip.on {
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
  }

  .chip-count {
    font-size: 10.5px;
    opacity: 0.65;
  }

  .picker {
    display: flex;
    flex-direction: column;
    gap: 8px;
    background: var(--panel);
    border-radius: 11px;
    padding: 10px 12px;
  }

  .picker-search {
    width: 220px;
    border: 1px solid var(--border);
    border-radius: 7px;
    background: transparent;
    color: inherit;
    padding: 5px 9px;
    font-size: 12.5px;
  }

  .picker-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    max-height: 180px;
    overflow-y: auto;
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
