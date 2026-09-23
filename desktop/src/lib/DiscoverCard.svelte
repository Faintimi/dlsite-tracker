<script lang="ts">
  import { onDestroy } from "svelte";
  import type { WorkView } from "$lib/api";
  import Cover from "./Cover.svelte";
  import type { DiscoveryItem } from "$lib/discovery";

  let {
    item,
    onopen,
    onhover,
    onleave,
    onseen,
    oncontext,
    seen = false,
  }: {
    item: DiscoveryItem;
    onopen?: (game: WorkView) => void;
    onhover?: (game: WorkView, event: MouseEvent) => void;
    onleave?: () => void;
    onseen?: (game: WorkView) => void;
    oncontext?: (game: WorkView, event: MouseEvent) => void;
    seen?: boolean;
  } = $props();

  let seenTimer: ReturnType<typeof setTimeout> | null = null;

  function enter(event: MouseEvent) {
    onhover?.(item.game, event);
    if (!seen) {
      seenTimer = setTimeout(() => {
        seenTimer = null;
        onseen?.(item.game);
      }, 2000);
    }
  }

  function leave() {
    if (seenTimer !== null) clearTimeout(seenTimer);
    seenTimer = null;
    onleave?.();
  }

  function open() {
    onseen?.(item.game);
    onopen?.(item.game);
  }

  onDestroy(() => {
    if (seenTimer !== null) clearTimeout(seenTimer);
  });
</script>

<div
  class="dcard"
  class:seen
  role="listitem"
  title={item.game.title}
  ondblclick={open}
  onmouseenter={enter}
  onmouseleave={leave}
  oncontextmenu={(event) => oncontext?.(item.game, event)}
>
  <div class="cover-wrap">
    <Cover src={item.game._cover} width="100%" height={196} rounded />
    {#if item.badges.length > 0}
      <div class="signal-badges">
        {#if item.badges.includes("sprint")}<span class="signal sprint">冲刺中</span>{/if}
        {#if item.badges.includes("hype")}<span class="signal hype">高期待</span>{/if}
      </div>
    {/if}
    {#if seen}<span class="seen-badge">看过</span>{/if}
  </div>
  <div class="d-title">{item.game.title}</div>
  <div class="d-note" title={item.note}>{item.note}</div>
</div>

<style>
  .dcard {
    display: flex;
    flex-direction: column;
    gap: 5px;
    min-width: 0;
    transition: opacity 150ms ease;
  }

  .dcard.seen {
    opacity: 0.52;
  }

  .dcard.seen:hover {
    opacity: 0.82;
  }

  .cover-wrap {
    position: relative;
  }

  .signal-badges {
    position: absolute;
    top: 6px;
    left: 6px;
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
  }

  .signal,
  .seen-badge {
    border-radius: 999px;
    padding: 2px 6px;
    color: #fff;
    font-size: 10px;
    font-weight: 650;
    line-height: 1.35;
    box-shadow: 0 1px 4px rgb(0 0 0 / 25%);
  }

  .signal.sprint {
    background: #e65d42;
  }

  .signal.hype {
    background: #a24fc4;
  }

  .seen-badge {
    position: absolute;
    right: 6px;
    bottom: 6px;
    background: rgb(50 50 55 / 82%);
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
