<script lang="ts">
  // 多选集合菜单（对齐 macOS SetFilterMenu：清除选择 + 勾选列表，触发条显示已选数量）
  import { ICONS } from "./ui";

  let {
    title,
    emptyLabel,
    options,
    selection,
    onchange,
  }: {
    title: string;
    emptyLabel: string;
    options: string[];
    selection: string[];
    onchange: (next: string[]) => void;
  } = $props();

  let open = $state(false);
  let container: HTMLDivElement | null = $state(null);

  function toggle(name: string): void {
    onchange(
      selection.includes(name)
        ? selection.filter((item) => item !== name)
        : [...selection, name],
    );
  }

  function onWindowClick(event: MouseEvent): void {
    if (!open || !container) return;
    if (!container.contains(event.target as Node)) open = false;
  }
</script>

<svelte:window onclick={onWindowClick} />

<div class="setfilter" bind:this={container}>
  <button class="trigger" onclick={() => (open = !open)}>
    {selection.length === 0 ? `${title}：${emptyLabel}` : `${title}：已选 ${selection.length} 项`}
  </button>
  {#if open}
    <div class="pop">
      <button class="header" onclick={() => onchange([])}>清除选择</button>
      <div class="hr"></div>
      <div class="list">
        {#each options as name (name)}
          <button class="opt" onclick={() => toggle(name)}>
            <span class="ck" class:on={selection.includes(name)}>
              {#if selection.includes(name)}{@html ICONS.check}{/if}
            </span>
            <span class="nm">{name}</span>
          </button>
        {/each}
      </div>
    </div>
  {/if}
</div>

<style>
  .setfilter {
    position: relative;
  }

  .trigger {
    appearance: none;
    border: 1px solid var(--border);
    background: var(--panel);
    color: var(--text);
    font: inherit;
    font-size: 12.5px;
    border-radius: 7px;
    padding: 5px 9px;
    width: 100%;
    text-align: left;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    cursor: default;
  }

  .pop {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    right: 0;
    z-index: 200;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 9px;
    box-shadow: 0 10px 26px rgb(0 0 0 / 26%);
    padding: 5px;
    display: flex;
    flex-direction: column;
  }

  .header {
    appearance: none;
    border: 0;
    background: transparent;
    color: var(--text);
    font: inherit;
    font-size: 12.5px;
    text-align: left;
    padding: 5px 7px;
    border-radius: 6px;
    cursor: default;
  }

  .header:hover {
    background: color-mix(in srgb, var(--text) 7%, transparent);
  }

  .hr {
    border-top: 1px solid var(--border);
    margin: 3px 4px;
  }

  .list {
    max-height: 320px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
  }

  .opt {
    appearance: none;
    border: 0;
    background: transparent;
    color: var(--text);
    font: inherit;
    font-size: 12.5px;
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 7px;
    border-radius: 6px;
    cursor: default;
    text-align: left;
  }

  .opt:hover {
    background: color-mix(in srgb, var(--text) 7%, transparent);
  }

  .ck {
    display: inline-flex;
    width: 12px;
    justify-content: center;
    color: var(--accent);
  }
</style>
