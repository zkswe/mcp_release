#!/bin/bash
# components/ble 编译自检（**btstack 后端** + 公共 TU + 示例），F133 交叉编译器，单文件 -c
#
# 用法（Windows 侧）： wsl bash components/ble/scripts/compile_check.sh
# 通过标准：rc=0；失败时输出前 60 行编译错误。
#
# 为什么还要编 src/zkble_public.cpp（不是可选）：
#   公共 API（version/setLogHook/on*/offAll）只有声明的头 + 一个实现 TU；
#   只 include 公开头的应用 TU 看不到定义 → 少编这个文件就链接不到（子代理链接验证时暴露过）。
#   所以这里同时用 nm 核对它在目标文件里**真的导出了**这些符号。
set -u
HERE="$(cd "$(dirname "$0")/.." && pwd)"
WSL_WS="/mnt/c/Users/zkswe/.openclaw/workspace"
TC="$WSL_WS/toolchain/F133-F135C906-Xuantie-900-gcc-linux-6.6.0-musl64-x86_64-V2.10.2-20240904/bin"
PKG="/mnt/c/Users/zkswe/.fuse/registry/public/f133"
CC="$TC/riscv64-unknown-linux-musl-gcc"
NM="$TC/riscv64-unknown-linux-musl-nm"

echo "== module : $HERE"
echo "== compiler: $($CC --version | head -1)"
cd "$HERE" || exit 1

# 1) btstack 后端（本文件只在 btstack 后端时编译；见 src/zkble_backend.h）
$CC -Wall -c src/zk_ble.cpp \
    -Iinclude \
    -I"$PKG/btstack/1.7.2/include" \
    -I"$PKG/easyui/2.9.0/include" \
    -o /tmp/zk_ble.o 2>&1 | head -60
rc=${PIPESTATUS[0]}
echo "== backend compile rc=$rc"
[ $rc -eq 0 ] || exit $rc
ls -l /tmp/zk_ble.o

# 2) 公共 TU（后端无关；两个后端工程都要编它）
$CC -Wall -c src/zkble_public.cpp -Iinclude -o /tmp/zkble_public.o 2>&1 | head -40
pub_rc=${PIPESTATUS[0]}
echo "== public TU compile rc=$pub_rc"
[ $pub_rc -eq 0 ] || exit $pub_rc
ls -l /tmp/zkble_public.o

# 2.1) 公共 API 符号核对（8 个：version/setLogHook/on×5/offAll）
if [ -x "$NM" ]; then
    syms=$("$NM" -C /tmp/zkble_public.o 2>/dev/null | grep -c "zk::ble::")
    echo "== public symbols in object: $syms (期望 >= 8)"
    if [ "$syms" -lt 8 ]; then
        echo "!! 公共 API 符号缺失：版本/回调/日志钩子少定义"
        "$NM" -C /tmp/zkble_public.o | grep "zk::ble::" || true
        exit 1
    fi
else
    echo "== NOTE: 没有 $NM，跳过符号核对"
fi

# 3) 示例也要真的编过（组件规范：example 必须真编过）
for ex in example/*.cc; do
    $CC -Wall -c "$ex" -Iinclude -o /tmp/"$(basename "$ex")".o 2>&1 | head -30
    ex_rc=${PIPESTATUS[0]}
    echo "== example $ex rc=$ex_rc"
    [ $ex_rc -eq 0 ] || exit $ex_rc
done

echo "== all ok (backend + public TU + examples)"
exit 0
