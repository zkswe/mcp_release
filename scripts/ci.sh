#!/usr/bin/env sh
# FlyThings MCP (open) — CI 前置闸门（POSIX sh；本地 / Gitee Go / GitHub Actions 通用）
#
# 跑什么：
#   1) 语法编译检查（python -m compileall，秒级，拦住低级语法错误）
#   2) 发布前置一致性 + 契约用例 + 冒烟：python scripts/check_consistency.py --with-tests
#      （内含 unittest 全量用例、smoke、**检索回归 check_retrieval**、manifest 新鲜度、双份 ui_tools 哈希、隐私扫描、静默 except）
# 可选：
#   CI_DEVICE=<adb serial 或 ip:port>   → 追加真机抓屏冒烟（需要 adb 与设备，缺省不跑）
#
# ⚠️ 契约用例**只跑一遍**（2026-10-03）：以前这里先单独跑一次 unittest、`--with-tests` 里又跑一次，
#    而全套是分钟级的真实离线工作（图像生成/构建编排类用例单条 5~10s）→ 白花一倍时间。
#    用例的"是否通过 + 条数是否与 tests/README 一致"由 `--with-tests` 一并负责。
#
# 用法：sh scripts/ci.sh
set -e
cd "$(dirname "$0")/.."
echo "=== python ==="
python -V

echo "=== 1/2 compileall ==="
python -m compileall -q . >/dev/null

echo "=== 2/2 consistency + tests + smoke ==="
python scripts/check_consistency.py --with-tests

if [ -n "$CI_DEVICE" ]; then
    echo "=== extra: device screenshot smoke ($CI_DEVICE) ==="
    python scripts/smoke.py --screenshot --device "$CI_DEVICE"
fi

echo "=== CI OK ==="
