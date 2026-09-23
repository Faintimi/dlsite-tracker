<script lang="ts">
  import type { GenreEntry } from "$lib/api";
  import type { FilterState } from "$lib/filter";
  import { DEFAULT_COLLECTION_NAME, library, type FavoriteCollection } from "$lib/library.svelte";

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

  const collectionCount = $derived(library.data.collections.length);
  const defaultCollectionId = $derived(
    library.data.collections.find((item) => item.name === DEFAULT_COLLECTION_NAME)?.id ?? "",
  );

  function addCollection() {
    const name = window.prompt("新建收藏夹名称：", "新收藏夹");
    if (name === null) return;
    library.createCollection(name);
  }

  function renameCollection(collection: FavoriteCollection) {
    const name = window.prompt("重命名收藏夹：", collection.name);
    if (name === null) return;
    library.renameCollection(collection.id, name);
  }

  function removeCollection(collection: FavoriteCollection) {
    if (!window.confirm(`删除收藏夹「${collection.name}」（${collection.work_ids.length} 件作品）？`)) {
      return;
    }
    library.deleteCollection(collection.id);
    if (filter.collectionId === collection.id) filter.collectionId = "all";
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
    <label class="field">
      <span>收藏</span>
      <select bind:value={filter.fav}>
        <option value="all">不限</option>
        <option value="yes">仅已收藏</option>
        <option value="no">仅未收藏</option>
      </select>
    </label>
    {#if filter.fav === "yes" && collectionCount > 1}
      <label class="field">
        <span>收藏夹</span>
        <select bind:value={filter.collectionId}>
          <option value="all">全部收藏夹</option>
          {#each library.data.collections as collection (collection.id)}
            <option value={collection.id}>{collection.name}</option>
          {/each}
        </select>
      </label>
    {/if}
    <label class="field">
      <span>作者</span>
      <select bind:value={filter.followed}>
        <option value="all">不限</option>
        <option value="yes">仅已关注</option>
      </select>
    </label>
    <button class="btn" onclick={onreset}>重置</button>
  </div>

  <div class="collections">
    <span class="col-label">收藏夹</span>
    {#each library.data.collections as collection (collection.id)}
      <span class="chip col" class:on={filter.fav === "yes" && filter.collectionId === collection.id}>
        <button
          class="chip-body"
          title="点击：只看该收藏夹"
          onclick={() => {
            filter.fav = "yes";
            filter.collectionId = collection.id;
          }}
        >
          {collection.name}（{collection.work_ids.length}）
        </button>
        <button class="mini" title="重命名" onclick={() => renameCollection(collection)}>✎</button>
        {#if collection.id !== defaultCollectionId}
          <button class="mini" title="删除" onclick={() => removeCollection(collection)}>×</button>
        {/if}
      </span>
    {/each}
    <button class="chip" onclick={addCollection}>＋ 新建收藏夹</button>
    {#if library.data.makers.length > 0}
      <span class="col-note">已关注作者 {library.data.makers.length}</span>
    {/if}
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

  .collections {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
  }

  .col-label {
    font-size: 12px;
    color: var(--muted);
    margin-right: 2px;
  }

  .chip.col {
    display: inline-flex;
    align-items: center;
    padding: 0 2px 0 0;
    overflow: hidden;
  }

  .chip-body {
    appearance: none;
    border: 0;
    background: transparent;
    color: inherit;
    font: inherit;
    font-size: 12px;
    padding: 3px 6px;
    cursor: pointer;
  }

  .mini {
    appearance: none;
    border: 0;
    background: transparent;
    color: var(--muted);
    font-size: 11px;
    padding: 2px 5px;
    cursor: pointer;
    border-radius: 4px;
  }

  .mini:hover {
    background: rgb(128 128 128 / 20%);
    color: var(--text);
  }

  .col-note {
    font-size: 11px;
    color: var(--muted);
    margin-left: 4px;
  }
</style>
