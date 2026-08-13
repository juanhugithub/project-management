@echo off
cd /d "%~dp0"
title 科技项目台账
echo ============================================
echo   科技项目台账 正在启动...
echo   如未自动打开浏览器，请手动访问 http://127.0.0.1:8765
echo   关闭本窗口即停止程序
echo ============================================
where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 Python。请安装 Python 3.8+ 并勾选 "Add Python to PATH"。
    pause
    exit /b 1
)
python app.py
pause
