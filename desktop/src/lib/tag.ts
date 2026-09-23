import { ICONS } from "./ui";

export const CONTENT_FLAG_TAGS = [
  { key: "voice", label: "配音", icon: ICONS.mic, help: "有配音" },
  { key: "music", label: "音乐", icon: ICONS.note, help: "有音乐" },
  { key: "video", label: "动画", icon: ICONS.film, help: "有动画" },
] as const;

export type ContentFlag = (typeof CONTENT_FLAG_TAGS)[number]["key"];
export type TagKind = "category" | "excluded" | "form" | ContentFlag;

export function flagTag(kind: TagKind) {
  return CONTENT_FLAG_TAGS.find((item) => item.key === kind);
}
