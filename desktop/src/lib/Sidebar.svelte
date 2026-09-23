<script lang="ts">
  // 左筛选侧栏（固定 280px；逐项对齐 macOS ContentView.sidebar）
  import type { GenreCatalogEntry, GenreEntry, WorkView } from "$lib/api";
  import type { FilterState, ViewFilter } from "$lib/filter";
  import { yearOf } from "$lib/filter";
  import type { FavoriteCollection, FollowedMaker } from "$lib/library.svelte";
  import type { GenreProgress, ImportProgress } from "$lib/pipeline";
  import { yearsLabel } from "$lib/pipeline";
  import { ICONS, categoriesOf, formsOf } from "$lib/ui";
  import ContextMenu from "./ContextMenu.svelte";
  import ConfirmDialog from "./ConfirmDialog.svelte";
  import NavRow from "./NavRow.svelte";
  import PromptDialog from "./PromptDialog.svelte";
  import RangeFields from "./RangeFields.svelte";
  import SetFilterMenu from "./SetFilterMenu.svelte";
  import YearPickerDialog from "./YearPickerDialog.svelte";

  let {
    works,
    genres,
    genreCatalog,
    collections,
    makers,
    filter = $bindable(),
    viewFilter = $bindable(),
    importYears = $bindable(),
    importProgress = null,
    genreProgress = null,
    onCreateCollection,
    onRenameCollection,
    onDeleteCollection,
    onGenreImport,
    onClearFilters,
    onImportToggle,
    onCancelImport,
    onCancelFollow,
    macosImport = null,
    onImportMacos,
  }: {
    works: WorkView[];
    genres: GenreEntry[];
    genreCatalog: GenreCatalogEntry[];
    collections: FavoriteCollection[];
    makers: FollowedMaker[];
    filter: FilterState;
    viewFilter: ViewFilter;
    importYears: string;
    importProgress?: ImportProgress | null;
    genreProgress?: GenreProgress | null;
    onCreateCollection: (name: string) => void;
    onRenameCollection: (id: string, name: string) => void;
    onDeleteCollection: (id: string) => void;
    onGenreImport: (id: string, name: string) => void;
    onClearFilters: () => void;
    onImportToggle: (on: boolean) => void;
    onCancelImport: () => void;
    onCancelFollow: (maker: FollowedMaker) => void;
    macosImport?: { path: string; collections: number; makers: number } | null;
    onImportMacos?: () => void;
  } = $props();

  let genreSearch = $state("");
  let categorySearch = $state("");

  let menu = $state<{ x: number; y: number; items: { label: string; action: () => void; danger?: boolean }[] } | null>(null);
  let editor = $state<{ mode: "new" | "rename"; id?: string } | null>(null);
  let editorName = $state("");
  let confirmDelete = $state<FavoriteCollection | null>(null);
  let yearPickOpen = $state(false);
  let yearPickValue = $state(new Date().getFullYear() - 5);
  let confirmCancelImport = $state(false);

  // 分类 / 形式 / 年份候选（对齐 macOS categories / forms / releaseYears）
  const categories = $derived.by(() => {
    const set = new Set<string>();
    for (const work of works) {
      for (const name of categoriesOf(work)) set.add(name);
    }
    return [...set].sort((a, b) => a.localeCompare(b, "zh-Hans-CN"));
  });
  const forms = $derived.by(() => {
    const set = new Set<string>();
    for (const work of works) {
      for (const name of formsOf(work)) set.add(name);
    }
    return [...set].sort((a, b) => a.localeCompare(b, "ja"));
  });
  const releaseYears = $derived.by(() => {
    const set = new Set<number>();
    for (const work of works) {
      const year = yearOf(work);
      if (year !== null) set.add(year);
    }
    return [...set].sort((a, b) => b - a);
  });
  const yearPickChoices = $derived.by(() => {
    const current = new Date().getFullYear();
    const out: { value: number; label: string }[] = [];
    for (let year = current; year >= 2006; year--) {
      out.push({ value: year, label: `${year} 年` });
    }
    return out;
  });

  /** 分类人气区块行数据（对齐 macOS genreEntries：默认已导入分类；搜索时匹配官方全量目录） */
  const genreEntries = $derived.by(() => {
    const keyword = genreSearch.trim().toLowerCase();
    if (!keyword) return genres;
    const known = new Map(genres.map((entry) => [entry.id, entry]));
    const source: { id: string; name: string }[] =
      genreCatalog.length > 0 ? genreCatalog : genres.map(({ id, name }) => ({ id, name }));
    return source
      .filter((entry) => entry.name.toLowerCase().includes(keyword) || entry.id.includes(keyword))
      .slice(0, 60)
      .map((entry) => known.get(entry.id) ?? { id: entry.id, name: entry.name });
  });

  const categoryMatches = $derived.by(() => {
    const keyword = categorySearch.trim().toLowerCase();
    if (!keyword) return [];
    return categories.filter((name) => name.toLowerCase().includes(keyword)).slice(0, 40);
  });

  const importJobActive = $derived(importProgress?.phase === "enrich");
  const importRunning = $derived(importProgress?.running === true);
  const genreJobActive = $derived(genreProgress?.running === true);

  const importRangeOptions = $derived.by(() => {
    const options = [
      { value: "1", label: "最近一年" },
      { value: "3", label: "最近三年" },
      { value: "5", label: "最近五年" },
      { value: "7", label: "最近七年" },
    ];
    if (importYears.startsWith("since:")) {
      options.push({
        value: importYears,
        label: `自 ${importYears.slice("since:".length)} 年`,
      });
    }
    return options;
  });

  function genreTrailing(entry: GenreEntry): string {
    if (!(entry.depth ?? 0)) return "未导入";
    if (typeof entry.count === "number") return `${entry.count} 件`;
    return "已导入";
  }

  function handleGenreTap(entry: GenreEntry): void {
    if ((entry.depth ?? 0) > 0) {
      filter.genreFocus = filter.genreFocus === entry.id ? "" : entry.id;
    } else {
      onGenreImport(entry.id, entry.name);
    }
  }

  function toggleIncludeCategory(name: string): void {
    if (filter.genres.includes(name)) {
      filter.genres = filter.genres.filter((item) => item !== name);
    } else {
      filter.genres = [...filter.genres, name];
      filter.excludeGenres = filter.excludeGenres.filter((item) => item !== name);
    }
  }

  function toggleExcludeCategory(name: string): void {
    if (filter.excludeGenres.includes(name)) {
      filter.excludeGenres = filter.excludeGenres.filter((item) => item !== name);
    } else {
      filter.excludeGenres = [...filter.excludeGenres, name];
      filter.genres = filter.genres.filter((item) => item !== name);
    }
  }

  function openCollectionMenu(collection: FavoriteCollection, event: MouseEvent): void {
    menu = {
      x: event.clientX,
      y: event.clientY,
      items: [
        {
          label: "重命名…",
          action: () => {
            editorName = collection.name;
            editor = { mode: "rename", id: collection.id };
          },
        },
        {
          label: "删除收藏夹",
          danger: true,
          action: () => {
            confirmDelete = collection;
          },
        },
      ],
    };
  }

  function openMakerMenu(maker: FollowedMaker, event: MouseEvent): void {
    menu = {
      x: event.clientX,
      y: event.clientY,
      items: [
        {
          label: "取消关注",
          danger: true,
          action: () => {
            onCancelFollow(maker);
          },
        },
      ],
    };
  }

  function submitEditor(value: string): void {
    if (!editor) return;
    if (editor.mode === "rename" && editor.id) {
      onRenameCollection(editor.id, value);
    } else {
      onCreateCollection(value);
    }
    editor = null;
  }

  function clearFilters(): void {
    genreSearch = "";
    categorySearch = "";
    onClearFilters();
  }
</script>

<aside class="sidebar">
  <div class="section">
    <div class="title">收藏</div>
    <NavRow
      icon={ICONS.gridAll}
      title="全部作品"
      count={works.length}
      selected={viewFilter.kind === "all"}
      onclick={() => (viewFilter = { kind: "all" })}
    />
    {#each collections as collection (collection.id)}
      <NavRow
        icon={ICONS.folder}
        title={collection.name}
        count={collection.work_ids.length}
        selected={viewFilter.kind === "collection" && viewFilter.id === collection.id}
        onclick={() => (viewFilter = { kind: "collection", id: collection.id })}
        onmenu={(event) => openCollectionMenu(collection, event)}
      />
    {/each}
    <button
      class="link"
      onclick={() => {
        editorName = "";
        editor = { mode: "new" };
      }}
    >
      <span class="link-icon">{@html ICONS.plus}</span>新建收藏夹
    </button>
    {#if macosImport}
      <button class="link" title={macosImport.path} onclick={onImportMacos}>
        <span class="link-icon">{@html ICONS.tray}</span>从 macOS 版导入收藏…
      </button>
    {/if}
    {#if makers.length > 0}
      <div class="subtitle">关注的制作者</div>
      {#each makers as maker (maker.key)}
        <NavRow
          icon={ICONS.personCircle}
          title={maker.name}
          selected={viewFilter.kind === "maker" && viewFilter.key === maker.key}
          onclick={() => (viewFilter = { kind: "maker", key: maker.key, name: maker.name, makerId: maker.maker_id })}
          onmenu={(event) => openMakerMenu(maker, event)}
        />
      {/each}
    {/if}
  </div>

  <div class="divider"></div>

  <div class="section">
    <div class="title">分类人气</div>
    <div class="block">
      <input class="box" placeholder="搜索分类（官方全量目录）" bind:value={genreSearch} />
      {#if genreEntries.length === 0}
        <div class="hint">
          {genres.length === 0
            ? "尚无分类人气数据：先点「开始更新数据」，或输入分类名用「现导入」。"
            : "没有匹配的分类。"}
        </div>
      {:else}
        {#each genreEntries.slice(0, 24) as entry (entry.id)}
          <button
            class="genre-row"
            class:selected={filter.genreFocus === entry.id}
            title={(entry.depth ?? 0) > 0
              ? `点击按「${entry.name}」官方人气名次浏览；再点取消`
              : "尚未导入：点击现导入前 200 名"}
            onclick={() => handleGenreTap(entry)}
          >
            <span class="genre-icon" class:selected={filter.genreFocus === entry.id}>
              {@html filter.genreFocus === entry.id ? ICONS.chartBarFill : ICONS.chartBar}
            </span>
            <span class="genre-name">{entry.name}</span>
            {#if genreJobActive && genreProgress?.genre_id === entry.id}
              <span class="spin"></span>
            {/if}
            <span class="spacer"></span>
            <span class="genre-tail">{genreTrailing(entry)}</span>
          </button>
        {/each}
        {#if genreEntries.length > 24}
          <div class="hint">还有 {genreEntries.length - 24} 个结果；继续输入可缩小范围</div>
        {/if}
      {/if}
    </div>
  </div>

  <div class="divider"></div>

  <div class="section">
    <div class="title">筛选条件</div>
    <div class="block">
      <div class="cap">游戏名或制作者</div>
      <input class="box" placeholder="搜索" bind:value={filter.keyword} />
    </div>
    <RangeFields title="评分区间" unit="星" bind:lower={filter.ratingLow} bind:upper={filter.ratingHigh} />
    <label class="check">
      <input type="checkbox" bind:checked={filter.includeUnrated} />
      包含未评分作品
    </label>
    <RangeFields title="销量区间" unit="份" bind:lower={filter.salesLow} bind:upper={filter.salesHigh} />
    <RangeFields title="价格区间" unit="日元" bind:lower={filter.priceLow} bind:upper={filter.priceHigh} />
    <div class="block">
      <div class="cap">分类 / 标签（已识别；多选取交集，同时满足全部所选）</div>
      <input class="box" placeholder="搜索分类…" bind:value={categorySearch} />
      {#if !categorySearch.trim()}
        <SetFilterMenu
          title="包含分类（交集）"
          emptyLabel="全部"
          options={categories}
          selection={filter.genres}
          onchange={(next) => (filter.genres = next)}
        />
        <SetFilterMenu
          title="排除分类"
          emptyLabel="不排除"
          options={categories}
          selection={filter.excludeGenres}
          onchange={(next) => (filter.excludeGenres = next)}
        />
      {:else if categoryMatches.length === 0}
        <div class="hint">没有匹配的分类</div>
      {:else}
        {#each categoryMatches as name (name)}
          <button
            class="cat-row"
            class:selected={filter.genres.includes(name)}
            onclick={() => toggleIncludeCategory(name)}
            oncontextmenu={(event) => {
              event.preventDefault();
              toggleExcludeCategory(name);
            }}
          >
            <span class="cat-name">{name}</span>
            <span class="spacer"></span>
            {#if filter.excludeGenres.includes(name)}<span class="tag">已排除</span>{/if}
            {#if filter.genres.includes(name)}<span class="ck">{@html ICONS.check}</span>{/if}
          </button>
        {/each}
      {/if}
    </div>
    <div class="block">
      <div class="cap">作品形式（如 RPG、SLG）</div>
      <select class="box" bind:value={filter.form}>
        <option value="">全部</option>
        {#each forms as form (form)}
          <option value={form}>{form}</option>
        {/each}
      </select>
    </div>
    <div class="block">
      <div class="cap">发售年份（可多选）</div>
      <SetFilterMenu
        title="包含年份"
        emptyLabel="全部"
        options={releaseYears.map(String)}
        selection={filter.selectedYears.map(String)}
        onchange={(next) => (filter.selectedYears = next.map(Number))}
      />
    </div>
    <div class="block">
      <div class="cap">内容标志（可多选，同时满足）</div>
      <div class="flags">
        <label class="check">
          <input
            type="checkbox"
            checked={filter.flags.voice}
            onchange={(event) => (filter.flags = { ...filter.flags, voice: event.currentTarget.checked })}
          />
          配音
        </label>
        <label class="check">
          <input
            type="checkbox"
            checked={filter.flags.music}
            onchange={(event) => (filter.flags = { ...filter.flags, music: event.currentTarget.checked })}
          />
          音乐
        </label>
        <label class="check">
          <input
            type="checkbox"
            checked={filter.flags.video}
            onchange={(event) => (filter.flags = { ...filter.flags, video: event.currentTarget.checked })}
          />
          动画
        </label>
      </div>
    </div>
  </div>

  <div class="divider"></div>

  <div class="section">
    <div class="block">
      <div class="cap">渐进导入（后台分批入库）</div>
      <label class="check">
        <input
          type="checkbox"
          checked={importRunning}
          onchange={(event) => onImportToggle(event.currentTarget.checked)}
        />
        开启（关闭 = 暂停，可随时再开）
      </label>
      <select class="box" bind:value={importYears} disabled={importJobActive} aria-label="渐进导入范围">
        {#each importRangeOptions as option (option.value)}
          <option value={option.value}>{option.label}</option>
        {/each}
      </select>
      <button class="link" disabled={importJobActive} onclick={() => (yearPickOpen = true)}>
        自选起始年份…
      </button>
      {#if importJobActive}
        <div class="hint">
          当前任务：{yearsLabel(importProgress?.years ?? "1")} · {importRunning ? "进行中" : "已暂停"}
        </div>
        <button class="link" onclick={() => (confirmCancelImport = true)}>取消导入任务…</button>
      {/if}
    </div>
    <button class="link" onclick={clearFilters}>清空筛选</button>
  </div>

  <div class="spacer"></div>
  <div class="footnote">
    数据来自你导入的文件。「更新」重读同一文件；「开始更新数据」运行本地管道（导入 → 销量 → 封面 → 导出），完成后自动刷新。收藏与偏好保存在本机。
  </div>
</aside>

{#if menu}
  <ContextMenu x={menu.x} y={menu.y} items={menu.items} onclose={() => (menu = null)} />
{/if}

{#if editor}
  <PromptDialog
    title={editor.mode === "new" ? "新建收藏夹" : "重命名收藏夹"}
    label="收藏夹名称"
    placeholder="收藏夹名称"
    bind:value={editorName}
    onsubmit={submitEditor}
    oncancel={() => (editor = null)}
  />
{/if}

{#if confirmDelete}
  <ConfirmDialog
    title="删除收藏夹？"
    message="只会移除这个收藏夹，作品与本地数据不受影响。"
    confirmLabel="删除"
    onconfirm={() => {
      if (confirmDelete) onDeleteCollection(confirmDelete.id);
      confirmDelete = null;
    }}
    oncancel={() => (confirmDelete = null)}
  />
{/if}

{#if yearPickOpen}
  <YearPickerDialog
    title="自定义导入起始年份"
    message="设置后，打开「渐进导入」开关即可从 {yearPickValue} 年至今分批入库。"
    options={yearPickChoices}
    bind:value={yearPickValue}
    onsubmit={(year) => {
      importYears = `since:${year}`;
      yearPickOpen = false;
    }}
    oncancel={() => (yearPickOpen = false)}
  />
{/if}

{#if confirmCancelImport}
  <ConfirmDialog
    title="取消导入任务？"
    message="任务定义将被删除，已入库的作品保留；之后可随时重新开启。"
    confirmLabel="取消任务"
    onconfirm={() => {
      confirmCancelImport = false;
      onCancelImport();
    }}
    oncancel={() => (confirmCancelImport = false)}
  />
{/if}

<style>
  .sidebar {
    width: 280px;
    flex: none;
    background: var(--panel);
    border-right: 1px solid var(--border);
    overflow-y: auto;
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .section {
    display: flex;
    flex-direction: column;
    gap: 7px;
  }

  .title {
    font-size: 16px;
    font-weight: 700;
  }

  .subtitle {
    font-size: 12px;
    color: var(--muted);
    padding-top: 2px;
  }

  .divider {
    border-top: 1px solid var(--border);
  }

  .block {
    display: flex;
    flex-direction: column;
    gap: 7px;
  }

  .cap {
    font-size: 12px;
    color: var(--muted);
  }

  .box {
    border: 1px solid var(--border);
    background: var(--bg);
    color: var(--text);
    border-radius: 7px;
    padding: 5px 8px;
    font-size: 12.5px;
    font-family: inherit;
    width: 100%;
    min-width: 0;
  }

  .hint {
    font-size: 12px;
    color: var(--muted);
    opacity: 0.85;
  }

  .link {
    appearance: none;
    border: 0;
    background: transparent;
    color: var(--accent);
    font: inherit;
    font-size: 12px;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 0;
    cursor: default;
    text-align: left;
  }

  .link:disabled {
    color: var(--muted);
    opacity: 0.6;
  }

  .link-icon {
    display: inline-flex;
  }

  .genre-row,
  .cat-row {
    appearance: none;
    border: 0;
    background: transparent;
    color: var(--text);
    font: inherit;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 5px 8px;
    border-radius: 7px;
    cursor: default;
    text-align: left;
    width: 100%;
  }

  .genre-row:hover,
  .cat-row:hover {
    background: color-mix(in srgb, var(--text) 6%, transparent);
  }

  .genre-row.selected,
  .cat-row.selected {
    background: color-mix(in srgb, var(--accent) 14%, transparent);
  }

  .genre-icon {
    display: inline-flex;
    width: 16px;
    justify-content: center;
    color: var(--muted);
  }

  .genre-icon.selected {
    color: var(--accent);
  }

  .genre-name {
    font-size: 13px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .genre-tail {
    font-size: 12px;
    color: var(--muted);
    opacity: 0.8;
  }

  .cat-name {
    font-size: 12.5px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .tag {
    font-size: 11px;
    color: var(--muted);
    opacity: 0.85;
  }

  .ck {
    display: inline-flex;
    color: var(--accent);
  }

  .spacer {
    flex: 1;
  }

  .flags {
    display: flex;
    gap: 14px;
  }

  .check {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12.5px;
    cursor: default;
  }

  .spin {
    width: 12px;
    height: 12px;
    border: 2px solid color-mix(in srgb, var(--accent) 30%, transparent);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.9s linear infinite;
    flex: none;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  .footnote {
    font-size: 11.5px;
    color: var(--muted);
    opacity: 0.8;
    line-height: 17px;
    padding-top: 10px;
  }
</style>
