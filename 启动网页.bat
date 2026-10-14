@echo off
rem =====================================================================
rem  PeptideRanker 肽活性打分 —— 一键启动（Windows）
rem
rem  双击本文件即可：自动找到可用的 Python、补齐 numpy、启动服务并打开网页。
rem  只监听本机 127.0.0.1，不联网（除首次自动安装 numpy 外）。
rem
rem  注意：本文件必须保存为 GBK/ANSI(936) 编码，cmd.exe 才能正确解析中文。
rem        改用 UTF-8 会导致命令被拆坏、脚本无法运行（已实测踩坑）。
rem =====================================================================
setlocal EnableExtensions EnableDelayedExpansion
chcp 936 >nul 2>&1
cd /d "%~dp0"
title PeptideRanker 肽活性打分

set "PY="
set "FAILMSG="

echo.
echo  正在准备 PeptideRanker 肽活性打分...
echo.

rem ---------- 0. 先做一次自检：必需文件是否齐全 ----------
set "MISSING="
if not exist "pr_engine\scoring.py" set "MISSING=!MISSING! pr_engine\scoring.py"
if not exist "pr_engine\reference\oracle.py" set "MISSING=!MISSING! pr_engine\reference\oracle.py"
if not exist "app\server.py" set "MISSING=!MISSING! app\server.py"
if not exist "app\static\index.html" set "MISSING=!MISSING! app\static\index.html"
if not exist "Models_Short.txt" set "MISSING=!MISSING! Models_Short.txt"
if not exist "Models_Long.txt" set "MISSING=!MISSING! Models_Long.txt"
if not exist "Models_Short\fold0_v0\trained--20.model" set "MISSING=!MISSING! Models_Short\"
if not exist "Models_Long\fold0_v0\trained--20.model" set "MISSING=!MISSING! Models_Long\"
if defined MISSING (
  echo  [错误] 以下必需文件不存在：
  for %%M in (!MISSING!) do echo         %%M
  echo.
  echo  请确认整个文件夹被完整解压（不要只复制其中几个文件），
  echo  并且当前目录就是解压后的目录。
  echo.
  pause
  exit /b 1
)

rem ---------- 1. 依次尝试各种 Python，并实际执行确认可用 ----------
rem  注意：Windows 自带的 WindowsApps\python3.exe 是"商店占位程序"，
rem  未安装 Python 时会弹商店或直接失败，所以必须验证而不是看到文件就算数。
call :try_candidate "%PYTHON_EXE%"
if defined PY goto :found

rem 1a. 项目随包附带的运行时（如果有）
for %%D in ("%~dp0python\python.exe" "%~dp0runtime\python.exe") do (
  call :try_candidate "%%~fD"
  if defined PY goto :found
)

rem 1b. PATH 里的 python / python3
for %%C in (python.exe python3.exe) do (
  for /f "delims=" %%P in ('where %%C 2^>nul') do (
    call :try_candidate "%%P"
    if defined PY goto :found
  )
)

rem 1c. py 启动器（Windows 官方推荐方式）
where py.exe >nul 2>&1
if not errorlevel 1 (
  py -3 -c "import sys;sys.exit(0 if sys.version_info>=(3,9) else 1)" >nul 2>&1
  if not errorlevel 1 (
    set "PY=py -3"
    goto :found
  )
)

rem 1d. 常见安装位置
for %%R in (
  "%LOCALAPPDATA%\Programs\Python"
  "%ProgramFiles%"
  "%ProgramFiles(x86)%"
  "C:\"
  "D:\"
) do (
  for /d %%V in ("%%~R\Python3*") do (
    call :try_candidate "%%~fV\python.exe"
    if defined PY goto :found
  )
)

echo  [错误] 没有找到可用的 Python 3.9 或更高版本。
echo.
echo  解决办法（任选其一）：
echo    1. 到 https://www.python.org/downloads/ 下载安装，
echo       安装时务必勾选 "Add python.exe to PATH"，装完重新双击本文件。
echo    2. 或在命令行执行：winget install Python.Python.3.12
echo.
echo  提示：如果弹出 Microsoft Store，说明系统里那个 python 只是占位程序，
echo        并不是真正的 Python，请按上面第 1 条安装。
echo.
pause
exit /b 1

:found
echo  使用 Python：!PY!

rem ---------- 2. 检查解释器版本 ----------
!PY! -c "import sys;sys.exit(0 if sys.version_info>=(3,9) else 1)" >nul 2>&1
if errorlevel 1 (
  echo  [错误] 这个 Python 版本低于 3.9，需要 3.9 或更高。
  !PY! -c "import sys;print('        当前版本：',sys.version)"
  echo.
  pause
  exit /b 1
)
for /f "delims=" %%V in ('!PY! -c "import sys;print(sys.version.split()[0])" 2^>nul') do echo  版本：%%V

rem ---------- 3. 检查 numpy，缺了就自动装 ----------
!PY! -c "import numpy" >nul 2>&1
if errorlevel 1 (
  echo.
  echo  [提示] 未检测到 numpy（推理必需），正在尝试自动安装...
  !PY! -m pip install --disable-pip-version-check numpy
  !PY! -c "import numpy" >nul 2>&1
  if errorlevel 1 (
    echo.
    echo  [错误] numpy 安装失败。可能是这台电脑不能联网。
    echo.
    echo  请在有网络的机器上执行下面这条命令，然后把装好的环境拷过来：
    echo        !PY! -m pip install numpy
    echo  或者手动下载 numpy 的 .whl 文件离线安装。
    echo.
    pause
    exit /b 1
  )
  echo  numpy 安装完成。
)

rem ---------- 4. 启动服务 ----------
echo.
echo  ================================================================
echo   即将启动本地服务，浏览器会自动打开 http://127.0.0.1:8737/
echo   关闭本窗口即停止服务。
echo  ================================================================
echo.
!PY! "app\server.py" --open
set "RC=%ERRORLEVEL%"

echo.
if not "%RC%"=="0" echo  服务退出，返回码 %RC%（若上面有错误信息，请按提示处理）
echo  服务已停止。
pause
endlocal
exit /b %RC%

rem ---------------------------------------------------------------------
rem  子过程：实际执行候选 Python，成功才采用
rem ---------------------------------------------------------------------
:try_candidate
set "TMPPY=%~1"
if "%TMPPY%"=="" exit /b 0
if not exist "%TMPPY%" exit /b 0
rem 排除 Microsoft Store 占位程序（执行它会弹商店或报错）
echo %TMPPY% | findstr /i "WindowsApps" >nul && exit /b 0
"%TMPPY%" -c "import sys;sys.exit(0 if sys.version_info>=(3,9) else 1)" >nul 2>&1
if errorlevel 1 exit /b 0
set "PY=%TMPPY%"
exit /b 0
