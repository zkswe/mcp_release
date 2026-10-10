# example —— Blend2D 门面（`zk::b2d`）最小可编示例（Z20 480×480）

> 这**就是一个能编的 FlyThings 工程**（只留必要文件，没有 `fsc.exe`/`fui.exe`/`.fun/` 产物）。
> 原样搬到开发工作区 → `fsc build -p Z20` 即可（本轮**只编译验证，未上真机**）。
> 真机性能/效果证据见组件 [README.md](../README.md) 的性能表与 [lib/BUILD_INFO.md](../lib/BUILD_INFO.md)。

## 它演示什么

一页 480×480：`B2dCanvas`（480×440 的只读 textview，当"画布"用）+ `TextDiag`（480×40 读数行）。
每 200 ms 用 Blend2D 在**内存画布**上重画一帧 —— 不透明底 + 圆角卡片 + **2 层阴影** + 1px 描边 +
**蓝→绿渐变圆角条**（宽度随帧动）+ **三行中英文文本** —— 然后 `setInvalid` 翻帧上屏；
首帧同时把同一份像素 `savePng("/tmp/b2d_card.png")`（演示"离屏出图"，与上屏同一份像素）。

## 文件清单

| 文件 | 作用 |
|---|---|
| `Manifest.xml` | 依赖声明：**`blend2d 0.11.1`** + easyui/log/zkhardware/zknet/base-utility |
| `.fun-lock.json` / `.deps.lock` | 依赖解析快照（实际落 `easyui 2.6.0` / `base-utility 10.12.4`） |
| `.project` | IDE 工程描述（`fsc build` 不需要） |
| `ui/main.json` / `ui/main.ftu` | 页面布局（json 是源，ftu 是产物） |
| `src/Main.cpp` | 应用入口（模板自带） |
| `src/logic/mainLogic.cc` | **示例逻辑本体**：open → setBackgroundBmp（只挂一次）→ 定时重绘 → setInvalid |
| `src/uart/*`、`src/activity/*` | 工程模板自带，本示例不改 |
| `src/zk/zk_blend2d.{h,cpp}` | **组件本体**（= `../include/zk/zk_blend2d.h` + `../src/zk_blend2d.cpp` 原样拷贝） |
| `src/dependencies/lib/libblend2d.so` | **要打进固件的那个 `.so`**（此处放的是原厂档 1,472,816 B） |

## 从零跑起来

```powershell
mkdir C:\work\B2dCardZ20
copy -r tools\FlyThings_mcp_open\components\blend2d\example\* C:\work\B2dCardZ20\
cd C:\work\B2dCardZ20
fsc build -p Z20                     # ← 本轮实测通过（见下）
```

**换性能档（NEON）**：把 `components/blend2d/lib/z20-neon/libblend2d.so` 覆盖到
`src/dependencies/lib/libblend2d.so` 即可，**代码一行不改**（ABI 787/787 全等；
⚠️ NEON 档多依赖 `libgcc_s.so.1`，Z20 真机有）。

**上真机（本示例未做，但通道已验）**：

```powershell
fsc launch -p Z20 -s <设备IP:5555>                        # 推 App（⚠️ 不推第三方包 .so）
adb push src\dependencies\lib\libblend2d.so /tmp/libblend2d.so   # ← 手推库，否则 initLib error
adb shell setprop ctl.restart zkswe                      # 重启应用加载新库
adb shell cat /tmp/b2d_card.png > card.png               # 取"离屏出图"证据（可选）
```
> 量产不要手推：`fsc pack` 会把 `src/dependencies/lib/*.so` 打进 `update.img`
> （实测：原厂档 `update.img` 1,143,336 B / NEON 档 1,262,120 B / 无 blend2d 基线 647,720 B）。

## 本轮实测（编译验证）

```
C:\work\B2dCardZ20> fsc build -p Z20
...
[8/10] Building CXX object CMakeFiles/zkgui.dir/.../src/logic/mainLogic.cc.o
.../src/logic/mainLogic.cc:26:9: warning: #pragma once in main file
[9/10] Building CXX object CMakeFiles/zkgui.dir/generated/ui_main.cpp.o
[10/10] Linking CXX shared library libzkgui.so
exit=0    产物 .fun/z20/libzkgui.so = 301,892 B（NEEDED 含 libblend2d.so）
```
> 旁边那串 `vector.tcc: parameter passing ... changed in GCC 7.1` 是 GCC 8.3 的**note**（非错误、非 warning），
> 由 `std::vector<std::pair<float, BLFont>>` 触发，可以无视。

## 上真机前必须知道的 3 条（否则大概率白跑）

1. **字体**：中文/文字 API 要 TTF。示例走候选链 `/res/font/zkswe-hans-common.ttf → /tmp/font/… → /mnt/extsd/font/…`；
   都没有时**文本会明确报 `ERR_FONT`**（不静默）——把 `components/fonts/` 的字体推上去即可。
2. **`.so` 必须在设备上**：`fsc launch` 不推第三方包 `.so`（只推 `libzkgui.so`+`ftu`+字体），按上面的 `adb push /tmp` 走。
3. **阴影层数**：示例用 2 层（推荐）。改成 8 层的话，480×480 一帧要多花 ~15 ms —— 实测 8 层阴影吃掉整帧 83%。
