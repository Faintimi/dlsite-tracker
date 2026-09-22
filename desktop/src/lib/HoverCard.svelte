<script lang="ts">
  import type { WorkView } from "$lib/api";

  let { work, x, y }: { work: WorkView; x: number; y: number } = $props();

  const WIDTH = 340;
  const HEIGHT = 300;
  const MARGIN = 12;

  const left = $derived(Math.min(Math.max(MARGIN, x + 18), window.innerWidth - WIDTH - MARGIN));
  const top = $derived(Math.min(Math.max(MARGIN, y + 18), window.innerHeight - HEIGHT - MARGIN));

  const ranks = $derived.by(() => {
    const list: { label: string; value: number }[] = [];
    if (typeof work.rank_day_current === "number" && work.rank_day_current > 0) {
      list.push({ label: "日榜", value: work.rank_day_current });
    }
    if (typeof work.rank_week_current === "number" && work.rank_week_current > 0) {
      list.push({ label: "周榜", value: work.rank_week_current });
    }
    if (typeof work.rank_month_current === "number" && work.rank_month_current > 0) {
      list.push({ label: "月榜", value: work.rank_month_current });
    }
    return list;
  });

  const hasDiscount = $derived(
    typeof work.discount_rate === "number" &&
      work.discount_rate > 0 &&
      typeof work.official_price === "number" &&
      typeof work.price === "number" &&
      work.official_price > work.price,
  );

  function fmtNum(n: number | null | undefined): string {
    return typeof n === "number" && Number.isFinite(n) ? n.toLocaleString("ja-JP") : "—";
  }

  function fmtRating(n: number | null | undefined): string {
    return typeof n === "number" && Number.isFinite(n) ? n.toFixed(1) : "—";
  }

  function fmtPrice(n: number | null | undefined): string {
    return typeof n === "number" ? `¥${n.toLocaleString("ja-JP")}` : "—";
  }
</script>

<div class="hover-card" style="left: {left}px; top: {top}px; width: {WIDTH}px">
  <div class="hc-title">{work.title}</div>
  <div class="hc-sub">{work.maker} · {work.id}</div>
  <div class="hc-line">
    <span>销量 {fmtNum(work.sales)}</span>
    <span>★ {fmtRating(work.rating)}（{fmtNum(work.rating_count)} 评）</span>
  </div>
  <div class="hc-line">
    <span class="price">{fmtPrice(work.price)}</span>
    {#if hasDiscount}
      <span class="hc-discount">原价 {fmtPrice(work.official_price)} · -{work.discount_rate}%</span>
    {/if}
  </div>
  {#if ranks.length > 0}
    <div class="hc-line">
      {#each ranks as rank (rank.label)}
        <span>当前{rank.label} #{rank.value}</span>
      {/each}
    </div>
  {/if}
  <div class="hc-sub">发售 {work.regist_date ? work.regist_date.slice(0, 10) : "—"}</div>
  <div class="hc-cats">{work.category}</div>
  <div class="hc-hint">点击打开 DLsite 页面 ↗</div>
</div>

<style>
  .hover-card {
    position: fixed;
    z-index: 100;
    pointer-events: none;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 10px;
    box-shadow: 0 10px 30px rgb(0 0 0 / 25%);
    padding: 10px 12px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .hc-title {
    font-size: 14px;
    font-weight: 600;
    line-height: 19px;
  }

  .hc-sub {
    font-size: 12px;
    color: var(--muted);
  }

  .hc-line {
    display: flex;
    flex-wrap: wrap;
    gap: 4px 14px;
    font-size: 12px;
  }

  .hc-line .price {
    color: var(--accent);
    font-weight: 600;
  }

  .hc-discount {
    color: #d97706;
  }

  .hc-cats {
    font-size: 12px;
    color: var(--muted);
    line-height: 17px;
    max-height: 68px;
    overflow: hidden;
  }

  .hc-hint {
    font-size: 11px;
    color: var(--accent);
    margin-top: 2px;
  }
</style>
