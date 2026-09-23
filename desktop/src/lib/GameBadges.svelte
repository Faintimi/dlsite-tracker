<script lang="ts">
  import type { WorkView } from "$lib/api";
  import { CONTENT_FLAG_TAGS, type ContentFlag } from "./tag";
  import TagChip from "./TagChip.svelte";

  let {
    game,
    showText = true,
    ontap,
  }: {
    game: WorkView;
    showText?: boolean;
    ontap?: (key: ContentFlag) => void;
  } = $props();

  const items = $derived(CONTENT_FLAG_TAGS.filter((item) => game[item.key]));
</script>

{#if items.length > 0}
  <div class="badges">
    {#each items as item (item.key)}
      <TagChip
        kind={item.key}
        text={showText ? item.label : ""}
        title={item.help}
        ariaLabel={item.help}
        onclick={ontap ? () => ontap(item.key) : undefined}
      />
    {/each}
  </div>
{/if}

<style>
  .badges {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }

</style>
