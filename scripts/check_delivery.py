"""交付检查：确认"拿到文件夹的人"能顺利跑起来。

在项目根目录生成 启动网页.bat 的"只探测不启动服务"副本，然后模拟几种真实的
接收方环境，验证启动脚本能否正确找到 Python 并启动：

  1. PYTHON_EXE 指向不存在的路径（有人配了坏的环境变量）
  2. PATH 上的 python 是 Microsoft Store 占位程序（未装 Python 的机器最常见）
  3. 什么都不设置（正常机器，靠自动探测）
  4. 完全没有 Python（清空 PATH 模拟）——必须给出清楚的中文安装指引
  5. 必需文件缺失（模拟只复制了部分文件）——必须明确报错而不是神秘失败

注意：副本必须放在项目根目录，因为启动脚本会 `cd /d "%~dp0"` 再做文件自检。
"""

from __future__ import annotations

import io
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GBK = "gbk"
LAUNCHER = ROOT / "启动网页.bat"
PROBE = ROOT / "_probe_launcher.bat"

STORE_STUB = r"C:\Users\wangchenxu\AppData\Local\Microsoft\WindowsApps\python3.exe"
PROBE_ECHO = "echo PROBE_OK_PY=!PY! & echo PROBE_DONE & exit /b 0"

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"  [{'OK' if ok else 'FAIL'}] {name}" + (f"   {detail}" if detail and not ok else ""))


def make_probe(break_files: bool = False) -> None:
    text = io.open(LAUNCHER, "r", encoding=GBK, newline="").read()
    text2, n = re.subn(r'(?m)^!PY! "app\\server\.py" --open\r?$', PROBE_ECHO, text)
    if n != 1:
        raise SystemExit(f"无法定位启动行（匹配到 {n} 次），启动脚本可能被改过")
    if break_files:
        # 让必需文件自检失败：把 oracle.py 指向一个不存在的名字
        text2 = text2.replace(r"pr_engine\reference\oracle.py",
                              r"pr_engine\reference\__not_here__.py")
    io.open(PROBE, "w", encoding=GBK, newline="").write(text2)


def run(env_overrides: dict[str, str | None], cwd: Path = ROOT) -> tuple[int, str]:
    env = dict(os.environ)
    for k, v in env_overrides.items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = v
    proc = subprocess.run(["cmd", "/c", str(PROBE)], capture_output=True, env=env, cwd=str(cwd))
    return proc.returncode, proc.stdout.decode(GBK, "replace")


def find_python(out: str) -> str | None:
    m = re.search(r"PROBE_OK_PY=([^\r\n]+)", out)
    return m.group(1).strip() if m else None


def main() -> int:
    if not LAUNCHER.is_file():
        print(f"未找到 {LAUNCHER}")
        return 2

    print("=" * 78)
    print("A. Python 发现能力")
    print("=" * 78)
    make_probe()
    scenarios = [
        ("PYTHON_EXE 指向不存在的路径", {"PYTHON_EXE": r"D:\no-such-python\python.exe"}),
        ("PATH 上的 python 是 Store 占位程序", {"PYTHON_EXE": STORE_STUB}),
        ("不设置任何变量（正常机器）", {"PYTHON_EXE": None}),
    ]
    for name, env in scenarios:
        code, out = run(env)
        found = find_python(out)
        record(f"{name} -> 能找到可用 Python", bool(found), out[:300])
        if found:
            print(f"         使用：{found}")

    print()
    print("=" * 78)
    print("B. 完全没有 Python（清空 PATH 模拟）")
    print("=" * 78)
    code, out = run({"PATH": r"C:\Windows\system32;C:\Windows", "PYTHON_EXE": None})
    record("提示没有找到 Python", "没有找到可用的 Python" in out, out[:300])
    record("给出 python.org 下载链接", "python.org" in out)
    record("提示勾选 Add python.exe to PATH", "Add python.exe to PATH" in out)
    record("解释 Store 占位程序的坑", "占位程序" in out)
    record("以退出码 1 结束（便于脚本判断）", code == 1, f"实际 {code}")

    print()
    print("=" * 78)
    print("C. 必需文件缺失（模拟只复制了部分文件）")
    print("=" * 78)
    make_probe(break_files=True)
    code, out = run({"PYTHON_EXE": None})
    record("明确报出缺失文件", "必需文件不存在" in out, out[:400])
    record("提示要完整解压", "完整解压" in out)
    record("以退出码 1 结束", code == 1, f"实际 {code}")

    # 清理
    if PROBE.exists():
        PROBE.unlink()

    print()
    print("=" * 78)
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"交付检查：通过 {passed} / {len(results)}")
    if passed != len(results):
        print("未通过项：")
        for n, ok, d in results:
            if not ok:
                print("  -", n)
        return 1
    print("启动脚本在各种接收方环境下都能正确工作。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
