"""区分"真实肽序列的偏差"与"抓取到的三字母缩写/蛋白名等脏数据"。

动机：文献表格里的行不全是单字母肽序列——常见脏数据包括
  * 三字母氨基酸缩写拼接：PHEHIS、METTYR、ALAGLYPHE
  * 蛋白质/酶名称：PAPAIN、PEPTIDE、ACEI、DPPIV
  * 带数字/小写/其他字符的行
这些行不该算作"引擎算错"，但必须把它们单独列出来，避免污染校验结论。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pr_engine import scoring  # noqa: E402

THREE_LETTER = {
    "ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY", "HIS", "ILE",
    "LEU", "LYS", "MET", "PHE", "PRO", "SER", "THR", "TRP", "TYR", "VAL",
    "ASX", "GLX", "SEC", "PYL", "UNK",
}
NON_SEQUENCE_WORDS = {
    "ACEI", "ACE", "PAPAIN", "PEPTIDE", "PEPTIDES", "DPPIV", "DPP", "PROTEIN",
    "SUBSTRATE", "INHIBITOR", "CONTROL", "SAMPLE", "TOTAL", "AVERAGE", "MEAN",
}


def looks_like_three_letter_code(seq: str) -> bool:
    """整串能被切成若干个三字母氨基酸缩写 → 是缩写而非单字母序列。"""
    if len(seq) < 3 or len(seq) % 3 != 0:
        return False
    return all(seq[i:i + 3] in THREE_LETTER for i in range(0, len(seq), 3))


def classify(seq: str, expected: float, got: float, tol: float = 0.01) -> str:
    if abs(got - expected) <= tol:
        return "ok"
    if seq in NON_SEQUENCE_WORDS or looks_like_three_letter_code(seq):
        return "junk"
    return "real"


def main() -> int:
    sys.path.insert(0, str(ROOT / "scripts"))
    from validate_published import read_rows  # type: ignore

    rows = read_rows(ROOT / "_re" / "reference_scores.tsv", has_length=False)
    buckets: dict[str, list[tuple[str, float, float]]] = {"ok": [], "junk": [], "real": []}
    for seq, expected, _src in rows:
        rep = scoring.score_sequences([{"id": "x", "sequence": seq}])
        got = rep.results[0].score if rep.results else float("nan")
        buckets[classify(seq, expected, got)].append((seq, expected, got))

    total = len(rows)
    print("=" * 100)
    print(f"总行数 {total}")
    print("=" * 100)
    print(f"  ✅ 在 ±0.01 内吻合          : {len(buckets['ok'])}")
    print(f"  🗑 脏数据（非单字母序列）   : {len(buckets['junk'])}")
    print(f"  ❌ 看起来是真实序列但超差   : {len(buckets['real'])}")

    effective = len(buckets["ok"]) + len(buckets["real"])
    if effective:
        print(f"\n  剔除脏数据后的有效通过率：{len(buckets['ok'])} / {effective} "
              f"= {len(buckets['ok']) / effective:.1%}")

    if buckets["junk"]:
        print()
        print("  脏数据示例（前 20 条）：")
        for seq, exp, got in buckets["junk"][:20]:
            print(f"    {seq:<28} 文献={exp:<10.6f} 引擎={got:<10.6f}")

    if buckets["real"]:
        print()
        print("  ⚠ 真实序列但超差（需要逐条排查）：")
        for seq, exp, got in sorted(buckets["real"], key=lambda x: -abs(x[2] - x[1]))[:30]:
            print(f"    {seq:<34} len={len(seq):<3} 文献={exp:<10.6f} 引擎={got:<10.6f} Δ={abs(got - exp):.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
