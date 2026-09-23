<script lang="ts">
  interface MenuItem {
    label: string;
    action: () => void;
    danger?: boolean;
  }

  let {
    x,
    y,
    items,
    onclose,
  }: {
    x: number;
    y: number;
    items: MenuItem[];
    onclose: () => void;
  } = $props();

  const WIDTH = 250;

  const left = $derived(Math.min(Math.max(8, x), window.innerWidth - WIDTH - 8));
  const top = $derived(
    Math.min(
      Math.max(8, y),
      Math.max(8, window.innerHeight - Math.min(72 + items.length * 30, 420) - 8),
    ),
  );

  function pick(action: () => void) {
    onclose();
    action();
  }

  // 点击菜单以外区域关闭（菜单内部的点击由各菜单项自行处理）
  function onWindowClick(event: MouseEvent) {
    const target = event.target as HTMLElement | null;
    if (target && target.closest(".menu")) return;
    onclose();
  }

  function onKeydown(event: KeyboardEvent) {
    if (event.key === "Escape") onclose();
  }
</script>

<svelte:window onclick={onWindowClick} oncontextmenu={onclose} onkeydown={onKeydown} />

<div class="menu" style="left: {left}px; top: {top}px; width: {WIDTH}px">
  {#each items as item, index (index)}
    <button class="item" class:danger={item.danger} onclick={() => pick(item.action)}>
      {item.label}
    </button>
  {/each}
</div>

<style>
  .menu {
    position: fixed;
    z-index: 200;
    padding: 4px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 8px;
    box-shadow: 0 10px 30px rgb(0 0 0 / 25%);
    display: flex;
    flex-direction: column;
  }

  .item {
    appearance: none;
    border: 0;
    background: transparent;
    color: var(--text);
    font: inherit;
    font-size: 13px;
    text-align: left;
    padding: 7px 10px;
    border-radius: 6px;
    cursor: pointer;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .item:hover {
    background: var(--bg);
  }

  .item.danger {
    color: #d64545;
  }
</style>
