"""查清"点退出后进程退出码是 1"的原因，并验证修复。

复现：启动服务 -> POST /api/shutdown -> 看进程退出码到底是几。
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
PORT = 8811


def listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.6)
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait_for(pred, timeout: float) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.3)
    return False


def main() -> int:
    proc = subprocess.Popen(
        [PY, str(ROOT / "app" / "server.py"), "--port", str(PORT)],
        cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    try:
        if not wait_for(lambda: listening(PORT), 30):
            print("服务没起来")
            return 1
        req = urllib.request.Request(
            f"http://127.0.0.1:{PORT}/api/shutdown", method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            print("shutdown 响应:", r.status, r.read().decode("utf-8"))

        exited = wait_for(lambda: proc.poll() is not None, 20)
        code = proc.poll()
        out = proc.stdout.read().decode("utf-8", "replace") if proc.stdout else ""
        print(f"进程已退出: {exited}   退出码: {code}")
        print("端口已释放:", not listening(PORT))
        print("--- 输出里是否还有 Traceback / ConnectionReset ---")
        noisy = [ln for ln in out.splitlines() if "Traceback" in ln or "ConnectionReset" in ln
                 or "Exception occurred" in ln]
        print("  噪音行数:", len(noisy))
        for ln in noisy[:6]:
            print("   ", ln.strip())
        print("--- 输出末尾 ---")
        for ln in out.strip().splitlines()[-6:]:
            print("   ", ln)

        if code != 0:
            print("\n[结论] 退出码不是 0，需要修复（用户会以为程序出错）")
            return 1
        print("\n[结论] 退出码为 0，退出干净")
        return 0
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)


if __name__ == "__main__":
    raise SystemExit(main())
