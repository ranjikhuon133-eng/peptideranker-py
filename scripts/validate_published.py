"""用公开文献里的**原版服务器分数**校验我们的引擎，并判定 20aa 边界归属。

数据来源：
  _re/reference_scores.tsv           原版 distille deep.ucd.ie/PeptideRanker 的输出（679 条）
  _re/reference_scores_boundary.tsv  长度 17~23 的边界探针（50 条，含 10 条正好 20aa）

判定 20aa 边界的方法：对每条长度正好 20 的序列，分别用短肽模型和长肽模型各算一次，
看哪一个与文献分数吻合，从而用外部证据回答"<=20 → Short"还是"<20 → Short"。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pr_engine import scoring  # noqa: E402

TOL = 0.01


def read_rows(path: Path, has_length: bool) -> list[tuple[str, float, str]]:
    rows = []
    if not path.is_file():
        return rows
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        seq = scoring.normalize_sequence(parts[0])
        idx = 2 if has_length else 1
        try:
            score = float(parts[idx])
        except (ValueError, IndexError):
            continue
        src = parts[-1] if len(parts) > idx + 1 else ""
        if seq:
            rows.append((seq, score, src))
    return rows


def score_one(seq: str, kind: str | None = None) -> float:
    rep = scoring.score_sequences(
        [{"id": "x", "sequence": seq}],
        length_handling=kind or "auto",
    )
    if not rep.results:
        raise RuntimeError("; ".join(rep.warnings) or "被跳过")
    return rep.results[0].score


def main() -> int:
    rows = read_rows(ROOT / "_re" / "reference_scores.tsv", has_length=False)
    print("=" * 100)
    print(f"主校验集：{len(rows)} 条公开文献中的原版 PeptideRanker 分数，容差 ±{TOL}")
    print("=" * 100)
    if not rows:
        print("未找到 _re/reference_scores.tsv")
        return 2

    deltas: list[float] = []
    worst: list[tuple[float, str, float, float, str]] = []
    passed = failed = 0
    short_rows = long_rows = 0
    for seq, expected, src in rows:
        if len(seq) <= 20:
            short_rows += 1
        else:
            long_rows += 1
        try:
            got = score_one(seq)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            worst.append((9.9, seq, expected, float("nan"), f"ERROR {exc}"))
            continue
        d = got - expected
        deltas.append(abs(d))
        if abs(d) <= TOL:
            passed += 1
        else:
            failed += 1
            worst.append((abs(d), seq, expected, got, src))

    if deltas:
        deltas_sorted = sorted(deltas)
        n = len(deltas_sorted)
        print(f"  样本构成：短肽(<=20aa) {short_rows} 条 / 长肽(>20aa) {long_rows} 条")
        print(f"  通过 {passed} / {passed + failed}  ({passed / (passed + failed):.1%})")
        print(f"  |差值| 中位 {deltas_sorted[n // 2]:.6f}  均值 {sum(deltas_sorted) / n:.6f}  "
              f"p90 {deltas_sorted[int(n * 0.9)]:.6f}  最大 {deltas_sorted[-1]:.6f}")

    worst.sort(reverse=True)
    if worst:
        print()
        print("  偏差最大的 15 条：")
        print("  %-32s %10s %10s %10s  %s" % ("序列", "文献", "引擎", "差值", "来源"))
        for d, seq, exp, got, src in worst[:15]:
            got_txt = "ERR" if got != got else f"{got:.6f}"
            print("  %-32s %10.6f %10s %10.6f  %s" % (seq[:32], exp, got_txt, d if d != 9.9 else float("nan"), src[:40]))

    # ---------------------------------------------------------------- #
    # 20aa 边界判定
    # ---------------------------------------------------------------- #
    boundary = read_rows(ROOT / "_re" / "reference_scores_boundary.tsv", has_length=True)
    twenty = [r for r in boundary if len(r[0]) == 20]
    print()
    print("=" * 100)
    print(f"20aa 边界判定：边界集 {len(boundary)} 条，其中长度正好 20 的 {len(twenty)} 条")
    print("=" * 100)
    if twenty:
        print("  %-24s %9s %11s %11s   %s" % ("序列", "文献", "Short模型", "Long模型", "更接近哪个"))
        short_hits = long_hits = 0
        for seq, expected, _src in twenty:
            try:
                s_short = score_one(seq, "short")
                s_long = score_one(seq, "long")
            except Exception as exc:  # noqa: BLE001
                print("  %-24s %9.6f  失败：%s" % (seq, expected, exc))
                continue
            d_short, d_long = abs(s_short - expected), abs(s_long - expected)
            if d_short <= TOL:
                short_hits += 1
            if d_long <= TOL:
                long_hits += 1
            verdict = "Short" if d_short < d_long else "Long"
            print("  %-24s %9.6f %11.6f %11.6f   %s (Δshort=%.4f Δlong=%.4f)"
                  % (seq, expected, s_short, s_long, verdict, d_short, d_long))
        print()
        print(f"  在 ±{TOL} 内吻合：Short 模型 {short_hits}/{len(twenty)}，Long 模型 {long_hits}/{len(twenty)}")
        if short_hits > long_hits:
            print("  => 外部证据支持 **<=20 → Short**（与 PeptideRanker.pl 第 30 行一致，本应用已采用）")
        elif long_hits > short_hits:
            print("  => 外部证据支持 **<20 → Short, 20 → Long**（与论文正文一致）—— 需要改路由！")
        else:
            print("  => 两种路由打平，边界无法判定")
    else:
        print("  未找到长度正好 20 的探针。")

    print()
    ok = failed == 0
    print(f"主校验集结论：{'全部通过' if ok else f'{failed} 条超出容差'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
