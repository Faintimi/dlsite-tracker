<script lang="ts">
  // 区间输入（对齐 macOS RangeFields：标题 + 最低 至 最高 + 单位）
  let {
    title,
    unit,
    lower = $bindable(),
    upper = $bindable(),
  }: {
    title: string;
    unit: string;
    lower: string;
    upper: string;
  } = $props();
</script>

<div class="range">
  <div class="label">{title}</div>
  <div class="row">
    <input class="box" placeholder="最低" bind:value={lower} />
    <span class="to">至</span>
    <input class="box" placeholder="最高" bind:value={upper} />
    <span class="unit">{unit}</span>
  </div>
</div>

<style>
  .range {
    display: flex;
    flex-direction: column;
    gap: 7px;
  }

  .label {
    font-size: 12px;
    color: var(--muted);
  }

  .row {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .box {
    flex: 1;
    min-width: 0;
    border: 1px solid var(--border);
    background: var(--panel);
    color: var(--text);
    border-radius: 7px;
    padding: 5px 8px;
    font-size: 12.5px;
    font-family: inherit;
  }

  .to {
    color: var(--muted);
    font-size: 12px;
  }

  .unit {
    font-size: 12px;
    color: var(--muted);
    flex: none;
  }
</style>
