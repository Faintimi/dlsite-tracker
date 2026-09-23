<script lang="ts">
  // 通用确认框（对齐 macOS alert：标题 + 说明 + 取消/确认，危险操作红色）
  let {
    title,
    message = "",
    confirmLabel,
    cancelLabel = "取消",
    danger = false,
    busy = false,
    onconfirm,
    oncancel,
  }: {
    title: string;
    message?: string;
    confirmLabel: string;
    cancelLabel?: string;
    danger?: boolean;
    busy?: boolean;
    onconfirm: () => void;
    oncancel: () => void;
  } = $props();

  function onKeydown(event: KeyboardEvent): void {
    if (event.key === "Escape") {
      event.preventDefault();
      oncancel();
    }
  }
</script>

<svelte:window onkeydown={onKeydown} />

<div class="overlay">
  <div class="panel" role="dialog" aria-modal="true">
    <div class="title">{title}</div>
    {#if message}
      <div class="message">{message}</div>
    {/if}
    <div class="buttons">
      <button class="btn" onclick={oncancel} disabled={busy}>{cancelLabel}</button>
      <button class="btn" class:danger onclick={onconfirm} disabled={busy}>{confirmLabel}</button>
    </div>
  </div>
</div>

<style>
  .overlay {
    position: fixed;
    inset: 0;
    z-index: 300;
    background: rgb(0 0 0 / 28%);
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .panel {
    min-width: 300px;
    max-width: 420px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 12px;
    box-shadow: 0 18px 50px rgb(0 0 0 / 35%);
    padding: 18px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .title {
    font-size: 14px;
    font-weight: 600;
  }

  .message {
    font-size: 12.5px;
    color: var(--muted);
    line-height: 18px;
  }

  .buttons {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    margin-top: 4px;
  }

  .danger {
    background: #d64545;
    border-color: #d64545;
    color: #fff;
    font-weight: 600;
  }

  .danger:hover {
    filter: brightness(1.06);
  }
</style>
