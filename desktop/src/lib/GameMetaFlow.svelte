<script lang="ts">
  import type { WorkView } from "$lib/api";
  import { ICONS, cardRatingColor, compactDateText, fmtNum, heatText, ratingText } from "$lib/ui";

  let {
    game,
    showRatingCount = true,
    rankText = null,
  }: {
    game: WorkView;
    showRatingCount?: boolean;
    rankText?: string | null;
  } = $props();

  const items = $derived.by(() => {
    const list: { key: string; icon: string; text: string; color?: string }[] = [];
    if (rankText) list.push({ key: "rank", icon: ICONS.rank, text: rankText });
    list.push({ key: "sales", icon: ICONS.bag, text: fmtNum(game.sales) });
    list.push({
      key: "rating",
      icon: ICONS.star,
      text: ratingText(game, showRatingCount),
      color: cardRatingColor(game),
    });
    if (game.regist_date) {
      list.push({ key: "date", icon: ICONS.calendar, text: compactDateText(game.regist_date) });
    }
    const heat = heatText(game);
    if (heat) list.push({ key: "heat", icon: ICONS.flame, text: heat });
    return list;
  });
</script>

<div class="flow">
  {#each items as item (item.key)}
    <span class="item" style:color={item.color}>
      <span class="icon">{@html item.icon}</span><span>{item.text}</span>
    </span>
  {/each}
</div>

<style>
  .flow {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 12px;
    font-size: 12px;
    color: var(--muted);
    min-width: 0;
  }

  .item {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    white-space: nowrap;
  }

  .icon {
    display: inline-flex;
    align-items: center;
    opacity: 0.85;
  }
</style>
