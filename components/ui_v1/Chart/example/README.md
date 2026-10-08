# example —— Chart 最小可跑示例（Z21 1024×600）

> 这个目录就是一个**能编、能跑的 FlyThings 工程**（只留必要文件，没有 `fsc.exe`/`fui.exe`/`.fun/` 产物）。
> 真机验收证据在 `evidence/`。原样搬到开发工作区即可跑。

## 文件清单

| 文件 | 作用 |
|---|---|
| `Manifest.xml` | 依赖声明（easyui ^2.2.0 + log/zkhardware/zknet/base-utility） |
| `.deps.lock` | 依赖解析结果快照（实际落到 easyui 2.6.0） |
| `.project` | IDE 工程描述（`fsc build` 不需要） |
| `ui/main.html` | **本示例的手写源（原型稿）**：五个 `div.painter`（折线/柱/三环/仪表/**分段环**）+ 刻度 `textview` + 两个按钮 |
| `ui/main.json` / `ui/main.ftu` | `html2json` / `fui pack` 产物 |
| `src/Main.cpp` | 应用入口 |
| `src/logic/mainLogic.cc` | **示例逻辑**：五个 Chart 实例（LINE/BAR/RING/GAUGE/**RING+setRingSegments**）+ 换数据/追加点 |
| `src/uart/*` | 工程模板自带，本示例不改 |
| `src/zk/zk_chart.{h,cpp}` | **组件本体**（= `../include/zk/zk_chart.h` + `../src/zk_chart.cpp` 原样拷贝） |
| `evidence/*.png` | 真机截图 + 像素 diff（见 README §7 验收表） |

## 从零跑起来

```powershell
mkdir C:\work\ChartDemo
copy -r tools\FlyThings_mcp_open\components\ui_v1\Chart\example\* C:\work\ChartDemo\

python tools\ui_tools\html2json.py C:\work\ChartDemo\ui\main.html C:\work\ChartDemo\ui\main.json
cd C:\work\ChartDemo\ui ; <fui.exe> pack .

cd C:\work\ChartDemo
fsc build -p Z21
fsc launch -p Z21 -s 192.168.1.100:5555
```

> 关键布局约束：**刻度文字 `textview` 必须与 `painter` 同父**（组件给文字坐标时会加 painter 的左上角偏移）。
> 本示例里两者都是 `WinMain` 的直接子控件。

## 真机验收步骤（复现 README §7 的证据）

```powershell
adb push tools\FlyThings_mcp_open\bin_tools\z21\touch /tmp/touch ; adb shell chmod 777 /tmp/touch

# ① 初始帧（抓屏 → evidence/01）
# ② 换一批数据（四张图全换）
adb shell "/tmp/touch tap 805 28"
# ③ 追加一个点（只折线变）
adb shell "/tmp/touch tap 947 28"
# ④ 分段环（v0.2.0）：初始帧 evidence/06；点「换一批数据」后分段权重全变 -> diff 出 evidence/07
adb shell "/tmp/touch tap 805 28"
```

像素判据（0 token，程序化）：

```powershell
python tools\ui_tools\ui_diff.py C:\work\a.png C:\work\b.png --out C:\work\diff.png
# 期望：换数据 → 4 个图表区都有差异块（实测 28 处 / 39,489 px）
#       追加点 → **只有折线区**有差异（实测折线 12,599 px，柱/环/仪表 0 px）
#       分段环那条：换数据 → 36 处差异 / 55,965 px（分段环区 664~832 x 424~592 出现多处差异块）
```
