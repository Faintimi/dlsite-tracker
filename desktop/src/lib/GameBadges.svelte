<script lang="ts">
  import type { WorkView } from "$lib/api";
  import { ICONS } from "$lib/ui";

  let {
    game,
    showText = true,
    ontap,
  }: {
    game: WorkView;
    showText?: boolean;
    ontap?: (key: "voice" | "music" | "video") => void;
  } = $props();

  const items = $derived.by(() => {
    const list: { key: "voice" | "music" | "video"; text: string; tint: string; icon: string; help: string }[] = [];
    if (game.voice) list.push({ key: "voice", text: "配音", tint: "#d42e70", icon: ICONS.mic, help: "有配音" });
    if (game.music) list.push({ key: "music", text: "音乐", tint: "#734ad9", icon: ICONS.note, help: "有音乐" });
    if (game.video) list.push({ key: "video", text: "动画", tint: "#05948f", icon: ICONS.film, help: "有动画" });
    return list;
  });
</script>

{#if items.length > 0}
  <div class="badges">
    {#each items as item (item.key)}
      {#if ontap}
        <button class="badge" style:background={item.tint} title={item.help} onclick={() => ontap(item.key)}>
          {@html item.icon}{#if showText}<span class="t">{item.text}</span>{/if}
        </button>
      {:else}
        <span class="badge" style:background={item.tint} title={item.help}>
          {@html item.icon}{#if showText}<span class="t">{item.text}</span>{/if}
        </span>
      {/if}
    {/each}
  </div>
{/if}

<style>
  .badges {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }

  .badge {
    appearance: none;
    border: 0;
    font: inherit;
    display: inline-flex;
    align-items: center;
    gap: 3px;
    padding: 3px 6px;
    border-radius: 999px;
    color: #fff;
    line-height: 1;
    cursor: default;
  }

  button.badge {
    cursor: pointer;
  }

  button.badge:hover {
    filter: brightness(1.12);
  }

  .t {
    font-size: 10px;
    font-weight: 600;
  }
</style>
