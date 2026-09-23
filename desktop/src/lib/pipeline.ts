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
  note?: string;
  updated_ts?: number;
}

interface ProgressFiles {
  update: string | null;
  import_progress: string | null;
}

/** 运行中的阶段（与 macOS 版横幅一致）。 */
export const ACTIVE_PHASES = new Set(["rankings", "sales", "images", "export", "import"]);

export function isRunning(state: UpdateState | null | undefined): boolean {
  return !!state && ACTIVE_PHASES.has(state.phase ?? "");
}

export function phaseLabel(state: UpdateState | null | undefined): string {
  switch (state?.phase) {
    case "rankings":
      return "正在抓取热榜（榜单/列表/人气序）并富化新作…";
    case "sales":
      return "正在刷新在榜作品销量…";
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

export type UpdateKind = "quick" | "daily" | "update-all";

/** 启动管道任务（脚本 / python -m 由后端选择）。 */
export function startUpdate(kind: UpdateKind, range?: string): Promise<string> {
  return invoke<string>("start_update", { kind, range: range ?? null });
}

/** 读取两条进度文件并解析（文件缺失或解析失败对应字段为 null）。 */
export async function readProgress(): Promise<{
  state: UpdateState | null;
  importProgress: ImportProgress | null;
}> {
  const files = await invoke<ProgressFiles>("read_progress_files");
  return {
    state: files.update ? (JSON.parse(files.update) as UpdateState) : null,
    importProgress: files.import_progress
      ? (JSON.parse(files.import_progress) as ImportProgress)
      : null,
  };
}
