@echo off
chcp 65001 >nul
echo ============================================
echo  FlyThings MCP Open - 依赖安装
echo ============================================
echo.
echo [1/3] 检查 Python...
python --version 2>nul
if %errorlevel% neq 0 (
    echo   未检测到 Python，请先安装 Python 3.10+：
    echo   https://www.python.org/downloads/
    pause
    exit /b 1
)
echo.
echo [2/3] 安装依赖（requirements.lock = 已验证版本组合，可复现）...
pip install -r "%~dp0requirements.lock"
if %errorlevel% neq 0 (
    echo   安装失败，请检查网络后重试
    pause
    exit /b 1
)
echo.
echo [3/3] 自检（离线 smoke，不连真机）...
python "%~dp0scripts\smoke.py"
if %errorlevel% neq 0 (
    echo   ⚠️ 自检未全绿，请把上面的输出发给维护者；依赖已装好，仍可继续配置。
)
echo.
echo ============================================
echo  安装完成！无需任何 API Key。
echo  下一步：在 AI 工具中按 README.md 配置 stdio
echo  （command: python  args: mcp_server.py 路径）
echo ============================================
pause
