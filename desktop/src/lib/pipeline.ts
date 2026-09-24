// 管道任务：启动更新与进度轮询（对齐 out/update-progress.json 与 out/import-progress.json）。
import { invoke } from "@tauri-apps/api/core";

export interface UpdateState {
  schema_version?: number;
  phase?: string;
  detail?: string;
  years?: string;
  pid?: number;
  updated_at?: string;
  updated_ts?: number;
  failed_steps?: string[];
}

export interface ImportProgress {
  running?: boolean;
  phase?: string;
  years?: string | number;
  enriched?: number;
  excluded?: number;
  skipped?: number;
  failed?: number;
  remaining?: number;
  total?: number;
  walk_done?: boolean;
  cursor_page?: number;
  note?: string;
  updated_ts?: number;
}

export interface GenreProgress {
  schema_version?: number;
  genre_id?: string;
  genre_name?: string;
  phase?: string;
  detail?: string;
  running?: boolean;
  done?: boolean;
  error?: string;
  more?: boolean;
  pid?: number;
  updated_at?: string;
  updated_ts?: number;
}

/** P23：已覆盖最深位置（out/import-coverage.json；供「继续抓更早」显示与命令） */
export interface ImportCoverage {
  schema_version?: number;
  updated_at?: string;
  years?: string;
  boundary_old?: number;
  boundary_modern?: number;
  page?: number;
  covered_days?: number;
  covered_years?: number;
}

interface ProgressFiles {
  update: string | null;
  daily_status: string | null;
  import_progress: string | null;
  genre: string | null;
  import_coverage: string | null;
}

/** 运行中的阶段（与 macOS 版横幅一致）。 */
export const ACTIVE_PHASES = new Set(["waiting", "init", "rankings", "sales", "images", "export", "import"]);

export function isRunning(state: UpdateState | null | undefined): boolean {
  return !!state && ACTIVE_PHASES.has(state.phase ?? "");
}

/** 进度时间戳是否已过期（对齐 macOS：update 48 小时、genre 6 小时）。 */
export function isStale(ts: number | undefined, hours: number): boolean {
  if (typeof ts !== "number") return false;
  return Date.now() / 1000 - ts > hours * 3600;
}

/** 范围文案（对齐 macOS yearsLabel）。 */
export function yearsLabel(years: string | number | null | undefined): string {
  const text = String(years ?? "").trim();
  if (!text) return "";
  const lower = text.toLowerCase();
  if (lower === "all") return "全部";
  if (lower === "daily") return "完整维护";
  if (lower === "quick") return "热榜快更";
  if (lower === "bootstrap") return "首次初始化";
  if (lower.startsWith("since:")) return `自 ${text.slice("since:".length)} 年至今`;
  if (lower.startsWith("deeper:")) {
    return `续深至最近 ${text.slice("deeper:".length)} 年（跳过已覆盖段）`;
  }
  return `最近 ${text} 年`;
}

export function phaseLabel(state: UpdateState | null | undefined): string {
  switch (state?.phase) {
    case "waiting":
      return state.detail ?? "正在等待渐进导入保存断点…";
    case "init":
      return "正在准备本地数据库…";
    case "rankings":
      return "正在抓取热榜（榜单/列表/人气序）并富化新作…";
    case "sales":
      return state.detail?.startsWith("正在补齐精确评分")
        ? state.detail : "正在刷新在榜作品销量…";
    case "images":
      return "正在补齐封面…";
    case "export":
      return "正在导出数据…";
    case "import":
      return "正在导入历史作品…";
    case "done":
      return "更新完成";
    case "failed":
      return "更新失败（详见 data/ 目录日志）";
    case "busy":
      return "已有任务在运行";
    default:
      return state?.phase ? `进行中：${state.phase}` : "";
  }
}

/** 更新横幅文案（逐字对齐 macOS UpdateProgress.summary）。 */
export function updateSummary(
  state: UpdateState,
  importProgress: ImportProgress | null,
): string {
  const scope = state.years ? `（${yearsLabel(state.years)}）` : "";
  switch (state.phase) {
    case "waiting":
      return `更新待开始${scope}：${state.detail ?? "等待渐进导入保存断点"}`;
    case "init":
      return `初始化中${scope}：正在准备本地数据库…`;
    case "rankings":
      if (state.detail?.startsWith("富化 ")) {
        return `更新中${scope}：${state.detail}…`;
      }
      return `更新中${scope}：正在抓取热榜（榜单/列表/人气序）并富化新作…`;
    case "import":
      if (importProgress && importProgress.phase === "enrich") {
        return `更新中${scope}：导入进行中 — 已入库 ${importProgress.enriched ?? 0} · 排除非游戏 ${importProgress.excluded ?? 0} · 忽略低销旧作 ${importProgress.skipped ?? 0} · 剩余 ${importProgress.remaining ?? 0}`;
      }
      return `更新中${scope}：导入进行中（断点续传）`;
    case "sales":
      return `更新中${scope}：${state.detail?.startsWith("正在补齐精确评分")
        ? state.detail : "正在刷新销量…"}`;
    case "images":
      return `更新中${scope}：${state.detail || "正在补齐封面…"}`;
    case "export":
      return `更新中${scope}：正在导出数据…`;
    case "done":
      return `更新完成${scope}：${state.detail ?? "数据已更新"}`;
    case "failed":
      return `更新中断${scope}：${state.detail ?? "详见 data/update.log"}`;
    case "busy":
      return state.detail ?? "已有更新在运行…";
    default:
      return "";
  }
}

/** 渐进导入横幅文案（逐字对齐 macOS ImportProgress.summary）。 */
export function importSummary(progress: ImportProgress): string {
  const skipped = progress.skipped ?? 0;
  switch (progress.phase) {
    case "enrich": {
      const stateText = progress.running ? "进行中" : "已暂停（打开「渐进导入」开关可继续）";
      if (progress.walk_done === false && typeof progress.cursor_page === "number") {
        const registered = progress.total ??
          (progress.enriched ?? 0) + (progress.excluded ?? 0) + skipped +
          (progress.failed ?? 0) + (progress.remaining ?? 0);
        return `渐进导入${stateText}：目录遍历第 ${progress.cursor_page} 页 · 已登记候选 ${registered} · 已入库 ${progress.enriched ?? 0} · 待处理 ${progress.remaining ?? 0}`;
      }
      const remaining = progress.remaining ?? 0;
      const total = progress.total;
      let percent = "";
      if (typeof total === "number" && total > 0) {
        const done = Math.max(0, Math.min(total, total - remaining));
        percent = ` · 约 ${Math.round((done / total) * 100)}%`;
      }
      return `渐进导入${stateText}：已入库 ${progress.enriched ?? 0} · 排除非游戏 ${progress.excluded ?? 0} · 忽略低销旧作 ${skipped} · 剩余 ${remaining}${percent}`;
    }
    case "done":
      return `渐进导入已完成：新增入库 ${progress.enriched ?? 0} 部（排除非游戏 ${progress.excluded ?? 0}，忽略低销旧作 ${skipped}）`;
    default:
      return "";
  }
}

/** 分类人气横幅文案（逐字对齐 macOS GenreProgress.summary）。 */
export function genreSummary(progress: GenreProgress): string {
  const name = progress.genre_name || progress.genre_id || "分类";
  switch (progress.phase) {
    case "fetch":
      return `分类人气榜：「${name}」正在抓取人气榜…`;
    case "enrich":
      return `分类人气榜：「${name}」正在导入新作品（可能数分钟）…`;
    case "images":
      return `分类人气榜：「${name}」正在补齐封面…`;
    case "export":
      return `分类人气榜：「${name}」正在导出数据…`;
    case "done":
      return `分类人气榜：「${name}」已更新（${progress.detail ?? "完成"}）`;
    case "failed":
      return `分类人气榜更新失败：「${name}」（${progress.error || progress.detail || "详见 data/genre.log"}）`;
    case "busy":
      return progress.detail ?? "";
    default:
      return "";
  }
}

export type UpdateKind = "quick" | "daily" | "covers" | "update-all";

/** 启动管道任务（脚本 / python -m 由后端选择）。 */
export function startUpdate(kind: UpdateKind, range?: string): Promise<string> {
  return invoke<string>("start_update", { kind, range: range ?? null });
}

/** 渐进导入开关（on=true 启动/续传；on=false 优雅暂停）。 */
export function importSwitch(on: boolean, years?: string): Promise<string> {
  return invoke<string>("import_switch", { on, years: years ?? null });
}

/** 取消渐进导入任务（已入库作品保留）。 */
export function cancelImport(): Promise<string> {
  return invoke<string>("cancel_import");
}

/** 分类人气：现导入 / 载入更多。 */
export function startGenreImport(genre: string, more: boolean): Promise<string> {
  return invoke<string>("start_genre_import", { genre, more });
}

/** 把分类加入每日刷新列表（写入配置）。 */
export function watchGenre(genre: string): Promise<string> {
  return invoke<string>("watch_genre", { genre });
}

/** 把分类移出每日刷新列表（保留已抓名次数据）。 */
export function unwatchGenre(genre: string): Promise<string> {
  return invoke<string>("unwatch_genre", { genre });
}

/** 移除分类与其名次数据（同时移出每日刷新；已入库作品保留）。 */
export function removeGenre(genre: string): Promise<string> {
  return invoke<string>("remove_genre", { genre });
}

/** 读取全部进度文件并解析（文件缺失或解析失败对应字段为 null）。 */
export async function readProgress(): Promise<{
  state: UpdateState | null;
  dailyStatus: UpdateState | null;
  importProgress: ImportProgress | null;
  genreProgress: GenreProgress | null;
  importCoverage: ImportCoverage | null;
}> {
  const files = await invoke<ProgressFiles>("read_progress_files");
  const parse = <T>(raw: string | null): T | null => {
    if (!raw) return null;
    try {
      return JSON.parse(raw) as T;
    } catch {
      return null;
    }
  };
  return {
    state: parse<UpdateState>(files.update),
    dailyStatus: parse<UpdateState>(files.daily_status),
    importProgress: parse<ImportProgress>(files.import_progress),
    genreProgress: parse<GenreProgress>(files.genre),
    importCoverage: parse<ImportCoverage>(files.import_coverage),
  };
}
