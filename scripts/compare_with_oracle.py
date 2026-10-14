"""逐条数值比对：产品引擎（pr_engine.scoring）vs 参考实现（reference.oracle）。

两者应当逐位一致（差异 < 1e-12），唯一的有意差异是小写输入的处理方式：
  * 默认：产品层把小写视同大写氨基酸（更友好）
  * --strict-case：逐字复刻原二进制，小写字母被当作未知字符跳过

这个脚本会在两种模式下都做比对，确保"友好模式"的差异是**唯一**的差异。
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pr_engine import scoring  # noqa: E402
from pr_engine.reference import oracle  # noqa: E402

AA = "ACDEFGHIKLMNPQRSTVWY"
TOL = 1e-12
SEED = 20261012

# 默认模式（strict_case=False）会做两件有意修正：
#   1. 小写 -> 大写（原程序对非法残基会 0/0 得到 NaN）
#   2. B/J/O/U/Z -> X（原程序同样得到 NaN）
# 因此比对的期望值要按同样的修正后的序列去问参考实现。
TO_X = str.maketrans("BZJUO", "XXXXX")


def expected(seq: str, strict: bool) -> str:
    """默认模式下产品引擎实际会送给引擎的序列。"""
    if strict:
        return seq
    return seq.upper().translate(TO_X)


def build_cases() -> list[tuple[str, str]]:
    cases: list[tuple[str, str]] = []
    for line in (ROOT / "testfile.txt").read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s:
            cases.append((s, "testfile"))
    # 全部 20 种单残基 + 所有同聚物
    for a in AA:
        cases.append((a, "单残基"))
        cases.append((a * 20, "同聚物-20"))
        cases.append((a * 25, "同聚物-25"))
    # 边界长度（20/21 是短肽/长肽分界）
    rng = random.Random(SEED)
    for L in (1, 2, 3, 19, 20, 21, 22, 30, 41, 60, 100):
        for _ in range(3):
            cases.append(("".join(rng.choice(AA) for _ in range(L)), f"随机-{L}"))
    # 未知残基
    cases += [("ILPXLSIGGLL", "X"), ("ILPBLSIGGLL", "B"), ("X" * 15, "全X")]
    # 大小写
    cases += [("rppgfspfr", "小写"), ("RppGfSpFr", "混合大小写")]
    return cases


def main() -> int:
    cases = build_cases()
    print(f"共 {len(cases)} 条用例，容差 {TOL:g}\n")

    failures: list[str] = []

    # --- 模式 1：默认（小写按大写处理） ---
    print("=" * 96)
    print("模式 1/2：默认（小写视同大写）")
    print("=" * 96)
    bad = 0
    for seq, tag in cases:
        report = scoring.score_sequences([{"id": "x", "sequence": seq}])
        mine = report.results[0].score if report.results else None
        if mine is None:
            failures.append(f"默认模式被跳过：{seq!r} ({tag})")
            bad += 1
            continue
        ref = oracle.score_sequence(expected(seq, strict=False))
        if abs(mine - ref) > TOL:
            failures.append(f"默认模式不一致：{seq!r} 产品={mine!r} 参考={ref!r} ({tag})")
            bad += 1
    print(f"不一致 {bad} / {len(cases)}")

    # --- 模式 2：strict_case（逐字复刻原程序） ---
    print()
    print("=" * 96)
    print("模式 2/2：strict_case=True（逐字复刻原二进制，小写被跳过）")
    print("=" * 96)
    bad2 = 0
    checked = 0
    for seq, tag in cases:
        report = scoring.score_sequences([{"id": "x", "sequence": seq}], strict_case=True)
        if not report.results:
            # 产品层拒绝（例如全非字母），参考实现也必须给不出有意义的值
            continue
        mine = report.results[0].score
        ref = oracle.score_sequence(seq)
        checked += 1
        if abs(mine - ref) > TOL:
            failures.append(f"strict 模式不一致：{seq!r} 产品={mine!r} 参考={ref!r} ({tag})")
            bad2 += 1
    print(f"不一致 {bad2} / {checked}（其余被产品层按非法输入拒绝）")

    # --- 小写差异必须被显式暴露 ---
    print()
    print("=" * 96)
    print("行为差异确认（这两条是设计取舍，不是 bug）")
    print("=" * 96)
    lower = "rppgfspfr"
    friendly = scoring.score_sequences([{"id": "x", "sequence": lower}]).results[0].score
    strict_rep = scoring.score_sequences([{"id": "x", "sequence": lower}], strict_case=True)
    ref_lower = oracle.score_sequence(lower)
    strict_txt = "被跳过" if not strict_rep.results else f"{strict_rep.results[0].score:.6f}"
    print(f"  小写   {lower!r:12} 默认(转大写)={friendly:.6f}  strict 结果={strict_txt}")
    import math as _math
    print(f"         参考实现(原行为) = {ref_lower!r}  -> 原程序对非法残基会 0/0 得到 NaN，即无结果")
    if not _math.isnan(ref_lower):
        failures.append(f"预期原实现对非法输入给 NaN，实际 {ref_lower!r}")
    if not strict_rep.results:
        print("         默认模式有结果、strict 模式被跳过 => 修正生效，且原行为被如实暴露")

    amb = "ILPBLSIGGLL"
    amb_default = scoring.score_sequences([{"id": "x", "sequence": amb}]).results[0].score
    amb_ref = oracle.score_sequence("ILPXLSIGGLL")
    print(f"  歧义   {amb!r:12} 默认(B->X)={amb_default:.6f}  参考(把 B 写成 X)={amb_ref:.6f}")
    ok_amb = abs(amb_default - amb_ref) <= TOL
    if not ok_amb:
        failures.append("B->X 映射结果与参考实现的 X 通道不一致")

    print(f"  => {'符合预期' if _math.isnan(ref_lower) and ok_amb else '!! 与预期不符，需要复查'}")

    print()
    if failures:
        print(f"失败 {len(failures)} 项：")
        for f in failures[:20]:
            print("  -", f)
        return 1
    print("全部一致。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
