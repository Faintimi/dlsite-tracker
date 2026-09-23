<script lang="ts">
  let {
    title,
    tasteNames,
    onhide,
    onlearn,
    oncancel,
  }: {
    title: string;
    tasteNames: string[];
    onhide: () => void;
    onlearn: () => void;
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
  <div class="panel" role="dialog" aria-modal="true" aria-label="不感兴趣反馈">
    <div class="title">不感兴趣</div>
    <div class="message">
      将「{title}」从发现页隐藏。
      {#if tasteNames.length > 0}
        它命中了你的口味：{tasteNames.join("、")}。是否同时移除这些口味？
      {:else}
        这次只隐藏作品，不修改你的口味。
      {/if}
    </div>
    <div class="buttons">
      <button class="btn" onclick={oncancel}>取消</button>
      <button class="btn" onclick={onhide}>仅隐藏</button>
      {#if tasteNames.length > 0}
        <button class="btn danger" onclick={onlearn}>隐藏并调整口味</button>
      {/if}
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
    width: min(460px, calc(100vw - 36px));
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 12px;
    box-shadow: 0 18px 50px rgb(0 0 0 / 35%);
    padding: 18px;
    display: flex;
    flex-direction: column;
    gap: 11px;
  }

  .title {
    font-size: 14px;
    font-weight: 650;
  }

  .message {
    font-size: 12.5px;
    color: var(--muted);
    line-height: 1.55;
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
</style>
