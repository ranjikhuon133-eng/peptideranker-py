"""生成 停止程序.bat（GBK + CRLF）。

设计取舍（实测后定下来的）：
  * 外部强杀 taskkill 在受限环境里会 "Access denied"，不可靠；
  * 而服务本身提供的 /api/shutdown 是**已验证可用**的优雅退出路径。
因此顺序是：先请服务自己退出（HTTP），5 秒后仍在则退回强杀。
"""

from __future__ import annotations

import io
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "停止程序.bat"

CONTENT = r"""@echo off
rem =====================================================================
rem  PeptideRanker 肽活性打分 —— 停止程序（兜底用）
rem
rem  正常退出请优先用：网页右上角「退出程序」，或直接关闭启动脚本那个窗口。
rem  只有窗口被误关、服务卡住没退干净时，才需要双击本文件。
rem
rem  顺序：先请服务自己优雅退出（HTTP，可靠），5 秒后仍在则强制结束进程。
rem  不依赖 wmic（新系统已移除）或 Get-CimInstance（受限环境会被拒绝）。
rem
rem  注意：本文件必须保存为 GBK/ANSI(936) 编码 + CRLF 换行。
rem =====================================================================
setlocal EnableExtensions EnableDelayedExpansion
chcp 936 >nul 2>&1
cd /d "%~dp0"
title 停止 PeptideRanker 服务

echo.
echo  正在停止本机的 PeptideRanker 打分服务...
echo.

set "PORT="
rem 找出正在监听的本机端口（默认 8737，也可能是自动顺延的端口）
for %%P in (8737 8738 8739 8740 8741 8742 8743 8744 8745 8746) do (
  if not defined PORT (
    for /f "tokens=5" %%A in ('netstat -ano -p TCP ^| findstr /r /c:"LISTENING" ^| findstr /c:":%%P "') do (
      echo %%A| findstr /r "^[0-9][0-9]*$" >nul
      if not errorlevel 1 (
        set "PORT=%%P"
        set "SPID=%%A"
      )
    )
  )
)

if not defined PORT (
  echo  没有发现正在运行的 PeptideRanker 服务（可能已经退出了）。
  echo  端口空闲，可以正常使用。
  echo.
  pause
  endlocal
  exit /b 0
)

echo  发现服务在端口 !PORT! 上运行（PID !SPID!）。
echo.

rem ---- 第一步：请服务自己优雅退出（这是网页「退出程序」走的同一条路）----
echo  [1/2] 正在请求服务优雅退出...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:!PORT!/api/shutdown' -TimeoutSec 8 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1

set "WAIT=0"
:wait_loop
if !WAIT! GEQ 10 goto still_running
powershell -NoProfile -Command "Start-Sleep -Milliseconds 500" >nul 2>&1
netstat -ano -p TCP | findstr /r /c:"LISTENING" | findstr /c:":!PORT! " >nul 2>&1
if errorlevel 1 goto stopped
set /a WAIT+=1
goto wait_loop

:still_running
echo  [2/2] 优雅退出未生效，改为强制结束进程...
taskkill /F /T /PID !SPID! >nul 2>&1
if errorlevel 1 (
  echo.
  echo  [失败] 无法结束进程 PID !SPID!（权限不足）。
  echo         请右键本文件选择「以管理员身份运行」，或直接重启电脑。
  echo.
  pause
  endlocal
  exit /b 1
)
powershell -NoProfile -Command "Start-Sleep -Milliseconds 800" >nul 2>&1
netstat -ano -p TCP | findstr /r /c:"LISTENING" | findstr /c:":!PORT! " >nul 2>&1
if not errorlevel 1 (
  echo.
  echo  [失败] 端口 !PORT! 仍被占用，请稍后重试或重启电脑。
  echo.
  pause
  endlocal
  exit /b 1
)

:stopped
echo.
echo  服务已停止，端口 !PORT! 已释放。
echo  下次使用：双击 启动网页.bat 即可。
echo.
pause
endlocal
exit /b 0
"""

io.open(OUT, "w", encoding="gbk", newline="\r\n").write(CONTENT)
print(f"已写入 {OUT.name}，{OUT.stat().st_size} 字节")
