---
name: flythings-use-library
description: 在 FlyThings 工程里使用「厂家依赖包」（easyui/zknet/zkhardware/mqtt-cxx/nanovg…）或「自研组件」（components/ 下的 Calendar/Chart/ble/vinyl…）时加载。给出装包、查 API、照示例改、按平台实测表判断可用性、真机复验的完整顺序，以及"别解析 easyui 源码""别按 LVGL/Qt 类推"等硬约束。
---

# 用库 / 用组件

## 先分清两类东西（用错查法会白费功夫）

| | 是什么 | 权威文档在哪 |
|---|---|---|
| **厂家依赖包** `packages/` | `fun install` 从 registry 装的（easyui / zknet / zkhardware / mbedtls / mqtt-cxx / nanovg / curl / rapidjson / ntp / openssl / paho-mqtt3as / cares） | `packages/<包>/README.md` + **`package.yaml`**（机读，AI 优先读）+ `platforms.md`（逐平台实测） |
| **自研组件** `components/` | 我方自己的可复用模块（ui_v1 控件包、ble、fonts、vinyl、imagecache、blur…） | `components/<组件>/README.md` + `platforms.md` + `example/` |

两者都**不是什么**：都不是现成 npm/pip 那种包管理器生态，别按 `npm install xxx` 的思路找。

## 步骤

### ① 先查有没有（别自己造轮子）

| 要什么 | 查哪个 op / 文档 |
|---|---|
| 别的框架的某控件 → 我们对应哪个 | op `flythings_map_control`（六框架 213 条，返回**可直接粘进 json 的片段** + 降级说明） |
| 组件总目 | `knowledge/components/components-catalog.md` |
| 依赖包总目 | op `flythings_list_packages(platform)`（带 `hasCard`）/ `flythings_package_search` / `flythings_query_package` |
| 真没有对应件 | `components/ui_v1/gap-list.md`（缺口 G-01~G-36，写明"组合实现"还是"真缺"） |

### ② 取 API（推荐顺序，重要）

```
flythings_get_package_api(package_id, platform)      # 装过的平台 → 逐字节头文件签名
flythings_get_package_api(package_id, platform, focus='ZKPainter')   # 只看一个类，别让它给 8 个无关类
```

- **本机装过该平台** → 返回**签名唯一真源**：本地 registry 头文件（换平台/换版本自动跟随）。
  用 `focus` 精确点名要用的类 —— 不问就只给前几个类，高频要用的那个常排在后面。
- **本机没装该平台** → 返回 `success: false`，但**同一个响应里带 `offlineApi`**：
  来自 `packages/<包>/package.yaml`（头文件实读写成、含真机实测的坑），**离线、可复现**。
  **只是想看"这库怎么用"，不用为了这个去 `fun install`**；要逐字节的当平台签名时才需要装。
- `easyui` 等**框架自带库没有包卡** → 控件用法走 `knowledge/uicontrols/`（每个控件一份字段规范），
  不要绕道解析库源码（见下面硬约束）。

### ③ 判断这个平台能不能用

**只认实测**：`packages/<包>/platforms.md`（或 `package.yaml` 的 `platforms`/`verified_*`）。
- 标 `✅ 可用` + 有证据 → 可以用；标 `未验证` → **不许按"应该能用"往下写**，要么先验，要么告诉用户。
- 平台差异是常态（RISC-V vs ARM、easyui 版本、固件里有没有那个 `.ko`/`.so`）——
  同一个包在 A 平台验过，不代表 B 平台可用。

### ④ 装 + 声明依赖

```
flythings_add_package(project_root, package, platform=..., with_install=True)
```

⚠️ **包卡里 `deps` 是硬要求**，别漏：例如 `paho-mqtt3as` **没有 Manifest.xml**，依赖不会自动带进来 ——
必须自己在 Manifest 里显式声明 `openssl`（+ pthread），否则链接期报 `SSL_CTX_new/RAND_bytes` undefined。
装完用 op `flythings_check_project_deps(project_root, platform)` 对账 include 与声明。

### ⑤ 照示例改（别从零写）

- `packages/<包>/example/`（最小可跑工程的可拷片段：ui json + logic + 回调注册）；
- `package.yaml` 的 `usage_cpp`（可直接粘的用法）与 `entry`（入口宏/头文件）；
- 组件的 `components/<组件>/example/`（同样有 example 工程）。

### ⑥ 真机复验 + 记录

按 skill `flythings-device-acceptance` 跑一遍。**遇到新坑要回写**：
`packages/<包>/gotchas`（或 `components/<组件>/platforms.md`），带证据 —— 这是仓库的既有约定，
"没实测的不写结论，实测过的必留证据"。回写用 op `flythings_knowledge_capture`。

## 硬约束（真踩过，别试）

| 约束 | 原因 |
|---|---|
| ⛔ **不要解析 easyui 库源码/头文件来推断控件用法** | easyui 是**预编译闭源库**，源码里拿不到 json 字段与回调语义，只会浪费时间；控件用法以 `knowledge/uicontrols/` 为准，没有就标"未收录"问需求方 |
| ⛔ 不参考 Qt/Android/Flutter/emWin/AWTK/LVGL 的控件属性/回调写法套用 | 自研 EasyUI，字段名与事件模型都不同 |
| ⛔ 不用通用 web 搜索查"XXX 控件怎么用" | 返回的是别的框架的答案 |
| ⚠️ `nvgImagePattern` **不平铺**（V85X 实测） | 只画首个 tile extent，之外透明；`NVG_IMAGE_REPEATX/Y` 无效 → 贴图必须 1:1 映射 |
| ⚠️ `nanovg` 渐变**全族失效**（V85X 实测） | 一律退化成纯 innerColor → 要渐变就自己烘色带贴图 |
| ⚠️ 别在 `onUI_init`/构造里取 `NETMANAGER->getWifiManager()` | 页面起不来（卡 `MI_SYS_IOCTL_Init`）；改成按钮/线程里惰性取 |
| ⚠️ 回调跑在库自己的线程里 | 回调里只置标志/打日志，状态以 manager 读回为准 |

## 反馈闭环（这是能力上限所在）

FlyThings 上模型先验 ≈ 0，能力几乎全由"知识注入 + 反馈闭环"决定。所以用库时：
**查文档 → 照示例 → 真机验 → 把新发现的坑回写**。只到"编译通过"不算完成，
运行期行为（回调、线程、平台差异）只有真机能暴露。
