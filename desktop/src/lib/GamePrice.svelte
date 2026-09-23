<script lang="ts">
  import type { WorkView } from "$lib/api";

  let {
    game,
    showDiscount = true,
    size = "md",
  }: {
    game: WorkView;
    showDiscount?: boolean;
    size?: "md" | "sm";
  } = $props();

  const discounted = $derived(
    showDiscount &&
      typeof game.official_price === "number" &&
      typeof game.price === "number" &&
      game.official_price > game.price &&
      typeof game.discount_rate === "number" &&
      game.discount_rate > 0,
  );

  function yen(value: number | null): string {
    return typeof value === "number" ? `¥${value.toLocaleString("ja-JP")}` : "价格未知";
  }
</script>

{#if discounted}
  <span class="row {size}">
    <span class="off">{game.discount_rate}%OFF</span>
    <span class="now">{yen(game.price)}</span>
    <span class="was">{yen(game.official_price)}</span>
  </span>
{:else}
  <span class="now {size}">{yen(game.price)}</span>
{/if}

<style>
  .row {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    min-width: 0;
  }

  /* 折扣角标：红色胶囊 + 白字 */
  .off {
    font-size: 10px;
    font-weight: 700;
    line-height: 1;
    padding: 2.5px 4px;
    border-radius: 999px;
    background: rgb(255 59 48 / 85%);
    color: #fff;
    flex: none;
  }

  .now {
    color: #ff9500;
    font-weight: 600;
    white-space: nowrap;
  }

  .now.md {
    font-size: 15px;
  }

  .now.sm {
    font-size: 13px;
  }

  .was {
    font-size: 12px;
    color: var(--muted);
    text-decoration: line-through;
    white-space: nowrap;
  }
</style>
