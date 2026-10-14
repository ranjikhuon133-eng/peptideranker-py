#!/usr/bin/env bash
# =====================================================================
# 用原始 PeptideRanker 二进制生成"标准答案"分数（golden values）
#
# 为什么需要：原始 PeptideRanker 是 2010 年编译的 Linux x86-64 ELF，
# 在 Windows / macOS 上无法直接执行。本脚本在 Linux（或 Docker 容器）里
# 运行它，输出 序列<TAB>分数，供 scripts/validate_against_original.py 比对。
#
# 用法（在 Linux 或 Docker 容器内的项目根目录执行）：
#     bash scripts/run_original.sh testfile.txt > _re/golden_original.txt
#
# Windows 上推荐用 Docker（见 scripts/Dockerfile.original）：
#     docker build -f scripts/Dockerfile.original -t peptideranker-original .
#     docker run --rm -v "%cd%:/w" -w /w peptideranker-original \
#         bash scripts/run_original.sh testfile.txt
# =====================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

INPUT="${1:-testfile.txt}"
WORK="_re/original_run"

if [[ ! -f "PeptideRanker" ]]; then
  echo "错误：找不到二进制 PeptideRanker（应在项目根目录）" >&2
  exit 1
fi
if [[ ! -f "$INPUT" ]]; then
  echo "错误：找不到输入文件 $INPUT" >&2
  exit 1
fi

# 1) 编译产物没有可执行位（Windows 文件系统通常丢掉了），补上
chmod +x PeptideRanker PeptideRanker.pl 2>/dev/null || true

# 2) 工作目录：原程序会把 peptide.dataset / peptide.dataset.predictions
#    写到当前目录，所以单独开一个目录，避免污染仓库根目录
mkdir -p "$WORK"
cp -f Models_Short.txt Models_Long.txt "$WORK/" 2>/dev/null || true
ln -sfn "$ROOT/Models_Short" "$WORK/Models_Short" 2>/dev/null || cp -r Models_Short "$WORK/" 2>/dev/null || true
ln -sfn "$ROOT/Models_Long"  "$WORK/Models_Long"  2>/dev/null || cp -r Models_Long  "$WORK/" 2>/dev/null || true
cp -f "$INPUT" "$WORK/input.txt"
cp -f PeptideRanker "$WORK/PeptideRanker"
chmod +x "$WORK/PeptideRanker"
# 原 .pl 里的 $pipeline_dir="." ，因此把 -I. 指向工作目录里的 libstdc++ 无必要，
# 只要系统有 libstdc++.so.6 即可（Ubuntu/Debian 默认有）。
sed 's#^\$pipeline_dir=.*#$pipeline_dir=".";#' PeptideRanker.pl > "$WORK/PeptideRanker.pl"
chmod +x "$WORK/PeptideRanker.pl"

echo "# 原始 PeptideRanker 输出（序列<TAB>分数），由 scripts/run_original.sh 生成" >&2
echo "# 输入：$INPUT" >&2

# 3) 运行：优先用 perl 包装脚本（与原作者用法一致）
cd "$WORK"
if command -v perl >/dev/null 2>&1; then
  perl ./PeptideRanker.pl input.txt ranked.txt
  RANKED="ranked.txt"
else
  # 没有 perl 时直接调二进制（等价逻辑：逐条序列写 dataset 再打分）
  : > ranked.txt
  while IFS= read -r seq; do
    [[ -z "$seq" ]] && continue
    len=${#seq}
    printf '1\npeptide\n%s\n%s\n1\n' "$len" "$seq" > peptide.dataset
    if [[ "$len" -le 20 ]]; then models=Models_Short.txt; else models=Models_Long.txt; fi
    ./PeptideRanker "$models" peptide.dataset ./ >/dev/null 2>&1 || true
    score=$(sed -n '6p' peptide.dataset.predictions | awk '{print $2}')
    printf '%s\t%s\n' "$seq" "$score" >> ranked.txt
  done < input.txt
  RANKED="ranked.txt"
fi

# 4) ranked.txt 的格式是 "<分数>\t<序列>"，翻转成 "<序列>\t<分数>"
awk -F'\t' 'NF>=2 && $1 ~ /^[0-9.]+$/ {print $2 "\t" $1}' "$RANKED"
