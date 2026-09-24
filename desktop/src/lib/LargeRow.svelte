<script lang="ts">
  import type { WorkView } from "$lib/api";
  import { ICONS, categoriesOf, formsOf } from "$lib/ui";
  import CategoryChips from "./CategoryChips.svelte";
  import Cover from "./Cover.svelte";
  import FormChips from "./FormChips.svelte";
  import GameBadges from "./GameBadges.svelte";
  import GameMetaFlow from "./GameMetaFlow.svelte";
  import GamePrice from "./GamePrice.svelte";
  import HeartButton from "./HeartButton.svelte";

  let {
    game,
    showBadges = true,
    showDiscount = true,
    showRatingCount = true,
    rankText = null,
    oncats,
    oncatmenu,
    onform,
    onbadge,
    onmaker,
    onopen,
  }: {
    game: WorkView;
    showBadges?: boolean;
    showDiscount?: boolean;
    showRatingCount?: boolean;
    rankText?: string | null;
    oncats?: (name: string) => void;
    oncatmenu?: (name: string, event: MouseEvent) => void;
    onform?: (name: string) => void;
    onbadge?: (key: "voice" | "music" | "video") => void;
    onmaker?: () => void;
    onopen: () => void;
  } = $props();

  const categories = $derived(categoriesOf(game));
  const forms = $derived(formsOf(game));
</script>

<article class="large">
  <Cover src={game._cover} width={110} height={146} rounded />
  <div class="main">
    <div class="headline">
      <div class="title">{game.title}</div>
      <GamePrice {game} {showDiscount} />
    </div>
    <div class="maker-row">
      <span class="picon">{@html ICONS.person}</span>
      <button
        class="maker"
        title="查看该作者的全部库内作品"
        onclick={(event) => {
          event.stopPropagation();
          onmaker?.();
        }}
        ondblclick={(event) => event.stopPropagation()}
      >{game.maker || "制作者未知"}</button>
      <span class="spacer"></span>
      <span class="id">{game.id}</span>
    </div>
    {#if categories.length > 0}
      <div class="labeled">
        <span class="label">分类</span>
        <CategoryChips {categories} limit={8} ontap={oncats} onmenu={oncatmenu} />
      </div>
    {/if}
    {#if forms.length > 0}
      <div class="labeled">
        <span class="label">形式</span>
        <FormChips {forms} limit={2} ontap={onform} />
      </div>
    {/if}
    {#if showBadges}
      <div class="labeled">
        <span class="label">标志</span>
        <GameBadges {game} ontap={onbadge} />
      </div>
    {/if}
    <div class="bottom">
      <GameMetaFlow {game} {showRatingCount} {rankText} />
      <span class="spacer"></span>
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
    </div>
  </div>
</article>

<style>
  .large {
    display: flex;
    gap: 16px;
    align-items: flex-start;
    padding: 13px;
    border-radius: 14px;
    background: var(--panel);
    border: 1px solid var(--border);
    height: 100%;
    box-sizing: border-box;
    overflow: hidden;
  }

  .main {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 5px;
    min-height: 146px;
  }

  .headline {
    display: flex;
    align-items: baseline;
    gap: 12px;
  }

  .title {
    font-size: 14px;
    font-weight: 600;
    line-height: 18px;
    flex: 1;
    min-width: 0;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .maker-row {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: var(--muted);
    min-width: 0;
  }

  .picon {
    display: inline-flex;
    flex: none;
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
  }

  .maker:hover {
    color: var(--accent);
  }

  .spacer {
    flex: 1;
  }

  .id {
    opacity: 0.7;
    font-size: 11px;
    flex: none;
  }

  .labeled {
    display: flex;
    gap: 7px;
    align-items: flex-start;
    min-width: 0;
  }

  .label {
    flex: none;
    width: 26px;
    font-size: 10px;
    color: var(--muted);
    padding-top: 4px;
  }

  .bottom {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: auto;
    min-width: 0;
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
