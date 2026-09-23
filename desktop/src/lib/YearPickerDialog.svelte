<script lang="ts">
  // 年份选择对话框（对齐 macOS yearPickerSheet / deeperPickerSheet：说明 + 年份下拉 + 取消/确定）
  let {
    title,
    message = "",
    options,
    value = $bindable(),
    confirmLabel = "确定",
    confirmDisabled = false,
    onsubmit,
    oncancel,
  }: {
    title: string;
    message?: string;
    options: { value: number; label: string }[];
    value: number;
    confirmLabel?: string;
    confirmDisabled?: boolean;
    onsubmit: (value: number) => void;
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
    <select class="box" bind:value aria-label={title}>
      {#each options as option (option.value)}
        <option value={option.value}>{option.label}</option>
      {/each}
    </select>
    <div class="buttons">
      <button class="btn" onclick={oncancel}>取消</button>
      <button class="btn primary" disabled={confirmDisabled} onclick={() => onsubmit(value)}>
        {confirmLabel}
      </button>
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
    width: 400px;
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

  .box {
    border: 1px solid var(--border);
    background: var(--bg);
    color: var(--text);
    border-radius: 8px;
    padding: 7px 10px;
    font-size: 13px;
    font-family: inherit;
    width: 240px;
  }

  .buttons {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
  }
</style>
