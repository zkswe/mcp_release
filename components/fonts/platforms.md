# fonts 模块 —— 平台说明

> 记录各平台的**字库现状**（设备自带什么、够不够显示中文）、判定阈值依据、以及投递后的验证方法。
> 未实测的平台一律标 `未验证`，不写"应该可以"。

---

## 0. 通用事实

- FlyThings 设备端字体由 **EasyUI.cfg 的 `font` 键**指定（多字体用 `:` 分隔），常见落点：
  - `/etc/font/`（系统自带，只读；**常常是裁剪字体，可能只含英文**）
  - `/res/font/`（**应用包带过去的**；升级/固化会整体替换 `/res` → 原 app 的字体随之消失）
- app 工程侧的对应关系（`fun` 工具链自动处理）：
  - `<项目>/font/*.ttf` → 进包 `/res/font/`
  - `<项目>/.settings/com.zksw.flythings.easyui.prefs` 的 `easyui.cfg.release/debug` 里加 `"font":"/res/font/<文件名>"`
    → 打包时写进 `/res/etc/EasyUI.cfg`
- 判定阈值（`scripts/device_font_check.py`）：最大字体 **< 200 KB ⇒ 大概率只有英文**（几十K~100多K）；
  200KB~1MB ⇒ 疑似只有常用字；>1MB ⇒ 认为带中文。**这是启发式，不是精确判定**——精确判定要读 cmap，见 §4 待办。

## 1. V85X（V851 系列）—— 已实测

| 项 | 实测值 | 说明 |
|---|---|---|
| 系统自带字体 | `/etc/font/fzcircle.ttf` = **20.7 KB** | 只有英文/符号；靠它显示汉字 = 全方块（真机复现） |
| 应用字体目录 | `/res/font/`（原 app 带过 `font.ttf` 2.58 MB 中文字体） | 我们把该 app 的包整体替换后 `/res/font` 曾为空 → 汉字变方块 |
| 投递后 | `/res/font/font.ttf` = 2521 KB，`EasyUI.cfg.font=/res/font/font.ttf` | 汉字正常；自检判定 `has_cjk` |

**实测板**：`Zkswe_V85X_SPINOR`（`product:swaio`，flythingsV2.1，480×800，BT 模组 8733bs）

**验证步骤（可照抄）**
```bash
# 1) 体检
python components/fonts/scripts/device_font_check.py          # 期望出口码 0
# 2) 看设备实际字体与配置
adb shell "ls -l /etc/font /res/font; cat /res/etc/EasyUI.cfg"
# 3) 看界面（汉字正常 = 无方块）
#    → 用 flythings_device_screenshot()，交给视觉模型确认
```

## 2. T113 / Z20 / Z21 —— 未验证

- 已知差异：`/res/font` 与 `EasyUI.cfg` 的字体路径各平台不同，**必须实测**（`adb shell "ls -l /res/font"`）；
- Z20/Z21 多为「电子价签/面板」类设备，界面文字量大（价格、单位、商品名），建议直接投 **`common`** 或 `full`；
- 上线前请按 §1 的验证步骤补实测值到本文件。

## 3. 什么时候用哪一版（与 README §1 一致）

| 场景 | 版本 |
|---|---|
| 常规中文 UI、内存/包体敏感（价签、副屏） | `zkswe-hans-common.ttf`（872 KB） |
| 需要生僻字（人名、地名、专业词） | `zkswe-hans-full.ttf`（7.39 MB） |
| 多国语言（含日/韩/西里尔） | `zkswe-hans-multi.ttf`（10.5 MB） |

## 4. 后续可做（待办）

1. **精确判定**：现在按体积猜；可加"读设备字体 cmap 里有无 U+4E00~U+9FFF"的判定（把字体拉回本机用 fontTools 读，几十 KB 的字体拉回来很快）。
2. **多字体链**：EasyUI 的 `font` 支持 `:` 分隔 → 可做"小体积英文字体 + 常用中文"组合，进一步压体积（英文用设备自带，中文只带常用）。
3. **按平台自动选版本**：把平台信息（`getprop`）与建议版本做成表，CI 里一次跑完（`--json` 已给机器可读输出）。
4. 其它平台实测值补录（T113 / Z20 / Z21）。
