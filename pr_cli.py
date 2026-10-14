"""PeptideRanker 命令行批量打分（与网页共用同一个 Python 引擎）。

示例：
    python pr_cli.py testfile.txt
    python pr_cli.py testfile.txt -o scores.csv
    python pr_cli.py --sequence ILPILSLIGGLL RPPGFSPFR
    type testfile.txt | python pr_cli.py -
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pr_engine import scoring  # noqa: E402


def _read_input(path: str, strict: bool = False) -> tuple[list, list[str]]:
    if path == "-":
        text = sys.stdin.read()
        items, warnings = scoring.parse_sequences(text, strict=strict)
        return [{"id": it.id, "sequence": it.sequence} for it in items], warnings
    p = Path(path)
    if not p.is_file():
        raise SystemExit(f"[错误] 找不到输入文件：{path}")
    text = p.read_text(encoding="utf-8", errors="replace")
    items, warnings = scoring.parse_sequences(text, strict=strict)
    return [{"id": it.id, "sequence": it.sequence} for it in items], warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="PeptideRanker 批量打分（纯 Python 引擎，无需 Linux 二进制）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input", nargs="?", help="输入文件（txt/fasta/csv），- 表示标准输入")
    parser.add_argument("--sequence", "-s", nargs="+", help="直接给定一条或多条序列")
    parser.add_argument("--out", "-o", help="输出 CSV 路径（默认打印到屏幕）")
    parser.add_argument(
        "--length-handling",
        choices=["auto", "short", "long"],
        default="auto",
        help="长度处理策略：auto（<=20 用短肽模型，默认）/ short / long",
    )
    parser.add_argument("--threshold", "-t", type=float, default=scoring.DEFAULT_THRESHOLD,
                        help=f"判定阈值（默认 {scoring.DEFAULT_THRESHOLD}）")
    parser.add_argument("--quiet", "-q", action="store_true", help="不打印警告")
    parser.add_argument(
        "--strict-case",
        action="store_true",
        help="逐字复刻原二进制的大小写行为（小写字母会被当成未知字符跳过；默认把小写视为大写氨基酸）",
    )
    args = parser.parse_args(argv)

    if args.sequence:
        items = [{"id": f"seq{i}", "sequence": s} for i, s in enumerate(args.sequence, start=1)]
        warnings: list[str] = []
    elif args.input:
        items, warnings = _read_input(args.input, strict=args.strict_case)
    else:
        parser.print_help()
        return 2

    if not items:
        print("[错误] 没有可打分的序列。", file=sys.stderr)
        return 2

    try:
        report = scoring.score_sequences(
            items, length_handling=args.length_handling, strict_case=args.strict_case
        )
    except scoring.EngineNotReady as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 3

    report.warnings = warnings + report.warnings
    if not args.quiet:
        for w in report.warnings:
            print(f"[警告] {w}", file=sys.stderr)

    if args.out:
        Path(args.out).write_text(scoring.results_to_csv(report), encoding="utf-8")
        print(f"已写入 {args.out}（{len(report.results)} 条）")
        return 0

    summary = report.as_dict()["summary"]
    print(f"{'排名':<5}{'分数':<10}{'长度':<6}{'模型':<7}序列")
    print("-" * 72)
    for r in report.results:
        flag = " *" if r.score >= args.threshold else ""
        print(f"{r.rank:<5}{r.score:<10.4f}{r.length:<6}{r.model:<7}{r.sequence}{flag}")
    print("-" * 72)
    print(
        f"共 {summary['count']} 条 | 平均 {summary['mean']:.4f} | 中位 {summary['median']:.4f} | "
        f"最高 {summary['max']:.4f} | ≥{args.threshold} 的 {summary['n_above_threshold']} 条 | "
        f"耗时 {report.elapsed_ms} ms"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
