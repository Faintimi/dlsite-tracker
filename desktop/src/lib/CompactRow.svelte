<script lang="ts">
  import type { WorkView } from "$lib/api";
  import { ICONS, cardRatingColor, compactDateText, fmtNum, ratingText } from "$lib/ui";
  import Cover from "./Cover.svelte";
  import GameBadges from "./GameBadges.svelte";
  import GamePrice from "./GamePrice.svelte";
  import HeartButton from "./HeartButton.svelte";

  let {
    game,
    showBadges = true,
    showDiscount = true,
    showRatingCount = true,
    rankText = null,
    onbadge,
    onmaker,
    onopen,
  }: {
    game: WorkView;
    showBadges?: boolean;
    showDiscount?: boolean;
    showRatingCount?: boolean;
    rankText?: string | null;
    onbadge?: (key: "voice" | "music" | "video") => void;
    onmaker?: () => void;
    onopen: () => void;
  } = $props();
</script>

<article class="compact">
  <Cover src={game._cover} width={50} height={64} rounded />
  <div class="main">
    <div class="title">{game.title}</div>
    <div class="sub">
      <button
        class="maker"
        title="查看该作者的全部库内作品"
        onclick={(event) => {
          event.stopPropagation();
          onmaker?.();
        }}
        ondblclick={(event) => event.stopPropagation()}
      >{game.maker || "制作者未知"}</button>
      {#if showBadges}
        <GameBadges {game} showText={false} ontap={onbadge} />
      {/if}
    </div>
  </div>
  <span class="spacer"></span>
  {#if rankText}
    <span class="meta rank">{@html ICONS.rank}<span>{rankText}</span></span>
  {/if}
  {#if game.regist_date}
    <span class="meta date">{compactDateText(game.regist_date)}</span>
  {/if}
  <span class="meta sales">{fmtNum(game.sales)}</span>
  <span class="meta rating" style:color={cardRatingColor(game)}>{ratingText(game, showRatingCount)}</span>
  <span class="price-box"><GamePrice {game} {showDiscount} /></span>
  <HeartButton id={game.id} />
  <button
    class="open"
    title="打开作品页"
    onclick={(event) => {
      event.stopPropagation();
      onopen();
    }}
    ondblclick={(event) => event.stopPropagation()}
  >
    {@html ICONS.open}
  </button>
</article>

<style>
  .compact {
    display: flex;
    align-items: center;
    gap: 11px;
    padding: 7px 11px;
    border-radius: 10px;
    background: var(--panel);
    border: 1px solid var(--border);
    height: 100%;
    box-sizing: border-box;
    overflow: hidden;
  }

  .maker {
    appearance: none;
    border: 0;
    background: transparent;
    font: inherit;
    color: inherit;
    padding: 0;
    cursor: default;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 40%;
  }

  .maker:hover {
    color: var(--accent);
  }

  .main {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .title {
    font-size: 13px;
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .sub {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
  }

  .maker {
    font-size: 11px;
    color: var(--muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .spacer {
    flex: none;
    width: 8px;
  }

  .meta {
    font-size: 12px;
    color: var(--muted);
    white-space: nowrap;
    flex: none;
  }

  .rank {
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }

  .sales {
    width: 76px;
    text-align: right;
  }

  .rating {
    width: 118px;
    text-align: right;
  }

  .price-box {
    width: 190px;
    text-align: right;
    display: inline-flex;
    justify-content: flex-end;
    flex: none;
    overflow: hidden;
  }

  .open {
    appearance: none;
    border: 0;
    background: transparent;
    color: var(--muted);
    padding: 3px;
    border-radius: 5px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    flex: none;
  }

  .open:hover {
    color: var(--text);
    background: color-mix(in srgb, var(--text) 10%, transparent);
  }
</style>
