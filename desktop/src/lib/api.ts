// 与 Rust 后端命令交互的薄封装：文件选择 / 读取 works.json / 封面 URL 组装。
// 数据契约见仓库根 `docs/integration.md`（schema v2）。
import { convertFileSrc, invoke } from "@tauri-apps/api/core";

/** works.json（schema v2）中的单条作品记录（仅声明界面使用的字段，其余字段透传保留）。 */
export interface Work {
  id: string;
  title: string;
  maker: string;
  category: string;
  form: string;
  sales: number | null;
  rating: number | null;
  price: number | null;
  image_path: string;
  url: string;
  official_price: number | null;
  discount_rate: number | null;
  rating_count: number | null;
  rank_day: number | null;
  rank_week: number | null;
  rank_month: number | null;
  rank_day_current: number | null;
  rank_week_current: number | null;
  rank_month_current: number | null;
  rank_trend_current: number | null;
  work_type: string;
  regist_date: string;
  sales_seen_at: string | null;
  maker_id: string | null;
  voice: boolean;
  music: boolean;
  video: boolean;
  genre_pos: Record<string, number>;
  [key: string]: unknown;
}

/** 界面用的作品视图对象：附上组装好的本地封面 URL。 */
export interface WorkView extends Work {
  _cover: string;
}

export interface GenreEntry {
  id: string;
  name: string;
  count: number;
  seen_at?: string;
  depth?: number;
  watched?: boolean;
}

export interface WorksFile {
  schema_version: number;
  generated_at: string;
  count: number;
  genres?: GenreEntry[];
  genre_catalog?: unknown;
  trend?: unknown;
  works: Work[];
}

export interface LoadedData {
  /** works.json 的绝对路径 */
  path: string;
  file: WorksFile;
  works: WorkView[];
}

/** 最近使用的数据文件路径（未设置则为 null）。 */
export function getDataPath(): Promise<string | null> {
  return invoke<string | null>("get_data_path");
}

/** 打开文件选择框；返回选中的 works.json 路径（取消则为 null）。 */
export function pickDataFile(): Promise<string | null> {
  return invoke<string | null>("pick_data_file");
}

/** 取路径的父目录（兼容 / 与 \ 分隔符）。 */
export function dirOf(path: string): string {
  return path.replace(/[\\/][^\\/]*$/, "");
}

/**
 * 读取并解析 works.json；为每条作品预组装封面 URL（asset 协议，本地文件）。
 * 封面路径形如 `covers/RJ007741.jpg`，相对于 works.json 所在目录。
 */
export async function loadWorks(): Promise<LoadedData> {
  const dataPath = await getDataPath();
  if (!dataPath) throw new Error("尚未选择数据文件");
  const raw = await invoke<string>("load_works");
  let file: WorksFile;
  try {
    file = JSON.parse(raw) as WorksFile;
  } catch {
    throw new Error("数据解析失败：不是有效的 JSON 文件");
  }
  if (!file || !Array.isArray(file.works)) {
    throw new Error("数据格式不正确：缺少 works 数组");
  }
  // 统一为正斜杠，asset 协议在各平台上都能正确处理
  const base = dirOf(dataPath).replace(/\\/g, "/");
  const works: WorkView[] = file.works.map((work) => ({
    ...work,
    _cover: work.image_path ? convertFileSrc(`${base}/${work.image_path}`) : "",
  }));
  return { path: dataPath, file, works };
}
