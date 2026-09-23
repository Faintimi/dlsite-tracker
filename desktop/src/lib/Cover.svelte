<script lang="ts">
  import { ICONS } from "$lib/ui";

  let {
    src,
    width,
    height,
    rounded = false,
  }: {
    src?: string;
    width?: number | string;
    height?: number | string;
    rounded?: boolean;
  } = $props();

  const style = $derived(
    `${width !== undefined ? `width:${typeof width === "number" ? `${width}px` : width};` : ""}` +
      `${height !== undefined ? `height:${typeof height === "number" ? `${height}px` : height};` : ""}`,
  );
</script>

<div class="cover" class:rounded style={style}>
  {#if src}
    <img src={src} alt="" loading="lazy" decoding="async" />
  {:else}
    <span class="fallback">{@html ICONS.gamepad}</span>
  {/if}
</div>

<style>
  .cover {
    flex: none;
    overflow: hidden;
    background: linear-gradient(135deg, #4a3873 0%, #21304d 100%);
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .cover.rounded {
    border-radius: 9px;
  }

  .cover img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }

  .fallback {
    color: rgb(255 255 255 / 65%);
    display: flex;
  }
</style>
