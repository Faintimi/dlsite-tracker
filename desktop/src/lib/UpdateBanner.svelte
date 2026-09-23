<script lang="ts">
  // 顶部状态横幅（对齐 macOS library.banner：单行、图标 + 说明文字、强调色淡底）
  let { icon, text }: { icon: string; text: string } = $props();
</script>

<div class="banner">
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
</style>
