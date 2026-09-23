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
  discovery: DiscoveryHistory;
  follow_updates: FollowUpdateHistory;
}

export interface DiscoveryHistory {
  /** 作品号 → 首次确认看过的 Unix 毫秒时间戳。 */
  seen: Record<string, number>;
  /** 作品号 → 标记为不感兴趣的 Unix 毫秒时间戳。 */
  dismissed: Record<string, number>;
}

export interface FollowUpdateHistory {
  /** 最近一次在本机作品库中检查关注作者新作的 Unix 毫秒时间戳。 */
  last_checked_at: number;
  /** 已经识别过的作品号，避免重复提醒。 */
  known_work_ids: string[];
  /** 尚未阅读的作品号 → 首次发现时间。 */
  unread: Record<string, number>;
}

export const DEFAULT_COLLECTION_NAME = "我的收藏";

function newId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `c-${Date.now()}-${Math.floor(Math.random() * 1_000_000)}`;
}

function newDefaultCollection(): FavoriteCollection {
  return { id: newId(), name: DEFAULT_COLLECTION_NAME, work_ids: [] };
}

function normalizeHistory(value: unknown): Record<string, number> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const out: Record<string, number> = {};
  for (const [key, raw] of Object.entries(value)) {
    const timestamp = Number(raw);
    if (key && Number.isFinite(timestamp) && timestamp > 0) out[key] = timestamp;
  }
  return out;
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
  const discovery = raw.discovery ?? { seen: {}, dismissed: {} };
  const followUpdates = raw.follow_updates ?? {
    last_checked_at: 0,
    known_work_ids: [],
    unread: {},
  };
  return {
    schema_version: 3,
    collections,
    makers,
    discovery: {
      seen: normalizeHistory(discovery.seen),
      dismissed: normalizeHistory(discovery.dismissed),
    },
    follow_updates: {
      last_checked_at: Number(followUpdates.last_checked_at) || 0,
      known_work_ids: Array.isArray(followUpdates.known_work_ids)
        ? [...new Set(followUpdates.known_work_ids.map(String).filter(Boolean))].slice(-5000)
        : [],
      unread: normalizeHistory(followUpdates.unread),
    },
  };
}

class LibraryStore {
  data = $state<LibraryData>({
    schema_version: 3,
    collections: [newDefaultCollection()],
    makers: [],
    discovery: { seen: {}, dismissed: {} },
    follow_updates: { last_checked_at: 0, known_work_ids: [], unread: {} },
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

  unreadFollowUpdateIds(): Set<string> {
    return new Set(Object.keys(this.data.follow_updates.unread));
  }

  /** 扫描当前作品库中的近两周关注作者新作；已知作品不会重复提醒。 */
  checkFollowUpdates(workIds: string[], force = false): number {
    const state = this.data.follow_updates;
    const now = Date.now();
    const last = new Date(state.last_checked_at);
    const today = new Date(now);
    const alreadyCheckedToday =
      last.getFullYear() === today.getFullYear() &&
      last.getMonth() === today.getMonth() &&
      last.getDate() === today.getDate();
    const known = new Set(state.known_work_ids);
    const current = new Set(workIds);
    let added = 0;
    let expired = 0;
    for (const id of Object.keys(state.unread)) {
      if (current.has(id)) continue;
      delete state.unread[id];
      expired += 1;
    }
    for (const id of workIds) {
      if (!id || known.has(id)) continue;
      known.add(id);
      state.unread[id] = now;
      added += 1;
    }
    if (!alreadyCheckedToday || force || added > 0) state.last_checked_at = now;
    if (added > 0 || expired > 0 || !alreadyCheckedToday || force) {
      state.known_work_ids = [...known].slice(-5000);
      this.scheduleSave();
    }
    return added;
  }

  markFollowUpdatesRead(workIds?: string[]): void {
    const unread = this.data.follow_updates.unread;
    const ids = workIds ?? Object.keys(unread);
    let changed = false;
    for (const id of ids) {
      if (!(id in unread)) continue;
      delete unread[id];
      changed = true;
    }
    if (changed) this.scheduleSave();
  }

  seenIds(): Set<string> {
    return new Set(Object.keys(this.data.discovery.seen));
  }

  dismissedIds(): Set<string> {
    return new Set(Object.keys(this.data.discovery.dismissed));
  }

  markSeen(workId: string): void {
    if (!workId || this.data.discovery.seen[workId]) return;
    this.data.discovery.seen[workId] = Date.now();
    this.scheduleSave();
  }

  dismiss(workId: string): void {
    if (!workId) return;
    this.data.discovery.dismissed[workId] = Date.now();
    this.markSeen(workId);
    this.scheduleSave();
  }
}

export const library = new LibraryStore();
