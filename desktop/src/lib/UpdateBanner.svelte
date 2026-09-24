<script lang="ts">
  // 顶部状态横幅：普通进度单行显示，失败提醒允许换行以完整呈现原因。
  let { icon, text, warning = false }: { icon: string; text: string; warning?: boolean } = $props();
</script>

<div class:warning class="banner">
  <span class="icon">{@html icon}</span>
  <span class="text">{text}</span>
  <span class="spacer"></span>
</div>

<style>
  .banner {
    flex: none;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 22px;
    font-size: 12px;
    color: var(--muted);
    background: color-mix(in srgb, var(--accent) 8%, transparent);
  }

  .icon {
    display: inline-flex;
    color: var(--muted);
  }

  .text {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .spacer {
    flex: 1;
  }

  .banner.warning {
    color: var(--text);
    background: color-mix(in srgb, var(--accent) 12%, var(--panel));
  }

  .banner.warning .icon {
    color: var(--accent);
  }

  .banner.warning .text {
    white-space: normal;
  }
</style>
