@echo off
chcp 65001 >nul
setlocal

REM 个人公网 MCP 启动器：数据库仍留在本机，Cloudflare 仅提供 HTTPS 临时入口。
REM Token 由 Windows 用户环境变量提供，绝不写入仓库、批处理文件或日志。
REM setx 写入的是“用户环境”；这里读取它，避免当前已打开终端尚未刷新环境变量。
if "%REMOTE_MCP_API_TOKEN%"=="" for /f "usebackq delims=" %%T in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('REMOTE_MCP_API_TOKEN','User')"`) do set "REMOTE_MCP_API_TOKEN=%%T"
if "%REMOTE_MCP_API_TOKEN%"=="" (
    echo [错误] 未找到 REMOTE_MCP_API_TOKEN。
    echo 请重新打开命令提示符后再运行本脚本，或先执行令牌初始化。
    pause
    exit /b 1
)

set "CLOUDFLARED_EXE=cloudflared"
where cloudflared >nul 2>nul
if errorlevel 1 set "CLOUDFLARED_EXE=C:\Program Files (x86)\cloudflared\cloudflared.exe"
if not exist "%CLOUDFLARED_EXE%" (
    echo [错误] 未找到 cloudflared。请先安装 Cloudflare Tunnel 客户端。
    pause
    exit /b 1
)

REM MCP 仅监听本机；Cloudflare Quick Tunnel 负责生成临时 HTTPS 公网地址。
start "科技项目台账 MCP" /b python -X utf8 remote_mcp.py
timeout /t 2 /nobreak >nul
echo.
echo MCP 已启动。下方会显示临时 https://*.trycloudflare.com 地址。
echo Agent MCP 地址 = 显示的地址 + /mcp
echo 使用完毕后关闭本窗口，或在“科技项目台账 MCP”窗口按 Ctrl+C。
echo.
"%CLOUDFLARED_EXE%" tunnel --url http://127.0.0.1:8001
