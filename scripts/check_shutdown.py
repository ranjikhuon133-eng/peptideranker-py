"""验证"退出程序"是否真的能让进程干净退出、端口释放。

这是用户最关心的一点：关掉浏览器**不会**关掉服务，所以必须有一个可靠的退出路径。
本脚本真实启动服务，然后分别验证三条退出路径：

  1. POST /api/shutdown（网页上的「退出程序」按钮走这条）
  2. Ctrl+C（等价于关闭启动脚本的窗口）
  3. 空闲自动退出（关掉网页后，心跳停止达到阈值）
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"  [{'OK' if ok else 'FAIL'}] {name}" + (f"   {detail}" if detail and not ok else ""))


def port_in_use(port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.6)
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait_until(predicate, timeout: float, interval: float = 0.25) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def start(port: int, extra: list[str] | None = None) -> subprocess.Popen:
    return subprocess.Popen(
        [PY, str(ROOT / "app" / "server.py"), "--port", str(port)] + (extra or []),
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def api(port: int, path: str, method: str = "GET"):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, {}
    except Exception:  # noqa: BLE001
        return 0, {}


def main() -> int:
    print("=" * 78)
    print("路径 1：网页点「退出程序」 -> POST /api/shutdown")
    print("=" * 78)
    port = 8801
    proc = start(port)
    try:
        up = wait_until(lambda: port_in_use(port), 25)
        record("服务能正常启动", up)
        if up:
            code, body = api(port, "/api/status")
            record("启动时 /api/status 可访问", code == 200)
            code, body = api(port, "/api/shutdown", "POST")
            record("/api/shutdown 返回 200", code == 200, f"实际 {code}")
            record("响应带提示文案", bool(body.get("message")), str(body))
            exited = wait_until(lambda: not port_in_use(port), 15)
            record("端口已释放（服务真的退出了）", exited)
            record("进程已结束", proc.poll() is not None, f"poll={proc.poll()}")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)

    print()
    print("=" * 78)
    print("路径 2：Ctrl+C（等价于关闭启动脚本窗口）")
    print("=" * 78)
    port = 8802
    proc = start(port)
    try:
        up = wait_until(lambda: port_in_use(port), 25)
        record("服务能正常启动", up)
        if up:
            proc.terminate()  # Windows 上等价于要求进程结束
            exited = wait_until(lambda: proc.poll() is not None, 15)
            record("进程响应终止信号并退出", exited, f"poll={proc.poll()}")
            record("端口已释放", wait_until(lambda: not port_in_use(port), 10))
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)

    print()
    print("=" * 78)
    print("路径 3：关掉网页后空闲自动退出（心跳停止触发）")
    print("=" * 78)
    port = 8803
    # 用极短的空闲阈值：--idle-exit-minutes 最小按分钟算，这里直接改内部逻辑不现实，
    # 因此改为验证"心跳被记录"以及"看门狗线程存在"两项可观测事实，
    # 再单独用一次真实心跳+短阈值组合验证退出。
    proc = subprocess.Popen(
        [PY, "-c",
         "import sys,time,threading;"
         f"sys.path.insert(0, r'{ROOT}');"
         "from app.server import LocalServer, Handler;"
         "s=LocalServer(('127.0.0.1',%d), Handler, idle_exit_minutes=1);"
         "s.idle_exit_seconds=3;"  # 直接压到 3 秒便于测试
         "s.heartbeat();"
         "threading.Thread(target=s.serve_forever, daemon=True).start();"
         "s.serve_forever()" % port],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        up = wait_until(lambda: port_in_use(port), 25)
        record("带空闲退出的服务能启动", up)
        if up:
            code, body = api(port, "/api/heartbeat")
            record("/api/heartbeat 可用", code == 200 and body.get("ok") is True, str(body))
            exited = wait_until(lambda: not port_in_use(port), 30)
            record("心跳停止后自动退出、端口释放", exited)
            record("进程已结束", proc.poll() is not None, f"poll={proc.poll()}")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)

    print()
    print("=" * 78)
    print("路径 4：双击「停止程序.bat」（兜底，先优雅退出再强杀）")
    print("=" * 78)
    port = 8804
    proc = start(port)
    try:
        up = wait_until(lambda: port_in_use(port), 25)
        record("服务能正常启动", up)
        if up:
            bat = ROOT / "停止程序.bat"
            record("停止程序.bat 存在", bat.is_file())
            if bat.is_file():
                # 脚本会自己找 8737~8746 的监听端口，这里把被测端口换成 8804 不现实，
                # 因此改为先直接在 8737 上起服务来测这条路径（与用户实际用法一致）。
                proc.kill()
                proc.wait(timeout=10)
                wait_until(lambda: not port_in_use(port), 5)

                port = 8737
                proc = start(port)
                if wait_until(lambda: port_in_use(port), 25):
                    out = subprocess.run(
                        ["cmd", "/c", str(bat)], cwd=str(ROOT),
                        capture_output=True, input=b"\r\n", timeout=90,
                    )
                    text = out.stdout.decode("gbk", "replace")
                    record("脚本识别出在运行的服务", "发现服务在端口" in text, text[:200])
                    record("端口已释放", wait_until(lambda: not port_in_use(port), 20))
                    record("服务进程已结束", wait_until(lambda: proc.poll() is not None, 10),
                           f"poll={proc.poll()}")
                else:
                    record("在 8737 上启动服务以测试停止脚本", False)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)

    print()
    print("=" * 78)
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"退出机制验证：通过 {passed} / {len(results)}")
    if passed != len(results):
        print("未通过项：")
        for n, ok, d in results:
            if not ok:
                print("  -", n, d)
        return 1
    print("所有退出路径都能干净地停止进程并释放端口。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
