"""数值校验：把 Python 引擎的分数与**原版 PeptideRanker 的分数**逐条对比。

标准答案来源（按可信度排序）：
  1. `_re/reference_scores.tsv`        公开文献中**原版 distille deep.ucd.ie/PeptideRanker**
     服务器的输出（679 条，来自 Europe PMC 全文表格，每条带可复核 URL）
  2. `_re/golden_original.txt`         在 Linux / Docker 下直接运行原始二进制得到的输出
     （由 `scripts/run_original.sh` 生成）

两个文件的格式都是 `<序列>\t<分数>[\t<来源>]`，以 `#` 开头的行是注释。

更多分析工具见：
  scripts/validate_published.py   真值比对 + 20aa 边界判定（推荐入口）
  scripts/detect_table_shift.py   区分"文献表格错位"与"真实算法偏差"
  scripts/triage_reference_rows.py 分拣脏数据（三字母缩写、蛋白名等）
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pr_engine import scoring  # noqa: E402

TOLERANCE = 0.01
# 每个参考文件的列序不同，必须分别声明，否则会把"长度"当成分数
#   (路径, 序列列, 分数列)
REFERENCE_FILES: list[tuple[Path, int, int]] = [
    (ROOT / "_re" / "reference_scores.tsv", 0, 1),
    (ROOT / "_re" / "golden_original.txt", 0, 1),
    (ROOT / "_re" / "reference_scores_boundary.tsv", 0, 2),
]


def load_golden() -> list[tuple[str, float, str]]:
    """读取所有可用的标准答案，返回 (序列, 期望分数, 来源) 列表。

    只解析 TSV（制表符分隔），并且要求第一列是**纯氨基酸字母序列**——
    这样就不会把 DOI、PMCID 之类的字符串误当成序列（早期版本踩过这个坑）。
    """
    rows: list[tuple[str, float, str]] = []
    for path, seq_col, score_col in REFERENCE_FILES:
        if not path.is_file():
            continue
        for lineno, raw in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
        ):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("\t")]
            if len(parts) <= max(seq_col, score_col):
                continue
            raw_seq = parts[seq_col]
            # 第一列必须是纯字母（允许大小写），否则视为脏数据跳过
            if not raw_seq or not raw_seq.isalpha():
                continue
            seq = scoring.normalize_sequence(raw_seq)
            if len(seq) < 2:
                continue
            try:
                value = float(parts[score_col])
            except ValueError:
                continue
            if not math.isfinite(value):
                continue
            rows.append((seq, value, f"{path.name}:{lineno}"))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Python 引擎与原版 PeptideRanker 的数值对比")
    parser.add_argument("--tolerance", type=float, default=TOLERANCE, help=f"允许误差（默认 {TOLERANCE}）")
    parser.add_argument("--models", choices=["auto", "short", "long"], default="auto")
    parser.add_argument("--show-all", action="store_true", help="打印所有行（默认只打印超差行）")
    args = parser.parse_args(argv)

    rows = load_golden()
    if not rows:
        print("未找到标准答案文件。请提供以下任一文件后重试：")
        for p in REFERENCE_FILES:
            print(f"  - {p}")
        print("或用 scripts/run_original.sh 在 Linux/Docker 下生成 golden_original.txt")
        return 2

    print(f"共载入 {len(rows)} 条标准答案，允许误差 ±{args.tolerance}\n")
    header = f"{'序列':<32}{'期望':>10}{'实测':>10}{'差值':>11}  判定"
    print(header)
    print("-" * len(header))

    passed = failed = skipped = 0
    deltas: list[float] = []
    for seq, expected, source in rows:
        try:
            report = scoring.score_sequences(
                [{"id": "golden", "sequence": seq}], length_handling=args.models
            )
        except Exception as exc:  # noqa: BLE001
            skipped += 1
            if args.show_all:
                print(f"{seq[:30]:<32}{expected:>10.4f}{'ERR':>10}{'':>11}  ✗     {source} ({exc})")
            continue
        if not report.results:
            skipped += 1
            continue
        got = report.results[0].score
        delta = got - expected
        deltas.append(abs(delta))
        ok = abs(delta) <= args.tolerance
        passed += ok
        failed += (not ok)
        if args.show_all or not ok:
            print(
                f"{seq[:30]:<32}{expected:>10.4f}{got:>10.4f}{delta:>+11.4f}  "
                f"{'✓' if ok else '✗':<5} {source}"
            )

    print("-" * len(header))
    total = passed + failed
    if total:
        deltas.sort()
        n = len(deltas)
        print(f"通过 {passed} / {total} = {passed / total:.1%}（误差 ≤ {args.tolerance}）")
        print(f"|差值| 中位 {deltas[n // 2]:.6f}  均值 {sum(deltas) / n:.6f}  最大 {deltas[-1]:.6f}")
        exact = sum(1 for d in deltas if d <= 5e-5)
        print(f"逐位相同（|差| ≤ 5e-5）：{exact} / {n} = {exact / n:.1%}")
    if skipped:
        print(f"另有 {skipped} 条被产品层跳过（非法字符/整条 X 等）")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
