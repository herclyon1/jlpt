#!/bin/bash
# 接收批量传来的真题文件（AirDrop/iCloud/网盘下载均可）
#   1) 从来源目录收走 PDF/图片
#   2) 按文件名猜场次，归入 exams/raw/<场次>/，猜不出的进 待分类/
#   3) 按内容去重（同内容不同文件名只留一份）
#   4) OCR，输出到 exams/ocr/ 对应目录
#
# 用法:
#   bash ocr/intake.sh                 # 默认从 ~/Downloads 收
#   bash ocr/intake.sh ~/某个目录
set -u
SRC="${1:-$HOME/Downloads}"
SRC="${SRC%/}"
REPO="/Users/herclyon/JLPT/repo"
OCRBIN="/Users/herclyon/JLPT/ocr/pdfocr"
cd "$REPO" || exit 1
[ -x "$OCRBIN" ] || { echo "pdfocr 未编译: swiftc -O -o $OCRBIN /Users/herclyon/JLPT/ocr/pdfocr.swift"; exit 1; }

echo "从 $SRC 收取真题文件…"
mkdir -p exams/raw/待分类

# 先解开压缩包（zip 用系统 unzip；7z 尝试 py7zr）
TMPX=""
for a in "$SRC"/*.zip "$SRC"/*.7z; do
  [ -e "$a" ] || continue
  [ -z "$TMPX" ] && { TMPX="$(mktemp -d)"; echo "  解压到临时目录…"; }
  case "$a" in
    *.zip) unzip -q -o "$a" -d "$TMPX" && echo "    解开 $(basename "$a")" ;;
    *.7z)  python3 -c "import py7zr,sys;py7zr.SevenZipFile(sys.argv[1]).extractall(sys.argv[2])" "$a" "$TMPX" 2>/dev/null \
             && echo "    解开 $(basename "$a")" \
             || echo "    ⚠ 7z 需要: python3 -m pip install --user py7zr" ;;
  esac
done
[ -n "$TMPX" ] && SRC="$TMPX"

guess_session() {   # 从文件名猜场次
  local n="$1" y m
  y=$(echo "$n" | grep -oE '20[0-9]{2}' | head -1)
  [ -z "$y" ] && { y=$(echo "$n" | grep -oE '(^|[^0-9])2[0-9]([^0-9]|$)' | grep -oE '2[0-9]' | head -1); [ -n "$y" ] && y="20$y"; }
  m=$(echo "$n" | grep -oE '(0?[17]|12)[ ]*月' | grep -oE '[0-9]+' | head -1)
  [ -z "$m" ] && m=$(echo "$n" | grep -oE '[-_](0?7|12)[-_]' | grep -oE '[0-9]+' | head -1)
  if [ -n "$y" ] && [ -n "$m" ]; then
    case "$m" in 7|07) echo "$y-07";; 12) echo "$y-12";; *) echo "";; esac
  fi
}

# 一次性建好已有文件的哈希集合（避免 O(n^2) 重复扫描）
HASHES="$(mktemp)"
find exams/raw -type f ! -name '.gitkeep' ! -name 'README.md' -print0 2>/dev/null \
  | xargs -0 -r shasum -a 256 2>/dev/null | cut -c1-16 | sort -u > "$HASHES"

moved=0; dup=0
while IFS= read -r -d '' f; do
  base="$(basename "$f")"
  reldir="$(dirname "${f#$SRC/}")"
  # 先用文件名猜, 猜不出再用它所在的目录名猜（你在手机上分好的文件夹）
  sess="$(guess_session "$base")"
  [ -z "$sess" ] && [ "$reldir" != "." ] && sess="$(guess_session "$reldir")"
  [ -z "$sess" ] && sess="待分类"
  mkdir -p "exams/raw/$sess"
  h="$(shasum -a 256 "$f" | cut -c1-16)"
  # 内容去重: 仓库里已有相同哈希的就跳过
  if grep -qx "$h" "$HASHES"; then
    echo "  跳过(内容重复) $base"; dup=$((dup+1)); continue
  fi
  echo "$h" >> "$HASHES"
  dst="exams/raw/$sess/$base"
  [ -e "$dst" ] && dst="exams/raw/$sess/${base%.*}_$h.${base##*.}"
  cp "$f" "$dst" && { echo "  → $sess/  $base"; moved=$((moved+1)); }
done < <(find "$SRC" -type f \( -iname '*.pdf' -o -iname '*.jpg' -o -iname '*.jpeg' \
         -o -iname '*.png' -o -iname '*.tif' -o -iname '*.tiff' -o -iname '*.heic' \) \
         ! -iname '*译文*' -print0 2>/dev/null)

rm -f "$HASHES"
[ -n "${TMPX:-}" ] && rm -rf "$TMPX"
echo "收取完成: 新增 $moved 个, 内容重复跳过 $dup 个"
[ "$moved" -eq 0 ] && exit 0

echo
echo "开始 OCR…"
n=0
while IFS= read -r -d '' f; do
  rel="${f#exams/raw/}"; sub="$(dirname "$rel")"
  stem="$(basename "$f")"; stem="${stem%.*}"
  mkdir -p "exams/ocr/$sub"
  dst="exams/ocr/$sub/$stem.txt"
  [ -f "$dst" ] && [ "$dst" -nt "$f" ] && continue
  printf '  %s ... ' "$rel"
  if "$OCRBIN" "$f" > "$dst.tmp" 2>/dev/null && [ -s "$dst.tmp" ]; then
    mv "$dst.tmp" "$dst"
    echo "$(grep -c '^=== PAGE' "$dst")页 $(wc -m < "$dst" | tr -d ' ')字"
    n=$((n+1))
  else
    rm -f "$dst.tmp"; echo "失败"
  fi
done < <(find exams/raw -type f ! -name '.gitkeep' ! -name 'README.md' -print0 | sort -z)

echo
echo "OCR 完成 $n 个。各场次现状:"
for d in exams/raw/*/; do
  s="$(basename "$d")"
  r=$(find "$d" -type f ! -name '.gitkeep' ! -name 'README.md' 2>/dev/null | wc -l | tr -d ' ')
  o=$(find "exams/ocr/$s" -type f -name '*.txt' 2>/dev/null | wc -l | tr -d ' ')
  [ "$r" = "0" ] && continue
  printf '  %-10s 原件 %2s 个 / OCR %2s 个\n' "$s" "$r" "$o"
done
echo
echo "下一步: git add exams/ocr && git commit && git push  （原件默认不入库，见 .gitignore）"
