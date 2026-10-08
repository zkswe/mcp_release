# example —— TabView 最小可跑示例（Z21 1024×600）

> 这个目录就是**一个能编、能跑的 FlyThings 工程**（只留了必要文件，没有 `fsc.exe`/`fui.exe`/`.fun/` 产物）。
> 真机验收证据在 `evidence/`。**原样搬到开发工作区就能跑**，不需要改任何代码。

## 文件清单

| 文件 | 作用 |
|---|---|
| `Manifest.xml` | 依赖声明（easyui ^2.2.0 + log/zkhardware/zknet/base-utility） |
| `.deps.lock` | 依赖解析结果快照（`fsc install` 生成；写清实际落到的 easyui 2.6.0） |
| `.project` | IDE 工程描述（`fsc build` 不需要，留给 FlyThings IDE 打开用） |
| `ui/main.html` | **本示例的手写源（原型稿）**：受限 HTML 原型（顶栏页签 + pagewindow 两页） |
| `ui/main.json` | `html2json` 产物（布局真源） |
| `ui/main.ftu` | `fui pack` 产物（设备端实际加载的布局） |
| `src/Main.cpp` | 应用入口（`onStartupApp` → `mainActivity`） |
| `src/logic/mainLogic.cc` | **示例逻辑**：attach 组件 + 回调 + 页内两个计数按钮 |
| `src/uart/*` | FlyThings 工程模板自带（`Main.cpp` 打开串口用），本示例不改 |
| `src/zk/zk_tabview.{h,cpp}` | **组件本体**（= `../include/zk/zk_tabview.h` + `../src/zk_tabview.cpp` 的原样拷贝） |
| `evidence/*.png` | 真机截图（见 README §6 验收表） |

## 从零跑起来（Windows + FlyThings 工具链）

```powershell
# 0) 准备一个工作副本（本目录只读心态用，别在仓里 build）
mkdir C:\work\TabViewDemo
copy -r tools\FlyThings_mcp_open\components\ui_v1\TabView\example\* C:\work\TabViewDemo\   # ← 拷内容，不含 example 这层

# 1) 改原型（可选）：ui/main.html 改完重新生成 json + 打包
python tools\ui_tools\html2json.py C:\work\TabViewDemo\ui\main.html C:\work\TabViewDemo\ui\main.json
cd C:\work\TabViewDemo\ui ; <fui.exe> pack .        # fui.exe 在 FlyThings 安装目录 / 工具箱里

# 2) 编译（fsc build 会自动把 src\**\*.cpp 收进编译单元，实测）
cd C:\work\TabViewDemo
fsc build -p Z21

# 3) 上机（设备 adb-over-network）
fsc launch -p Z21 -s 192.168.1.100:5555
```

部署说明（Z21 特有，写死在这里省得踩）：`/res` 是 **squashfs 只读**，`fsc launch` 把
`libzkgui.so` / `main.ftu` / `EasyUI.cfg` 推到 **`/tmp/{lib,ui}`** 并重启应用；
`/data` **已满**，别往 `/data` 推东西。

## 真机验收步骤（复现 README §6 的证据）

```powershell
# 触摸注入工具（bin_tools/z21/touch，自动判 MT 协议）
adb push tools\FlyThings_mcp_open\bin_tools\z21\touch /tmp/touch ; adb shell chmod 777 /tmp/touch

adb shell "/tmp/touch swipe 900 300 150 300"      # 滑动切页：page0 -> page1
adb shell "/tmp/touch tap 110 42"                 # 点页签 Page 0 -> 回 page0
adb shell "/tmp/touch tap 130 248"                # 页内 +1 按钮（证明点击没被手势吃掉）
```

抓屏（**必须按 pan 偏移**，否则抓到的是上一帧）：

```powershell
cd tools\FlyThings_mcp_open
python -c "import sys;sys.path.insert(0,'ui_tools');import device_screenshot as dss;print(dss.capture(device='192.168.1.100:5555', out=r'C:\work\shot.png'))"
```

## 预期结果

- 初始：顶部 `Page 0` 文字为蓝色、其下方 2px 蓝色下划线；正文大字「第 0 页」；状态行 `onPageChanged: page=0 (当前页=0 OK)`。
- 左滑后：正文变「第 1 页」，`Page 1` 变蓝、下划线移到右侧，状态行 `page=1`。
- 点 `Page 0`：回到第 0 页，下划线回左侧。
- 连点页内 `点我 +1`：数字 0→1→2→3（**翻页手势不吃点击**）。
