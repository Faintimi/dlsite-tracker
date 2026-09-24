import type { GenreCatalogEntry, GenreEntry } from "./api";

/** 卡片只有分类名称；导入前必须解析到官方分类 ID，不做模糊猜测。 */
export function matchingGenreCandidates(
  name: string,
  catalog: GenreCatalogEntry[],
  imported: GenreEntry[],
): GenreCatalogEntry[] {
  const target = name.trim();
  const matches = new Map<string, GenreCatalogEntry>();
  for (const entry of catalog) {
    if (entry.name.trim() === target) matches.set(entry.id, { id: entry.id, name: entry.name });
  }
  // 兼容旧导出：全量目录缺席时，已导入分类仍可按其权威 ID 打开。
  for (const entry of imported) {
    if (entry.name.trim() === target) matches.set(entry.id, { id: entry.id, name: entry.name });
  }
  return [...matches.values()];
}
