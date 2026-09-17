# 可复用组件（components）—— 组件化落地规范

> 检索导引：可复用模块 / 组件化 / 封装一层 / wxapi 风格 API / 参考代码目录 / 组件规范 / 四件套 /
> 模块目录 / 资产型模块 / 组件 README / 平台说明 / package 引用
> 定规：2026-09-13（沛哥：落地形态 = 在参考代码目录下提供 `components/` 模块，以后模块代码放这里；
> 规范 = 落地 README + package 引用 + 平台说明 + 代码直接可以调用）

---

## 0. 一句话

**把散落在专题文章/聊天/各工程里的"这么做就对了"，沉淀成可复用模块**：一个模块一个目录，四件套齐全，拿去能编、能跑、能查。

现状（**随 MCP 发布的路径：`components/`**，即本仓 `tools/FlyThings_mcp_open/components/`；
这样所有接入本 MCP 的 AI 都能直接拿到代码）：

| 模块 | 类型 | 说明 |
|---|---|---|
| `ble/` | 代码型 | BLE 门面 `zk::ble`：把蓝牙收拾成 wxapi 那种（**一个 API 面、两个后端**：中心扫描/连接/GATT + 外设广播/GATT 服务/notify）；中心：F133、V85X；双角色：Z20/Z21/T113EMMC |
| `fonts/` | 资产型 | 思源黑体三版（常用中文872KB / 全中文7.4MB / 多国语言10.5MB）+ 设备字体自检（缺中文自动投递） |

---

## 1. 目录与四件套（硬要求）

```
components/
└─ <模块名>/                     ← 小写中划线/单词，如 ble、fonts、ota
   ├─ README.md                  ← ① 落地 README：是什么 / 怎么用 / API / 依赖 / 限制 / 排错
   ├─ platforms.md               ← ② 平台说明：哪些平台可用、每平台前置条件与实测值、已知限制
   ├─ Manifest.xml               ← ③ package 引用：需要哪些底层包、怎么声明；外部怎么引用本模块
   ├─ include/ + src/            ← ④ 头文件 + 实现（代码型模块）
   ├─ example/                   ←    可直接调用的最小示例（能拷进工程就跑）
   └─ scripts/ + <产物目录>/      ←    资产/工具型模块：可复现的生成/检查脚本 + 产物（如字体）
```

**两种模块形态**（都算合格）：

- **代码型**（默认）：`include/ + src/ + example/`，对外命名空间 `zk::<模块>`，头文件 `include/zk/zk_<模块>.h`；
- **资产/工具型**（如 `fonts/`）：无 `include/src`，四件套对应为
  `README.md + platforms.md + scripts/（可复现的生成/检查脚本）+ 产物目录`，使用方式写成"一条命令"。

**四件套缺一不收**：没有 `platforms.md` 的模块 = 把"什么板子上会翻车"藏起来了；
没有 `example/` 的模块 = 让下一个人从零猜调用姿势。

---

## 2. 代码规范（review 尺子）

1. **不把底层库类型泄漏到对外头文件**：BLE 模块对外只有 `std::string`，没有 `bd_addr_t` / `hci_con_handle_t`。
   想用底层的自己 include 底层头，别逼所有人一起。
2. **统一结果类型** `Result{code, msg}`：`msg` 必须是**人话**（可直接打日志/回给用户）；禁止只回 `-1`、禁止静默失败。
3. **默认参数要安全**：不传参也能跑；有超时；写操作默认"要回应"。
4. **线程模型写进 README**：哪些回调在库线程里被调、业务能做什么不能做什么；跨线程一律库内封装，
   不要求业务理解底层 run loop。
5. **平台差异关在内部**：`#ifdef`/平台分支只允许出现在平台适配层，业务层代码里不出现平台名。
6. **可诊断 > 可配置**：能自动探测的不做成配置项；探不到就明确报错并给出"下一步查什么"
   （如 `zk::ble` 的 `getDiag()` 一次给 芯片/上电/预初始化/HCI状态/真实事件数/hint）。
7. **资源/节点路径一律给候选链**（不同板子内核枚举不同，写死必翻车）。
8. **日志要能接出去**：库内部日志提供钩子（如 `setLogHook`），否则 app 模式下 stdout 是 `/dev/null`，
   现场排错只能靠猜。

---

## 3. package 引用（怎么让工程用上）

**A) 源码引入（起步推荐）**：把 `components/<模块>/` 整目录拷进工程 `src/` 下，
并在工程 `Manifest.xml`/`fun.json` 声明模块所需底层包（见模块自己的 `Manifest.xml`）。

**B) 依赖包引用（模块定型后）**：模块按平台编出 `include/ + lib/`，注册进包仓库，工程一行：
```xml
<package id="<模块名>" version="x.y.z"></package>
```
版本号**写死**，不用 `^` 浮动（底层 ABI 一变就不可复现）。

⚠️ 工程侧两个坑：`fun.json` **优先于** `Manifest.xml`（依赖写 `fun.json`）；
`type:"executable"` 才出可执行 ELF（否则出 `libzkgui.so`）。

⚠️ 模块自己的 `Manifest.xml` 里声明底层包时，**框架基础包 `base-utility` 不能漏**：fun 生成的
`generated/event_dispatcher.h` 等固定 `#include <base/functional.h>`（`base-http-client` 的 `base/http_*.h`、
`base-json` 的 `base/json_*.h` 不算）。漏了工程侧表现是 `fatal error: base/functional.h: No such file or directory`，
且**改 Manifest 后必须重跑 `fun install`**（include 路径才进 CMake）——
详见 `cli-fun-toolchain.md` §4.7「老工程升级：补 base-utility」。

---

## 4. platforms.md 必须写什么

每个平台一段：可用性（可用/部分可用/不支持）、**前置条件**（电源/串口/固件/属性门）、
实测值（节点路径、波特率、校验、超时、包版本）、已知限制、真机验收步骤。
**禁止写"应该可以"**；没实测的标 `未验证`。

---

## 5. 新增模块 checklist

- [ ] 目录名/命名空间定好（`zk::<模块>` / `include/zk/zk_<模块>.h`，或资产型则定产物与脚本入口）
- [ ] `README.md`：用法（10~30 行可跑示例）+ API 表 + 依赖 + 限制 + 排错
- [ ] `platforms.md`：逐平台前置条件与实测值（未实测标 `未验证`）
- [ ] `Manifest.xml`：底层依赖 + 本模块被引用的两种方式
- [ ] `example/`（或资产型的"一条命令"）：**真的跑过/编过**，把命令写进 README
- [ ] 版本号 + 变更记录（模块内 README 顶部一段）

---

## 6. 与 MCP 知识库的分工

- **知识库（knowledge/）**：讲清"为什么/怎么判/坑在哪"——可检索，写给 AI 与工程师；
- **组件（components/，随 MCP 一起发布）**：给出"可直接调的代码/资产"——能给业务/AI 直接用。
- 两者互链：知识库文档里指向对应组件相对路径（如 `components/fonts/`），组件 README 里反向引用经验来源。

> ⚠️ 定位（沛哥 2026-09-13 明确）：**底层过程不入库**。例如蓝牙/射频模组的 bring-up 与上电时序，
> 用户与 AI 只需要"上层概念 + 直接用组件"，不再让任何人去跑那套排查流程；
> 因此这类文档已从知识库删除，实现细节只保留在组件自带文档（`components/ble/`）里供维护者查阅。

## 相关

- `components/ble/`（BLE 门面 `zk::ble`：上层直接调；上电/预初始化/线程/TLV 全在组件内部）
- `components/fonts/`（思源黑体三版 + 设备字体自检）
- `components/icons/`（Tabler 图标库：语义图标 → 任意分辨率单色 PNG，两条命令出图）
- `components/ui_v1/`（**框架基线目录，文档型**：当前这代 FlyThings IDE + easyui 的跨框架**控件映射唯一权威表** + 逻辑映射 + 缺口五级处置 + 候选组件登记；**跨框架控件映射查这里**）
- `devflow/custom-font-config.md`（字库机制 + 设备字体自检使用口径）
- `devflow/upgrade-pack-image.md`（固化出包与刷机；⚠️ 会整体替换 `/res`）
