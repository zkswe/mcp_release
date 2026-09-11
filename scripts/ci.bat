@echo off
chcp 65001 >nul
rem FlyThings MCP (open) — CI 前置闸门（Windows；等价于 scripts/ci.sh）
rem
rem  1) 语法编译检查  2) 契约用例  3) 一致性 + 冒烟（发布前置）
rem  可选：set CI_DEVICE=192.168.1.100:5555  → 追加真机抓屏冒烟
setlocal
cd /d "%~dp0.."

echo === python ===
python --version || (echo [X] 未检测到 python & exit /b 1)

echo === 1/3 compileall ===
python -m compileall -q . >nul || (echo [X] 语法检查失败 & exit /b 1)

echo === 2/3 tests ===
python -m unittest discover -s tests -q || (echo [X] 契约用例失败 & exit /b 1)

echo === 3/3 consistency + smoke ===
python scripts\check_consistency.py --with-tests || (echo [X] 前置闸门失败 & exit /b 1)

if not "%CI_DEVICE%"=="" (
    echo === extra: device screenshot smoke (%CI_DEVICE%) ===
    python scripts\smoke.py --screenshot --device %CI_DEVICE% || (echo [X] 真机抓屏冒烟失败 & exit /b 1)
)

echo === CI OK ===
endlocal
