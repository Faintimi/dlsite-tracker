// 发现系统（P34）：口味画像 → 共现扩展 → 四段候选（冲刺中 / 高期待 / 合口味新作 / 遗珠）。
// 全部在本地计算：仅消费 works.json 中的信号字段（sales_delta / wishlist_count / regist_date），
// 不改动管道数据；调整口味即时重算。
import type { WorkView } from "$lib/api";
import { categoriesOf } from "$lib/ui";
import { makerKeyOf } from "$lib/filter";
import type { TasteLevel } from "$lib/prefs.svelte";

/** 阈值与权重（初版经验值；跑一段时间后可按真实数据调整） */
export const DISCOVERY = {
  /** 「黑马新锐」窗口：发售天数内 */
  newWindowDays: 180,
  /** 「冲刺中」最小销量增量（实际窗口见每张卡片的 ±N 天） */
  sprintMinDelta: 30,
  /** 「高期待」最小心愿单数 */
  hypeWishMin: 300,
  /** 「高期待」未爆线：销量 ≤ 心愿单 × 该比例（0.35 ≈ 实卖三成半以内） */
  hypeRatio: 0.35,
  /** 「合口味的新作」窗口（发售天数内） */
  freshWindowDays: 45,
  /** 「遗珠」最低年龄（发售天数） */
  oldMinDays: 365,
  /** 口味得分阈值（命中一个口味分类得 2 分） */
  tasteMinScore: 2,
  /** 共现扩展阈值：P(B|A) ≥ 该值视为「近似口味」分类 */
  coocProbMin: 0.12,
  /** 权重：命中口味分类 / 近似分类按概率 / 已关注作者 */
  hitScore: 2,
  loveScore: 3,
  lessScore: -3,
  coocScore: 1,
  makerScore: 1.5,
  /** 每区首屏卡片数回退值（窗口测量前；实际＝网格列数 ×2，保证首屏铺满整行） */
  sectionPreview: 12,
} as const;

export interface DiscoveryItem {
  game: WorkView;
  score: number;
  /** 卡片上的理由（如 "±2 天 +2181" / "含「RPG」"） */
  note: string;
  /** 可同时出现的客观信号角标。 */
  badges: DiscoveryBadge[];
}

export type DiscoveryBadge = "sprint" | "hype";

export interface DiscoveryResult {
  sprint: DiscoveryItem[];
  hype: DiscoveryItem[];
  fresh: DiscoveryItem[];
  old: DiscoveryItem[];
}

/** 口味上下文：口味集合 + 共现扩展（分类名 → 条件概率权重）+ 已关注作者 */
export interface TasteContext {
  taste: Set<string>;
  levels: Map<string, TasteLevel>;
  expanded: Map<string, number>;
  followedMakers: Set<string>;
}

/** 发售距今天数（注册日期缺失/非法返回 null） */
export function daysSinceRegist(game: WorkView, now: number = Date.now()): number | null {
  const raw = (game.regist_date ?? "").trim();
  if (raw.length < 10) return null;
  const ts = Date.parse(`${raw.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(ts)) return null;
  return Math.max(0, Math.floor((now - ts) / 86_400_000));
}

/**
 * 口味上下文：
 * - 统计「口味分类 A 出现时，分类 B 也出现」的条件概率 P(B|A)；
 * - P ≥ coocProbMin 且不在口味集内的 B 记为「近似口味」分类（权重取最大概率）。
 */
export function buildTasteContext(
  works: WorkView[],
  profile: Record<string, TasteLevel>,
  followedMakers: Set<string>,
): TasteContext {
  const levels = new Map(Object.entries(profile));
  const taste = new Set(
    Object.entries(profile)
      .filter(([, level]) => level !== "less")
      .map(([name]) => name),
  );
  const expanded = new Map<string, number>();
  if (taste.size > 0) {
    const countA = new Map<string, number>();
    const pairCounts = new Map<string, Map<string, number>>();
    for (const work of works) {
      const cats = categoriesOf(work);
      const set = new Set(cats);
      for (const a of taste) {
        if (!set.has(a)) continue;
        countA.set(a, (countA.get(a) ?? 0) + 1);
        let inner = pairCounts.get(a);
        if (!inner) {
          inner = new Map<string, number>();
          pairCounts.set(a, inner);
        }
        for (const b of cats) {
          if (b === a) continue;
          inner.set(b, (inner.get(b) ?? 0) + 1);
        }
      }
    }
    for (const [a, inner] of pairCounts) {
      const base = countA.get(a) ?? 0;
      if (base === 0) continue;
      for (const [b, n] of inner) {
        if (taste.has(b)) continue;
        const p = n / base;
        if (p >= DISCOVERY.coocProbMin && p > (expanded.get(b) ?? 0)) {
          expanded.set(b, p);
        }
      }
    }
  }
  return { taste, levels, expanded, followedMakers };
}

/** 作品口味得分：命中口味分类 ×2 + 近似分类按概率加权 + 已关注作者加分 */
export function tasteScore(game: WorkView, ctx: TasteContext): number {
  if (ctx.taste.size === 0) return 0;
  let score = 0;
  for (const cat of categoriesOf(game)) {
    const level = ctx.levels.get(cat);
    if (level === "love") {
      score += DISCOVERY.loveScore;
    } else if (level === "like") {
      score += DISCOVERY.hitScore;
    } else if (level === "less") {
      score += DISCOVERY.lessScore;
    } else {
      const weight = ctx.expanded.get(cat);
      if (weight !== undefined) score += DISCOVERY.coocScore * weight;
    }
  }
  if (ctx.followedMakers.has(makerKeyOf(game.maker, game.maker_id))) {
    score += DISCOVERY.makerScore;
  }
  return score;
}

/** 推荐理由：「含 X」/「近味 Y」/「已关注作者」 */
export function tasteNote(game: WorkView, ctx: TasteContext): string {
  const loved: string[] = [];
  const hits: string[] = [];
  const near: string[] = [];
  for (const cat of categoriesOf(game)) {
    if (ctx.levels.get(cat) === "love") loved.push(cat);
    else if (ctx.levels.get(cat) === "like") hits.push(cat);
    else if (ctx.expanded.has(cat)) near.push(cat);
  }
  const parts: string[] = [];
  if (loved.length) parts.push(`很喜欢「${loved.slice(0, 2).join("」「")}」`);
  if (hits.length) parts.push(`含「${hits.slice(0, 3).join("」「")}」`);
  if (near.length) parts.push(`近味「${near.slice(0, 2).join("」「")}」`);
  if (parts.length === 0 && ctx.followedMakers.has(makerKeyOf(game.maker, game.maker_id))) {
    parts.push("已关注作者");
  }
  return parts.join(" · ") || "与你口味相关";
}

/** 生成四段候选（已排序；截断在各区渲染时处理） */
export function buildDiscovery(
  works: WorkView[],
  ctx: TasteContext,
  seen: Set<string> = new Set(),
  dismissed: Set<string> = new Set(),
  now: number = Date.now(),
): DiscoveryResult {
  const sprint: DiscoveryItem[] = [];
  const hype: DiscoveryItem[] = [];
  const fresh: DiscoveryItem[] = [];
  const old: DiscoveryItem[] = [];
  for (const game of works) {
    if (dismissed.has(game.id)) continue;
    const days = daysSinceRegist(game, now);
    if (days === null) continue;

    const delta = typeof game.sales_delta === "number" ? game.sales_delta : null;
    const deltaDays = typeof game.sales_delta_days === "number" ? game.sales_delta_days : null;
    const wish = typeof game.wishlist_count === "number" ? game.wishlist_count : null;
    const sales = game.sales ?? 0;
    const isSprint =
      days <= DISCOVERY.newWindowDays && delta !== null && delta >= DISCOVERY.sprintMinDelta;
    const isHype =
      days <= DISCOVERY.newWindowDays &&
      wish !== null &&
      wish >= DISCOVERY.hypeWishMin &&
      sales <= wish * DISCOVERY.hypeRatio;
    const badges: DiscoveryBadge[] = [
      ...(isSprint ? (["sprint"] as const) : []),
      ...(isHype ? (["hype"] as const) : []),
    ];

    if (isSprint) {
      sprint.push({ game, score: delta, note: `±${deltaDays ?? "?"} 天 +${delta}`, badges });
    }
    if (isHype) {
      hype.push({ game, score: wish, note: `心愿 ${wish} · 销量 ${sales}`, badges });
    }

    if (ctx.taste.size > 0) {
      const score = tasteScore(game, ctx);
      if (score >= DISCOVERY.tasteMinScore) {
        if (days <= DISCOVERY.freshWindowDays) {
          fresh.push({ game, score, note: tasteNote(game, ctx), badges });
        } else if (days >= DISCOVERY.oldMinDays && !seen.has(game.id)) {
          old.push({ game, score, note: tasteNote(game, ctx), badges });
        }
      }
    }
  }
  const rank = (a: DiscoveryItem, b: DiscoveryItem) =>
    b.score - a.score || (b.game.sales ?? 0) - (a.game.sales ?? 0);
  return {
    sprint: sprint.sort(rank),
    hype: hype.sort(rank),
    fresh: fresh.sort(rank),
    old: old.sort(rank),
  };
}

/**
 * 加权随机洗牌（Efraimidis–Spirakis）：以口味分为权，分数越高越容易靠前，
 * 但每一项都有机会出现。用于「遗珠」区分批随机探索（UI 每批截取固定数量）。
 */
export function weightedShuffle(items: DiscoveryItem[]): DiscoveryItem[] {
  return items
    .map((item) => ({ item, key: Math.pow(Math.random(), 1 / Math.max(item.score, 0.5)) }))
    .sort((a, b) => b.key - a.key)
    .map((entry) => entry.item);
}
