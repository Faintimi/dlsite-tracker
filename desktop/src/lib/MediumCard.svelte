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

<article class="medium">
  <div class="top">
    <Cover src={game._cover} width={92} height={122} rounded />
    <div class="info">
      <div class="title" title={game.title}>{game.title}</div>
      <button
        class="maker"
        title="查看该作者的全部库内作品"
        onclick={(event) => {
          event.stopPropagation();
          onmaker?.();
        }}
        ondblclick={(event) => event.stopPropagation()}
      >{game.maker || "制作者未知"}</button>
      <div class="category-slot">
        {#if categories.length > 0}
          <CategoryChips {categories} limit={5} maxRows={2} ontap={oncats} onmenu={oncatmenu} />
        {/if}
      </div>
      <div class="form-slot">
        {#if forms.length > 0}
          <FormChips {forms} limit={1} ontap={onform} />
        {/if}
      </div>
      <div class="badge-slot">
        {#if showBadges}
          <GameBadges {game} ontap={onbadge} />
        {/if}
      </div>
    </div>
  </div>
  <GameMetaFlow {game} {showRatingCount} {rankText} />
  <div class="bottom">
    <GamePrice {game} {showDiscount} size="sm" />
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
</article>

<style>
  .medium {
    display: flex;
    flex-direction: column;
    gap: 7px;
    padding: 11px;
    border-radius: 12px;
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
    font-size: 12px;
    color: var(--muted);
    padding: 0;
    cursor: default;
    text-align: left;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .maker:hover {
    color: var(--accent);
  }
  .top {
    display: flex;
    gap: 11px;
    align-items: flex-start;
    min-height: 122px;
  }

  .info {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .category-slot { height: 43px; overflow: hidden; }
  .form-slot { height: 19px; overflow: hidden; }
  .badge-slot { height: 36px; overflow: hidden; }

  .title {
    font-size: 13px;
    font-weight: 600;
    line-height: 16px;
    white-space: nowrap;
    text-overflow: ellipsis;
    overflow: hidden;
    height: 16px;
  }

  .maker {
    font-size: 11px;
    color: var(--muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    height: 14px;
  }

  .bottom {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-top: auto;
  }

  .spacer {
    flex: 1;
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
  }

  .open:hover {
    color: var(--text);
    background: color-mix(in srgb, var(--text) 10%, transparent);
  }
</style>
