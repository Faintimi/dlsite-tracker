<script lang="ts">
  import type { WorkView } from "$lib/api";
  import Cover from "./Cover.svelte";
  import type { DiscoveryItem } from "$lib/discovery";

  let {
    item,
    onopen,
    onhover,
    onleave,
  }: {
    item: DiscoveryItem;
    onopen?: (game: WorkView) => void;
    onhover?: (game: WorkView, event: MouseEvent) => void;
    onleave?: () => void;
  } = $props();
</script>

<div
  class="dcard"
  role="listitem"
  title={item.game.title}
  ondblclick={() => onopen?.(item.game)}
  onmouseenter={(event) => onhover?.(item.game, event)}
  onmouseleave={() => onleave?.()}
>
  <Cover src={item.game._cover} width="100%" height={196} rounded />
  <div class="d-title">{item.game.title}</div>
  <div class="d-note" title={item.note}>{item.note}</div>
</div>

<style>
  .dcard {
    display: flex;
    flex-direction: column;
    gap: 5px;
    min-width: 0;
  }

  .d-title {
    font-size: 12px;
    line-height: 1.35;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .d-note {
    font-size: 11px;
    color: var(--accent);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
</style>
