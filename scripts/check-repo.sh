#!/usr/bin/env bash
# 公开前自检（P18.1）：确认 git 追踪范围里没有数据/图片/大文件/个人路径。
# 用法：bash scripts/check-repo.sh   （退出码 0 = 通过；1 = 发现问题）
# 背景：数据库（data/）与导出产物（out/，含 R18 封面缩略图）必须永不入库；
#       公开前请再过一遍内部安全清单（本地 docs/，不入库）。
set -u
cd "$(dirname "$0")/.." || exit 1

status=0
fail() { echo "[失败] $1"; status=1; }

echo "== 1/4 追踪文件中是否有本机数据/产物 =="
hits=$(git ls-files | grep -E '^(data|out|app/dist)/' || true)
if [ -n "$hits" ]; then
  echo "$hits" | head -20
  fail "发现 data/、out/ 或 app/dist/ 下的文件被 git 追踪"
else
  echo "OK：data/、out/、app/dist/ 均未被追踪"
fi

echo "== 2/4 追踪文件中是否有图片/二进制/压缩包 =="
hits=$(git ls-files | grep -iE '\.(jpg|jpeg|png|gif|webp|bmp|ico|svg|pdf|zip|gz|tgz|tar|7z|rar|mp4|mov|webm|mp3|wav|flac|sqlite|db)$' || true)
if [ -n "$hits" ]; then
  echo "$hits" | head -20
  fail "发现图片/二进制/压缩包被追踪"
else
  echo "OK：无图片/二进制/压缩包"
fi

echo "== 3/4 追踪文件中是否有大文件（>200KB） =="
big=0
while IFS= read -r file; do
  [ -n "$file" ] || continue
  [ -f "$file" ] || continue
  size=$(wc -c < "$file" | tr -d ' ')
  if [ "$size" -gt 204800 ]; then
    echo "  $size $file"
    big=1
  fi
done <<EOF
$(git ls-files)
EOF
if [ "$big" -eq 1 ]; then fail "存在超过 200KB 的追踪文件"; else echo "OK：无大文件"; fi

echo "== 4/4 追踪文件中是否有本机绝对路径 =="
if git grep -nE '/Users/[A-Za-z0-9._-]+/|/home/[A-Za-z0-9._-]+/' >/dev/null 2>&1; then
  git grep -nE '/Users/[A-Za-z0-9._-]+/|/home/[A-Za-z0-9._-]+/' | head -10
  fail "发现本机绝对路径"
else
  echo "OK：无本机绝对路径"
fi

echo
if [ "$status" -eq 0 ]; then
  echo "== 通过：追踪范围干净（公开前仍建议人工过一遍内部安全清单） =="
else
  echo "== 未通过：请先把上述内容移出 git（必要时须重写历史后再公开） =="
fi
exit "$status"
