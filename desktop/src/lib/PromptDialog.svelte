<script lang="ts">
  // 文本输入对话框（对齐 macOS sheet：标题 + 输入框 + 取消/确定；回车确定、Esc 取消）
  let {
    title,
    label,
    placeholder = "",
    value = $bindable(""),
    confirmLabel = "确定",
    onsubmit,
    oncancel,
  }: {
    title: string;
    label: string;
    placeholder?: string;
    value?: string;
    confirmLabel?: string;
    onsubmit: (value: string) => void;
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
    <input
      class="box"
      aria-label={label}
      {placeholder}
      bind:value
      onkeydown={(event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          onsubmit(value);
        }
      }}
    />
    <div class="buttons">
      <button class="btn" onclick={oncancel}>取消</button>
      <button class="btn primary" onclick={() => onsubmit(value)}>{confirmLabel}</button>
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
    width: 340px;
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

  .box {
    border: 1px solid var(--border);
    background: var(--bg);
    color: var(--text);
    border-radius: 8px;
    padding: 7px 10px;
    font-size: 13px;
    font-family: inherit;
  }

  .buttons {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
  }
</style>
