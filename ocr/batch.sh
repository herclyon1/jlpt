#!/bin/bash
# 批量 OCR: 扫描输入目录下所有 PDF/图片，输出同名 .txt
# 用法: ./batch.sh [输入目录] [输出目录]
#   默认: ./batch.sh ../exams/raw ../exams/ocr
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
IN="${1:-$HERE/../exams/raw}"
OUT="${2:-$HERE/../exams/ocr}"
BIN="$HERE/pdfocr"

[ -x "$BIN" ] || { echo "编译 pdfocr..."; swiftc -O -o "$BIN" "$HERE/pdfocr.swift" || exit 1; }
mkdir -p "$OUT"
[ -d "$IN" ] || { echo "输入目录不存在: $IN"; exit 1; }

n=0; skip=0; fail=0; t0=$(date +%s)
while IFS= read -r -d '' f; do
  base="$(basename "$f")"; stem="${base%.*}"
  dst="$OUT/$stem.txt"
  if [ -f "$dst" ] && [ "$dst" -nt "$f" ]; then
    skip=$((skip+1)); continue
  fi
  printf '  处理 %s ... ' "$base"
  if "$BIN" "$f" > "$dst.tmp" 2>/dev/null && [ -s "$dst.tmp" ]; then
    mv "$dst.tmp" "$dst"
    pages=$(grep -c '^=== PAGE' "$dst"); chars=$(wc -m < "$dst" | tr -d ' ')
    echo "${pages}页 ${chars}字"
    n=$((n+1))
  else
    rm -f "$dst.tmp"; echo "失败"; fail=$((fail+1))
  fi
done < <(find "$IN" -type f \( -iname '*.pdf' -o -iname '*.jpg' -o -iname '*.jpeg' \
         -o -iname '*.png' -o -iname '*.tif' -o -iname '*.tiff' -o -iname '*.heic' \) -print0 | sort -z)

echo
echo "完成: 新处理 $n 个, 跳过(已存在且未更新) $skip 个, 失败 $fail 个, 用时 $(( $(date +%s)-t0 ))秒"
echo "输出目录: $OUT"
