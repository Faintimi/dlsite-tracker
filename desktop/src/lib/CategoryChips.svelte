<script lang="ts">
  let {
    categories,
    limit = 100,
    ontap,
  }: {
    categories: string[];
    limit?: number;
    ontap?: (name: string) => void;
  } = $props();

  const shown = $derived(categories.slice(0, limit));
  const more = $derived(Math.max(0, categories.length - shown.length));
</script>

<div class="chips">
  {#each shown as name (name)}
    {#if ontap}
      <button class="chip" title={`点击筛选分类「${name}」（再点取消）`} onclick={() => ontap(name)}>
        {name}
      </button>
    {:else}
      <span class="chip">{name}</span>
    {/if}
  {/each}
  {#if more > 0}<span class="more">+{more}</span>{/if}
</div>

<style>
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
    min-width: 0;
  }

  .chip {
    appearance: none;
    border: 0;
    font: inherit;
    font-size: 11px;
    line-height: 1;
    padding: 4px 7px;
    border-radius: 999px;
    background: color-mix(in srgb, var(--text) 8%, transparent);
    color: var(--muted);
    white-space: nowrap;
    cursor: default;
  }

  button.chip {
    cursor: pointer;
  }

  button.chip:hover {
    background: color-mix(in srgb, var(--text) 16%, transparent);
    color: var(--text);
  }

  .more {
    font-size: 11px;
    color: var(--muted);
    padding: 4px 3px;
    opacity: 0.7;
  }
</style>
