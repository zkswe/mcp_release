@echo off
chcp 65001 >nul
echo ============================================
echo  FlyThings MCP Open - 依赖安装
echo ============================================
echo.
echo [1/2] 检查 Python...
python --version 2>nul
if %errorlevel% neq 0 (
    echo   未检测到 Python，请先安装 Python 3.10+：
    echo   https://www.python.org/downloads/
    pause
    exit /b 1
)
echo.
echo [2/2] 安装依赖（mcp + 本地向量模型推理）...
pip install mcp onnxruntime tokenizers
if %errorlevel% neq 0 (
    echo   安装失败，请检查网络后重试
    pause
    exit /b 1
)
echo.
echo ============================================
echo  安装完成！无需任何 API Key。
echo  下一步：在 AI 工具中按 README.md 配置 stdio
echo  （command: python  args: mcp_server.py 路径）
echo ============================================
pause
