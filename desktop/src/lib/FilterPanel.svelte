<script lang="ts">
  import type { GenreEntry } from "$lib/api";
  import type { FilterState } from "$lib/filter";

  let {
    filter = $bindable(),
    genres,
    years,
    onreset,
  }: {
    filter: FilterState;
    genres: GenreEntry[];
    years: number[];
    onreset: () => void;
  } = $props();

  // 分类芯片：按作品数降序取前 60 个
  const topGenres = $derived([...genres].sort((a, b) => b.count - a.count).slice(0, 60));

  function toggleGenre(name: string) {
    filter.genres = filter.genres.includes(name)
      ? filter.genres.filter((item) => item !== name)
      : [...filter.genres, name];
  }
</script>

<div class="panel">
  <div class="row">
    <label class="field">
      <span>关键词</span>
      <input type="search" placeholder="标题 / 作者 / 分类 / 编号" bind:value={filter.keyword} />
    </label>
    <div class="field">
      <span>年份</span>
      <select bind:value={filter.yearFrom}>
        <option value={0}>不限</option>
        {#each years as y (y)}<option value={y}>{y}</option>{/each}
      </select>
      <span>–</span>
      <select bind:value={filter.yearTo}>
        <option value={0}>不限</option>
        {#each years as y (y)}<option value={y}>{y}</option>{/each}
      </select>
    </div>
    <label class="field">
      <span>销量 ≥</span>
      <input type="number" min="0" step="1000" placeholder="不限" bind:value={filter.salesMin} />
    </label>
    <label class="field">
      <span>价格 ≤</span>
      <input type="number" min="0" step="100" placeholder="不限" bind:value={filter.priceMax} />
    </label>
    <label class="field">
      <span>评分 ≥</span>
      <select bind:value={filter.ratingMin}>
        <option value={0}>不限</option>
        <option value={3}>3.0</option>
        <option value={3.5}>3.5</option>
        <option value={4}>4.0</option>
        <option value={4.5}>4.5</option>
      </select>
    </label>
    <button class="btn" onclick={onreset}>重置</button>
  </div>

  <div class="genres">
    {#each topGenres as genre (genre.id)}
      <button
        class="chip"
        class:on={filter.genres.includes(genre.name)}
        onclick={() => toggleGenre(genre.name)}
      >
        {genre.name}<span class="count">{genre.count}</span>
      </button>
    {/each}
  </div>
</div>

<style>
  .panel {
    flex: none;
    padding: 10px 16px 12px;
    background: var(--panel);
    border-bottom: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px 16px;
  }

  .field {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: var(--muted);
  }

  .field input[type="search"],
  .field input[type="number"],
  .field select {
    border: 1px solid var(--border);
    background: var(--bg);
    color: var(--text);
    border-radius: 8px;
    padding: 5px 8px;
    font-size: 13px;
    font-family: inherit;
  }

  .field input[type="search"] {
    width: 200px;
  }

  .field input[type="number"] {
    width: 90px;
  }

  .genres {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    max-height: 88px;
    overflow-y: auto;
  }

  .chip {
    border: 1px solid var(--border);
    background: var(--bg);
    color: var(--text);
    border-radius: 999px;
    padding: 3px 10px;
    font-size: 12px;
    font-family: inherit;
    cursor: pointer;
    transition:
      border-color 0.12s ease,
      background 0.12s ease,
      color 0.12s ease;
  }

  .chip:hover {
    border-color: var(--accent);
  }

  .chip.on {
    border-color: var(--accent);
    background: var(--accent);
    color: #fff;
  }

  .chip .count {
    margin-left: 5px;
    font-size: 11px;
    opacity: 0.65;
  }
</style>
