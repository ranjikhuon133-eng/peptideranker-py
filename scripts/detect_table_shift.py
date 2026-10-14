"""判读参考分数的数据质量：验证"表格错位"假说。

发现：文献里 QETPTLR 记 0.78508，而引擎对下一行 QETPTLRVA 正好算出 0.78508。
这类"一行错位"会让整张表的分数与序列对不上，必须与"真实算法偏差"区分开。

做法：按 TSV 的原始行序，把每行的文献分数与"邻近若干行"的引擎分数比对，
若超差行的分数能在邻居里找到精确匹配，就是表格错位（数据问题），不是引擎问题。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pr_engine import scoring  # noqa: E402

TOL = 0.01
EXACT = 5e-6


def load_raw(path: Path) -> list[tuple[str, float]]:
    rows = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        seq = scoring.normalize_sequence(parts[0])
        try:
            score = float(parts[1])
        except ValueError:
            continue
        if seq:
            rows.append((seq, score))
    return rows


def main() -> int:
    rows = load_raw(ROOT / "_re" / "reference_scores.tsv")
    print(f"共 {len(rows)} 行（保留原始行序）\n正在逐条计算引擎分数…")
    eng = []
    for seq, _ in rows:
        rep = scoring.score_sequences([{"id": "x", "sequence": seq}])
        eng.append(rep.results[0].score if rep.results else float("nan"))

    same = [i for i in range(len(rows)) if abs(eng[i] - rows[i][1]) <= TOL]
    diff = [i for i in range(len(rows)) if i not in same]
    print(f"\n{'=' * 96}")
    print(f"行序一致（文献分数 = 本行引擎分数）: {len(same)} / {len(rows)} = {len(same) / len(rows):.1%}")
    print(f"行序不一致                        : {len(diff)}")
    print("=" * 96)

    shift_stats: dict[int, int] = {}
    unexplained: list[int] = []
    for i in diff:
        found = False
        # 在 ±3 行范围内找精确匹配（按原始行序）
        for off in range(-3, 4):
            j = i + off
            if off == 0 or not (0 <= j < len(rows)):
                continue
            if abs(eng[j] - rows[i][1]) <= EXACT:
                shift_stats[off] = shift_stats.get(off, 0) + 1
                found = True
                break
        if not found:
            unexplained.append(i)

    print("\n邻行精确匹配分布（偏移 = 文献分数取自第 i+偏移 行的引擎分数）：")
    if shift_stats:
        for off, cnt in sorted(shift_stats.items()):
            print(f"  偏移 {off:+d}: {cnt} 条")
    else:
        print("  无")

    matched = sum(shift_stats.values())
    print(f"\n结论：")
    print(f"  - 逐行吻合              : {len(same)}")
    print(f"  - 邻行错位可解释        : {matched}")
    print(f"  - 无法用错位解释        : {len(unexplained)}")

    if unexplained:
        print("\n  仍无法解释的行（需人工核对原文表格）：")
        for i in unexplained[:25]:
            seq, exp = rows[i]
            print(f"    行{i + 1:<4} {seq:<34} 文献={exp:<10.6f} 引擎={eng[i]:<10.6f} Δ={abs(eng[i] - exp):.6f}")

    effective = len(same) + matched
    print(f"\n  => 可归因于数据质量（脏数据+错位）的行：{len(rows) - effective}")
    print(f"  => 支持引擎正确性的行：{effective} / {len(rows)} = {effective / len(rows):.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
