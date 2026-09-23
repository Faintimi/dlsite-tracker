// 筛选与排序逻辑（纯函数；逐项对齐 macOS 版 ContentView.visibleGames 与 SortOrder）。
import type { WorkView } from "./api";
import { categoriesOf, compareRank, formsOf } from "./ui";

/** 视图范围（对齐 macOS ViewFilter）：全部 / 某收藏夹 / 某制作者 */
export type ViewFilter =
  | { kind: "all" }
  | { kind: "collection"; id: string }
  | { kind: "maker"; key: string; name: string; makerId: string };

export function viewFilterTitle(viewFilter: ViewFilter, collectionName: string): string {
  switch (viewFilter.kind) {
    case "all":
      return "";
    case "collection":
      return `收藏夹「${collectionName}」`;
    case "maker":
      return `制作者「${viewFilter.name}」`;
  }
}

export interface FilterState {
  /** 游戏名或制作者（大小写不敏感包含匹配） */
  keyword: string;
  /** 评分区间（文本输入，允许空；"4,5" 视为 4.5） */
  ratingLow: string;
  ratingHigh: string;
  /** 包含未评分作品（评分缺失时是否纳入区间匹配） */
  includeUnrated: boolean;
  /** 销量区间 */
  salesLow: string;
  salesHigh: string;
  /** 价格区间（日元） */
  priceLow: string;
  priceHigh: string;
  /** 包含分类（取交集：同时满足所选全部分类） */
  genres: string[];
  /** 排除分类（命中任一项即排除） */
  excludeGenres: string[];
  /** 作品形式（"" = 全部） */
  form: string;
  /** 发售年份（可多选；空 = 全部） */
  selectedYears: number[];
  /** 内容标志（可多选，同时满足） */
  flags: { voice: boolean; music: boolean; video: boolean };
  /** 分类人气态：非空时按该分类官方人气名次浏览（genre id） */
  genreFocus: string;
}

export type SortKey =
  | "sales"
  | "rating"
  | "priceLow"
  | "priceHigh"
  | "registDate"
  | "rankDay"
  | "rankWeek"
  | "rankMonth"
  | "trend"
  | "title";

// 排序选项（文案逐字对齐 macOS SortOrder）
export const SORT_OPTIONS: { key: SortKey; label: string }[] = [
  { key: "sales", label: "销量从高到低" },
  { key: "rating", label: "评分从高到低" },
  { key: "priceLow", label: "价格从低到高" },
  { key: "priceHigh", label: "价格从高到低" },
  { key: "registDate", label: "发售时间（新→旧）" },
  { key: "rankDay", label: "日热度从高到低" },
  { key: "rankWeek", label: "周热度从高到低" },
  { key: "rankMonth", label: "月热度从高到低" },
  { key: "trend", label: "人气（官方）" },
  { key: "title", label: "名称" },
];

export function emptyFilter(): FilterState {
  return {
    keyword: "",
    ratingLow: "",
    ratingHigh: "",
    includeUnrated: false,
    salesLow: "",
    salesHigh: "",
    priceLow: "",
    priceHigh: "",
    genres: [],
    excludeGenres: [],
    form: "",
    selectedYears: [],
    flags: { voice: false, music: false, video: false },
    genreFocus: "",
  };
}

/** 生效中的筛选条件数量（供侧栏「筛选条件」标题摘要）。 */
export function activeFilterCount(f: FilterState): number {
  let count = 0;
  if (f.keyword.trim()) count += 1;
  count += f.genres.length + f.excludeGenres.length;
  if (f.ratingLow.trim() || f.ratingHigh.trim()) count += 1;
  if (f.includeUnrated) count += 1;
  if (f.salesLow.trim() || f.salesHigh.trim()) count += 1;
  if (f.priceLow.trim() || f.priceHigh.trim()) count += 1;
  if (f.form) count += 1;
  count += f.selectedYears.length;
  if (f.flags.voice) count += 1;
  if (f.flags.music) count += 1;
  if (f.flags.video) count += 1;
  if (f.genreFocus) count += 1;
  return count;
}

/** 作者键（与 macOS 版一致：优先 maker_id，否则 `n:名称`）。 */
export function makerKeyOf(maker: string, makerId: string | null | undefined): string {  const id = makerId ?? "";
  return id ? id : `n:${maker}`;
}

/** 从 regist_date（"YYYY-MM-DD HH:MM:SS"）解析发售年份 */
export function yearOf(work: WorkView): number | null {
  const match = /^(\d{4})/.exec(work.regist_date ?? "");
  return match ? Number(match[1]) : null;
}

/** 文本转数字（对齐 macOS bound()：去空白、逗号视为小数点；非法返回 null） */
function bound(text: string): number | null {
  const cleaned = text.trim().replace(/,/g, ".");
  if (!cleaned) return null;
  const value = Number(cleaned);
  return Number.isFinite(value) ? value : null;
}

/**
 * 区间匹配（逐分支对齐 macOS matches()）：
 * 上下界都可解析 → 必须有值且落在闭区间内（缺失值看 includeMissing）；
 * 只有单边 → 缺值时直接放行（includeMissing 仍生效），仅对有值者比较。
 */
function matches(
  value: number | null,
  low: string,
  high: string,
  includeMissing = false,
): boolean {
  const lower = bound(low);
  const upper = bound(high);
  if (lower === null || upper === null) {
    if (!low.trim() && !high.trim()) return true;
    if (value === null) return includeMissing;
    if (lower !== null && value < lower) return false;
    if (upper !== null && value > upper) return false;
    return true;
  }
  if (value === null) return includeMissing;
  return value >= lower && value <= upper;
}

function compare(a: WorkView, b: WorkView, sort: SortKey): number {
  switch (sort) {
    case "sales":
      return (b.sales ?? -1) - (a.sales ?? -1);
    case "rating":
      return (b.rating ?? -1) - (a.rating ?? -1);
    case "priceLow":
      return (a.price ?? Number.POSITIVE_INFINITY) - (b.price ?? Number.POSITIVE_INFINITY);
    case "priceHigh":
      return (b.price ?? -1) - (a.price ?? -1);
    case "registDate":
      return (b.regist_date ?? "").localeCompare(a.regist_date ?? "");
    case "rankDay":
      return compareRank(a, b, "rank_day_current");
    case "rankWeek":
      return compareRank(a, b, "rank_week_current");
    case "rankMonth":
      return compareRank(a, b, "rank_month_current");
    case "trend":
      return compareRank(a, b, "rank_trend_current");
    case "title":
      return a.title.localeCompare(b.title, "ja");
  }
}

function matchesViewFilter(work: WorkView, viewFilter: ViewFilter, favoriteIds: Set<string>): boolean {
  switch (viewFilter.kind) {
    case "all":
      return true;
    case "collection":
      return favoriteIds.has(work.id);
    case "maker":
      return makerKeyOf(work.maker, work.maker_id) === viewFilter.key;
  }
}

/** 应用筛选并按指定键排序；返回新数组（不修改输入）。 */
export function applyFilters(
  works: WorkView[],
  f: FilterState,
  sort: SortKey,
  ctx: { viewFilter: ViewFilter; favoriteIds: Set<string> },
): WorkView[] {
  const keyword = f.keyword.trim().toLowerCase();
  const years = new Set(f.selectedYears);
  const out = works.filter((work) => {
    if (f.genreFocus && !(typeof work.genre_pos?.[f.genreFocus] === "number")) return false;
    if (keyword) {
      const title = work.title.toLowerCase();
      const maker = (work.maker ?? "").toLowerCase();
      if (!title.includes(keyword) && !maker.includes(keyword)) return false;
    }
    if (f.genres.length > 0) {
      const categories = categoriesOf(work);
      for (const genre of f.genres) {
        if (!categories.includes(genre)) return false;
      }
    }
    if (f.excludeGenres.length > 0) {
      const categories = categoriesOf(work);
      for (const genre of f.excludeGenres) {
        if (categories.includes(genre)) return false;
      }
    }
    if (years.size > 0) {
      const year = yearOf(work);
      if (year === null || !years.has(year)) return false;
    }
    if (f.form && !formsOf(work).includes(f.form)) return false;
    if (f.flags.voice && !work.voice) return false;
    if (f.flags.music && !work.music) return false;
    if (f.flags.video && !work.video) return false;
    if (!matchesViewFilter(work, ctx.viewFilter, ctx.favoriteIds)) return false;
    if (!matches(work.rating, f.ratingLow, f.ratingHigh, f.includeUnrated)) return false;
    if (!matches(work.sales, f.salesLow, f.salesHigh)) return false;
    if (!matches(work.price, f.priceLow, f.priceHigh)) return false;
    return true;
  });
  if (f.genreFocus) {
    // P19.1 人气态：按该分类官方人气名次升序（未上榜的排后，同档优先销量）
    out.sort((a, b) => {
      const left = (a.genre_pos?.[f.genreFocus] as number | undefined) ?? Number.MAX_SAFE_INTEGER;
      const right = (b.genre_pos?.[f.genreFocus] as number | undefined) ?? Number.MAX_SAFE_INTEGER;
      if (left !== right) return left - right;
      return (b.sales ?? -1) - (a.sales ?? -1);
    });
    return out;
  }
  out.sort((a, b) => compare(a, b, sort));
  return out;
}
