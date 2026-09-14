#!/bin/bash
# components/ble 编译自检（**gatt 后端** + 公共 TU：Z20 / Z21 两组 include 目录都要过）
#
# 用法（Windows 侧，本机实测可复现的一条命令）：
#     wsl bash components/ble/scripts/compile_check_gatt.sh
#
# 为什么在 WSL 里要让 cmd.exe 代跑编译器（踩坑结论，别改）：
#   交叉编译器 C:\zkswe\fun\toolchains\z21\bin\arm-pc-linux-gnueabihf-gcc.exe 是
#   **Windows 可执行文件**（fun 就是这么用的）。直接从 WSL 里 exec 它（无论用 /mnt/c 路径还是
#   C:\ 路径）会有两个连锁问题：
#     1) argv[0] 变成 POSIX 路径 → 驱动按 argv[0] 推算自己的 libexec 前缀算错 →
#        `CreateProcess: No such file or directory`（找不到 cc1plus.exe）；
#     2) 就算用 -B 硬指到 libexec 把 cc1plus 找回来，sysroot / C++ 头路径也是从同一个前缀推的
#        → 直接 `fatal error: stdint.h: No such file or directory`。
#   → 正解：写一个最小 .bat（路径全用 Windows 形式），用 cmd.exe /c 代跑，argv[0] 恢复成
#     C:\... 形式，驱动自己就能把 libexec / sysroot / C++ 头全推对（实测 rc=0）。
#
# 通过标准：两个平台 rc 都 = 0，且后端产物 .o > 4KB（几百字节 = ZKBLE_IS_GATT 门被关掉了，
#          说明 gatt 的 include 路径没生效，要当失败看），公共 TU 里 8 个公共 API 符号齐全。
set -u

HERE="$(cd "$(dirname "$0")/.." && pwd)"                 # = .../components/ble
SRC="$HERE/src/zk_ble_gatt.cpp"
PUB="$HERE/src/zkble_public.cpp"                          # 公共 API 实现（后端无关，必须一起编）
INC="$HERE/include"

CC_W='C:\zkswe\fun\toolchains\z21\bin\arm-pc-linux-gnueabihf-gcc.exe'
CBAT="/mnt/c/Windows/System32/cmd.exe"
OUTDIR="${ZKBLE_OUTDIR:-/mnt/c/Users/zkswe/AppData/Local/Temp}"
MIN_OBJ=4096                                             # 小于这个字节数 = gate 没生效
MIN_PUB=1024

mkdir -p "$OUTDIR" 2>/dev/null || { echo "!! 输出目录不可用: $OUTDIR"; exit 1; }
[ -f "$SRC" ] || { echo "!! 源文件不存在: $SRC"; exit 1; }
[ -f "$PUB" ] || { echo "!! 公共 TU 不存在（应用会链接不到 version/on*/offAll）: $PUB"; exit 1; }
SRC_W="$(wslpath -w "$SRC")"
INC_W="$(wslpath -w "$INC")"

echo "== module  : $HERE"
echo "== compiler: $CC_W"
echo "== source  : zk_ble_gatt.cpp $(wc -l < "$SRC") 行 / zkble_public.cpp $(wc -l < "$PUB") 行"
echo "== outdir  : $OUTDIR"

# compile_one <平台> <源文件(POSIX 路径)> <标签>  → stdout 只吐产物字节数
compile_one() {
    local plat="$1" src="$2" tag="$3"
    local out="$OUTDIR/zkble_${tag}_${plat}.o"
    local log="$OUTDIR/zkble_${tag}_${plat}.log"
    local bat="$OUTDIR/zkble_${tag}_${plat}.bat"
    local srcw outw batw
    srcw="$(wslpath -w "$src")"
    outw="$(wslpath -w "$out")"
    batw="$(wslpath -w "$bat")"
    rm -f "$out"
    {
        printf '@echo off\r\n'
        printf '"%s" -std=c++11 -Wall -c "%s" -I"%s" -I"%s" -o "%s"\r\n' \
               "$CC_W" "$srcw" "$INC_W" "$PKG_W" "$outw"
        printf 'exit /b %%errorlevel%%\r\n'
    } > "$bat"
    "$CBAT" /c "$batw" > "$log" 2>&1
    local rc=$?
    if [ $rc -ne 0 ]; then
        echo "== [$plat/$tag] compile rc=$rc —— 报错/告警前 60 行：" >&2
        grep -n -E "error|warning" "$log" | head -60 >&2
        return $rc
    fi
    local size
    size=$(stat -c %s "$out" 2>/dev/null || echo 0)
    echo "== [$plat/$tag] compile rc=0  size=$size bytes  ($out)" >&2
    echo "$size"
    return 0
}

rc_all=0
for plat in z20 z21; do
    # gatt 包可能落在用户注册表（~/.fun）或工具链自带注册表（C:\zkswe\fun\registry），两个都探
    PKG=""
    for cand in \
        "/mnt/c/Users/zkswe/.fun/registry/public/$plat/gatt/1.0.0/include" \
        "/mnt/c/zkswe/fun/registry/public/$plat/gatt/1.0.0/include"; do
        if [ -d "$cand" ]; then PKG="$cand"; break; fi
    done
    if [ -z "$PKG" ]; then
        echo "== [$plat] SKIP：找不到 $plat/gatt/1.0.0/include（先在项目里 fun install gatt 1.0.0）"
        rc_all=1
        continue
    fi
    echo "== [$plat] gatt include: $PKG"
    PKG_W="$(wslpath -w "$PKG")"

    OUT="$OUTDIR/zkble_gatt_$plat.o"
    size=$(compile_one "$plat" "$SRC" gatt) || { rc_all=1; continue; }
    if [ "$size" -lt "$MIN_OBJ" ]; then
        echo "== [$plat] 后端产物只有 $size 字节 → 门 ZKBLE_IS_GATT 没开（include 路径没生效）"
        rc_all=1
        continue
    fi

    # 公共 TU（后端无关；两个后端工程都要编它）
    POUT="$OUTDIR/zkble_public_$plat.o"
    psize=$(compile_one "$plat" "$PUB" public) || { rc_all=1; continue; }
    if [ "$psize" -lt "$MIN_PUB" ]; then
        echo "== [$plat] 公共 TU 产物只有 $psize 字节，疑似空对象"
        rc_all=1
        continue
    fi

    # 公共 API 符号核对（8 个：version/setLogHook/on×5/offAll）
    syms=$(nm -C "$POUT" 2>/dev/null | grep -c "zk::ble::")
    echo "== [$plat] public symbols in object: $syms (期望 >= 8)"
    if [ "$syms" -lt 8 ]; then
        echo "!! 公共 API 符号缺失（应用会链接不到）："
        nm -C "$POUT" | grep "zk::ble::" || true
        rc_all=1
    fi
done

echo "== summary rc=$rc_all"
exit $rc_all

# ---------------------------------------------------------------- Windows 原生等价命令（不开 WSL，实测 rc=0）
# 在 PowerShell 里直接跑：
#   cd C:\Users\zkswe\.openclaw\workspace\tools\FlyThings_mcp_open\components\ble
#   & "C:\zkswe\fun\toolchains\z21\bin\arm-pc-linux-gnueabihf-gcc.exe" -std=c++11 -Wall -c src/zk_ble_gatt.cpp `
#       -Iinclude -I"C:\Users\zkswe\.fun\registry\public\z20\gatt\1.0.0\include" `
#       -o "$env:TEMP\zk_ble_gatt.o"
#   & "C:\zkswe\fun\toolchains\z21\bin\arm-pc-linux-gnueabihf-gcc.exe" -std=c++11 -Wall -c src/zkble_public.cpp `
#       -Iinclude -o "$env:TEMP\zkble_public.o"
