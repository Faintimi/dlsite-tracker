<script lang="ts">
  import { isRunning, phaseLabel, type ImportProgress, type UpdateState } from "$lib/pipeline";

  let {
    state,
    importProgress,
    ondismiss,
  }: {
    state: UpdateState;
    importProgress: ImportProgress | null;
    ondismiss: () => void;
  } = $props();

  const active = $derived(isRunning(state));
  const processed = $derived(
    importProgress
      ? (importProgress.enriched ?? 0) +
          (importProgress.excluded ?? 0) +
          (importProgress.skipped ?? 0) +
          (importProgress.failed ?? 0)
      : 0,
  );
</script>

<div
  class="banner"
  class:running={active}
  class:ok={state.phase === "done"}
  class:fail={state.phase === "failed"}
  class:warn={state.phase === "busy"}
>
  {#if active}<span class="dot"></span>{/if}
  <span class="text">
    {phaseLabel(state)}{state.detail ? ` — ${state.detail}` : ""}
  </span>
  {#if active && state.phase === "import" && importProgress?.running}
    <span class="extra">
      已处理 {processed}/{importProgress.total ?? "?"} · 入库 {importProgress.enriched ?? 0}
    </span>
  {/if}
  {#if !active}
    <button class="close" title="关闭" onclick={ondismiss}>×</button>
  {/if}
</div>

<style>
  .banner {
    flex: none;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 7px 16px;
    font-size: 12px;
    border-bottom: 1px solid var(--border);
    background: var(--panel);
    color: var(--text);
  }

  .banner.running {
    background: color-mix(in srgb, var(--accent) 12%, var(--panel));
  }

  .banner.ok {
    background: color-mix(in srgb, #2f9e44 14%, var(--panel));
  }

  .banner.fail {
    background: color-mix(in srgb, #d64545 14%, var(--panel));
  }

  .banner.warn {
    background: color-mix(in srgb, #d97706 14%, var(--panel));
  }

  .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--accent);
    animation: pulse 1.2s ease-in-out infinite;
  }

  @keyframes pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.25;
    }
  }

  .text {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .extra {
    color: var(--muted);
    white-space: nowrap;
  }

  .close {
    margin-left: auto;
    appearance: none;
    border: 0;
    background: transparent;
    color: var(--muted);
    font-size: 14px;
    line-height: 1;
    padding: 2px 6px;
    border-radius: 4px;
    cursor: pointer;
  }

  .close:hover {
    background: rgb(128 128 128 / 20%);
    color: var(--text);
  }
</style>
