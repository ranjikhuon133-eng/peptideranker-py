"""PeptideRanker 本地网页应用 —— 零依赖 HTTP 服务。

用法：
    python app/server.py                      # 默认 http://127.0.0.1:8737
    python app/server.py --port 9000 --open
    python app/server.py --idle-exit-minutes 15   # 关掉网页多久后自动退出（0 = 不自动退出）

只监听回环地址（127.0.0.1），不对外网暴露；不需要联网。

退出方式（三者等效，都会干净地释放端口）：
  1. 网页右上角点「退出程序」
  2. 关闭启动脚本的那个命令行窗口（或按 Ctrl+C）
  3. 关掉所有网页后等待 --idle-exit-minutes 分钟，自动退出
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import socket
import sys
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

# 允许以 `python app/server.py` 直接运行
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pr_engine import scoring  # noqa: E402
from pr_engine import i18n as _i18n  # noqa: E402

STATIC_DIR = ROOT / "app" / "static"
DEFAULT_PORT = 8737
MAX_BODY_BYTES = 8 * 1024 * 1024  # 8 MB 足够容纳 2 万条序列
DEFAULT_IDLE_EXIT_MINUTES = 10


def _json_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


class LocalServer(ThreadingHTTPServer):
    """带"退出"与"空闲自动退出"能力的本地服务。

    daemon_threads=True 保证关闭时不会被残留的工作线程拖住。
    """

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, handler, idle_exit_minutes: int = DEFAULT_IDLE_EXIT_MINUTES):
        super().__init__(addr, handler)
        self.shutdown_requested = threading.Event()
        self._last_beat = time.time()
        self._beat_seen = False
        self._started = time.time()
        self.idle_exit_seconds = max(0, int(idle_exit_minutes)) * 60
        if self.idle_exit_seconds:
            threading.Thread(target=self._idle_watchdog, daemon=True).start()

    # ---- 心跳：网页活着的时候会定期 ping，用于判断"网页是否已关闭" ----
    def heartbeat(self) -> None:
        self._beat_seen = True
        self._last_beat = time.time()

    def _idle_watchdog(self) -> None:
        # 每 15 秒检查一次；只有在"曾经收到过心跳"之后才计时，
        # 避免用户还没打开网页就被判为空闲而退出。
        while not self.shutdown_requested.is_set():
            time.sleep(15)
            if not self._beat_seen:
                continue
            idle = time.time() - self._last_beat
            if idle >= self.idle_exit_seconds:
                print(
                    f"\n[自动退出] 已有 {idle / 60:.1f} 分钟没有收到网页心跳"
                    f"（网页可能已关闭），正在停止服务…"
                )
                self.request_shutdown("idle")
                return

    def request_shutdown(self, reason: str = "api") -> None:
        """请求停止服务。可从任意线程调用（不会阻塞当前请求）。"""
        if self.shutdown_requested.is_set():
            return
        self.shutdown_requested.set()

        def _stop() -> None:
            time.sleep(0.2)  # 让当前响应先发出去
            try:
                self.shutdown()
            except Exception:  # noqa: BLE001
                pass
            try:
                self.server_close()
            except Exception:  # noqa: BLE001
                pass

        threading.Thread(target=_stop, daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    server_version = "PeptideRankerLocal/1.0"
    protocol_version = "HTTP/1.1"

    # ---------------------------- 工具方法 ---------------------------- #
    def log_message(self, fmt: str, *args) -> None:  # 精简日志
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def handle_one_request(self) -> None:
        """吞掉"浏览器关页面"这类连接中断，不要往控制台刷一堆 Traceback。

        用户关标签页/刷新时，连接被强制关闭是**正常现象**，但 socketserver 默认会
        打印完整的 ConnectionResetError 堆栈，看起来像程序出错了。这里静默处理。
        """
        try:
            super().handle_one_request()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, TimeoutError):
            self.close_connection = True

    def _send(self, code: int, body: bytes, ctype: str, extra: dict[str, str] | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_json(self, code: int, payload: object) -> None:
        self._send(code, _json_bytes(payload), "application/json; charset=utf-8")

    def _error(self, code: int, message: str) -> None:
        self._send_json(code, {"error": message})

    # ---- 多语言：请求体里的 lang 优先，其次 Accept-Language，最后默认中文 ----
    def _header_lang(self) -> str:
        first = (self.headers.get("Accept-Language") or "").split(",")[0]
        return _i18n.normalize(first)

    def _payload_lang(self, payload: dict | None = None) -> str:
        raw = (payload or {}).get("lang")
        return _i18n.normalize(raw) if raw else self._header_lang()

    def _read_json(self) -> dict:
        lang = self._header_lang()
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ValueError(_i18n.msg(lang, "srv.content_length_invalid"))
        if length <= 0:
            return {}
        if length > MAX_BODY_BYTES:
            raise ValueError(_i18n.msg(
                lang, "srv.body_too_large", length=length, limit=MAX_BODY_BYTES
            ))
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise ValueError(_i18n.msg(lang, "srv.body_not_utf8", error=exc)) from exc
        except json.JSONDecodeError as exc:
            raise ValueError(_i18n.msg(lang, "srv.body_not_json", error=exc)) from exc
        if not isinstance(data, dict):
            raise ValueError(_i18n.msg(lang, "srv.body_must_be_object"))
        return data

    # ---------------------------- 路由 ---------------------------- #
    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/status":
            # 恒返回 200：引擎不可用时用 ready=false + error 表达，
            # 避免前端把 503 当成"请求失败"而不是"引擎未就绪"。
            status = scoring.engine_status(self._header_lang())
            status["idle_exit_minutes"] = int(
                getattr(self.server, "idle_exit_seconds", 0) // 60
            )
            self._send_json(200, status)
            return
        if path == "/api/heartbeat":
            # 网页每 20 秒 ping 一次；超过设定时间没收到就认为网页已关闭
            self.server.heartbeat()  # type: ignore[attr-defined]
            self._send_json(200, {"ok": True})
            return
        if path in ("/", ""):
            self._serve_static("index.html")
            return
        if path.startswith("/api/"):
            self._error(404, _i18n.msg(self._header_lang(), "srv.unknown_api", path=path))
            return
        self._serve_static(path.lstrip("/"))

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/shutdown":
            self._send_json(200, {
                "ok": True,
                "message": _i18n.msg(self._header_lang(), "srv.stopping"),
            })
            print("\n[退出] 收到网页的退出请求，正在停止服务…")
            self.server.request_shutdown("api")  # type: ignore[attr-defined]
            return
        if path not in ("/api/score", "/api/export"):
            self._error(404, _i18n.msg(self._header_lang(), "srv.unknown_api", path=path))
            return
        try:
            payload = self._read_json()
        except ValueError as exc:
            self._error(400, str(exc))
            return
        lang = self._payload_lang(payload)

        try:
            items, parse_warnings = self._extract_items(payload, lang)
        except ValueError as exc:
            self._error(400, str(exc))
            return

        length_handling = str(payload.get("length_handling") or "auto").lower()
        if length_handling not in ("auto", "short", "long"):
            self._error(400, _i18n.msg(lang, "srv.bad_length_handling"))
            return

        if not items:
            self._error(400, _i18n.msg(lang, "srv.no_sequences"))
            return

        # strict_case=true 时逐字复刻原二进制的大小写行为（小写会被当作未知字符跳过）
        strict_case = bool(payload.get("strict_case", False))

        try:
            report = scoring.score_sequences(
                items, length_handling=length_handling, strict_case=strict_case, lang=lang
            )
        except scoring.EngineNotReady as exc:
            self._error(503, str(exc))
            return
        except scoring.SequenceError as exc:
            self._error(400, str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._error(500, _i18n.msg(
                lang, "srv.score_failed", error=f"{type(exc).__name__}: {exc}"
            ))
            return

        report.warnings = parse_warnings + report.warnings

        if path == "/api/score":
            self._send_json(200, report.as_dict())
            return

        # /api/export
        fmt = str(payload.get("format") or "csv").lower()
        if fmt != "csv":
            self._error(400, _i18n.msg(lang, "srv.export_format"))
            return
        body = scoring.results_to_csv(report).encode("utf-8")
        self._send(
            200,
            body,
            "text/csv; charset=utf-8",
            {"Content-Disposition": 'attachment; filename="peptideranker_scores.csv"'},
        )

    # ---------------------------- 辅助 ---------------------------- #
    @staticmethod
    def _extract_items(payload: dict, lang: str = _i18n.DEFAULT_LANG) -> tuple[list[dict], list[str]]:
        warnings: list[str] = []
        raw_seqs = payload.get("sequences")
        if raw_seqs is None and "text" in payload:
            items, warnings = scoring.parse_sequences(
                str(payload.get("text") or ""),
                strict=bool(payload.get("strict_case", False)),
                lang=lang,
            )
            return [{"id": it.id, "sequence": it.sequence} for it in items], warnings
        if not isinstance(raw_seqs, list):
            raise ValueError(_i18n.msg(lang, "srv.sequences_type"))
        items: list[dict] = []
        for idx, entry in enumerate(raw_seqs, start=1):
            if isinstance(entry, str):
                items.append({"id": f"seq{idx}", "sequence": entry})
            elif isinstance(entry, dict):
                if "sequence" not in entry:
                    raise ValueError(_i18n.msg(lang, "srv.item_missing_sequence", index=idx - 1))
                items.append(
                    {
                        "id": str(entry.get("id") or f"seq{idx}"),
                        "sequence": str(entry.get("sequence")),
                    }
                )
            else:
                raise ValueError(_i18n.msg(
                    lang, "srv.item_bad_type", index=idx - 1, type=type(entry).__name__
                ))
        return items, warnings

    def _serve_static(self, rel: str) -> None:
        rel = unquote(rel or "index.html")
        lang = self._header_lang()
        target = (STATIC_DIR / rel).resolve()
        try:
            target.relative_to(STATIC_DIR.resolve())
        except ValueError:
            self._error(403, _i18n.msg(lang, "srv.path_forbidden"))
            return
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            self._send(
                404,
                _json_bytes({"error": _i18n.msg(lang, "srv.static_not_found", path=rel)}),
                "application/json; charset=utf-8",
            )
            return
        ctype, _ = mimetypes.guess_type(str(target))
        ctype = ctype or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self._send(200, target.read_bytes(), ctype)


def _port_available(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PeptideRanker 本地打分服务")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认仅本机）")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"端口（默认 {DEFAULT_PORT}）")
    parser.add_argument("--open", action="store_true", help="启动后自动打开浏览器")
    parser.add_argument(
        "--idle-exit-minutes",
        type=int,
        default=DEFAULT_IDLE_EXIT_MINUTES,
        help=f"多久没收到网页心跳就自动退出（分钟，默认 {DEFAULT_IDLE_EXIT_MINUTES}；0 = 不自动退出）",
    )
    args = parser.parse_args(argv)

    if not STATIC_DIR.is_dir():
        print(f"[警告] 未找到前端目录 {STATIC_DIR}，网页将无法打开", file=sys.stderr)

    port = args.port
    if not _port_available(port, args.host):
        for candidate in range(port + 1, port + 20):
            if _port_available(candidate, args.host):
                print(f"[提示] 端口 {port} 被占用，改用 {candidate}")
                port = candidate
                break
        else:
            print(f"[错误] 端口 {port}~{port + 19} 均被占用", file=sys.stderr)
            return 2

    url = f"http://{args.host}:{port}/"
    httpd = LocalServer((args.host, port), Handler, idle_exit_minutes=args.idle_exit_minutes)

    status = scoring.engine_status()
    print("=" * 68)
    print("  PeptideRanker 本地打分服务已启动")
    print(f"  地址：{url}")
    if status.get("ready"):
        models = status.get("models") or {}
        print(f"  引擎：Python 复刻版（短肽模型 {models.get('short', '?')} 个 / 长肽模型 {models.get('long', '?')} 个）")
    else:
        print(f"  [警告] {status.get('error')}")
    print()
    print("  退出方式（任选其一）：")
    print("    · 网页右上角点「退出程序」")
    print("    · 关闭本窗口，或在这里按 Ctrl+C")
    if args.idle_exit_minutes:
        print(f"    · 关闭所有网页后等待 {args.idle_exit_minutes} 分钟，自动退出")
    print("=" * 68)

    if args.open:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[退出] 收到 Ctrl+C，正在停止服务…")
    finally:
        httpd.server_close()
    print("[退出] 服务已停止，端口已释放。现在可以关闭本窗口了。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
