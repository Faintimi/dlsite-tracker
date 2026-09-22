// 筛选与排序逻辑（纯函数，便于测试与复用）
import type { WorkView } from "./api";

export interface FilterState {
  /** 关键词：匹配标题 / 作者 / 分类 / 编号 */
  keyword: string;
  /** 分类交集：作品分类需同时包含全部选中项 */
  genres: string[];
  /** 年份范围（0 = 不限） */
  yearFrom: number;
  yearTo: number;
  /** 销量下限（undefined = 不限） */
  salesMin: number | undefined;
  /** 价格上限（undefined = 不限） */
  priceMax: number | undefined;
  /** 评分下限（0 = 不限） */
  ratingMin: number;
}

export type SortKey =
  | "sales"
  | "rating"
  | "regist_desc"
  | "regist_asc"
  | "price_asc"
  | "price_desc"
  | "title";

export const SORT_OPTIONS: { key: SortKey; label: string }[] = [
  { key: "sales", label: "销量 ↓" },
  { key: "rating", label: "评分 ↓" },
  { key: "regist_desc", label: "发售日 ↓" },
  { key: "regist_asc", label: "发售日 ↑" },
  { key: "price_asc", label: "价格 ↑" },
  { key: "price_desc", label: "价格 ↓" },
  { key: "title", label: "名称" },
];

export function emptyFilter(): FilterState {
  return {
    keyword: "",
    genres: [],
    yearFrom: 0,
    yearTo: 0,
    salesMin: undefined,
    priceMax: undefined,
    ratingMin: 0,
  };
}

/** 生效中的筛选条件数量（用于工具条角标） */
export function activeFilterCount(f: FilterState): number {
  let count = 0;
  if (f.keyword.trim()) count += 1;
  count += f.genres.length;
  if (f.yearFrom > 0 || f.yearTo > 0) count += 1;
  if (typeof f.salesMin === "number" && !Number.isNaN(f.salesMin)) count += 1;
  if (typeof f.priceMax === "number" && !Number.isNaN(f.priceMax)) count += 1;
  if (f.ratingMin > 0) count += 1;
  return count;
}

/** 从 regist_date（"YYYY-MM-DD HH:MM:SS"）解析发售年份 */
export function yearOf(work: WorkView): number | null {
  const match = /^(\d{4})/.exec(work.regist_date ?? "");
  return match ? Number(match[1]) : null;
}

function compare(a: WorkView, b: WorkView, sort: SortKey): number {
  switch (sort) {
    case "sales":
      return (b.sales ?? -1) - (a.sales ?? -1);
    case "rating":
      return (b.rating ?? -1) - (a.rating ?? -1);
    case "price_asc":
      return (a.price ?? Number.POSITIVE_INFINITY) - (b.price ?? Number.POSITIVE_INFINITY);
    case "price_desc":
      return (b.price ?? -1) - (a.price ?? -1);
    case "regist_desc":
      return (b.regist_date ?? "").localeCompare(a.regist_date ?? "");
    case "regist_asc":
      return (a.regist_date ?? "").localeCompare(b.regist_date ?? "");
    case "title":
      return a.title.localeCompare(b.title, "ja");
  }
}

/** 应用筛选并按指定键排序；返回新数组（不修改输入）。 */
export function applyFilters(works: WorkView[], f: FilterState, sort: SortKey): WorkView[] {
  const keyword = f.keyword.trim().toLowerCase();
  const genres = f.genres;
  const out = works.filter((work) => {
    if (keyword) {
      const haystack = `${work.title} ${work.maker} ${work.category} ${work.id}`.toLowerCase();
      if (!haystack.includes(keyword)) return false;
    }
    if (
      typeof f.salesMin === "number" &&
      !Number.isNaN(f.salesMin) &&
      (work.sales ?? 0) < f.salesMin
    ) {
      return false;
    }
    if (
      typeof f.priceMax === "number" &&
      !Number.isNaN(f.priceMax) &&
      (work.price ?? Number.POSITIVE_INFINITY) > f.priceMax
    ) {
      return false;
    }
    if (f.ratingMin > 0 && (work.rating ?? 0) < f.ratingMin) return false;
    if (f.yearFrom > 0 || f.yearTo > 0) {
      const year = yearOf(work);
      if (year === null) return false;
      if (f.yearFrom > 0 && year < f.yearFrom) return false;
      if (f.yearTo > 0 && year > f.yearTo) return false;
    }
    if (genres.length > 0) {
      const categories = (work.category ?? "").split(" | ");
      for (const genre of genres) {
        if (!categories.includes(genre)) return false;
      }
    }
    return true;
  });
  out.sort((a, b) => compare(a, b, sort));
  return out;
}
