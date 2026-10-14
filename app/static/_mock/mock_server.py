#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PeptideRanker 前端自测用 mock 服务（仅开发自测用，不属于产品交付代码）。

- 按冻结契约实现 GET /api/status、POST /api/score、POST /api/export
- 同时把 app/static/ 作为静态目录提供，方便在 http://127.0.0.1:8899/ 打开前端
- 额外提供 /__mock/mode 用于切换故障模式，测试前端的错误处理

用法（不要占用 8737，避免与真实后端冲突）：
    D:\\01APP\\51python3.14.3\\python.exe app/static/_mock/mock_server.py --port 8899
前端访问：
    http://127.0.0.1:8899/?api=http://127.0.0.1:8899
故障模式：
    curl -X POST http://127.0.0.1:8899/__mock/mode -d '{"mode":"notready"}'
    mode ∈ ok | notready | down | err500
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

STATIC_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
THRESHOLD = 0.5
VERSION = "1.0"
BUCKETS = 10

LOCK = threading.Lock()
STATE = {"mode": "ok", "requests": []}


def record(method, path, body=None):
    """记录收到的请求，供前端契约一致性测试断言请求体字段名。"""
    with LOCK:
        STATE["requests"].append({"method": method, "path": path.split("?")[0], "body": body})
        if len(STATE["requests"]) > 200:
            del STATE["requests"][:-200]


def score_of(seq: str) -> float:
    """确定性伪分数：同一序列永远得到同一分数，且分布铺满 0~1。"""
    digest = hashlib.md5(seq.encode("utf-8")).digest()
    raw = int.from_bytes(digest[:8], "big") / float(2 ** 64)
    # 轻微向两端扩散，视觉上更像概率分布
    value = raw ** 0.72
    return round(min(0.9999, max(0.0001, value)), 4)


def model_of(length: int, handling: str) -> str:
    if handling in ("short", "long"):
        return handling
    return "short" if length <= 20 else "long"


def review(sequences, handling):
    results, warnings = [], []
    for index, item in enumerate(sequences):
        line_no = index + 1
        seq_id = str(item.get("id") or ("seq%d" % line_no))
        raw = str(item.get("sequence") or "")
        cleaned = raw.strip().upper()
        if not cleaned:
            warnings.append("第 %d 行为空，已跳过" % line_no)
            continue
        bad = [c for c in cleaned if not ("A" <= c <= "Z")]
        if bad:
            warnings.append("第 %d 行含非法字符 '%s'，已跳过" % (line_no, bad[0]))
            continue
        results.append(
            {
                "id": seq_id,
                "sequence": cleaned,
                "length": len(cleaned),
                "score": score_of(cleaned),
                "model": model_of(len(cleaned), handling),
            }
        )
    results.sort(key=lambda r: (-r["score"], r["id"]))
    for i, row in enumerate(results, start=1):
        row["rank"] = i
    out = []
    for row in results:
        out.append(
            {
                "rank": row["rank"],
                "id": row["id"],
                "sequence": row["sequence"],
                "length": row["length"],
                "score": row["score"],
                "model": row["model"],
            }
        )
    return out, warnings


def summarize(results):
    scores = [r["score"] for r in results]
    if not scores:
        return {"count": 0, "mean": None, "median": None, "min": None, "max": None, "n_above_threshold": 0}
    ordered = sorted(scores)
    mid = len(ordered) // 2
    median = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2.0
    return {
        "count": len(results),
        "mean": round(sum(scores) / len(scores), 4),
        "median": round(median, 4),
        "min": min(scores),
        "max": max(scores),
        "n_above_threshold": sum(1 for s in scores if s >= THRESHOLD),
    }


def histogram(results):
    bins = [{"lo": i / BUCKETS, "hi": (i + 1) / BUCKETS, "count": 0} for i in range(BUCKETS)]
    for row in results:
        idx = min(BUCKETS - 1, int(row["score"] * BUCKETS))
        bins[idx]["count"] += 1
    return bins


def csv_text(results):
    lines = ["rank,id,sequence,length,score,model"]
    for row in sorted(results, key=lambda r: r["rank"]):
        lines.append(
            "%d,%s,%s,%d,%.4f,%s"
            % (row["rank"], row["id"], row["sequence"], row["length"], row["score"], row["model"])
        )
    return "\n".join(lines) + "\n"


class Handler(SimpleHTTPRequestHandler):
    server_version = "PeptideRankerMock/1.0"
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, **kwargs):
        kwargs["directory"] = STATIC_DIR
        super().__init__(*args, **kwargs)

    # ---------------------------------------------------------------- 基础
    def log_message(self, fmt, *args):
        if os.environ.get("MOCK_QUIET") != "1":
            sys.stderr.write("[mock] " + (fmt % args) + "\n")
            sys.stderr.flush()

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Expose-Headers", "Content-Disposition, Content-Type, Content-Length")

    def _send(self, code, body: bytes, content_type: str, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self._cors()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _error(self, code, message):
        self._json(code, {"error": message})

    def _mode(self):
        with LOCK:
            return STATE["mode"]

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    # ---------------------------------------------------------------- 路由
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/status":
            record("GET", path)
            return self._status()
        if path == "/__mock/mode":
            return self._json(200, {"mode": self._mode()})
        if path == "/__mock/log":
            with LOCK:
                return self._json(200, {"requests": list(STATE["requests"])})
        return super().do_GET()

    def do_HEAD(self):
        return self.do_GET()

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/__mock/mode":
            body = self._read_json() or {}
            mode = str(body.get("mode") or "ok")
            if mode not in ("ok", "notready", "notready503", "down", "err500"):
                return self._error(400, "未知 mode：%s" % mode)
            with LOCK:
                STATE["mode"] = mode
            return self._json(200, {"mode": mode})
        if path == "/__mock/log":
            body = self._read_json() or {}
            if body.get("clear"):
                with LOCK:
                    STATE["requests"] = []
            with LOCK:
                return self._json(200, {"requests": list(STATE["requests"])})
        if path == "/api/score":
            return self._score()
        if path == "/api/export":
            return self._export()
        return self._error(404, "未实现的接口：%s" % path)

    # ---------------------------------------------------------------- 接口
    def _status(self):
        mode = self._mode()
        if mode == "down":
            return self._error(503, "mock：服务不可用（mode=down）")
        if mode == "notready":
            return self._json(200, {"ready": False, "error": "模型文件缺失：Models_Short.txt / Models_Long.txt 未找到"})
        if mode == "notready503":
            # 复刻真实后端 app/server.py 的行为：未就绪时用 503 + ready=false
            return self._json(503, {"ready": False, "error": "模型文件缺失：Models_Short.txt / Models_Long.txt 未找到"})
        return self._json(200, {
            "ready": True,
            "engine": "python-port",
            "models": {"short": 15, "long": 15},
            "threshold": THRESHOLD,
            "version": VERSION,
        })

    def _payload(self):
        body = self._read_json()
        if body is None or not isinstance(body, dict):
            self._error(400, "请求体必须是 JSON 对象")
            return None
        sequences = body.get("sequences")
        if not isinstance(sequences, list):
            self._error(400, "缺少 sequences 数组")
            return None
        handling = body.get("length_handling", "auto")
        if handling not in ("auto", "short", "long"):
            self._error(400, "length_handling 只能是 auto/short/long，收到：%r" % handling)
            return None
        return sequences, handling, body

    def _score(self):
        mode = self._mode()
        if mode == "down":
            return self._error(503, "mock：服务不可用（mode=down）")
        parsed = self._payload()
        if parsed is None:
            return
        sequences, handling, _body = parsed
        record("POST", "/api/score", _body)
        if mode == "err500":
            return self._error(500, "mock：打分引擎内部错误（mode=err500）")
        started = time.time()
        record("POST", "/api/score", _body)
        results, warnings = review(sequences, handling)
        time.sleep(0.05)  # 模拟一点计算耗时，方便观察加载态
        elapsed = int((time.time() - started) * 1000)
        self._json(200, {
            "results": results,
            "warnings": warnings,
            "summary": summarize(results),
            "histogram": histogram(results),
            "elapsed_ms": elapsed,
        })

    def _export(self):
        mode = self._mode()
        if mode == "down":
            return self._error(503, "mock：服务不可用（mode=down）")
        parsed = self._payload()
        if parsed is None:
            return
        sequences, handling, body = parsed
        record("POST", "/api/export", body)
        if body.get("format") != "csv":
            return self._error(400, "format 必须是 csv")
        results, _warnings = review(sequences, handling)
        body_bytes = b"\xef\xbb\xbf" + csv_text(results).encode("utf-8")
        self._send(200, body_bytes, "text/csv; charset=utf-8", {
            "Content-Disposition": 'attachment; filename="peptideranker_scores.csv"',
        })


def main():
    parser = argparse.ArgumentParser(description="PeptideRanker 前端自测 mock 服务")
    parser.add_argument("--port", type=int, default=8899)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    sys.stderr.write("[mock] serving %s at http://%s:%d/  (?api=http://%s:%d)\n"
                     % (STATIC_DIR, args.host, args.port, args.host, args.port))
    sys.stderr.flush()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
