<script lang="ts">
  import type { WorkView } from "$lib/api";
  import type { FavoriteCollection } from "$lib/library.svelte";
  import type { TasteLevel } from "$lib/prefs.svelte";
  import { categoriesOf } from "$lib/ui";
  import Cover from "./Cover.svelte";

  type Tab = "works" | "collections" | "themes";

  let {
    works,
    collections,
    profile,
    collectionIds,
    exemplarIds,
    onboarded,
    onsave,
    oncancel,
  }: {
    works: WorkView[];
    collections: FavoriteCollection[];
    profile: Record<string, TasteLevel>;
    collectionIds: string[];
    exemplarIds: string[];
    onboarded: boolean;
    onsave: (value: {
      profile: Record<string, TasteLevel>;
      collectionIds: string[];
      exemplarIds: string[];
    }) => void;
    oncancel: () => void;
  } = $props();

  // 组件每次打开都会重新挂载；草稿只在打开瞬间从已保存状态复制一次。
  function initialProfile(): Record<string, TasteLevel> {
    return { ...profile };
  }

  function initialCollections(): string[] {
    return collectionIds.length > 0 ? [...collectionIds] : collections.map((item) => item.id);
  }

  function initialExemplars(): string[] {
    return [...exemplarIds];
  }

  let tab = $state<Tab>("works");
  let draft = $state<Record<string, TasteLevel>>(initialProfile());
  let selectedCollectionIds = $state<string[]>(initialCollections());
  let selectedExemplarIds = $state<string[]>(initialExemplars());
  let themeQuery = $state("");

  const levelMeta: Record<TasteLevel, { label: string; hint: string }> = {
    love: { label: "很喜欢", hint: "强加权" },
    like: { label: "喜欢", hint: "正常加权" },
    less: { label: "少推荐", hint: "明显降权，但不排除" },
  };
  const groupOrder = [
    "游戏与玩法",
    "世界观与时代",
    "主角特征",
    "人物关系",
    "情节与氛围",
    "成人内容主题",
    "视觉与表现",
    "制作与技术",
    "其他主题",
  ];

  const workById = $derived(new Map(works.map((work) => [work.id, work])));
  const favoriteWorks = $derived.by(() => {
    const ids = new Set(collections.flatMap((collection) => collection.work_ids));
    return works.filter((work) => ids.has(work.id));
  });
  const exemplarWorks = $derived(
    selectedExemplarIds.map((id) => workById.get(id)).filter((work): work is WorkView => Boolean(work)),
  );
  const categoryCounts = $derived.by(() => {
    const counts = new Map<string, number>();
    for (const work of works) {
      for (const name of new Set(categoriesOf(work))) counts.set(name, (counts.get(name) ?? 0) + 1);
    }
    return counts;
  });

  const collectionSuggestions = $derived.by(() => {
    const ids = new Set(
      collections
        .filter((collection) => selectedCollectionIds.includes(collection.id))
        .flatMap((collection) => collection.work_ids),
    );
    const picked = works.filter((work) => ids.has(work.id));
    if (picked.length === 0 || works.length === 0) return [];
    const sample = new Map<string, number>();
    for (const work of picked) {
      for (const name of new Set(categoriesOf(work))) sample.set(name, (sample.get(name) ?? 0) + 1);
    }
    return [...sample.entries()]
      .map(([name, count]) => {
        const global = categoryCounts.get(name) ?? 1;
        const lift = count / picked.length / (global / works.length);
        return { name, count, total: picked.length, lift, rank: lift * Math.sqrt(count) };
      })
      .filter((item) => item.count >= Math.min(2, picked.length))
      .sort((a, b) => b.rank - a.rank || b.count - a.count)
      .slice(0, 36);
  });

  const semanticGroups = $derived.by(() => {
    const groups = new Map<string, { name: string; count: number }[]>();
    for (const [name, count] of categoryCounts) {
      if (themeQuery.trim() && !name.includes(themeQuery.trim())) continue;
      const group = semanticGroup(name);
      const list = groups.get(group) ?? [];
      list.push({ name, count });
      groups.set(group, list);
    }
    for (const list of groups.values()) list.sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
    return groupOrder.flatMap((name) => {
      const entries = groups.get(name);
      return entries ? ([[name, entries]] as [string, { name: string; count: number }[]][]) : [];
    });
  });

  const profileGroups = $derived({
    love: Object.keys(draft).filter((name) => draft[name] === "love"),
    like: Object.keys(draft).filter((name) => draft[name] === "like"),
    less: Object.keys(draft).filter((name) => draft[name] === "less"),
  });

  function semanticGroup(name: string): string {
    const rules: [string, RegExp][] = [
      ["游戏与玩法", /RPG|角色扮演|模拟|动作|冒险|解谜|经营|养成|射击|格斗|卡牌|回合|探索|战斗|迷宫/],
      ["世界观与时代", /奇幻|异世界|现代|学园|校园|魔法|科幻|历史|和风|西部|末世|赛博|中世纪|宇宙|乡村/],
      ["主角特征", /主人公|主角|勇者|魔王|魔法少女|变身女主|人外娘|魔物娘|女性主导/],
      ["人物关系", /后宫|百合|女同|纯爱|恋爱|夫妻|人妻|母女|姐妹|兄妹|师生|青梅竹马|主从|多P|乱交/],
      ["情节与氛围", /催眠|洗脑|堕落|NTR|凌辱|悬疑|恐怖|喜剧|治愈|复仇|背德|羞耻|寝取|调教/],
      ["成人内容主题", /巨乳|爆乳|贫乳|微乳|乳交|肛交|孕妇|怀孕|触手|异种|兽交|拘束|排泄|药物|痴汉|强奸|处女|淫语/],
      ["视觉与表现", /3D|像素|动画|配音|音乐|CG|立绘|Live2D|全彩|语音|音声/],
      ["制作与技术", /AI|制作大师|Unity|RPG制作|工具|素材|生成/],
    ];
    return rules.find(([, pattern]) => pattern.test(name))?.[0] ?? "其他主题";
  }

  /** 未选 → 喜欢 → 很喜欢 → 少推荐 → 未选。 */
  function cycle(name: string): void {
    const current = draft[name];
    const next = { ...draft };
    if (current === undefined) next[name] = "like";
    else if (current === "like") next[name] = "love";
    else if (current === "love") next[name] = "less";
    else delete next[name];
    draft = next;
  }

  function toggleCollection(id: string): void {
    selectedCollectionIds = selectedCollectionIds.includes(id)
      ? selectedCollectionIds.filter((item) => item !== id)
      : [...selectedCollectionIds, id];
  }

  function toggleExemplar(id: string): void {
    selectedExemplarIds = selectedExemplarIds.includes(id)
      ? selectedExemplarIds.filter((item) => item !== id)
      : [...selectedExemplarIds, id];
  }

  function next(): void {
    if (tab === "works") tab = "collections";
    else if (tab === "collections") tab = "themes";
    else save();
  }

  function save(): void {
    onsave({
      profile: { ...draft },
      collectionIds: [...selectedCollectionIds],
      exemplarIds: [...selectedExemplarIds],
    });
  }

  function onKeydown(event: KeyboardEvent): void {
    if (event.key === "Escape") oncancel();
  }
</script>

<svelte:window onkeydown={onKeydown} />

<div class="overlay">
  <div class="editor" role="dialog" aria-modal="true" aria-label="编辑口味">
    <header>
      <div>
        <h2>{onboarded ? "编辑口味" : "建立你的口味"}</h2>
        <p>从你真正喜欢的收藏作品中发现偏好，再按人的认知方式调整。所有分析仅在本机完成。</p>
      </div>
      <button class="close" title="关闭" onclick={oncancel}>×</button>
    </header>

    <div class="cycle-help">
      <span>连续点击分类即可调整：</span>
      <span class="legend like">喜欢</span><span>→</span>
      <span class="legend love">很喜欢</span><span>→</span>
      <span class="legend less">少推荐</span><span>→ 不选择</span>
      <span class="cycle-note">“少推荐”只降低排序，不会彻底排除</span>
    </div>

    <div class="content">
      <div class="main">
        <nav>
          <button class:active={tab === "works"} onclick={() => (tab = "works")}>1　从收藏中挑作品</button>
          <button class:active={tab === "collections"} onclick={() => (tab = "collections")}>2　从收藏中发现</button>
          <button class:active={tab === "themes"} onclick={() => (tab = "themes")}>3　按主题浏览</button>
        </nav>

        <div class="pane">
          {#if tab === "works"}
            <div class="intro">从你已经收藏的作品里，挑几部“这就是我的口味”。不需要记作品名，也不需要输入 RJ 号。</div>
            {#if favoriteWorks.length > 0}
              <div class="favorite-grid">
                {#each favoriteWorks as work (work.id)}
                  <button class="favorite-card" class:selected={selectedExemplarIds.includes(work.id)} onclick={() => toggleExemplar(work.id)}>
                    <Cover src={work._cover} width="100%" height={126} rounded />
                    <span class="favorite-title">{work.title}</span>
                    <span class="favorite-maker">{work.maker}</span>
                    {#if selectedExemplarIds.includes(work.id)}<span class="selected-mark">✓ 已选</span>{/if}
                  </button>
                {/each}
              </div>
            {:else}
              <div class="empty">收藏夹里还没有作品。先在浏览页点几颗心，回来就能直接看封面挑选。</div>
            {/if}
            {#if exemplarWorks.length === 0}
              <div class="empty compact">尚未挑选。也可以跳过，直接分析全部收藏。</div>
            {:else}
              <div class="exemplars">
                {#each exemplarWorks as work (work.id)}
                  <section class="exemplar">
                    <div class="exemplar-head">
                      <strong>{work.title}</strong>
                      <button class="text-btn" onclick={() => toggleExemplar(work.id)}>不再参考这部</button>
                    </div>
                    <div class="muted">具体喜欢它的哪些方面？</div>
                    <div class="chips">
                      {#each categoriesOf(work) as name (name)}
                        <button class="chip" class:love={draft[name] === "love"} class:like={draft[name] === "like"} class:less={draft[name] === "less"} onclick={() => cycle(name)}>{name}</button>
                      {/each}
                    </div>
                  </section>
                {/each}
              </div>
            {/if}
          {:else if tab === "collections"}
            <div class="intro">默认分析全部收藏夹；可以取消不代表口味的收藏夹。建议不会自动写入口味。</div>
            <div class="collection-list">
              {#each collections as collection (collection.id)}
                <label>
                  <input type="checkbox" checked={selectedCollectionIds.includes(collection.id)} onchange={() => toggleCollection(collection.id)} />
                  <span>{collection.name}</span><span class="muted">{collection.work_ids.length} 部</span>
                </label>
              {/each}
            </div>
            {#if collectionSuggestions.length === 0}
              <div class="empty">所选收藏夹里还没有足够的本地作品可供分析。</div>
            {:else}
              <div class="suggestions">
                {#each collectionSuggestions as item (item.name)}
                  <button class="suggestion" class:love={draft[item.name] === "love"} class:like={draft[item.name] === "like"} class:less={draft[item.name] === "less"} onclick={() => cycle(item.name)}>
                    <span class="suggestion-name">{item.name}</span>
                    <span class="suggestion-why">收藏中 {item.count}/{item.total} 部 · 是全库平均的 {item.lift.toFixed(1)} 倍</span>
                  </button>
                {/each}
              </div>
            {/if}
          {:else}
            <div class="intro">官方分类已按人的认知方式重新组织；每个分类只归入一个主组，搜索仍可直接找到。</div>
            <input class="search" placeholder="搜索题材、玩法、关系或表现形式…" bind:value={themeQuery} />
            <div class="theme-groups">
              {#each semanticGroups as [group, entries] (group)}
                <section class="theme-group">
                  <h3>{group}</h3>
                  <div class="chips">
                    {#each entries.slice(0, themeQuery.trim() ? 100 : 24) as entry (entry.name)}
                      <button class="chip with-count" class:love={draft[entry.name] === "love"} class:like={draft[entry.name] === "like"} class:less={draft[entry.name] === "less"} onclick={() => cycle(entry.name)}>
                        {entry.name}<span>{entry.count}</span>
                      </button>
                    {/each}
                  </div>
                </section>
              {/each}
            </div>
          {/if}
        </div>
      </div>

      <aside class="profile">
        <h3>当前口味画像</h3>
        <p class="muted">共 {Object.keys(draft).length} 项；连续点击可切换状态</p>
        {#each ["love", "like", "less"] as level (level)}
          <section class="profile-level">
            <div class="profile-label">{levelMeta[level as TasteLevel].label} · {profileGroups[level as TasteLevel].length}</div>
            <div class="profile-chips">
              {#each profileGroups[level as TasteLevel] as name (name)}
                <button class="profile-chip" class:love={level === "love"} class:less={level === "less"} title="点击继续切换状态" onclick={() => cycle(name)}>{name}</button>
              {/each}
            </div>
          </section>
        {/each}
      </aside>
    </div>

    <footer>
      <button class="btn" onclick={oncancel}>取消</button>
      {#if !onboarded && tab !== "themes"}
        <button class="btn primary" onclick={next}>下一步</button>
      {:else}
        <button class="btn primary" onclick={save}>保存口味</button>
      {/if}
    </footer>
  </div>
</div>

<style>
  .overlay { position: fixed; inset: 0; z-index: 300; display: flex; align-items: center; justify-content: center; padding: 24px; background: rgb(0 0 0 / 34%); }
  .editor { width: min(1120px, calc(100vw - 48px)); height: min(780px, calc(100vh - 48px)); display: flex; flex-direction: column; overflow: hidden; background: var(--bg); border: 1px solid var(--border); border-radius: 16px; box-shadow: 0 24px 80px rgb(0 0 0 / 38%); }
  header { display: flex; align-items: flex-start; padding: 18px 20px 12px; }
  h2, h3, p { margin: 0; }
  h2 { font-size: 18px; }
  header p { margin-top: 4px; color: var(--muted); font-size: 12px; }
  .close { margin-left: auto; border: 0; background: transparent; color: var(--muted); font-size: 24px; cursor: pointer; }
  .cycle-help { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; padding: 9px 20px; border-block: 1px solid var(--border); background: var(--panel); color: var(--muted); font-size: 11.5px; }
  .legend { border-radius: 999px; padding: 3px 8px; color: #fff; }
  .legend.like { background: var(--accent); }
  .legend.love { background: #d94a65; }
  .legend.less { background: #737782; }
  .cycle-note { margin-left: auto; }
  .content { min-height: 0; flex: 1; display: grid; grid-template-columns: minmax(0, 1fr) 280px; overflow: hidden; }
  .main { min-width: 0; min-height: 0; display: flex; flex-direction: column; overflow: hidden; }
  nav { display: flex; gap: 4px; padding: 10px 14px 0; }
  nav button { border: 0; border-bottom: 2px solid transparent; background: transparent; color: var(--muted); padding: 8px 12px; font: inherit; font-size: 12.5px; cursor: pointer; }
  nav button.active { color: var(--accent); border-bottom-color: var(--accent); font-weight: 650; }
  .pane { height: 0; min-height: 0; flex: 1 1 0; overflow-y: auto; overscroll-behavior: contain; -webkit-overflow-scrolling: touch; padding: 14px 18px 22px; }
  .intro, .empty { color: var(--muted); font-size: 12px; line-height: 1.5; margin-bottom: 10px; }
  .empty { padding: 22px; text-align: center; background: var(--panel); border-radius: 10px; }
  .empty.compact { margin-top: 12px; padding: 12px; }
  .search { width: min(480px, 100%); border: 1px solid var(--border); background: var(--panel); color: var(--text); border-radius: 8px; padding: 8px 10px; font: inherit; font-size: 12.5px; }
  .favorite-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(128px, 1fr)); gap: 10px; }
  .favorite-card { position: relative; min-width: 0; display: flex; flex-direction: column; gap: 4px; border: 1px solid var(--border); background: var(--panel); color: var(--text); border-radius: 11px; padding: 7px; text-align: left; cursor: pointer; }
  .favorite-card:hover { border-color: color-mix(in srgb, var(--accent) 55%, var(--border)); }
  .favorite-card.selected { border-color: var(--accent); box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 18%, transparent); }
  .favorite-title, .favorite-maker { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
  .favorite-title { font-size: 11.5px; font-weight: 650; }
  .favorite-maker { color: var(--muted); font-size: 10.5px; }
  .selected-mark { position: absolute; top: 12px; right: 12px; border-radius: 999px; padding: 3px 7px; background: var(--accent); color: #fff; font-size: 10px; box-shadow: 0 2px 8px rgb(0 0 0 / 30%); }
  .text-btn { color: var(--accent); }
  .exemplars { display: flex; flex-direction: column; gap: 10px; margin-top: 14px; }
  .exemplar { padding: 12px; border-radius: 10px; background: var(--panel); }
  .exemplar-head { display: flex; gap: 10px; justify-content: space-between; margin-bottom: 4px; }
  .text-btn { border: 0; background: transparent; font: inherit; font-size: 11.5px; cursor: pointer; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
  .chip { border: 1px solid var(--border); background: transparent; color: var(--muted); border-radius: 999px; padding: 4px 9px; font: inherit; font-size: 11.5px; cursor: pointer; }
  .chip.with-count { display: inline-flex; gap: 5px; }
  .chip.with-count span { opacity: 0.55; }
  .chip.love, .suggestion.love { color: #fff; border-color: #d94a65; background: #d94a65; }
  .chip.like, .suggestion.like { color: #fff; border-color: var(--accent); background: var(--accent); }
  .chip.less, .suggestion.less { color: #fff; border-color: #737782; background: #737782; }
  .collection-list { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }
  .collection-list label { display: inline-flex; align-items: center; gap: 6px; padding: 6px 9px; border-radius: 8px; background: var(--panel); font-size: 12px; }
  .suggestions { display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 8px; }
  .suggestion { min-width: 0; display: flex; flex-direction: column; gap: 3px; border: 1px solid var(--border); background: var(--panel); color: var(--text); border-radius: 9px; padding: 9px 10px; text-align: left; cursor: pointer; }
  .suggestion-name { font-weight: 650; }
  .suggestion-why { font-size: 10.5px; opacity: 0.68; }
  .theme-groups { display: flex; flex-direction: column; gap: 16px; margin-top: 14px; }
  .theme-group h3 { font-size: 12.5px; }
  .profile { min-height: 0; overflow-y: auto; padding: 16px; border-left: 1px solid var(--border); background: var(--panel); }
  .profile > h3 { font-size: 14px; }
  .muted { color: var(--muted); font-size: 11.5px; }
  .profile-level { margin-top: 16px; }
  .profile-label { font-size: 11.5px; color: var(--muted); margin-bottom: 6px; }
  .profile-chips { display: flex; flex-wrap: wrap; gap: 5px; }
  .profile-chip { border: 0; border-radius: 999px; padding: 4px 8px; background: var(--accent); color: #fff; font: inherit; font-size: 11px; cursor: pointer; }
  .profile-chip.love { background: #d94a65; }
  .profile-chip.less { background: #737782; }
  footer { display: flex; justify-content: flex-end; gap: 8px; padding: 12px 18px; border-top: 1px solid var(--border); background: var(--panel); }
  @media (max-width: 820px) { .content { grid-template-columns: 1fr; } .profile { display: none; } .cycle-note { width: 100%; margin-left: 0; } }
</style>
