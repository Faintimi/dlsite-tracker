// 偏好持久化（对齐 macOS @AppStorage 的五个键；存 localStorage，随应用目录保留）
const KEY = "radar.prefs.v1";

export interface SectionsState {
  favorites: boolean;
  follows: boolean;
  genres: boolean;
  filters: boolean;
  imports: boolean;
}

export interface Prefs {
  /** 显示模式（大卡列表 largeCards / 双列卡片 twoColumn / 紧凑列表 compact / 自适应网格 adaptiveGrid / 封面墙 coverWall） */
  displayMode: string;
  showBadges: boolean;
  showDiscount: boolean;
  showRatingCount: boolean;
  hideImages: boolean;
  sidebarVisible: boolean;
  /** 侧栏分区展开状态（收藏 / 关注 / 分类人气 / 筛选条件 / 渐进导入） */
  sections: SectionsState;
  /** 筛选条件内的「更多筛选」展开状态 */
  filtersMore: boolean;
  /** 「关注」分区内的作者列表展开状态 */
  followedMakersExpanded: boolean;
  /** 发现系统：我的口味（分类名列表，手动勾选） */
  taste: string[];
  /** 发现系统：三档口味画像（旧 taste 自动迁移为 like）。 */
  tasteProfile: Record<string, TasteLevel>;
  /** 参与口味推断的收藏夹；空数组表示全部。 */
  tasteCollectionIds: string[];
  /** 用户从收藏中挑选、用于辅助建立口味的作品。 */
  tasteExemplarIds: string[];
  /** 是否完成过首次口味引导。 */
  tasteOnboarded: boolean;
}

export type TasteLevel = "love" | "like" | "less";

function defaults(): Prefs {
  return {
    displayMode: "largeCards",
    showBadges: true,
    showDiscount: true,
    showRatingCount: true,
    hideImages: false,
    sidebarVisible: true,
    sections: { favorites: true, follows: false, genres: false, filters: true, imports: false },
    filtersMore: false,
    followedMakersExpanded: true,
    taste: [],
    tasteProfile: {},
    tasteCollectionIds: [],
    tasteExemplarIds: [],
    tasteOnboarded: false,
  };
}

function load(): Prefs {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<Prefs>;
      const base = defaults();
      const sections = parsed.sections && typeof parsed.sections === "object" && !Array.isArray(parsed.sections)
        ? parsed.sections : {};
      const loaded = { ...base, ...parsed, sections: { ...base.sections, ...sections } };
      if (typeof loaded.hideImages !== "boolean") loaded.hideImages = false;
      if (typeof loaded.followedMakersExpanded !== "boolean") loaded.followedMakersExpanded = true;
      if (!loaded.tasteProfile || typeof loaded.tasteProfile !== "object" || Array.isArray(loaded.tasteProfile)) {
        loaded.tasteProfile = {};
      }
      if (Object.keys(loaded.tasteProfile).length === 0 && Array.isArray(parsed.taste)) {
        loaded.tasteProfile = Object.fromEntries(
          parsed.taste.filter((name) => typeof name === "string" && name).map((name) => [name, "like"]),
        );
      }
      return loaded;
    }
  } catch {
    // 忽略：损坏时回到默认
  }
  return defaults();
}

class PrefsStore {
  data = $state<Prefs>(load());

  private persist(): void {
    try {
      localStorage.setItem(KEY, JSON.stringify(this.data));
    } catch {
      // 忽略存储失败
    }
  }

  set<K extends keyof Prefs>(key: K, value: Prefs[K]): void {
    this.data[key] = value;
    this.persist();
  }

  /** 切换侧栏某分区的展开状态（合并写入，避免覆盖其他分区）。 */
  toggleSection(key: keyof SectionsState, value: boolean): void {
    this.data.sections = { ...this.data.sections, [key]: value };
    this.persist();
  }

  setTasteLevel(name: string, level: TasteLevel | null): void {
    const next = { ...this.data.tasteProfile };
    if (level === null) delete next[name];
    else next[name] = level;
    this.data.tasteProfile = next;
    // 保留旧键供降级读取；只记录正向口味。
    this.data.taste = Object.entries(next)
      .filter(([, value]) => value !== "less")
      .map(([key]) => key);
    this.persist();
  }

  replaceTasteProfile(profile: Record<string, TasteLevel>): void {
    this.data.tasteProfile = { ...profile };
    this.data.taste = Object.entries(profile)
      .filter(([, value]) => value !== "less")
      .map(([key]) => key);
    this.persist();
  }
}

export const prefs = new PrefsStore();
