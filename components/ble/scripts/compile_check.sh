#!/bin/bash
# components/ble 编译自检（F133 交叉编译器，单文件 -c）
# 用法（Windows 侧）： wsl bash components/ble/scripts/compile_check.sh
# 通过标准：rc=0；失败时输出前 60 行编译错误。
set -u
HERE="$(cd "$(dirname "$0")/.." && pwd)"
WSL_WS="/mnt/c/Users/zkswe/.openclaw/workspace"
TC="$WSL_WS/toolchain/F133-F135C906-Xuantie-900-gcc-linux-6.6.0-musl64-x86_64-V2.10.2-20240904/bin"
PKG="/mnt/c/Users/zkswe/.fuse/registry/public/f133"
CC="$TC/riscv64-unknown-linux-musl-gcc"

echo "== module : $HERE"
echo "== compiler: $($CC --version | head -1)"
cd "$HERE" || exit 1
$CC -Wall -c src/zk_ble.cpp \
    -Iinclude \
    -I"$PKG/btstack/1.7.2/include" \
    -I"$PKG/easyui/2.9.0/include" \
    -o /tmp/zk_ble.o 2>&1 | head -60
rc=${PIPESTATUS[0]}
echo "== compile rc=$rc"
[ $rc -eq 0 ] && ls -l /tmp/zk_ble.o
exit $rc
