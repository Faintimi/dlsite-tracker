// 偏好持久化（对齐 macOS @AppStorage 的五个键；存 localStorage，随应用目录保留）
const KEY = "radar.prefs.v1";

export interface Prefs {
  /** 显示模式（大卡列表 largeCards / 双列卡片 twoColumn / 紧凑列表 compact / 自适应网格 adaptiveGrid / 封面墙 coverWall） */
  displayMode: string;
  showBadges: boolean;
  showDiscount: boolean;
  showRatingCount: boolean;
  sidebarVisible: boolean;
}

function defaults(): Prefs {
  return {
    displayMode: "largeCards",
    showBadges: true,
    showDiscount: true,
    showRatingCount: true,
    sidebarVisible: true,
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
}

export const prefs = new PrefsStore();
