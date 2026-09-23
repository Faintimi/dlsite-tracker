// 偏好持久化（对齐 macOS @AppStorage 的五个键；存 localStorage，随应用目录保留）
const KEY = "radar.prefs.v1";

export interface SectionsState {
  favorites: boolean;
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
  sidebarVisible: boolean;
  /** 侧栏分区展开状态（收藏 / 分类人气 / 筛选条件 / 渐进导入） */
  sections: SectionsState;
  /** 筛选条件内的「更多筛选」展开状态 */
  filtersMore: boolean;
  /** 发现系统：我的口味（分类名列表，手动勾选） */
  taste: string[];
}

function defaults(): Prefs {
  return {
    displayMode: "largeCards",
    showBadges: true,
    showDiscount: true,
    showRatingCount: true,
    sidebarVisible: true,
    sections: { favorites: true, genres: false, filters: true, imports: false },
    filtersMore: false,
    taste: [],
  };
}

function load(): Prefs {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return { ...defaults(), ...(JSON.parse(raw) as Partial<Prefs>) };
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
}

export const prefs = new PrefsStore();
