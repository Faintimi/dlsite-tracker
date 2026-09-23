<script lang="ts">
  import { onMount, tick } from "svelte";
  import TagChip from "./TagChip.svelte";
  let {
    categories,
    limit = 100,
    maxRows,
    ontap,
  }: {
    categories: string[];
    limit?: number;
    maxRows?: number;
    ontap?: (name: string) => void;
  } = $props();

  let container = $state<HTMLDivElement>();
  let measure = $state<HTMLDivElement>();
  let fitted = $state<number | null>(null);
  const shown = $derived(categories.slice(0, Math.min(limit, fitted ?? limit)));
  const more = $derived(Math.max(0, categories.length - shown.length));

  function fitRows() {
    if (!maxRows || !container || !measure) return;
    const width = container.clientWidth;
    if (!width) return;
    const widths = Array.from(measure.children, (child) => child.getBoundingClientRect().width);
    const gap = 5;
    const max = Math.min(limit, categories.length);
    for (let count = max; count >= 0; count--) {
      const items = widths.slice(0, count);
      if (count < categories.length) items.push(widths[max]);
      let rows = 1;
      let line = 0;
      let lineItems = 0;
      for (const itemWidth of items) {
        if (line && line + gap + itemWidth > width) {
          rows++;
          line = 0;
          lineItems = 0;
        }
        line += (line ? gap : 0) + itemWidth;
        lineItems++;
      }
      const orphanMore = count > 0 && count < categories.length && lineItems === 1;
      if (rows <= maxRows && !orphanMore) {
        fitted = count;
        return;
      }
    }
    fitted = 0;
  }

  $effect(() => {
    categories;
    limit;
    if (maxRows) void tick().then(fitRows);
  });

  onMount(() => {
    if (!maxRows) return;
    const observer = new ResizeObserver(fitRows);
    if (container) observer.observe(container);
    return () => observer.disconnect();
  });
</script>

<div class="chips" bind:this={container}>
  {#each shown as name (name)}
    <TagChip
      kind="category"
      text={name}
      title={ontap ? `点击筛选分类「${name}」（再点取消）` : ""}
      onclick={ontap ? () => ontap(name) : undefined}
    />
  {/each}
  {#if more > 0}<span class="more">+{more}</span>{/if}
</div>
{#if maxRows}
  <div class="measure" bind:this={measure} aria-hidden="true">
    {#each categories.slice(0, limit) as name, index (index)}
      <TagChip kind="category" text={name} />
    {/each}
    <span class="more">+{categories.length}</span>
  </div>
{/if}

<style>
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
    min-width: 0;
  }

  .measure {
    position: absolute;
    visibility: hidden;
    pointer-events: none;
    display: flex;
    width: max-content;
    white-space: nowrap;
  }
  .measure :global(*) { flex: none; }

  .more {
    font-size: 11px;
    line-height: 1;
    color: var(--muted);
    padding: 4px 3px;
    opacity: 0.7;
  }
</style>
