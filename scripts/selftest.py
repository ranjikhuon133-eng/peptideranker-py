"""端到端自检：不需要真实模型也能验证 HTTP 层、解析、统计、导出是否正确。

做法：注入一个确定性的伪 oracle（score = 由序列哈希决定的固定值），
然后真实启动 app/server.py 并逐个接口打请求。
"""

from __future__ import annotations

import hashlib
import json
import sys
import threading
import types
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def install_fake_oracle() -> None:
    """把 pr_engine.reference.oracle 替换成确定性伪实现。"""
    pkg = types.ModuleType("pr_engine.reference")
    pkg.__path__ = []  # type: ignore[attr-defined]
    oracle = types.ModuleType("pr_engine.reference.oracle")

    def score_sequence(seq: str, models: str = "auto") -> float:
        digest = hashlib.md5(seq.encode()).hexdigest()
        return int(digest[:8], 16) / 0xFFFFFFFF

    def model_info() -> dict:
        return {"short": 15, "long": 15}

    oracle.score_sequence = score_sequence  # type: ignore[attr-defined]
    oracle.model_info = model_info  # type: ignore[attr-defined]
    pkg.oracle = oracle  # type: ignore[attr-defined]
    sys.modules["pr_engine.reference"] = pkg
    sys.modules["pr_engine.reference.oracle"] = oracle


def main() -> int:
    install_fake_oracle()
    from pr_engine import scoring

    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        print(f"  {'✓' if cond else '✗'} {name}{'' if cond else '  ' + detail}")
        if not cond:
            failures.append(name)

    print("[1] /api/status")
    status = scoring.engine_status()
    check("ready 为 True", status.get("ready") is True, str(status))
    check("模型数量正确", status.get("models") == {"short": 15, "long": 15}, str(status.get("models")))

    print("[2] 批量打分与排序")
    text = (ROOT / "testfile.txt").read_text(encoding="utf-8")
    items, warnings = scoring.parse_sequences(text)
    check("解析出 15 条序列", len(items) == 15, f"实际 {len(items)}")
    report = scoring.score_sequences([{"id": i.id, "sequence": i.sequence} for i in items])
    check("结果条数一致", len(report.results) == 15, f"实际 {len(report.results)}")
    check("按分数降序", all(report.results[i].score >= report.results[i + 1].score
                          for i in range(len(report.results) - 1)))
    check("排名从 1 连续", [r.rank for r in report.results] == list(range(1, 16)))
    check("分数均在 [0,1]", all(0.0 <= r.score <= 1.0 for r in report.results))
    payload = report.as_dict()
    check("直方图 10 个桶", len(payload["histogram"]) == 10)
    check("直方图计数之和等于样本数",
          sum(b["count"] for b in payload["histogram"]) == 15,
          str(sum(b["count"] for b in payload["histogram"])))

    print("[3] 长度分派（短肽 <=20 / 长肽 >20）")
    kinds = {r.sequence: r.model for r in report.results}
    short_ok = kinds["ILPILSLIGGLL"] == "short"
    long_ok = kinds["EEERDEDEVIEEEVKRGLLSVFKGVLKGVGKNVAGSLLDQLKCKISGGC"] == "long"
    check("11 肽走短肽模型", short_ok)
    check("52 肽走长肽模型", long_ok)

    print("[4] 非法输入与边界")
    rep2 = scoring.score_sequences(
        [
            {"id": "ok", "sequence": "ILPILSLIGGLL"},
            {"id": "bad_char", "sequence": "ILP1LS"},
            {"id": "empty", "sequence": ""},
            {"id": "lowercase", "sequence": "rppgfspfr"},
            {"id": "unknown_res", "sequence": "ILPXLS"},
        ]
    )
    check("合法行被保留", {r.id for r in rep2.results} >= {"ok", "lowercase", "unknown_res"},
          str([r.id for r in rep2.results]))
    check("非法字符行被跳过", all(r.id != "bad_char" for r in rep2.results))
    check("空行被跳过", all(r.id != "empty" for r in rep2.results))
    check("产生至少 2 条警告", len(rep2.warnings) >= 2, str(rep2.warnings))
    check("小写序列被规范化", any(r.sequence == "RPPGFSPFR" for r in rep2.results))

    print("[5] CSV 导出")
    csv_text = scoring.results_to_csv(report)
    check("含 BOM", csv_text.startswith("\ufeff"))
    header = csv_text.lstrip("\ufeff").splitlines()[0]
    check("列头正确", header == "rank,id,sequence,length,score,model", header)
    check("行数 = 样本数 + 1", len(csv_text.strip().splitlines()) == 16,
          str(len(csv_text.strip().splitlines())))
    tsv = scoring.results_to_tsv(report)
    check("TSV 列头正确", tsv.splitlines()[0] == "rank\tid\tsequence\tlength\tscore\tmodel")

    print("[6] 真实 HTTP 服务（端口 8899）")
    from app.server import Handler
    from http.server import ThreadingHTTPServer

    httpd = ThreadingHTTPServer(("127.0.0.1", 8899), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = "http://127.0.0.1:8899"
    try:
        with urllib.request.urlopen(f"{base}/api/status", timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        check("GET /api/status 返回 ready", body.get("ready") is True, str(body))

        req = urllib.request.Request(
            f"{base}/api/score",
            data=json.dumps({"sequences": [{"id": "a", "sequence": "ILPILSLIGGLL"}]}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        check("POST /api/score 有 results", len(body.get("results", [])) == 1, str(body)[:200])
        check("summary 字段齐全",
              all(k in body.get("summary", {}) for k in ("count", "mean", "median", "min", "max", "n_above_threshold")))

        req = urllib.request.Request(
            f"{base}/api/export",
            data=json.dumps({"sequences": [{"id": "a", "sequence": "ILPILSLIGGLL"}], "format": "csv"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            csv_body = resp.read().decode("utf-8")
            disp = resp.headers.get("Content-Disposition", "")
        check("导出 CSV 正常", csv_body.lstrip("\ufeff").startswith("rank,"), csv_body[:80])
        check("Content-Disposition 指定文件名", "peptideranker_scores.csv" in disp, disp)

        # 空输入应 400
        req = urllib.request.Request(
            f"{base}/api/score",
            data=json.dumps({"sequences": []}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=10)
            check("空输入返回 400", False, "居然成功了")
        except urllib.error.HTTPError as exc:
            check("空输入返回 400", exc.code == 400, f"实际 {exc.code}")

        # 静态首页
        try:
            with urllib.request.urlopen(f"{base}/", timeout=10) as resp:
                html = resp.read().decode("utf-8", "replace")
            check("GET / 返回页面", "<html" in html.lower() or "<!doctype" in html.lower(),
                  html[:80])
        except urllib.error.HTTPError as exc:
            check("GET / 返回页面", False, f"HTTP {exc.code}（前端可能尚未交付）")
    finally:
        httpd.shutdown()
        httpd.server_close()

    print()
    if failures:
        print(f"自检失败 {len(failures)} 项：{failures}")
        return 1
    print("全部自检项通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
