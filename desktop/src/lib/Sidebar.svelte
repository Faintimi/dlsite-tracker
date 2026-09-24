<script lang="ts">
  // 左筛选侧栏（固定 280px）：四个分区为独立卡片（边界清晰）、折叠带滑动动画（P34.1）
  import { slide } from "svelte/transition";
  import type { GenreCatalogEntry, GenreEntry, WorkView } from "$lib/api";
  import type { FilterState, ViewFilter } from "$lib/filter";
  import { activeFilterCount, yearOf } from "$lib/filter";
  import type { FavoriteCollection, FollowedMaker } from "$lib/library.svelte";
  import type { GenreProgress, ImportProgress } from "$lib/pipeline";
  import { yearsLabel } from "$lib/pipeline";
  import { prefs } from "$lib/prefs.svelte";
  import { ICONS, categoriesOf, formsOf } from "$lib/ui";
  import ContextMenu from "./ContextMenu.svelte";
  import ConfirmDialog from "./ConfirmDialog.svelte";
  import NavRow from "./NavRow.svelte";
  import PromptDialog from "./PromptDialog.svelte";
  import RangeFields from "./RangeFields.svelte";
  import SetFilterMenu from "./SetFilterMenu.svelte";
  import YearPickerDialog from "./YearPickerDialog.svelte";

  let {
    active = true,
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
    onGenreWatch,
    onGenreUnwatch,
    onGenreRemove,
    onClearFilters,
    onImportToggle,
    onCancelImport,
    onCancelFollow,
    followUpdatesSelected = false,
    followUpdatesUnread = 0,
    onOpenFollowUpdates,
    onOpenBrowse,
  }: {
    active?: boolean;
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
    onGenreWatch: (id: string) => void;
    onGenreUnwatch: (id: string) => void;
    onGenreRemove: (id: string) => void;
    onClearFilters: () => void;
    onImportToggle: (on: boolean) => void;
    onCancelImport: () => void;
    onCancelFollow: (maker: FollowedMaker) => void;
    followUpdatesSelected?: boolean;
    followUpdatesUnread?: number;
    onOpenFollowUpdates: () => void;
    onOpenBrowse: () => void;
  } = $props();

  const SECTION_DURATION = 220;

  let genreSearch = $state("");
  let categorySearch = $state("");

  let menu = $state<{ x: number; y: number; items: { label: string; action: () => void; danger?: boolean; divider?: boolean }[] } | null>(null);
  let editor = $state<{ mode: "new" | "rename"; id?: string } | null>(null);
  let editorName = $state("");
  let confirmDelete = $state<FavoriteCollection | null>(null);
  let yearPickOpen = $state(false);
  let yearPickValue = $state(new Date().getFullYear() - 5);
  let confirmCancelImport = $state(false);
  let genresExpanded = $state(false);
  let removeRequest = $state<{ id: string; name: string } | null>(null);

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
  const watchedCount = $derived(genres.filter((entry) => entry.watched).length);
  const filterCount = $derived(activeFilterCount(filter));

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

  /** 分类行右键菜单：每日刷新开关 + 移除分类（未导入的行只有「现导入」） */
  function openGenreMenu(entry: GenreEntry, event: MouseEvent): void {
    event.preventDefault();
    event.stopPropagation();
    const items: { label: string; action: () => void; danger?: boolean; divider?: boolean }[] = [];
    if ((entry.depth ?? 0) > 0) {
      if (entry.watched) {
        items.push({ label: "取消每日刷新", action: () => onGenreUnwatch(entry.id) });
      } else {
        items.push({ label: "加入每日刷新", action: () => onGenreWatch(entry.id) });
      }
      items.push({
        label: "移除分类（含名次数据）…",
        divider: true,
        danger: true,
        action: () => {
          removeRequest = { id: entry.id, name: entry.name };
        },
      });
    } else {
      items.push({ label: "现导入（前 200 名）", action: () => onGenreImport(entry.id, entry.name) });
    }
    menu = { x: event.clientX, y: event.clientY, items };
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

<aside class="sidebar" class:inactive={!active}>
  <section class="card flat">
    <button
      class="section-head"
      title={prefs.data.sections.favorites ? "收起「收藏」" : "展开「收藏」"}
      onclick={() => prefs.toggleSection("favorites", !prefs.data.sections.favorites)}
    >
      <span class="chev" class:open={prefs.data.sections.favorites}>{@html ICONS.chevronRight}</span>
      <span class="bar"></span>
      <span class="sec-icon">{@html ICONS.folder}</span>
      <span class="title">收藏</span>
      <span class="spacer"></span>
      {#if !prefs.data.sections.favorites}
        <span class="summary">
          {collections.length} 收藏夹
        </span>
      {/if}
    </button>
    {#if prefs.data.sections.favorites}
      <div class="section-body" transition:slide={{ duration: SECTION_DURATION }}>
        <NavRow
          icon={ICONS.gridAll}
          title="全部作品"
          count={works.length}
          selected={!followUpdatesSelected && viewFilter.kind === "all"}
          onclick={() => {
            onOpenBrowse();
            viewFilter = { kind: "all" };
          }}
        />
        {#each collections as collection (collection.id)}
          <NavRow
            icon={ICONS.folder}
            title={collection.name}
            count={collection.work_ids.length}
            selected={!followUpdatesSelected && viewFilter.kind === "collection" && viewFilter.id === collection.id}
            onclick={() => {
              onOpenBrowse();
              viewFilter = { kind: "collection", id: collection.id };
            }}
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
      </div>
    {/if}
  </section>

  <section class="card flat">
    <button
      class="section-head"
      title={prefs.data.sections.follows ? "收起「关注」" : "展开「关注」"}
      aria-expanded={prefs.data.sections.follows}
      onclick={() => prefs.toggleSection("follows", !prefs.data.sections.follows)}
    >
      <span class="chev" class:open={prefs.data.sections.follows}>{@html ICONS.chevronRight}</span>
      <span class="bar"></span>
      <span class="sec-icon">{@html ICONS.personCircle}</span>
      <span class="title">关注</span>
      <span class="spacer"></span>
      {#if !prefs.data.sections.follows}<span class="summary">{makers.length} 位作者</span>{/if}
      {#if followUpdatesUnread > 0}
        <span class="follow-unread">{followUpdatesUnread} 部未读</span>
      {/if}
    </button>
    {#if prefs.data.sections.follows}
      <div class="section-body" transition:slide={{ duration: SECTION_DURATION }}>
        <NavRow
          icon={ICONS.flame}
          title="关注更新"
          count={followUpdatesUnread > 0 ? followUpdatesUnread : null}
          selected={followUpdatesSelected}
          onclick={onOpenFollowUpdates}
        />
        {#if makers.length > 0}<div class="subtitle">关注的作者（{makers.length}）</div>{/if}
        {#each makers as maker (maker.key)}
          <NavRow
            icon={ICONS.personCircle}
            title={maker.name}
            selected={!followUpdatesSelected && viewFilter.kind === "maker" && viewFilter.key === maker.key}
            onclick={() => {
              onOpenBrowse();
              viewFilter = { kind: "maker", key: maker.key, name: maker.name, makerId: maker.maker_id };
            }}
            onmenu={(event) => openMakerMenu(maker, event)}
          />
        {/each}
      </div>
    {/if}
  </section>

  <section class="card">
    <button
      class="section-head genre-section-head"
      title={prefs.data.sections.genres ? "收起「分类人气榜」" : "展开「分类人气榜」"}
      onclick={() => prefs.toggleSection("genres", !prefs.data.sections.genres)}
    >
      <span class="chev" class:open={prefs.data.sections.genres}>{@html ICONS.chevronRight}</span>
      <span class="bar"></span>
      <span class="sec-icon">{@html ICONS.chartBarFill}</span>
      <span class="genre-head-copy">
        <span class="title">分类人气榜</span>
        {#if !prefs.data.sections.genres}
          <span class="summary">
            {genres.length === 0
              ? "暂无已导入分类"
              : `已导入 ${genres.length} 个分类${watchedCount > 0 ? ` · 每日刷新 ${watchedCount}` : ""}`}
          </span>
        {/if}
      </span>
    </button>
    {#if prefs.data.sections.genres}
      <div class="section-body" transition:slide={{ duration: SECTION_DURATION }}>
        <div class="hint">点击按官方人气名次浏览；右键可现导入 / 每日刷新 / 移除</div>
        <input class="box" placeholder="搜索分类（官方全量目录）" bind:value={genreSearch} />
        {#if genreEntries.length === 0}
          <div class="hint">
            {genres.length === 0
              ? "尚无分类人气榜数据：先点「开始更新数据」，或输入分类名用「现导入」。"
              : "没有匹配的分类。"}
          </div>
        {:else}
          {#each (genresExpanded ? genreEntries : genreEntries.slice(0, 12)) as entry (entry.id)}
            <button
              class="genre-row"
              class:selected={filter.genreFocus === entry.id}
              title={(entry.depth ?? 0) > 0
                ? `点击按「${entry.name}」官方人气名次浏览；右键管理`
                : "尚未导入：点击现导入前 200 名"}
              onclick={() => handleGenreTap(entry)}
              oncontextmenu={(event) => openGenreMenu(entry, event)}
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
          {#if genreEntries.length > 12}
            {#if genresExpanded}
              <button class="link" onclick={() => (genresExpanded = false)}>收起</button>
            {:else}
              <button class="link" onclick={() => (genresExpanded = true)}>
                显示全部（{genreEntries.length}）
              </button>
            {/if}
          {/if}
        {/if}
      </div>
    {/if}
  </section>

  <section class="card">
    <div class="head-row">
      <button
        class="section-head"
        title={prefs.data.sections.filters ? "收起「筛选条件」" : "展开「筛选条件」"}
        onclick={() => prefs.toggleSection("filters", !prefs.data.sections.filters)}
      >
        <span class="chev" class:open={prefs.data.sections.filters}>{@html ICONS.chevronRight}</span>
        <span class="bar"></span>
        <span class="sec-icon">{@html ICONS.filterCircle}</span>
        <span class="title">筛选条件</span>
        <span class="spacer"></span>
        {#if !prefs.data.sections.filters && filterCount > 0}
          <span class="summary">已用 {filterCount} 项</span>
        {/if}
      </button>
      <button class="link" onclick={clearFilters}>清空筛选</button>
    </div>
    {#if prefs.data.sections.filters}
      <div class="section-body" transition:slide={{ duration: SECTION_DURATION }}>
        <div class="block">
          <div class="cap">游戏名或制作者</div>
          <input class="box" placeholder="搜索" bind:value={filter.keyword} />
        </div>
        <div class="block">
          <div class="cap" title="已识别；多选取交集，同时满足全部所选">分类 / 标签</div>
          <input class="box" placeholder="搜索分类…" bind:value={categorySearch} />
          {#if !categorySearch.trim()}
            <SetFilterMenu
              title="包含分类"
              hint="多选取交集：同时满足全部所选"
              emptyLabel="全部"
              options={categories}
              selection={filter.genres}
              onchange={(next) => (filter.genres = next)}
            />
            <SetFilterMenu
              title="排除分类"
              hint="命中任一所选分类即排除"
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
          <div class="cap">作品形式</div>
          <SetFilterMenu
            title="包含形式"
            hint="多选取并集：符合任一所选形式即可"
            emptyLabel="全部"
            options={forms}
            selection={filter.forms}
            onchange={(next) => (filter.forms = next)}
          />
        </div>
        <div class="block">
          <div class="cap">内容标志</div>
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
        <button
          class="more-toggle"
          onclick={() => prefs.set("filtersMore", !prefs.data.filtersMore)}
        >
          <span class="chev" class:open={prefs.data.filtersMore}>{@html ICONS.chevronRight}</span>
          更多筛选（评分 / 销量 / 价格 / 年份）
        </button>
        {#if prefs.data.filtersMore}
          <div class="section-body" transition:slide={{ duration: SECTION_DURATION }}>
            <RangeFields title="评分区间" unit="星" bind:lower={filter.ratingLow} bind:upper={filter.ratingHigh} />
            <label class="check">
              <input type="checkbox" bind:checked={filter.includeUnrated} />
              包含未评分作品
            </label>
            <RangeFields title="销量区间" unit="份" bind:lower={filter.salesLow} bind:upper={filter.salesHigh} />
            <RangeFields title="价格区间" unit="日元" bind:lower={filter.priceLow} bind:upper={filter.priceHigh} />
            <div class="block">
              <div class="cap">发售年份</div>
              <SetFilterMenu
                title="包含年份"
                hint="可多选；作品发售年份需在所选之内"
                emptyLabel="全部"
                options={releaseYears.map(String)}
                selection={filter.selectedYears.map(String)}
                onchange={(next) => (filter.selectedYears = next.map(Number))}
              />
            </div>
          </div>
        {/if}
      </div>
    {/if}
  </section>

  <section class="card">
    <button
      class="section-head"
      title={prefs.data.sections.imports ? "收起「渐进导入」" : "展开「渐进导入」"}
      onclick={() => prefs.toggleSection("imports", !prefs.data.sections.imports)}
    >
      <span class="chev" class:open={prefs.data.sections.imports}>{@html ICONS.chevronRight}</span>
      <span class="bar"></span>
      <span class="sec-icon">{@html ICONS.tray}</span>
      <span class="title">渐进导入</span>
      <span class="spacer"></span>
      {#if !prefs.data.sections.imports && importJobActive}
        <span class="summary">{importRunning ? "进行中" : "已暂停"}</span>
      {/if}
    </button>
    {#if prefs.data.sections.imports}
      <div class="section-body" transition:slide={{ duration: SECTION_DURATION }}>
        <div class="cap">后台分批入库</div>
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
    {/if}
  </section>
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

{#if removeRequest}
  <ConfirmDialog
    title="移除分类？"
    message={`将删除「${removeRequest.name}」已抓取的人气名次数据，并移出每日刷新；已入库的作品会保留。`}
    confirmLabel="移除"
    danger
    onconfirm={() => {
      const request = removeRequest;
      removeRequest = null;
      if (request) onGenreRemove(request.id);
    }}
    oncancel={() => (removeRequest = null)}
  />
{/if}

<style>
  .sidebar {
    width: 280px;
    flex: none;
    background: var(--bg);
    border-right: 1px solid var(--border);
    overflow-y: auto;
    padding: 14px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .sidebar.inactive { display: none; }

  /* 控制区 = 无边框浅底圆角组（系统设置内容区那种 inset 分组） */
  .card {
    background: var(--panel);
    border: 0;
    border-radius: 11px;
    padding: 8px 12px 12px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  /* 导航区 = macOS 扁平风（无底色，列表直接落在侧栏底上） */
  .card.flat {
    background: transparent;
    border-radius: 0;
    padding: 0 2px;
  }

  .bar {
    width: 3px;
    height: 12px;
    border-radius: 2px;
    background: var(--accent);
    flex: none;
    opacity: 0.9;
  }

  .sec-icon {
    display: inline-flex;
    color: var(--accent);
    flex: none;
  }

  .section-head {
    appearance: none;
    border: 0;
    background: transparent;
    color: var(--text);
    font: inherit;
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 5px 4px;
    margin: 0 -4px;
    border-radius: 8px;
    width: 100%;
    cursor: default;
    text-align: left;
    transition: background 0.15s ease;
  }

  .section-head:hover {
    background: color-mix(in srgb, var(--text) 5%, transparent);
  }

  .chev {
    display: inline-flex;
    color: var(--muted);
    flex: none;
    transition: transform 0.22s cubic-bezier(0.2, 0, 0, 1);
  }

  .chev.open {
    transform: rotate(90deg);
  }

  .title {
    font-size: 13.5px;
    font-weight: 650;
    letter-spacing: 0.1px;
  }

  .summary {
    font-size: 11.5px;
    color: var(--muted);
    font-weight: 400;
    white-space: nowrap;
  }

  .follow-unread {
    flex: none;
    border-radius: 999px;
    padding: 2px 6px;
    background: color-mix(in srgb, var(--accent) 13%, transparent);
    color: var(--accent);
    font-size: 10.5px;
    font-weight: 650;
    white-space: nowrap;
  }

  /* 分类人气榜的标题与统计分两行，避免窄侧栏中标题被摘要挤成竖排。 */
  .genre-section-head {
    align-items: flex-start;
  }

  .genre-section-head > .chev,
  .genre-section-head > .bar,
  .genre-section-head > .sec-icon {
    margin-top: 2px;
  }

  .genre-head-copy {
    min-width: 0;
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .genre-head-copy .title,
  .genre-head-copy .summary {
    display: block;
    white-space: nowrap;
  }

  .head-row {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .head-row .section-head {
    flex: 1;
  }

  .section-body {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding-top: 2px;
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
    border-radius: 8px;
    padding: 5px 8px;
    font-size: 12.5px;
    font-family: inherit;
    width: 100%;
    min-width: 0;
  }

  .box:focus-visible {
    outline: none;
    border-color: color-mix(in srgb, var(--accent) 60%, var(--border));
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
    white-space: nowrap;
    transition: opacity 0.15s ease;
  }

  .link:hover {
    opacity: 0.75;
  }

  .link:disabled {
    color: var(--muted);
    opacity: 0.6;
  }

  .link-icon {
    display: inline-flex;
  }

  .more-toggle {
    appearance: none;
    border: 0;
    background: transparent;
    color: var(--text);
    font: inherit;
    font-size: 12.5px;
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 5px 4px;
    margin: 0 -4px;
    border-radius: 8px;
    cursor: default;
    text-align: left;
    transition: background 0.15s ease;
  }

  .more-toggle:hover {
    background: color-mix(in srgb, var(--text) 5%, transparent);
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
    border-radius: 8px;
    cursor: default;
    text-align: left;
    width: 100%;
    transition: background 0.15s ease;
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

  .subtitle {
    font-size: 12px;
    color: var(--muted);
    padding-top: 2px;
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

  @media (prefers-reduced-motion: reduce) {
    .chev {
      transition: none;
    }
  }
</style>
