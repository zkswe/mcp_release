#!/usr/bin/env sh
# FlyThings MCP (open) — CI 前置闸门（POSIX sh；本地 / Gitee Go / GitHub Actions 通用）
#
# 跑什么：
#   1) 语法编译检查（python -m compileall，秒级，拦住低级语法错误）
#   2) 发布前置一致性 + 契约用例 + 冒烟：python scripts/check_consistency.py --with-tests
#      （内含 unittest 38 项、smoke 30+ 项、manifest 新鲜度、双份 ui_tools 哈希、隐私扫描、静默 except）
# 可选：
#   CI_DEVICE=<adb serial 或 ip:port>   → 追加真机抓屏冒烟（需要 adb 与设备，缺省不跑）
#
# 用法：sh scripts/ci.sh
set -e
cd "$(dirname "$0")/.."
echo "=== python ==="
python -V

echo "=== 1/3 compileall ==="
python -m compileall -q . >/dev/null

echo "=== 2/3 tests ==="
python -m unittest discover -s tests -q

echo "=== 3/3 consistency + smoke ==="
python scripts/check_consistency.py --with-tests

if [ -n "$CI_DEVICE" ]; then
    echo "=== extra: device screenshot smoke ($CI_DEVICE) ==="
    python scripts/smoke.py --screenshot --device "$CI_DEVICE"
fi

echo "=== CI OK ==="
