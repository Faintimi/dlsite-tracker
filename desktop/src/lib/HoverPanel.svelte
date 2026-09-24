<script lang="ts">
  import type { GenreEntry, WorkView } from "$lib/api";
  import { ICONS, categoriesOf, fmtNum, formsOf, preciseRatingColor, preciseRatingText } from "$lib/ui";
  import CategoryChips from "./CategoryChips.svelte";
  import FormChips from "./FormChips.svelte";
  import GameBadges from "./GameBadges.svelte";
  import GamePrice from "./GamePrice.svelte";

  let {
    game,
    x,
    y,
    genres = [],
  }: { game: WorkView; x: number; y: number; genres?: GenreEntry[] } = $props();

  const WIDTH = 320;
  const HEIGHT = 380;
  const MARGIN = 12;

  const left = $derived(Math.min(Math.max(MARGIN, x + 18), window.innerWidth - WIDTH - MARGIN));
  const top = $derived(Math.min(Math.max(MARGIN, y + 18), window.innerHeight - HEIGHT - MARGIN));

  const categories = $derived(categoriesOf(game));
  const forms = $derived(formsOf(game));

  const rankItems = $derived.by(() => {
    const items: string[] = [];
    if (typeof game.rank_day_current === "number") items.push(`日榜 #${game.rank_day_current}`);
    if (typeof game.rank_week_current === "number") items.push(`周榜 #${game.rank_week_current}`);
    if (typeof game.rank_month_current === "number") items.push(`月榜 #${game.rank_month_current}`);
    if (typeof game.rank_trend_current === "number") items.push(`官方人气 #${game.rank_trend_current}`);
    const positions = game.genre_pos ?? {};
    const entries = Object.entries(positions).sort((a, b) => Number(a[1]) - Number(b[1]));
    for (const [id, position] of entries) {
      items.push(`${genreName(String(id))} #${position}`);
    }
    return items;
  });

  function genreName(id: string): string {
    return genres.find((item) => item.id === id)?.name ?? `分类 ${id}`;
  }
</script>

<div class="hover-card" style="left: {left}px; top: {top}px; width: {WIDTH}px">
  <div class="hc-title">{game.title}</div>
  <div class="hc-maker">
    <span class="picon">{@html ICONS.person}</span>
    <span class="maker">{game.maker || "制作者未知"}</span>
    <span class="spacer"></span>
    <span class="id">{game.id}</span>
  </div>
  {#if categories.length > 0}
    <CategoryChips {categories} />
  {/if}
  {#if forms.length > 0}
    <FormChips {forms} />
  {/if}
  <GameBadges {game} />
  <div class="hc-divider"></div>
  <div class="hc-line">
    <span class="li">{@html ICONS.bag}<span>{fmtNum(game.sales)}</span></span>
    <span class="li" style:color={preciseRatingColor(game.rating_precise)}>
      {@html ICONS.star}<span>{preciseRatingText(game)}</span>
    </span>
  </div>
  <div class="hc-line">
    {#if game.regist_date}
      <span class="li">{@html ICONS.calendar}<span>{game.regist_date.slice(0, 10)}</span></span>
    {/if}
    <GamePrice {game} />
  </div>
  <div class="hc-line">
    <span class="li rank-item">
      {@html ICONS.rank}
      <span>{rankItems.length > 0 ? rankItems.join(" · ") : "暂无榜单名次"}</span>
    </span>
  </div>
  <div class="hc-hint">双击打开作品页 · 右键加入收藏夹</div>
</div>

<style>
  .hover-card {
    position: fixed;
    z-index: 100;
    pointer-events: none;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 10px;
    box-shadow: 0 10px 30px rgb(0 0 0 / 28%);
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 7px;
    font-size: 12.5px;
  }

  .hc-title {
    font-size: 14px;
    font-weight: 600;
    line-height: 18px;
    display: -webkit-box;
    -webkit-line-clamp: 6;
    line-clamp: 6;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .hc-maker {
    display: flex;
    align-items: center;
    gap: 6px;
    color: var(--muted);
    font-size: 12px;
  }

  .picon {
    display: inline-flex;
  }

  .maker {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .spacer {
    flex: 1;
  }

  .id {
    opacity: 0.7;
    font-size: 11px;
    flex: none;
  }

  .hc-divider {
    border-top: 1px solid var(--border);
    margin: 2px 0;
  }

  .hc-line {
    display: flex;
    flex-wrap: wrap;
    gap: 4px 14px;
    color: var(--muted);
  }

  .li {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    white-space: nowrap;
  }

  .li :global(svg) {
    opacity: 0.85;
  }

  .rank-item {
    white-space: normal;
    line-height: 17px;
  }

  .hc-hint {
    font-size: 11px;
    color: var(--muted);
    opacity: 0.75;
  }
</style>
