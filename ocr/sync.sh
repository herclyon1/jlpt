#!/bin/bash
# 一键同步: 拉取仓库 → OCR 新文件 → 提交推回
# 手动执行: bash ocr/sync.sh
# 你在手机上传文件到 exams/raw/ 之后，回到 Mac 跑这一条就行
set -u
REPO="/Users/herclyon/JLPT/repo"
OCRBIN="/Users/herclyon/JLPT/ocr/pdfocr"
LOG="/Users/herclyon/JLPT/ocr/sync.log"
exec > >(tee -a "$LOG") 2>&1     # 同时打屏幕和日志，手动执行要看得见
echo "===== $(date '+%F %T')"

cd "$REPO" || { echo "仓库不存在: $REPO"; exit 1; }
[ -x "$OCRBIN" ] || { echo "pdfocr 未编译"; exit 1; }

# 1) 拉取（先暂存本地改动，避免 rebase 中断）
git stash -q -u 2>/dev/null
if ! git pull -q --rebase origin main; then
  echo "拉取失败，跳过本轮"
  git rebase --abort 2>/dev/null
  git stash pop -q 2>/dev/null
  exit 1
fi
git stash pop -q 2>/dev/null

# 2) OCR 尚未处理的原始文件
mkdir -p exams/raw exams/ocr
new=0
while IFS= read -r -d '' f; do
  rel="${f#exams/raw/}"; sub="$(dirname "$rel")"
  stem="$(basename "$f")"; stem="${stem%.*}"
  [ "$sub" = "." ] && sub="待分类"      # 传到根目录的自动归入待分类
  mkdir -p "exams/ocr/$sub"
  dst="exams/ocr/$sub/$stem.txt"
  if [ -f "$dst" ] && [ "$dst" -nt "$f" ]; then continue; fi
  printf '  OCR %s ... ' "$rel"
  if "$OCRBIN" "$f" > "$dst.tmp" 2>/dev/null && [ -s "$dst.tmp" ]; then
    mv "$dst.tmp" "$dst"
    echo "$(grep -c '^=== PAGE' "$dst")页 $(wc -m < "$dst" | tr -d ' ')字"
    new=$((new+1))
  else
    rm -f "$dst.tmp"; echo "失败"
  fi
done < <(find exams/raw -type f \( -iname '*.pdf' -o -iname '*.jpg' -o -iname '*.jpeg' \
         -o -iname '*.png' -o -iname '*.tif' -o -iname '*.tiff' -o -iname '*.heic' \) \
         -print0 2>/dev/null | sort -z)

if [ "$new" -eq 0 ]; then echo "无新文件"; exit 0; fi

# 3) 提交推回
git add -A exams/
if git diff --cached --quiet; then echo "无变更"; exit 0; fi
git commit -q -m "自动 OCR: 新增 ${new} 个文件的文字层

由 ocr/sync.sh 生成。源文件 exams/raw/，输出 exams/ocr/"
if git push -q origin main; then
  echo "✅ 已推送 ${new} 个 OCR 结果"
else
  echo "⚠ 推送失败，请检查网络或冲突"
fi
