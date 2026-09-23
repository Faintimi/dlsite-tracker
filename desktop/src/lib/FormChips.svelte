<script lang="ts">
  import TagChip from "./TagChip.svelte";
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
    <TagChip
      kind="form"
      text={name}
      title={ontap ? `点击筛选形式「${name}」（再点取消）` : ""}
      onclick={ontap ? () => ontap(name) : undefined}
    />
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

  .more {
    font-size: 11px;
    color: var(--muted);
    padding: 4px 3px;
    opacity: 0.7;
  }
</style>
