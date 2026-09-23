// 收藏与关注（本地 JSON 存储；结构对齐 macOS 版的 favorites.json，便于后续迁移/导入）。
import { invoke } from "@tauri-apps/api/core";

export interface FavoriteCollection {
  id: string;
  name: string;
  work_ids: string[];
}

export interface FollowedMaker {
  key: string;
  name: string;
  maker_id: string;
}

export interface LibraryData {
  schema_version: number;
  collections: FavoriteCollection[];
  makers: FollowedMaker[];
}

export const DEFAULT_COLLECTION_NAME = "我的收藏";

function newId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `c-${Date.now()}-${Math.floor(Math.random() * 1_000_000)}`;
}

function newDefaultCollection(): FavoriteCollection {
  return { id: newId(), name: DEFAULT_COLLECTION_NAME, work_ids: [] };
}

function normalize(raw: LibraryData): LibraryData {
  const collections = (Array.isArray(raw.collections) ? raw.collections : []).map((item) => ({
    id: String(item.id ?? newId()),
    name: String(item.name ?? "未命名收藏夹"),
    work_ids: Array.isArray(item.work_ids) ? item.work_ids.map(String) : [],
  }));
  if (!collections.some((item) => item.name === DEFAULT_COLLECTION_NAME)) {
    collections.push(newDefaultCollection());
  }
  const makers = (Array.isArray(raw.makers) ? raw.makers : []).map((item) => ({
    key: String(item.key ?? ""),
    name: String(item.name ?? ""),
    maker_id: String(item.maker_id ?? ""),
  }));
  return { schema_version: 1, collections, makers };
}

class LibraryStore {
  data = $state<LibraryData>({
    schema_version: 1,
    collections: [newDefaultCollection()],
    makers: [],
  });
  loaded = $state(false);

  private timer: ReturnType<typeof setTimeout> | null = null;

  async load(): Promise<void> {
    try {
      const raw = await invoke<string | null>("load_library");
      if (raw) {
        this.data = normalize(JSON.parse(raw) as LibraryData);
      }
    } catch (error) {
      console.error("[radar] 收藏数据读取失败：", error);
    }
    this.loaded = true;
  }

  /** 防抖保存（400ms；连续操作只落盘一次）。 */
  private scheduleSave(): void {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      void this.save();
    }, 400);
  }

  async save(): Promise<void> {
    try {
      await invoke("save_library", { data: JSON.stringify(this.data) });
    } catch (error) {
      console.error("[radar] 收藏数据保存失败：", error);
    }
  }

  /** 是否在任一收藏夹中（心形填充状态；与 macOS 版语义一致）。 */
  isFavorited(workId: string): boolean {
    return this.data.collections.some((collection) => collection.work_ids.includes(workId));
  }

  /** 指定收藏夹包含的作品集合（"all" = 全部收藏夹的并集）。 */
  idsIn(scope: string): Set<string> {
    if (scope === "all") {
      const out = new Set<string>();
      for (const collection of this.data.collections) {
        for (const id of collection.work_ids) out.add(id);
      }
      return out;
    }
    const collection = this.data.collections.find((item) => item.id === scope);
    return new Set(collection ? collection.work_ids : []);
  }

  /** 心形快按：切换「我的收藏」（不存在时自动创建）。 */
  toggleFavorite(workId: string): void {
    const collection =
      this.data.collections.find((item) => item.name === DEFAULT_COLLECTION_NAME) ??
      (() => {
        const created = newDefaultCollection();
        this.data.collections.push(created);
        return created;
      })();
    this.toggleIn(workId, collection.id);
  }

  toggleIn(workId: string, collectionId: string): void {
    const collection = this.data.collections.find((item) => item.id === collectionId);
    if (!collection) return;
    const position = collection.work_ids.indexOf(workId);
    if (position >= 0) collection.work_ids.splice(position, 1);
    else collection.work_ids.push(workId);
    this.scheduleSave();
  }

  createCollection(name: string, addWorkId?: string): void {
    const trimmed = name.trim() || "未命名收藏夹";
    this.data.collections.push({
      id: newId(),
      name: trimmed,
      work_ids: addWorkId ? [addWorkId] : [],
    });
    this.scheduleSave();
  }

  renameCollection(collectionId: string, name: string): void {
    const trimmed = name.trim();
    if (!trimmed) return;
    const collection = this.data.collections.find((item) => item.id === collectionId);
    if (!collection) return;
    collection.name = trimmed;
    this.scheduleSave();
  }

  deleteCollection(collectionId: string): void {
    this.data.collections = this.data.collections.filter((item) => item.id !== collectionId);
    this.scheduleSave();
  }

  isFollowing(key: string): boolean {
    return this.data.makers.some((maker) => maker.key === key);
  }

  followedKeys(): Set<string> {
    return new Set(this.data.makers.map((maker) => maker.key));
  }

  toggleFollow(key: string, name: string, makerId: string): void {
    const index = this.data.makers.findIndex((maker) => maker.key === key);
    if (index >= 0) this.data.makers.splice(index, 1);
    else this.data.makers.push({ key, name, maker_id: makerId });
    this.scheduleSave();
  }

  /** 是否还没有任何收藏与关注（用于 macOS 迁移入口的显示判断）。 */
  isEmpty(): boolean {
    return (
      this.data.makers.length === 0 &&
      this.data.collections.every((collection) => collection.work_ids.length === 0)
    );
  }

  /** 解析 macOS 版 favorites.json（camelCase）并统计条目数。 */
  describeMacosFavorites(raw: string): { collections: number; makers: number } {
    const parsed = JSON.parse(raw) as MacosFavoritesData;
    return {
      collections: Array.isArray(parsed.collections) ? parsed.collections.length : 0,
      makers: Array.isArray(parsed.makers) ? parsed.makers.length : 0,
    };
  }

  /** 合并 macOS 版收藏（同名收藏夹合并去重；同 key 制作者去重；不覆盖现有数据）。 */
  mergeMacosFavorites(raw: string): { collections: number; makers: number } {
    const parsed = JSON.parse(raw) as MacosFavoritesData;
    let addedCollections = 0;
    let addedMakers = 0;
    for (const item of Array.isArray(parsed.collections) ? parsed.collections : []) {
      const name = String(item.name ?? "").trim() || "未命名收藏夹";
      const ids = Array.isArray(item.workIDs) ? item.workIDs.map(String) : [];
      const existing = this.data.collections.find((collection) => collection.name === name);
      if (existing) {
        for (const id of ids) {
          if (!existing.work_ids.includes(id)) existing.work_ids.push(id);
        }
      } else {
        this.data.collections.push({ id: newId(), name, work_ids: ids });
        addedCollections += 1;
      }
    }
    for (const item of Array.isArray(parsed.makers) ? parsed.makers : []) {
      const key = String(item.key ?? "");
      if (!key || this.data.makers.some((maker) => maker.key === key)) continue;
      this.data.makers.push({
        key,
        name: String(item.name ?? ""),
        maker_id: String(item.makerID ?? ""),
      });
      addedMakers += 1;
    }
    this.scheduleSave();
    return { collections: addedCollections, makers: addedMakers };
  }
}

/** macOS 版 favorites.json 结构（camelCase） */
interface MacosFavoritesData {
  collections?: { id?: string; name?: string; workIDs?: string[] }[];
  makers?: { key?: string; name?: string; makerID?: string }[];
}

export const library = new LibraryStore();
