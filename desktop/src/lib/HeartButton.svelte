<script lang="ts">
  import { library } from "$lib/library.svelte";

  let { id }: { id: string } = $props();

  const on = $derived(library.isFavorited(id));
</script>

<button
  class="heart"
  class:on
  title={on ? "移出「我的收藏」（右键管理收藏夹）" : "加入「我的收藏」（右键管理收藏夹）"}
  onclick={(event) => {
    event.stopPropagation();
    library.toggleFavorite(id);
  }}
  ondblclick={(event) => event.stopPropagation()}
>
  {on ? "♥" : "♡"}
</button>

<style>
  .heart {
    appearance: none;
    border: 0;
    background: transparent;
    font: inherit;
    font-size: 13px;
    line-height: 1;
    padding: 2px;
    color: var(--muted);
    cursor: pointer;
    flex: none;
  }

  .heart:hover {
    color: var(--text);
  }

  .heart.on {
    color: #ff2d55;
  }

  .heart.on:hover {
    color: #ff5d7d;
  }
</style>
