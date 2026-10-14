"""前端 + 真实服务层的联调验证（不需要真实模型）。

流程：用 _re/stub_oracle.py 当假引擎启动真实 app/server.py（端口 8737），
然后检查静态资源、接口契约、以及前端 JS 里是否真的按契约取字段。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
BASE = "http://127.0.0.1:8737"
STATIC = ROOT / "app" / "static"

failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'✓' if cond else '✗'} {name}{'' if cond else '  ' + detail}")
    if not cond:
        failures.append(name)


def wait_ready(url: str, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                resp.read()
                return True
        except Exception:  # noqa: BLE001
            time.sleep(0.4)
    return False


def get(path: str, raw: bool = False):
    """GET 请求；raw=False 时尝试解析 JSON（/api/status 就是 JSON）。"""
    req = urllib.request.Request(f"{BASE}{path}", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read()
            ctype = resp.headers.get("Content-Type", "")
            if raw or "json" not in ctype:
                return resp.status, body, dict(resp.headers)
            return resp.status, json.loads(body.decode("utf-8")), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        body = exc.read()
        try:
            parsed = json.loads(body.decode("utf-8"))
        except Exception:  # noqa: BLE001
            parsed = {"error": body.decode("utf-8", "replace")}
        return exc.code, parsed, dict(exc.headers)


def post(path: str, payload: dict, raw: bool = False):
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read()
            return resp.status, (body if raw else json.loads(body.decode("utf-8"))), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        body = exc.read()
        try:
            parsed = json.loads(body.decode("utf-8"))
        except Exception:  # noqa: BLE001
            parsed = {"error": body.decode("utf-8", "replace")}
        return exc.code, parsed, dict(exc.headers)


def main() -> int:
    print("[准备] 检查前端文件是否存在")
    for name in ("index.html", "app.js", "style.css", "i18n.js"):
        check(f"app/static/{name} 存在", (STATIC / name).is_file())
    if failures:
        print("\n前端尚未交付，跳过联调。")
        return 1

    print("[启动] 用桩引擎启动真实服务（127.0.0.1:8737）")
    proc = subprocess.Popen(
        [PY, str(ROOT / "scripts" / "run_server_with_stub.py"), "--port", "8737"],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
    )
    try:
        if not wait_ready(f"{BASE}/api/status"):
            out = ""
            try:
                proc.terminate()
                out = (proc.communicate(timeout=10)[0] or "")[-3000:]
            except Exception:  # noqa: BLE001
                pass
            print("服务未能启动，输出如下：\n" + out)
            return 1

        print("[1] 静态资源可访问")
        status, body, headers = get("/")
        check("GET / 返回 200", status == 200, str(status))
        html = body.decode("utf-8", "replace")
        check("返回的是 HTML", "<html" in html.lower() or "<!doctype" in html.lower())
        check("HTML 引用了 app.js", "app.js" in html)
        check("HTML 引用了 style.css", "style.css" in html)
        check("HTML 引用了 i18n.js", "i18n.js" in html)
        check("i18n.js 在 app.js 之前加载",
              -1 < html.find("i18n.js") < html.find("app.js"))
        for asset in ("/app.js", "/style.css", "/i18n.js"):
            st, b, h = get(asset)
            check(f"GET {asset} 返回 200", st == 200, str(st))
            check(f"{asset} 非空", len(b) > 200, f"{len(b)} 字节")

        print("[2] 接口契约")
        status, body, _ = get("/api/status")
        check("GET /api/status -> 200", status == 200, str(status))
        check("status.ready 为 true", body.get("ready") is True, str(body))
        check("status.models 含 short/long", set(body.get("models", {})) >= {"short", "long"}, str(body))
        counts = body.get("models") or {}
        check("模型数量计数非 0（不应显示 0/0）",
              int(counts.get("short", 0)) > 0 and int(counts.get("long", 0)) > 0, str(counts))

        text = (ROOT / "testfile.txt").read_text(encoding="utf-8")
        seqs = [ln.strip() for ln in text.splitlines() if ln.strip()]
        status, body, _ = post("/api/score", {"sequences": [{"id": f"s{i}", "sequence": s} for i, s in enumerate(seqs, 1)]})
        check("POST /api/score -> 200", status == 200, str(status))
        results = body.get("results", [])
        check("返回条数与输入一致", len(results) == len(seqs), f"{len(results)} vs {len(seqs)}")
        check("results 已降序", all(results[i]["score"] >= results[i + 1]["score"] for i in range(len(results) - 1)))
        check("rank 从 1 开始连续", [r["rank"] for r in results] == list(range(1, len(results) + 1)))
        check("每条含 score/length/model/id/sequence",
              all({"score", "length", "model", "id", "sequence"} <= set(r) for r in results))
        summary = body.get("summary", {})
        check("summary 字段齐全",
              {"count", "mean", "median", "min", "max", "n_above_threshold"} <= set(summary), str(sorted(summary)))
        check("histogram 有 10 个桶", len(body.get("histogram", [])) == 10)
        check("elapsed_ms 存在", isinstance(body.get("elapsed_ms"), int))
        check("短肽/长肽分派正确",
              {r["model"] for r in results} <= {"short", "long"}
              and any(r["model"] == "short" for r in results)
              and any(r["model"] == "long" for r in results),
              str(sorted({r["model"] for r in results})))

        print("[3] 非法输入")
        status, body, _ = post("/api/score", {"sequences": [{"id": "ok", "sequence": "ILPILSLIGGLL"}, {"id": "bad", "sequence": "ILP1LS"}]})
        check("含非法字符的批次仍返回 200", status == 200, str(status))
        check("非法行被跳过", all(r["id"] != "bad" for r in body.get("results", [])), str(body.get("results")))
        check("有 warnings", len(body.get("warnings", [])) >= 1, str(body.get("warnings")))
        status, body, _ = post("/api/score", {"sequences": []})
        check("空输入 -> 400", status == 400, str(status))
        status, body, _ = post("/api/score", {"sequences": [{"id": "x", "sequence": "AAAA"}], "length_handling": "bogus"})
        check("非法 length_handling -> 400", status == 400, str(status))

        print("[4] CSV 导出")
        status, body, headers = post("/api/export", {"sequences": [{"id": "a", "sequence": "ILPILSLIGGLL"}], "format": "csv"}, raw=True)
        check("POST /api/export -> 200", status == 200, str(status))
        text_out = body.decode("utf-8")
        check("CSV 带 BOM", text_out.startswith("\ufeff"))
        header = text_out.lstrip("\ufeff").splitlines()[0]
        check("CSV 列头正确", header == "rank,id,sequence,length,score,model", header)
        check("CSV Content-Type 正确", "text/csv" in headers.get("Content-Type", ""), headers.get("Content-Type", ""))
        check("CSV 带附件文件名", "peptideranker_scores.csv" in headers.get("Content-Disposition", ""),
              headers.get("Content-Disposition", ""))

        print("[5] 前端 JS 是否按契约取字段（静态检查）")
        js = (STATIC / "app.js").read_text(encoding="utf-8", errors="replace")
        for token in ("/api/status", "/api/score", "/api/export", "results", "summary", "histogram",
                      "n_above_threshold", "elapsed_ms", "warnings", "length_handling"):
            check(f"app.js 使用 {token}", token in js)
        check("app.js 无 CDN 依赖", "https://" not in js and "http://" not in js.replace("http://127.0.0.1", ""),
              "发现外部 URL")
        i18n_js = (STATIC / "i18n.js").read_text(encoding="utf-8", errors="replace")
        check("i18n.js 无 CDN 依赖",
              "https://" not in i18n_js and "http://" not in i18n_js.replace("http://127.0.0.1", ""),
              "发现外部 URL")
        check("i18n.js 提供中英两种语言", "'zh'" in i18n_js and "'en'" in i18n_js)
        check("index.html 无 CDN 依赖",
              not re.search(r'(src|href)\s*=\s*["\']https?://', html), "发现外部资源引用")
        check("index.html 含中英切换控件", 'id="langSwitch"' in html and 'data-lang="en"' in html)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            proc.kill()

    print()
    if failures:
        print(f"联调失败 {len(failures)} 项：{failures}")
        return 1
    print("联调全部通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
