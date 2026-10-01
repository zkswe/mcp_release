#!/usr/bin/env bash
# =============================================================================
# build-neon.sh —— 重编 Blend2D 0.11.1（ARM32 + NEON）为「性能档」libblend2d.so
#
# 产出：<工作目录>/build_o2/libblend2d.so  → 覆盖到 components/blend2d/lib/z20-neon/
# 口径：与 components/blend2d/lib/BUILD_INFO.md §2 完全一致（构建日期 2026-10-01 的那一份）
#
# 环境：WSL Ubuntu（bash + zip/unzip + cmake + ninja + git），驱动 Windows 版 Z20/z21 工具链
#   Z21  = /mnt/c/zkswe/fun/toolchains/z21        （arm-pc-linux-gnueabihf-gcc 8.3.0，Windows PE）
#   WORK = 工作目录（默认 ./blend2d-build，产物与源码都留在这里）
# 用法：
#   bash components/blend2d/scripts/build-neon.sh
#   Z21=/mnt/c/zkswe/fun/toolchains/z21 WORK=$HOME/b2d bash build-neon.sh
#
# 三个坑（本脚本已内置，别删）：
#   ① 上游 **没有 git tag** —— 0.11.1 只能按 commit `a7f9476`（2024-05-31）取；
#   ② 工具链默认 CPU 是 **armv5te** —— 必须显式 `-march=armv7-a`，否则编出 v5 代码；
#   ③ `--sysroot` + Windows 交叉工具链会让 **C++ 头搜索路径全丢** ——
#      必须显式补 `-isystem .../include/c++/8.3.0{,,/arm-pc-linux-gnueabihf,/backward}`，
#      否则 CMake 的 C++ 编译第一句就报 `cmath: No such file or directory`。
# =============================================================================
set -euo pipefail

Z21="${Z21:-/mnt/c/zkswe/fun/toolchains/z21}"
WORK="${WORK:-$(pwd)/blend2d-build}"
T=arm-pc-linux-gnueabihf
V=8.3.0
SRC_COMMIT=a7f9476          # = BL_MAKE_VERSION(0, 11, 1)，见 BUILD_INFO.md §1
MIRROR="${MIRROR:-https://gitee.com/mirrors/blend2d.git}"

need() { command -v "$1" >/dev/null 2>&1 || { echo "缺工具：$1（apt install $2）"; exit 1; }; }
need cmake cmake; need ninja ninja-build; need git git

mkdir -p "$WORK"
cd "$WORK"

# ---------------------------------------------------------------- 1. 工具链包装器
# 为什么要包装器：Windows 版 .exe 工具链在 WSL 里直接跑会因为
#   (a) 找不到 GCC 内部子程序（-B 要指到 bin / target-bin / libexec cc1 / lib gcc）
#   (b) /mnt/* 路径 Windows 不认（要翻译成 C:\...）
#   (c) --sysroot 让驱动丢掉 C++ 内建头（要补三条 -isystem）
#   (d) WSL<->Win 互操作偶发 UtilAcceptVsock 故障（要重试）
# 而失败，所以统一用它。
mkdir -p "$WORK/toolchain"
cat > "$WORK/toolchain/z21-gcc" <<'WRAP'
#!/usr/bin/env bash
# z21-gcc - drive the official z21 Windows toolchain from WSL
Z=/mnt/c/zkswe/fun/toolchains/z21
T=arm-pc-linux-gnueabihf
V=8.3.0
GCC="$Z/bin/${Z21_GCC_TOOL:-${T}-gcc}.exe"
RETRY="${Z21_RETRY:-8}"
W() { wslpath -w "$1"; }
args=(
  -B"$(W "$Z/bin")/"
  -B"$(W "$Z/$T/bin")/"
  -B"$(W "$Z/libexec/gcc/$T/$V")/"
  -B"$(W "$Z/lib/gcc/$T/$V")/"
  --sysroot="$(W "$Z/$T/sysroot")"
  # ★ 三条 C++ 头路径（少了就报 cmath: No such file or directory）
  -isystem "$(W "$Z/$T/include/c++/$V")"
  -isystem "$(W "$Z/$T/include/c++/$V/$T")"
  -isystem "$(W "$Z/$T/include/c++/$V/backward")"
  -isystem "$(W "$Z/lib/gcc/$T/$V/include")"
  -isystem "$(W "$Z/lib/gcc/$T/$V/include-fixed")"
)
for a in "$@"; do
  case "$a" in
    /dev/null) args+=('NUL'); continue ;;
    -I/mnt/*|-L/mnt/*|-B/mnt/*|-isystem/mnt/*|--sysroot=/mnt/*|-isysroot/mnt/*|-idirafter/mnt/*|-iquote/mnt/*)
      p="/${a#*/}"; pre="${a%"$p"}"; args+=("${pre}$(W "$p")"); continue ;;
    /mnt/*) args+=("$(W "$a")"); continue ;;
  esac
  args+=("$a")
done
n=1
while :; do
  out="$("$GCC" "${args[@]}" 2>&1)"; rc=$?
  [ $rc -eq 0 ] && { [ -n "$out" ] && printf '%s\n' "$out"; exit 0; }
  case "$out" in
    *error:*|*Error:*|*"fatal error"*|*warning:*|*undefined*)
      printf '%s\n' "$out"; exit $rc ;;
  esac
  [ "$n" -ge "$RETRY" ] && { printf '%s\n' "$out"; exit $rc; }
  n=$((n+1)); sleep 0.4
done
WRAP
chmod +x "$WORK/toolchain/z21-gcc"
cat > "$WORK/toolchain/z21-g++" <<'WRAP'
#!/usr/bin/env bash
export Z21_GCC_TOOL=arm-pc-linux-gnueabihf-g++
exec "$(dirname "$0")/z21-gcc" "$@"
WRAP
chmod +x "$WORK/toolchain/z21-g++"

cat > "$WORK/toolchain/z20-toolchain.cmake" <<CMAKE
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR arm)
set(TC_DIR $WORK/toolchain)
set(CMAKE_C_COMPILER   \${TC_DIR}/z21-gcc)
set(CMAKE_CXX_COMPILER \${TC_DIR}/z21-g++)
set(CMAKE_FIND_ROOT_PATH $Z21/$T/sysroot)
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
CMAKE

# ---------------------------------------------------------------- 2. 取源码（按 commit 锁）
if [ ! -d "$WORK/repo/.git" ]; then
  git clone --no-checkout "$MIRROR" "$WORK/repo"
fi
git -C "$WORK/repo" fetch --all --tags --quiet || true
git -C "$WORK/repo" worktree add -f "$WORK/src_0111" "$SRC_COMMIT" 2>/dev/null \
  || { mkdir -p "$WORK/src_0111"; git -C "$WORK/repo" --work-tree="$WORK/src_0111" checkout -f "$SRC_COMMIT"; }
# 版本自证：必须是 0, 11, 1
grep -n "BL_MAKE_VERSION(0, 11, 1)" "$WORK/src_0111/src/blend2d/api.h" \
  || { echo "警告：源码不是 0.11.1（commit $SRC_COMMIT 变了？）"; }

# ---------------------------------------------------------------- 3. 配置 + 编译
cd "$WORK"
cmake -G Ninja -S src_0111 -B build_o2 \
  -DCMAKE_TOOLCHAIN_FILE="$WORK/toolchain/z20-toolchain.cmake" \
  -DCMAKE_BUILD_TYPE=Release -DBLEND2D_NO_JIT=ON -DBLEND2D_STATIC=OFF \
  -DBLEND2D_NO_STDCXX=0 -DBLEND2D_TEST=OFF -DBLEND2D_NO_INSTALL=ON \
  -DCMAKE_C_FLAGS='-march=armv7-a -mfpu=neon -mfloat-abi=hard' \
  -DCMAKE_CXX_FLAGS='-march=armv7-a -mfpu=neon -mfloat-abi=hard' \
  -DCMAKE_C_FLAGS_RELEASE='-O2 -DNDEBUG' -DCMAKE_CXX_FLAGS_RELEASE='-O2 -DNDEBUG'
ninja -C build_o2 -j"${JOBS:-8}"

# ---------------------------------------------------------------- 4. 产物自检
SO="$WORK/build_o2/libblend2d.so"
ls -l "$SO"; md5sum "$SO"
RE="$Z21/bin/${T}-readelf.exe"; OD="$Z21/bin/${T}-objdump.exe"
if [ -x "$RE" ]; then
  "$RE" -A "$SO" | grep -E "Tag_CPU_name|Tag_CPU_arch:|Tag_FP_arch|Tag_Advanced_SIMD" || true
  "$RE" -d "$SO" | grep NEEDED || true
  "$RE" --dyn-syms "$SO" | awk '$7!="UND" && $8 ~ /^bl/ {n++} END{print "defined bl* symbols:", n}'
fi
if [ -x "$OD" ]; then
  echo "objdump 统计中（几十秒）..."
  "$OD" -d "$SO" | grep -oE '(^|[ ,\t])q[0-9]+' | wc -l | sed 's/^/q-reg hits: /'
fi
echo
echo "完成。换档：cp $SO <工程>/src/dependencies/lib/libblend2d.so"
echo "并对照 lib/BUILD_INFO.md §3 核对 md5 = C1E9DCCE2D1ACCC28EB46BB60F39CF72 / 1,874,056 B"
