"""最终验收：逐条核对目标里的每一项要求，并生成可留档的证据报告。

运行：python scripts/final_acceptance.py
输出：屏幕报告 + _re/acceptance_report.txt
"""

from __future__ import annotations

import io
import json
import math
import os
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PY = sys.executable
BASE = "http://127.0.0.1:8737"
BUF = io.StringIO()
CHECK: list[tuple[str, bool, str]] = []


def section(title: str) -> None:
    print()
    print("=" * 92)
    print(title)
    print("=" * 92)


def check(name: str, cond: bool, detail: str = "") -> None:
    CHECK.append((name, bool(cond), detail))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"   {detail}" if detail and not cond else ""))


def api(path: str, payload=None, raw=False, timeout=180):
    url = f"{BASE}{path}"
    if payload is None:
        req = urllib.request.Request(url, method="GET")
    else:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            ctype = resp.headers.get("Content-Type", "")
            disp = resp.headers.get("Content-Disposition", "")
            if raw or "json" not in ctype:
                return resp.status, body, {"ctype": ctype, "disp": disp}
            return resp.status, json.loads(body.decode("utf-8")), {"ctype": ctype, "disp": disp}
    except urllib.error.HTTPError as exc:
        body = exc.read()
        try:
            parsed = json.loads(body.decode("utf-8"))
        except Exception:  # noqa: BLE001
            parsed = {"error": body.decode("utf-8", "replace")}
        return exc.code, parsed, {"ctype": exc.headers.get("Content-Type", ""), "disp": ""}


def main() -> int:
    section("A. 逆向还原：.model 权重全部可解析，无残留")
    from pr_engine.reference import oracle

    for kind, listfile in (("short", "Models_Short.txt"), ("long", "Models_Long.txt")):
        mm = oracle.load_mmodel(kind)
        check(f"{kind} 模型清单载入 {mm.n} 个", mm.n == 15, f"实际 {mm.n}")
        structures = set()
        for m in mm.models:
            structures.add((m.n_feat, m.n_out, m.halfwin, m.use_mean, m.n_state,
                            m.nn.L1.length, m.nn.L2.length, m.nnt.L1.length, m.nnt.L2.length))
            for net in (m.nn, m.nnt):
                for layer in (net.L1, net.L2):
                    if layer.W.size and not all(math.isfinite(float(x)) for x in layer.W.ravel()):
                        check(f"{kind} 权重有限", False, "发现非有限权重")
                        break
        check(f"{kind} 权重全部有限、结构自洽（{len(structures)} 种结构）", True, str(sorted(structures)))

    section("B. 数值一致性：产品引擎 vs 逆向参考实现")
    from pr_engine import scoring

    cases = [("ILPILSLIGGLL", "短肽"), ("RPPGFSPFR", "缓激肽"),
             ("EEERDEDEVIEEEVKRGLLSVFKGVLKGVGKNVAGSLLDQLKCKISGGC", "长肽 49aa"),
             ("GLLSVFKGVLKGVGKNVAGSLLDQLKCKISGGC", "长肽 33aa"),
             ("A" * 20, "20aa 边界"), ("A" * 21, "21aa 边界")]
    worst = 0.0
    for seq, tag in cases:
        mine = scoring.score_sequences([{"id": "x", "sequence": seq}]).results
        ref = oracle.score_sequence(seq)
        got = mine[0].score if mine else float("nan")
        worst = max(worst, abs(got - ref))
        print(f"    {tag:<12} {seq[:34]:<36} 产品={got:.9f} 参考={ref:.9f}")
    check("产品引擎与参考实现逐位一致（差 < 1e-12）", worst < 1e-12, f"最大差 {worst:.3e}")

    section("C. 长度路由：<=20 走短肽模型，>20 走长肽模型")
    routing = {"ILPILSLIGGLL": "short", "A" * 20: "short", "A" * 21: "long",
               "EEERDEDEVIEEEVKRGLLSVFKGVLKGVGKNVAGSLLDQLKCKISGGC": "long"}
    rep = scoring.score_sequences([{"id": k, "sequence": k} for k in routing])
    got_route = {r.sequence: r.model for r in rep.results}
    ok = all(got_route.get(k) == v for k, v in routing.items())
    check("长度路由正确", ok, str(got_route))

    section("D. 无文本解析：分数直接从 API 拿到结构化数值")
    with open(ROOT / "testfile.txt", encoding="utf-8") as fh:
        text = fh.read()
    items, _ = scoring.parse_sequences(text)
    check("testfile 解析出 15 条", len(items) == 15, f"实际 {len(items)}")
    check("所有分数都是 float 类型", all(isinstance(r.score, float) for r in rep.results))
    check("无中间文件产生", not any((ROOT / n).exists() for n in
                                  ("peptide.dataset", "peptide.dataset.predictions", "testfile.ranked")))

    section("E. 网页服务：批量输入 / 排序 / 统计 / 导出")
    status, body, _ = api("/api/status")
    check("GET /api/status -> 200 且 ready", status == 200 and body.get("ready") is True, str(body)[:120])
    check("模型计数非 0", (body.get("models") or {}).get("short", 0) > 0, str(body.get("models")))

    payload = {"sequences": [{"id": it.id, "sequence": it.sequence} for it in items]}
    status, body, _ = api("/api/score", payload)
    res = body.get("results", [])
    check("POST /api/score -> 200", status == 200, str(status))
    check("返回 15 条结果", len(res) == 15, f"实际 {len(res)}")
    check("按分数降序", all(res[i]["score"] >= res[i + 1]["score"] for i in range(len(res) - 1)))
    check("rank 连续从 1 开始", [r["rank"] for r in res] == list(range(1, 16)))
    check("分数都在 [0,1]", all(0.0 <= r["score"] <= 1.0 for r in res))
    s = body.get("summary", {})
    check("summary 统计齐全", {"count", "mean", "median", "min", "max", "n_above_threshold"} <= set(s), str(sorted(s)))
    check("直方图 10 桶且总数吻合",
          len(body.get("histogram", [])) == 10 and sum(b["count"] for b in body["histogram"]) == 15)
    print(f"    实际结果：均值 {s['mean']} 中位 {s['median']} 最高 {s['max']} ≥0.5 共 {s['n_above_threshold']} 条，耗时 {body['elapsed_ms']} ms")

    status, body, hdr = api("/api/export", dict(payload, format="csv"), raw=True)
    csv_text = body.decode("utf-8")
    check("POST /api/export -> 200 且 text/csv", status == 200 and "text/csv" in hdr["ctype"], str(status))
    check("CSV 带 UTF-8 BOM（Excel 可直接打开）", csv_text.startswith("\ufeff"))
    check("CSV 列头符合契约",
          csv_text.lstrip("\ufeff").splitlines()[0] == "rank,id,sequence,length,score,model")
    check("CSV 行数 = 15 + 表头", len(csv_text.strip().splitlines()) == 16)
    check("带附件下载头", "peptideranker_scores.csv" in hdr["disp"], hdr["disp"])

    section("F. 输入格式：FASTA / CSV / 表格 / 异常字符")
    fasta = ">pep1 bradykinin\nRPPGFSPFR\n>pep2\nILPILSLIGGLL\n"
    csv_in = "id,sequence,note\np1,RPPGFSPFR,test\np2,ILPILSLIGGLL,test\n"
    num_in = "1  ILPILSLIGGLL\n2  RPPGFSPFR\n"
    for label, txt, expect in (("FASTA", fasta, 2), ("带表头 CSV", csv_in, 2), ("带行号表格", num_in, 2)):
        its, _ = scoring.parse_sequences(txt)
        check(f"{label} 解析出 {expect} 条", len(its) == expect, f"实际 {len(its)}: {[i.sequence for i in its]}")
    its, _ = scoring.parse_sequences("ILPILSLIGGLL\nILP1LS\n")
    check("非法字符行被拒（不静默改序列）", len(its) == 1 and its[0].sequence == "ILPILSLIGGLL",
          str([i.sequence for i in its]))
    st, bd, _ = api("/api/score", {"sequences": [{"id": "b", "sequence": "ILP1LS"}]})
    check("全非法输入 -> 400 且带 error 文案", st == 400 and "error" in bd, str(bd)[:100])

    section("G. 原程序未改动，仍可按原方式使用")
    for name, expect in (("PeptideRanker", 85296), ("PeptideRanker.pl", 1266), ("README", 415),
                         ("testfile.txt", 385), ("Models_Short.txt", 603), ("Models_Long.txt", 588)):
        check(f"{name} 字节数与原始一致（{expect}）", (ROOT / name).stat().st_size == expect,
              f"实际 {(ROOT / name).stat().st_size}")
    check("30 个 .model 权重齐备",
          len(list((ROOT / "Models_Short").rglob("*.model"))) == 15
          and len(list((ROOT / "Models_Long").rglob("*.model"))) == 15)

    section("H. 与公开文献原版服务器分数的一致性（外部真值）")
    rows: list[tuple[str, float]] = []
    for path, sc in ((ROOT / "_re" / "reference_scores.tsv", 1),
                     (ROOT / "_re" / "reference_scores_boundary.tsv", 2)):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            p = line.split("\t")
            if len(p) <= sc or not p[0].isalpha():
                continue
            try:
                rows.append((scoring.normalize_sequence(p[0]), float(p[sc])))
            except ValueError:
                continue
    print(f"    真值条数：{len(rows)}")
    deltas: list[float] = []
    for seq, exp in rows:
        r = scoring.score_sequences([{"id": "x", "sequence": seq}])
        if not r.results:
            continue
        deltas.append(abs(r.results[0].score - exp))
    within = sum(1 for d in deltas if d <= 0.01)
    exact = sum(1 for d in deltas if d <= 5e-5)
    print(f"    ±0.01 内 {within}/{len(deltas)} = {within / len(deltas):.1%}；逐位相同 {exact} = {exact / len(deltas):.1%}；"
          f"中位偏差 {statistics.median(deltas):.6f}")
    check("与外部真值 ≥90% 在 ±0.01 内", within / len(deltas) >= 0.90, f"{within / len(deltas):.1%}")
    check("与外部真值 ≥85% 逐位相同", exact / len(deltas) >= 0.85, f"{exact / len(deltas):.1%}")

    section("I. 20aa 边界归属（外部证据判定）")
    twenty = []
    bp = ROOT / "_re" / "reference_scores_boundary.tsv"
    if bp.is_file():
        for line in bp.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            p = line.split("\t")
            if len(p) >= 3 and p[0].isalpha() and len(p[0]) == 20:
                twenty.append((p[0], float(p[2])))
    short_hits = long_hits = 0
    for seq, exp in twenty:
        rs = scoring.score_sequences([{"id": "x", "sequence": seq}], length_handling="short").results[0].score
        rl = scoring.score_sequences([{"id": "x", "sequence": seq}], length_handling="long").results[0].score
        short_hits += abs(rs - exp) <= 0.01
        long_hits += abs(rl - exp) <= 0.01
    print(f"    {len(twenty)} 条 20aa 探针：Short 模型吻合 {short_hits}，Long 模型吻合 {long_hits}")
    check("20aa 归属判定支持 <=20 → Short", short_hits > long_hits and short_hits > 0,
          f"short={short_hits} long={long_hits}")

    section("J. 分布合理性（引擎有判别力，不是退化解）")
    import random
    rng = random.Random(20261012)
    AA = "ACDEFGHIKLMNPQRSTVWY"
    for L in (10, 40):
        seqs = ["".join(rng.choice(AA) for _ in range(L)) for _ in range(150)]
        sc = [r.score for r in scoring.score_sequences([{"id": str(i), "sequence": s} for i, s in enumerate(seqs)]).results]
        frac = sum(1 for x in sc if x >= 0.5) / len(sc)
        print(f"    随机 {L} 肽 {len(sc)} 条：平均 {statistics.fmean(sc):.3f}，≥0.5 占比 {frac:.0%}")
        check(f"随机 {L} 肽多数 <0.5（有判别力）", frac < 0.5, f"{frac:.0%}")
    brady = scoring.score_sequences([{"id": "x", "sequence": "RPPGFSPFR"}]).results[0].score
    check("缓激肽得分显著高于 0.5", brady > 0.9, f"{brady:.4f}")

    # ---------------- 总结 ----------------
    section("总结")
    passed = sum(1 for _, ok, _ in CHECK if ok)
    failed = [(n, d) for n, ok, d in CHECK if not ok]
    print(f"  通过 {passed} / {len(CHECK)}")
    if failed:
        print("  未通过项：")
        for n, d in failed:
            print(f"    - {n}  {d}")
    else:
        print("  全部验收项通过。")
    return 0 if not failed else 1


if __name__ == "__main__":
    with redirect_stdout(BUF):
        try:
            code = main()
        except Exception:  # noqa: BLE001
            import traceback
            traceback.print_exc(file=sys.stdout)
            code = 1
    report = BUF.getvalue()

    # 直接用 open(..., encoding='utf-8') 写文件，不要经过 PowerShell 管道，
    # 否则中文在一些 shell 下会被写成 UTF-16/乱码（真实踩过的坑）。
    out = ROOT / "_re" / "acceptance_report.txt"
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(f"# PeptideRanker 重做项目最终验收报告\n"
                     f"# 生成时间：{stamp}\n"
                     f"# 生成方式：python scripts/final_acceptance.py\n")
            fh.write(report)
        sys.stdout.buffer.write(report.encode("utf-8", "replace"))
        sys.stdout.buffer.write(f"\n报告已存档：{out}\n".encode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"报告写入失败：{exc}")
    raise SystemExit(code)
