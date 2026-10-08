# fonts —— 字库模块：思源黑体三版本 + 设备字体自检

> 解决一个很常见、但每次都要重新踩的坑：**设备自带字库是裁剪字库（甚至只有英文）→ 界面汉字显示成方块**。
> 本模块给出：① 思源黑体裁好的三个版本；② 一条命令体检设备、缺中文就自动把字体投进工程。
> 立项：2026-09-13（现场反馈：字体只有几十K/100多K 大概率只有英文 → 这时默认把思源黑体放进去；先把思源黑体裁成 常用中文/全中文/多国语言 三版）

## 0. 默认口径（v0.27.86 接成自动动作；v0.27.87 判定升级为**硬判据**）

- `flythings_build_ui_flow` 每次构建/部署前都会做**字体体检**：有设备就扫设备字体，没设备就退化为
工程侧 self-scan；判定**缺中文**就**默认投 `common` 档**进工程 `font/`（在 build 之前完成），
返回体 `fontCheck` 写清 `missingChinese` / `maxFontBytes` / `advisedTier` / `delivered` / `deviceFonts`。
- **判定用 cmap 覆盖率（硬判据，v0.27.87）**：挑设备上**最大的**ttf/ttc → **拉回本机**（临时文件，
用完即删）→ `fontTools` 读 cmap → 以 **GB2312 一级 3755 字**为基准：
  **≥90% → `ok`（不投）／50–90% → `low`（投 + 写明覆盖率）／<50% → `missing`（投）**；
返回体字段 `source`（`cmap`/`size`）、`cmapCoverageGB2312L1`、`checkedFont`；
超 12 MB 或 fontTools 不可用 → **退回体积判据**（`source="size"`，原因进 `warnings`）。
结论缓存到 `~/.fun/font-probe.json`（键 = serial+文件+体积+ls 时间）→ 不会每次 build 都拉。
- 档位怎么选**：**默认 `common`**；**要生僻字 → `full`**；**多语言/日韩 → `multi`**
  （`flythings_build_ui_flow(font_tier='full'|'multi')`）。
- ⚠️ **「自己裁字库」只在要更小体积 / 自定义字符集时才做**（§4）——日常场景直接用现成三版，
不要一上来就裁。
- 关掉：`font_check='off'`；只想要结论：`flythings_check_project_deps`（默认只报不投，带一键修复命令）。
- 本文的 CLI 用法（§2）是**不走 MCP 时的兜底**。权威口径见 `knowledge/devflow/custom-font-config.md` §0.2。

---

## 1. 三个版本（已裁好，直接可用）

| 文件 | 体积 | 覆盖 | 什么时候用 |
|---|---|---|---|
| `zkswe-hans-common.ttf` | **872 KB**| GB2312 一级汉字 3755 + 中文标点 + 全角 + ASCII | **默认（缺中文时 AI 自动投这版，`font_tier='common'`）；低内存平台（Z21/Z20）也用它 |
| `zkswe-hans-full.ttf` | **7.39 MB**| CJK 基本区 20902 + 扩展A 6582 + 标点/全角 | 需要生僻字（人名/地名/专业词） |
| `zkswe-hans-multi.ttf` | **10.5 MB**| 全中文 + 扩展B + 拉丁/希腊/西里尔/假名/谚文 | 多国语言界面、日韩客户 |

源字体：思源黑体（Source Han Sans / SIL OFL，商用免费）。
裁剪脚本可复现：`scripts/gen_font_subset.py`（见 §4）。

---

## 2. 快速开始

```bash
# ① 体检设备（getprop 平台信息 + 扫 /etc/font /res/font 等目录的字体体积）
python components/fonts/scripts/device_font_check.py
#判定为"缺中文字库"时，退出码=1

# ② 缺就投递（默认常用中文版；把字体塞进工程 font/ 并改 .settings 的 easyui prefs）
python components/fonts/scripts/device_font_check.py --apply \
       --project <项目目录> --tier common

# ③ 重新出包（app 的升级包会整体替换 /res，字体必须随包走）
cd <项目目录> && ./fsc.exe build      # 或 flythings_build_ui_flow
flythings_pack_upgrade(project_root=..., release_version=...)   # 出 update.img
# ④ ADB 固化刷机（详见组件规范里的 platforms.md）
```

工程侧最终形态（打包时自动进包）：
```
<项目>/font/zkswe-hans-common.ttf   →  /res/font/
<项目>/.settings/com.zksw.flythings.easyui.prefs 里 "font":"/res/font/zkswe-hans-common.ttf"
```

---

## 3. 判定规则（cmap 硬判据为主，体积判据兑底）

`device_font_check.py` 扫 `/etc/font`、`/res/font`、`/system/font`、`/usr/share/fonts`，
挑最大字体 → 拉回本机读 cmap 算 **GB2312 一级 3755 字覆盖率**：

| cmap 覆盖率 | verdict | 动作 |
|---|---|---|
| **≥ 90%**| `ok` | 不投递（设备中文可用） |
| **50–90%**| `low` | 投递 `common` + 写明覆盖率 |
| **< 50%**| `missing` | 投递 `common` |

兑底（`source="size"`）：拉取超 12 MB / fontTools 不可用 / 拉取或解析失败 → 退回**体积判据**：

| 最大字体体积 | 判定 | 动作 |
|---|---|---|
| 没有字体文件 | `no_font` → 缺中文 | 投递 `common` |
| **< 200 KB**（几十K / 100多K 就在这类） | `no_cjk`（大概率只有英文） | 投递 `common` |
| 200 KB ~ 1 MB | `partial_cjk`（像只有常用字） | 有生僻字需求才升级到 `full` |
| > 1 MB | `has_cjk` | 不动 |

CLI：`--json` 输出里 `source` / `cmapCoverageGB2312L1` / `probe.reason` 可直接消费；
`--no-probe` 关掉硬判据（只体积判据）。退出码：`0` = 设备已有中文字库；`1` = 缺中文；`2` = 出错。

> 实测对照（V85X SPINOR）：`/etc/font/fzcircle.ttf` = **20.7 KB**（命中“只有英文”）；
> 我们把 2.5 MB 的中文字体随包投递后，`/res/font/font.ttf` = 2521 KB → `has_cjk`。

---

## 4. 重新裁剪（换源/换字表时）

> ⚠️ **只在要更小体积 / 自定义字符集（行业术语、只留几十字）时才需要自己裁**；
> 常规需求直接选 `common`/`full`/`multi` 三版（AI 默认就投 common）。

```bash
pip install fonttools
python components/fonts/scripts/gen_font_subset.py \
  --src       "<CN 版思源黑体 ttf>"        \
  --src-multi "<完整版思源黑体 ttf>"        \
  --out components/fonts/fonts
```
- `--src`：常用/全中文用（CN 变体即可，体积小）
- `--src-multi`：多国语言用，**必须含谚文/假名/扩展B 的完整版**（CN 变体会缺谚文，实测 0 个）
- 手上可用的两份源（本机）：
  - CN 版：`tools/FlyThingsIDE/bin/configuration/org.eclipse.osgi/551/0/.cp/bundle/font/SourceHanSansCN-Normal.ttf`
  - 完整版：内部仪表工程 `font/aaaSourceHanSansSC-Normal.ttf`

---

## 5. 注意

- **字体必须随 app 包走**：升级/固化会整体替换目标机的 `/res`，原 app 带的字体会被清掉（真机踩过）。
- 三个文件合计 ≈ 18.8 MB，已在仓库内；若要精简仓库，可以只保留 `common`，另两版按需重裁。
- 界面字体大小/字重：设备端只看**一个**ttf（EasyUI.cfg 的 `font`），多文件用 `:` 分隔（easyui 支持多字体链）。
- 本模块无 include/src（纯资产 + 工具），是 `components/` 规范里"资产型模块"的形态。

## 6. 验收状态

| 项 | 状态 |
|---|---|
| 三版本裁剪 | ✅ 已产出并逐版核验覆盖（ASCII/CJK/扩展A/扩展B/假名/谚文逐段计数；三版 GB2312 一级覆盖率实测均 100%） |
| 设备自检脚本 | ✅ 真机跑通（V85X SPINOR：正确识别 20.7KB 无中文 / 2.5MB 有中文） |
| **cmap 硬判据（v0.27.87）**| ✅ 离线用例覆盖（真字体 100% → `ok` / 53.3% → `low` / 拉丁 0% → `missing` / 缓存命中 / 超限退回 / fontTools 不可用 / 拉取失败 / 临时文件清理） |
| 投递 + 固化 | ✅ 已在 app 工程验证（汉字正常显示，见 platforms.md） |
| 非 V85X 平台 | ⏳ 仅在 V85X 实测；其它平台请按 platforms.md 补实测值 |
