<script lang="ts">
  let {
    forms,
    limit = 100,
    ontap,
  }: {
    forms: string[];
    limit?: number;
    ontap?: (name: string) => void;
  } = $props();

  const shown = $derived(forms.slice(0, limit));
  const more = $derived(Math.max(0, forms.length - shown.length));
</script>

<div class="chips">
  {#each shown as name (name)}
    {#if ontap}
      <button class="chip" title={`点击筛选形式「${name}」（再点取消）`} onclick={() => ontap(name)}>
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

  /* P16.1：作品形式 = 实心蓝色胶囊 + 白字 */
  .chip {
    appearance: none;
    border: 0;
    font: inherit;
    font-size: 11px;
    font-weight: 600;
    line-height: 1;
    padding: 4px 8px;
    border-radius: 999px;
    background: #007aff;
    color: #fff;
    white-space: nowrap;
    cursor: default;
  }

  button.chip {
    cursor: pointer;
  }

  button.chip:hover {
    filter: brightness(1.12);
  }

  .more {
    font-size: 11px;
    color: var(--muted);
    padding: 4px 3px;
    opacity: 0.7;
  }
</style>
