// 与 macOS 版一致的展示辅助与图标（颜色 / 文案 / 拆分规则逐项对齐）。
import type { WorkView } from "./api";

/** 数值：千分位；缺失显示「未知」（对齐 macOS formatted / 未知） */
export function fmtNum(n: number | null | undefined): string {
  return typeof n === "number" && Number.isFinite(n) ? n.toLocaleString("ja-JP") : "未知";
}

/** 评分文案：4.5 / 4.75 / 未评分；showCount 时附「（人数）」 */
export function ratingText(game: WorkView, showCount = true): string {
  if (typeof game.rating !== "number" || !Number.isFinite(game.rating)) return "未评分";
  const base = game.rating.toFixed(2).replace(/\.?0+$/, "");
  if (showCount && typeof game.rating_count === "number" && game.rating_count > 0) {
    return `${base}（${game.rating_count}）`;
  }
  return base;
}

/** P21 评分星级分色：≤3.5 蓝、≤4.0 紫、≤4.5 粉、>4.5 亮金 #FFC700；未评分次级色 */
export function ratingColor(rating: number | null | undefined): string {
  if (typeof rating !== "number" || !Number.isFinite(rating)) return "var(--muted)";
  if (rating <= 3.5) return "#0a84ff";
  if (rating <= 4.0) return "#bf5af2";
  if (rating <= 4.5) return "#ff375f";
  return "#ffc700";
}

/** 数据行省字：今年 MM-DD，跨年 YYYY-MM */
export function compactDateText(raw: string | null | undefined): string {
  const date = (raw ?? "").slice(0, 10);
  const parts = date.split("-");
  if (parts.length !== 3) return date || "—";
  const current = String(new Date().getFullYear());
  return parts[0] === current ? `${parts[1]}-${parts[2]}` : `${parts[0]}-${parts[1]}`;
}

/** 热度文案：当前榜位「日X 周Y 月Z」（取 *_current） */
export function heatText(game: WorkView): string | null {
  const parts: string[] = [];
  if (typeof game.rank_day_current === "number") parts.push(`日${game.rank_day_current}`);
  if (typeof game.rank_week_current === "number") parts.push(`周${game.rank_week_current}`);
  if (typeof game.rank_month_current === "number") parts.push(`月${game.rank_month_current}`);
  return parts.length > 0 ? parts.join(" ") : null;
}

/** 分类拆分（对齐 macOS Game.parts：按 | ; ； 、 ， , 拆分） */
export function categoriesOf(game: WorkView): string[] {
  return splitParts(game.category);
}

/** 作品形式（我们的导出为单值，兼容多值分隔） */
export function formsOf(game: WorkView): string[] {
  return splitParts(game.form);
}

export function splitParts(value: string | null | undefined): string[] {
  return (value ?? "")
    .split(/[|;；、，,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

/** 内联 SVG 图标（10–11px，跟随 currentColor） */
export const ICONS = {
  rank: '<svg viewBox="0 0 12 12" width="10" height="10" fill="currentColor"><rect x="1" y="6" width="2.5" height="5" rx="0.6"/><rect x="4.75" y="3" width="2.5" height="8" rx="0.6"/><rect x="8.5" y="1" width="2.5" height="10" rx="0.6"/></svg>',
  bag: '<svg viewBox="0 0 12 12" width="10" height="10" fill="none" stroke="currentColor" stroke-width="1.2"><path d="M2.2 4h7.6l-.7 6.8H2.9L2.2 4z"/><path d="M4.2 4V3.2a1.8 1.8 0 0 1 3.6 0V4"/></svg>',
  star: '<svg viewBox="0 0 12 12" width="10" height="10" fill="currentColor"><path d="M6 1.2l1.5 3 3.3.4-2.4 2.3.6 3.3L6 8.6 3 10.2l.6-3.3L1.2 4.6l3.3-.4z"/></svg>',
  calendar:
    '<svg viewBox="0 0 12 12" width="10" height="10" fill="none" stroke="currentColor" stroke-width="1.2"><rect x="1.6" y="2.4" width="8.8" height="8" rx="1.2"/><path d="M1.6 4.8h8.8M4 1.4v2M8 1.4v2"/></svg>',
  flame:
    '<svg viewBox="0 0 12 12" width="10" height="10" fill="currentColor"><path d="M6 1.2c.3 1.9-2.2 3-2.2 5.6a2.6 2.6 0 0 0 5.2 0C9 4.2 6.3 3 6.6 1.2z"/></svg>',
  mic: '<svg viewBox="0 0 12 12" width="9" height="9" fill="none" stroke="currentColor" stroke-width="1.2"><rect x="4.4" y="1.2" width="3.2" height="5" rx="1.6"/><path d="M2.8 6a3.2 3.2 0 0 0 6.4 0M6 9.2v1.4"/></svg>',
  note: '<svg viewBox="0 0 12 12" width="9" height="9" fill="none" stroke="currentColor" stroke-width="1.1"><path d="M4.8 9.6V4.4l5-1v5.2"/><circle cx="3.4" cy="9.8" r="1.4" fill="currentColor" stroke="none"/><circle cx="8.4" cy="8.6" r="1.4" fill="currentColor" stroke="none"/></svg>',
  film: '<svg viewBox="0 0 12 12" width="9" height="9" fill="none" stroke="currentColor" stroke-width="1.1"><rect x="1.4" y="2.6" width="9.2" height="6.8" rx="1"/><path d="M2.6 2.6v6.8M9.4 2.6v6.8M1.4 6h9.2"/></svg>',
  open: '<svg viewBox="0 0 12 12" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.2"><path d="M5 2H2.4A1.4 1.4 0 0 0 1 3.4v6.2A1.4 1.4 0 0 0 2.4 11h6.2A1.4 1.4 0 0 0 10 9.6V7"/><path d="M7 1h4v4M11 1L5.5 6.5"/></svg>',
  gamepad:
    '<svg viewBox="0 0 24 24" width="30" height="30" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="2.5" y="7" width="19" height="10" rx="4.5"/><path d="M7.5 10v4M5.5 12h4M15.5 11h.01M17.8 13.2h.01" stroke-linecap="round"/></svg>',
  person:
    '<svg viewBox="0 0 12 12" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.2"><circle cx="6" cy="4" r="2.2"/><path d="M1.8 11a4.2 4.2 0 0 1 8.4 0"/></svg>',
  personCircle:
    '<svg viewBox="0 0 14 14" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.2"><circle cx="7" cy="7" r="5.8"/><circle cx="7" cy="5.6" r="1.8"/><path d="M3.6 11.2a3.6 3.6 0 0 1 6.8 0"/></svg>',
  folder:
    '<svg viewBox="0 0 12 12" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.2"><path d="M1.4 3.2A1.2 1.2 0 0 1 2.6 2h2.1l1.1 1.4h3.6a1.2 1.2 0 0 1 1.2 1.2v4.2a1.2 1.2 0 0 1-1.2 1.2H2.6a1.2 1.2 0 0 1-1.2-1.2z"/></svg>',
  gridAll:
    '<svg viewBox="0 0 12 12" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.1"><rect x="1.4" y="1.4" width="4" height="4" rx="1"/><rect x="6.6" y="1.4" width="4" height="4" rx="1"/><rect x="1.4" y="6.6" width="4" height="4" rx="1"/><rect x="6.6" y="6.6" width="4" height="4" rx="1"/></svg>',
  plus: '<svg viewBox="0 0 12 12" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M6 2.2v7.6M2.2 6h7.6"/></svg>',
  chevronDown:
    '<svg viewBox="0 0 12 12" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2.6 4.4L6 7.8l3.4-3.4"/></svg>',
  chevronRight:
    '<svg viewBox="0 0 12 12" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4.4 2.6L7.8 6l-3.4 3.4"/></svg>',
  info: '<svg viewBox="0 0 14 14" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.2"><circle cx="7" cy="7" r="5.6"/><path d="M7 6.2v3.6M7 4.6h.01"/></svg>',
  check:
    '<svg viewBox="0 0 12 12" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M2.2 6.4l2.6 2.6 5-5.4"/></svg>',
  chartBar:
    '<svg viewBox="0 0 12 12" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.1"><path d="M1.6 10.6h8.8"/><rect x="2.4" y="6.4" width="2" height="3.6"/><rect x="5.6" y="3.6" width="2" height="6.4"/><rect x="8.8" y="5" width="2" height="5"/></svg>',
  chartBarFill:
    '<svg viewBox="0 0 12 12" width="12" height="12" fill="currentColor"><rect x="2.2" y="6.2" width="2.2" height="4"/><rect x="5.4" y="3.4" width="2.2" height="6.8"/><rect x="8.6" y="4.8" width="2.2" height="5.4"/></svg>',
  filterCircle:
    '<svg viewBox="0 0 14 14" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.3"><circle cx="7" cy="7" r="5.6"/><path d="M4.2 5.4h5.6M4.2 7h5.6M4.2 8.6h3.4"/></svg>',
  external:
    '<svg viewBox="0 0 12 12" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.2"><rect x="1.6" y="4.2" width="6.2" height="6.2" rx="1.2"/><path d="M7 1.6h3.4V5M10.4 1.6L6 6"/></svg>',
  tray: '<svg viewBox="0 0 14 14" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.2"><path d="M7 2v5.4M4.6 5.4L7 7.8l2.4-2.4"/><path d="M1.8 8.6v1.6a1.4 1.4 0 0 0 1.4 1.4h7.6a1.4 1.4 0 0 0 1.4-1.4V8.6"/></svg>',
  refresh:
    '<svg viewBox="0 0 14 14" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.3"><path d="M11.6 7a4.6 4.6 0 1 1-1.4-3.3"/><path d="M11.9 2.2v3h-3"/></svg>',
  warn: '<svg viewBox="0 0 14 14" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.2"><path d="M7 1.8l5.6 10H1.4z"/><path d="M7 5.6v3M7 10.2h.01"/></svg>',
  hourglass:
    '<svg viewBox="0 0 14 14" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.2"><path d="M3.4 1.8h7.2M3.4 12.2h7.2"/><path d="M4.4 1.8c0 2.6 2.6 3.4 2.6 5.2 0-1.8 2.6-2.6 2.6-5.2M4.4 12.2c0-2.6 2.6-3.4 2.6-5.2 0 1.8 2.6 2.6 2.6 5.2"/></svg>',
  slider:
    '<svg viewBox="0 0 14 14" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.2"><path d="M2 4.4h6M10.4 4.4h1.6M2 9.6h1.6M6 9.6h6"/><circle cx="9" cy="4.4" r="1.5"/><circle cx="4.6" cy="9.6" r="1.5"/></svg>',
  sidebar:
    '<svg viewBox="0 0 16 14" width="18" height="16" fill="none" stroke="currentColor" stroke-width="1.2"><rect x="1.4" y="1.8" width="13.2" height="10.4" rx="1.8"/><path d="M6.2 1.8v10.4"/></svg>',
  stackSlash:
    '<svg viewBox="0 0 24 24" width="44" height="44" fill="none" stroke="currentColor" stroke-width="1.3"><path d="M12 3l9 5-9 5-9-5 9-5z"/><path d="M3 13l9 5 9-5"/></svg>',
  modeLarge:
    '<svg viewBox="0 0 14 14" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.2"><rect x="1.4" y="3" width="11.2" height="8" rx="1.4"/><path d="M5 5.4h5.6M5 7h5.6M5 8.6h5.6M3.4 5.4h.01M3.4 7h.01M3.4 8.6h.01"/></svg>',
  modeTwo:
    '<svg viewBox="0 0 14 14" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.2"><rect x="2.6" y="1.6" width="8.8" height="4.6" rx="1"/><rect x="2.6" y="7.8" width="8.8" height="4.6" rx="1"/></svg>',
  modeCompact:
    '<svg viewBox="0 0 14 14" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.2"><path d="M5 4h6.6M5 7h6.6M5 10h6.6M2.6 4h.4M2.6 7h.4M2.6 10h.4"/></svg>',
  modeGrid:
    '<svg viewBox="0 0 14 14" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.2"><rect x="1.6" y="1.6" width="4.8" height="4.8" rx="1"/><rect x="7.6" y="1.6" width="4.8" height="4.8" rx="1"/><rect x="1.6" y="7.6" width="4.8" height="4.8" rx="1"/><rect x="7.6" y="7.6" width="4.8" height="4.8" rx="1"/></svg>',
  modeWall:
    '<svg viewBox="0 0 14 14" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.2"><rect x="1.2" y="2.2" width="3.4" height="3.4" rx="0.8"/><rect x="5.3" y="2.2" width="3.4" height="3.4" rx="0.8"/><rect x="9.4" y="2.2" width="3.4" height="3.4" rx="0.8"/><rect x="1.2" y="6.4" width="3.4" height="3.4" rx="0.8"/><rect x="5.3" y="6.4" width="3.4" height="3.4" rx="0.8"/><rect x="9.4" y="6.4" width="3.4" height="3.4" rx="0.8"/></svg>',
} as const;

/** 评分缓存（对齐 macOS：按 *_current 名次）；tie 时优先销量 */
export function compareRank(a: WorkView, b: WorkView, key: "rank_day_current" | "rank_week_current" | "rank_month_current" | "rank_trend_current"): number {
  const left = (a[key] as number | null) ?? Number.MAX_SAFE_INTEGER;
  const right = (b[key] as number | null) ?? Number.MAX_SAFE_INTEGER;
  if (left !== right) return left - right;
  return (b.sales ?? -1) - (a.sales ?? -1);
}
