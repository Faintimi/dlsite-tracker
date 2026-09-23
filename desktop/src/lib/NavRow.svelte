<script lang="ts">
  let {
    icon,
    title,
    count = null,
    selected = false,
    onclick,
    onmenu,
  }: {
    icon: string;
    title: string;
    count?: number | null;
    selected?: boolean;
    onclick: () => void;
    onmenu?: (event: MouseEvent) => void;
  } = $props();
</script>

<button
  class="nav-row"
  class:selected
  {onclick}
  oncontextmenu={(event) => {
    if (!onmenu) return;
    event.preventDefault();
    event.stopPropagation();
    onmenu(event);
  }}
>
  <span class="icon" class:selected>{@html icon}</span>
  <span class="title">{title}</span>
  <span class="spacer"></span>
  {#if typeof count === "number"}
    <span class="count">{count}</span>
  {/if}
</button>

<style>
  .nav-row {
    appearance: none;
    border: 0;
    background: transparent;
    font: inherit;
    color: var(--text);
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 5px 8px;
    border-radius: 8px;
    cursor: default;
    text-align: left;
    transition: background 0.15s ease;
  }

  .nav-row:hover {
    background: color-mix(in srgb, var(--text) 6%, transparent);
  }

  .nav-row.selected {
    background: color-mix(in srgb, var(--accent) 14%, transparent);
  }

  .icon {
    display: inline-flex;
    width: 16px;
    justify-content: center;
    color: var(--muted);
  }

  .icon.selected {
    color: var(--accent);
  }

  .title {
    font-size: 13px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .spacer {
    flex: 1;
  }

  .count {
    font-size: 12px;
    color: var(--muted);
    opacity: 0.8;
  }
</style>
