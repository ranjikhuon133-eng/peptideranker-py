"""分布合理性检验：用随机序列检查引擎输出是否有判别力。

一个可用的肽活性预测器应当满足：
  - 随机序列的分数分布**大部分 < 0.5**（原论文以 0.5 为阈值）
  - 已知活性肽（如缓激肽 RPPGFSPFR）应当明显高于随机序列
  - 分数不应全部挤在 1.0 附近（说明激活/归一化写错）

如果随机序列也普遍 >0.9，说明复刻里某处（很可能是长肽 profile 路径或
归一化）有错，需要回去对着反汇编查。
"""

from __future__ import annotations

import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pr_engine import scoring  # noqa: E402

AA = "ACDEFGHIKLMNPQRSTVWY"
SEED = 20261012


def make_random(length: int, count: int, rng: random.Random) -> list[dict]:
    return [
        {"id": f"rnd{length}_{i}", "sequence": "".join(rng.choice(AA) for _ in range(length))}
        for i in range(count)
    ]


def describe(label: str, scores: list[float]) -> None:
    if not scores:
        print(f"{label:<28} 无数据")
        return
    above = sum(1 for s in scores if s >= 0.5)
    print(
        f"{label:<28} n={len(scores):<4} 平均={statistics.fmean(scores):.3f} "
        f"中位={statistics.median(scores):.3f} 最小={min(scores):.3f} 最大={max(scores):.3f} "
        f"≥0.5 占比={above / len(scores):.0%}"
    )


def main() -> int:
    rng = random.Random(SEED)

    print("=" * 100)
    print("随机序列分布（多组长度，每组 200 条）")
    print("=" * 100)
    for length in (8, 12, 15, 20, 25, 35, 50):
        items = make_random(length, 200, rng)
        report = scoring.score_sequences(items)
        describe(f"随机 {length} 肽", [r.score for r in report.results])

    print()
    print("=" * 100)
    print("已知活性肽 vs 随机序列")
    print("=" * 100)
    known = [
        ("缓激肽 RPPGFSPFR", "RPPGFSPFR"),
        ("示例 ILPILSLIGGLL", "ILPILSLIGGLL"),
        ("示例 ALLHHGLNCAKGVLA", "ALLHHGLNCAKGVLA"),
        ("示例 FLSLALAALPKLFCLIFKKC", "FLSLALAALPKLFCLIFKKC"),
    ]
    report = scoring.score_sequences([{"id": name, "sequence": seq} for name, seq in known])
    known_scores = {r.id: r.score for r in report.results}
    for name, _ in known:
        print(f"  {name:<34} {known_scores.get(name, float('nan')):.4f}")

    rnd_short = [r.score for r in scoring.score_sequences(make_random(10, 300, rng)).results]
    rnd_long = [r.score for r in scoring.score_sequences(make_random(40, 300, rng)).results]
    describe("随机 10 肽", rnd_short)
    describe("随机 40 肽", rnd_long)

    print()
    print("=" * 100)
    print("判定")
    print("=" * 100)
    problems: list[str] = []
    frac_short = sum(1 for s in rnd_short if s >= 0.5) / len(rnd_short)
    frac_long = sum(1 for s in rnd_long if s >= 0.5) / len(rnd_long)
    mean_short = statistics.fmean(rnd_short)
    mean_long = statistics.fmean(rnd_long)

    print(f"随机短肽 ≥0.5 占比 {frac_short:.0%}，平均 {mean_short:.3f}")
    print(f"随机长肽 ≥0.5 占比 {frac_long:.0%}，平均 {mean_long:.3f}")

    if frac_short > 0.5:
        problems.append(f"随机短肽有 {frac_short:.0%} 被判为阳性（阈值语义可能不对）")
    if frac_long > 0.5:
        problems.append(f"随机长肽有 {frac_long:.0%} 被判为阳性（长肽 profile 路径很可能有错）")
    if mean_long > 0.8:
        problems.append(f"随机长肽平均分 {mean_long:.3f} 过高，疑似长肽路径归一化/拼接有错")
    if mean_short > 0.8:
        problems.append(f"随机短肽平均分 {mean_short:.3f} 过高，疑似前向有错")

    brady = known_scores.get("缓激肽 RPPGFSPFR")
    if brady is not None and brady <= mean_short:
        problems.append(f"缓激肽分数 {brady:.3f} 未高于随机短肽平均 {mean_short:.3f}，判别力可疑")

    if problems:
        print()
        for p in problems:
            print(f"  [!] {p}")
        return 1
    print("  分布合理：随机序列多数 <0.5，活性肽明显更高。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
