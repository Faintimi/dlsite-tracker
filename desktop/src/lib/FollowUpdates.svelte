<script lang="ts">
  import type { WorkView } from "$lib/api";
  import { makerKeyOf } from "$lib/filter";
  import Cover from "./Cover.svelte";

  let {
    active = true,
    resetScrollToken = 0,
    works,
    unreadIds,
    lastCheckedAt,
    refreshing = false,
    onrefresh,
    onopen,
    onmaker,
  }: {
    active?: boolean;
    resetScrollToken?: number;
    works: WorkView[];
    unreadIds: Set<string>;
    lastCheckedAt: number;
    refreshing?: boolean;
    onrefresh: () => void;
    onopen: (work: WorkView) => void;
    onmaker: (work: WorkView) => void;
  } = $props();

  let updatesEl: HTMLDivElement | null = $state(null);
  let savedScrollTop = 0;
  $effect(() => {
    if (active && updatesEl) updatesEl.scrollTop = savedScrollTop;
  });
  $effect(() => {
    void resetScrollToken;
    savedScrollTop = 0;
    updatesEl?.scrollTo({ top: 0 });
  });

  const groups = $derived.by(() => {
    const byMaker = new Map<string, { name: string; works: WorkView[] }>();
    for (const work of works) {
      const key = makerKeyOf(work.maker, work.maker_id);
      const group = byMaker.get(key) ?? { name: work.maker || "制作者未知", works: [] };
      group.works.push(work);
      byMaker.set(key, group);
    }
    return [...byMaker.entries()]
      .map(([key, group]) => ({
        key,
        ...group,
        unread: group.works.filter((work) => unreadIds.has(work.id)).length,
      }))
      .sort((a, b) => b.unread - a.unread || a.name.localeCompare(b.name, "zh-Hans-CN"));
  });

  function releaseTime(value: string): number {
    const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
    if (match) return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3])).getTime();
    const stamp = Date.parse(value);
    return Number.isFinite(stamp) ? stamp : 0;
  }

  function ageLabel(value: string): string {
    const stamp = releaseTime(value);
    if (!stamp) return value || "日期未知";
    const days = Math.max(0, Math.floor((Date.now() - stamp) / 86_400_000));
    if (days === 0) return "今天发布";
    if (days === 1) return "昨天发布";
    return `${days} 天前发布`;
  }

  function checkedLabel(): string {
    if (!lastCheckedAt) return "尚未检查";
    return `上次检查 ${new Date(lastCheckedAt).toLocaleString("zh-CN", {
      month: "numeric",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    })}`;
  }
</script>

<div
  class="updates"
  class:inactive={!active}
  bind:this={updatesEl}
  onscroll={(event) => { if (active) savedScrollTop = event.currentTarget.scrollTop; }}
>
  <header>
    <div>
      <h2>关注更新</h2>
      <p>关注作者最近 14 天发布的新作；打开本页会清除未读数字，但 NEW 标志保留。</p>
    </div>
    <div class="check">
      <span>{checkedLabel()}</span>
      <button class="btn primary" disabled={refreshing} onclick={onrefresh}>
        {refreshing ? "正在检查…" : "立即检查"}
      </button>
    </div>
  </header>

  {#if groups.length === 0}
    <div class="empty">
      <div class="empty-title">近两周没有发现关注作者的新作</div>
      <div>应用每天首次打开时自动检查；更新作品数据后也会再次识别。</div>
    </div>
  {:else}
    <div class="group-list">
      {#each groups as group (group.key)}
        <section class="maker-group">
          <div class="maker-head">
            <button class="maker" onclick={() => onmaker(group.works[0])}>{group.name}</button>
            <span>{group.works.length} 部近两周新作</span>
            {#if group.unread > 0}<span class="unread">{group.unread} 部未读</span>{/if}
          </div>
          <div class="work-grid">
            {#each group.works.sort((a, b) => releaseTime(b.regist_date) - releaseTime(a.regist_date)) as work (work.id)}
              <button class="work" onclick={() => onopen(work)} title={work.title}>
                <div class="cover-wrap">
                  <Cover src={work._cover} width="100%" height={168} rounded />
                  <span class="new">NEW</span>
                  {#if unreadIds.has(work.id)}<span class="dot" title="未读"></span>{/if}
                </div>
                <span class="title">{work.title}</span>
                <span class="date">{ageLabel(work.regist_date)}</span>
              </button>
            {/each}
          </div>
        </section>
      {/each}
    </div>
  {/if}
</div>

<style>
  .updates { min-height: 0; flex: 1; overflow-y: auto; padding: 20px 22px 34px; }
  .updates.inactive { display: none; }
  header { display: flex; align-items: flex-start; gap: 20px; margin-bottom: 18px; }
  h2, p { margin: 0; }
  h2 { font-size: 19px; }
  p { margin-top: 5px; color: var(--muted); font-size: 12px; }
  .check { margin-left: auto; display: flex; align-items: center; gap: 10px; color: var(--muted); font-size: 11.5px; white-space: nowrap; }
  .btn { border: 1px solid var(--border); border-radius: 8px; background: var(--panel); color: var(--text); padding: 6px 11px; font: inherit; font-size: 12px; cursor: pointer; }
  .btn.primary { border-color: var(--accent); background: var(--accent); color: #fff; }
  .btn:disabled { cursor: default; opacity: 0.55; }
  .group-list { display: flex; flex-direction: column; gap: 22px; }
  .maker-group { min-width: 0; }
  .maker-head { display: flex; align-items: baseline; gap: 8px; margin-bottom: 9px; color: var(--muted); font-size: 11.5px; }
  .maker { border: 0; background: transparent; color: var(--text); padding: 0; font: inherit; font-size: 14px; font-weight: 700; cursor: pointer; }
  .maker:hover { color: var(--accent); }
  .unread { color: var(--accent); }
  .work-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(142px, 1fr)); gap: 13px; }
  .work { min-width: 0; display: flex; flex-direction: column; gap: 5px; border: 0; background: transparent; color: var(--text); padding: 0; text-align: left; cursor: pointer; }
  .cover-wrap { position: relative; }
  .new { position: absolute; left: 7px; top: 7px; border-radius: 999px; padding: 2px 7px; background: var(--accent); color: #fff; font-size: 9.5px; font-weight: 750; box-shadow: 0 1px 5px rgb(0 0 0 / 28%); }
  .dot { position: absolute; right: 7px; top: 7px; width: 9px; height: 9px; border-radius: 50%; background: #ff3b30; border: 2px solid #fff; box-shadow: 0 1px 4px rgb(0 0 0 / 30%); }
  .title { min-height: 32px; font-size: 12px; line-height: 1.35; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .date { color: var(--accent); font-size: 10.5px; }
  .empty { margin-top: 50px; padding: 28px; border-radius: 12px; background: var(--panel); color: var(--muted); text-align: center; font-size: 12px; }
  .empty-title { margin-bottom: 5px; color: var(--text); font-size: 14px; font-weight: 650; }
  @media (max-width: 760px) { header { flex-direction: column; } .check { margin-left: 0; } }
</style>
