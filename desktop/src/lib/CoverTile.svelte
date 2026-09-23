<script lang="ts">
  import type { WorkView } from "$lib/api";
  import { fmtNum } from "$lib/ui";
  import Cover from "./Cover.svelte";
  import GameBadges from "./GameBadges.svelte";
  import HeartButton from "./HeartButton.svelte";

  let {
    game,
    showBadges = true,
    onbadge,
  }: {
    game: WorkView;
    showBadges?: boolean;
    onbadge?: (key: "voice" | "music" | "video") => void;
  } = $props();
</script>

<div class="tile">
  <Cover src={game._cover} height={196} />
  <div class="overlay">
    <div class="spacer"></div>
    <div class="title">{game.title}</div>
    <div class="row">
      {#if showBadges}
        <GameBadges {game} showText={false} ontap={onbadge} />
      {/if}
      <span class="spacer"></span>
      <span class="price">{typeof game.price === "number" ? `¥${fmtNum(game.price)}` : ""}</span>
    </div>
  </div>
  <div class="heart"><HeartButton id={game.id} /></div>
</div>

<style>
  .tile {
    position: relative;
    height: 196px;
    border-radius: 10px;
    overflow: hidden;
    cursor: default;
    background: linear-gradient(135deg, #4a3873 0%, #21304d 100%);
  }

  .tile :global(.cover) {
    width: 100%;
    height: 100%;
  }

  /* 悬停覆盖层：渐变 + 标题 + 标志/价格（对齐 CoverWallTile） */
  .overlay {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 8px;
    background: linear-gradient(to bottom, rgb(0 0 0 / 5%), rgb(0 0 0 / 78%));
    opacity: 0;
    transition: opacity 0.12s ease;
    pointer-events: none;
  }

  .tile:hover .overlay {
    opacity: 1;
    pointer-events: auto;
  }

  .spacer {
    flex: 1;
  }

  .title {
    color: #fff;
    font-size: 12px;
    font-weight: 600;
    line-height: 15px;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .row {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .price {
    color: #fff;
    font-size: 11px;
    font-weight: 600;
  }

  .heart {
    position: absolute;
    top: 6px;
    right: 6px;
    width: 26px;
    height: 26px;
    border-radius: 50%;
    background: rgb(0 0 0 / 35%);
    display: flex;
    align-items: center;
    justify-content: center;
    opacity: 0;
    transition: opacity 0.12s ease;
  }

  .tile:hover .heart,
  .heart:has(:global(.heart.on)) {
    opacity: 1;
  }

  .heart :global(.heart) {
    color: #fff;
  }

  .heart :global(.heart.on) {
    color: #ff5d7d;
  }
</style>
