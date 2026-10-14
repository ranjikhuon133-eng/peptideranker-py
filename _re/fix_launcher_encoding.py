"""把启动脚本的 `@echo off` 提到第一行（保持 GBK 编码 + CRLF 换行）。

背景：cmd.exe 要求 .bat 是 GBK/ANSI(936) + CRLF；若 `@echo off` 不是第一行，
前两条命令会被回显，而回显时控制台按 OEM 代码页解码，中文会显示成乱码，
用户第一眼看到的是一屏乱码，体验很差。
"""
import io
import sys

path = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\wangchenxu\Desktop\PeptideRanker_Share\启动网页.bat"
gbk = "gbk"

with io.open(path, "r", encoding=gbk, newline="") as fh:
    text = fh.read()

# 归一化换行
text = text.replace("\r\n", "\n").replace("\r", "\n")
lines = text.split("\n")

# 去掉所有位于开头的空行/注释前的 @echo off，再插到最前面
lines = [ln for ln in lines if ln.strip().lower() != "@echo off"]
while lines and not lines[0].strip():
    lines.pop(0)
lines.insert(0, "@echo off")

text = "\r\n".join(lines)
if not text.endswith("\r\n"):
    text += "\r\n"

with io.open(path, "w", encoding=gbk, newline="") as fh:
    fh.write(text)

# 校验
with io.open(path, "r", encoding=gbk, newline="") as fh:
    back = fh.read()
first = back.split("\n")[0].rstrip("\r")
print("first_line=%r" % first)
print("has_crlf=%s" % ("\r\n" in back))
print("echo_off_count=%d" % sum(1 for ln in back.split("\n") if ln.strip().lower() == "@echo off"))
print("total_lines=%d" % len(back.split("\n")))
