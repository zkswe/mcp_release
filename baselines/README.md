# baselines —— 真机基线库（离线所见即所得回归）

**干什么用的**：一次上机抓一批真机截图当**基线**；以后改布局**离线**跑回归 ——
`wysiwyg_regress.py` 把布局 json 重新渲染一张图，跟基线截图逐像素比对，
回答「改了之后设备上看起来还一样吗」，**不用每次上机**。（0 token，纯本地算法。）

```
baselines/
  README.md                     ← 本文件
  wysiwyg_regress.py            ← 离线回归 CLI（唯一入口）
  z20_480x480/                  ← 一个「集合」= 一台设备 × 一种分辨率 × 一个工程
    manifest.json               ← 索引：每张基线的页面/尺寸/时间/设备/工程 json/md5 + 运行期状态
    01_main_screensaver.png     ← 真机截图（基线真源）
    02_home.png
    … 09_scenes.png
```

## 跑回归（离线，不需要设备）

```bash
python tools/FlyThings_mcp_open/baselines/wysiwyg_regress.py            # 全部条目
python tools/FlyThings_mcp_open/baselines/wysiwyg_regress.py --only wall,home
python tools/FlyThings_mcp_open/baselines/wysiwyg_regress.py --json temp/regress.json
```
输出：逐条 `wysiwyg_diff` **原文**（非文字区一致率 / 结构块 / 逐控件归因 top-N）+ 末尾**汇总表**。
退出码 `0` 全 PASS / `1` 有 FAIL / `2` 环境错。

判据与 `ui_tools/wysiwyg_diff.py` 同源：**非文字区超容差 ≤ 1.0%，且无 ≥8×8 的连通差异块**。
「运行期文字」（时钟/设备状态/主机 IP 一类由代码灌进去的值）自动从判据里排除（扫工程 `src/` 判定）。

## 上机重取基线（`--update`）

```bash
# 设备串口用参数或环境变量传，**设备 IP 不落盘**（仓库隐私扫描禁止内网 IP）
python tools/FlyThings_mcp_open/baselines/wysiwyg_regress.py --update --only wall \
       --device <serial|IP>:5555
# 或 export FLYTHINGS_TEST_DEVICE=<serial|IP>:5555 后 --update
```
流程：按 manifest 的 `capture.steps` **先回主页**（连点 7 次「返回」，并与 home 基线自检）
→ 逐步注入触摸 → 抓屏覆盖基线 → 更新 md5/时间 → **立刻跑一次该条回归当自检**。
`capture.from != "home"` 的条目（如屏保页）要人工把设备停到该页再加 `--force`。

## manifest 结构（关键字段）

| 字段 | 含义 |
|------|------|
| `device.*` | 型号/平台/分辨率/fb/bpp/rotate/easyui 版本/os 版本/机上 lib md5/触摸节点与协议 |
| `project.root` | 工程根（仓库相对路径）；`project.ftuMd5` = 设备上 ftu 的 md5（**应与本地一致**，证明确实在比同一版） |
| `entries[].page` / `json` | 归属页面 与 对应布局 json（**页面名按截图内容核对过**，不是猜的） |
| `entries[].md5` / `capturedAt` / `width`·`height` | 截图 md5 / 抓取时间 / 分辨率 |
| `entries[].capture.steps` | 复现该页的触摸序列（从主页起手；`tap/swipe` 原样执行，`wait N` 等待） |
| `entries[].scrollY` | 滚动页：内容容器上移该像素（= 滚到该位置） |
| `entries[].visibleOverrides` | 按 caption 覆盖 `visible`（复现运行期显示/隐藏，如 HA 模式下面板显示二维码块、隐藏主机 IP 行） |
| `entries[].ignoreRegions` | 运行期生成内容（二维码控件等）：两边同色置空不比 |

> ⚠️ 这三类「运行期状态」（scrollY / visibleOverrides / ignoreRegions）**必须写进 manifest**，
> 否则静态 json ≠ 设备上的样子 → 必假 FAIL。它们都会落一份临时 json，
> 且**渲染与 wysiwyg_diff 用同一份**（否则文字盒错位 → 假结构块）。

**不在离线承诺范围内**：滚动位置本身、动画、视频、屏保、旋转、系统栏 —— 见
`knowledge/devflow/wysiwyg-render-spec.md` 边界表。

## 纪律 / 注意

- 基线图是**真机像素**，含该设备当时的界面内容（设备名、内网地址文字、二维码等）→
  当作**开发期证据**留在仓库内可以，若要随包对外发布需先评估脱敏。
- 临时产物落 `temp/baseline_render/<集合>/`：渲染图会被清掉，`*.diff.json`（逐控件归因）保留当证据。
- 本 CLI 只用现成实现（子进程调 `ui_tools/wysiwyg_diff.py`、导入 `ui_tools/json2img.py` 与
  `ui_tools/device_screenshot.py`），不复制渲染/比对逻辑。
