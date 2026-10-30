@echo off
chcp 65001 >nul
title 银掌柜 · 本地演示服务（关掉此窗口即停止）
cd /d "%~dp0"

echo ============================================
echo   银掌柜 · 银行 AI 智能体   本地演示服务
echo ============================================
echo.
echo   服务地址： http://127.0.0.1:8000
echo   停止服务： 关闭此窗口 或 按 Ctrl+C
echo.

REM 3 秒后自动打开默认浏览器
start "" cmd /c "timeout /t 3 >nul & start http://127.0.0.1:8000/"

python run.py 8000

if errorlevel 1 (
  echo.
  echo [错误] 启动失败，可能是：
  echo   1) python 不在 PATH 中
  echo   2) 8000 端口已被占用（可先关闭其他命令行窗口）
  echo.
  pause
)
