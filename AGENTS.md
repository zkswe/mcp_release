# AGENTS.md —— 在本仓工作的 AI 必读

本仓 = **FlyThings MCP 服务器**（把 FlyThings 开发所需的知识与操作暴露成 MCP 工具）。你在这里做的事，
多数是**改这套工具/知识库本身**；若任务是在某个 FlyThings 工程里写代码，先读第 2 节的定位口径。

## 1. 唯一真源与门禁（改任何东西前先懂这条）

- 每个事实**只有一个权威来源**；其它地方要么**派生生成**，要么**显式引用**。
  发现"两份说法不一致"时，**不是挑一个改，而是找出真源并让另一处变成派生**。
- 一切**数字**（op 数、用例数、预算字符数、页面数…）都由脚本生成或核对，
  **不许手写后放着**。改完跑：

  ```
  python scripts/check_consistency.py --with-tests
  ```

  → 必须 `total=<N> fail=0 OK`。它会把"你写的数字与实测不符"指名道姓报出来。
- 派生文件（`tools_manifest.json` / `rag_index.json` / `knowledge/kb_index.json` /
  `knowledge/_reports/*` / `op_seealso.json` / 门禁清单…）改完真源后**必须重生成**，
  重生成顺序：**索引类在前、manifest 最后**。
- 顺序错/漏生成会被门禁抓到，别靠记忆——跑一遍即可。

## 2. 技术定位（判断"能不能做"的基线，别按别的栈类推）

- **FlyThings = Linux 基座**：基线同 buildroot/OpenWrt，**不是** MCU/ESP32 SDK，**不是**普通 Linux 用户态 App。
- **GUI 是自研 EasyUI**（≠ LVGL、≠ Qt/Android）。控件字段/回调以本仓知识库为准。
- ⛔ **不要解析 easyui 库源码/头文件来推断控件用法**——它是预编译闭源库，源码里没有 json 字段与回调语义。
- MCP 只承担**老框架**（`ui/*.json` + `ui/*.ftu` + `Manifest.xml` + Eclipse `.project`/`.cproject`）。
  `fun create` 能生成 **fv 新框架**（`fsc.json` + `app/**/*.fv`），但**本仓不服务 fv**：
  其格式与细节没有资料，不要采用、不要按猜的写、不要把它加进工具或知识页。

## 3. 材料在哪（问"某个能力/库怎么用"时的查找顺序）

| 要什么 | 去哪 |
|---|---|
| 检索知识 | op `flythings_knowledge_search`（`knowledge/` 是散文权威；`packages/`、`components/` 也在检索面） |
| 厂家依赖包用法 | `packages/<包>/README.md` + **`package.yaml`**（机读版，AI 优先读：api/usage_cpp/gotchas/verified）+ `platforms.md`（**逐平台实测表**） |
| 自研组件用法 | `components/<组件>/README.md` + `platforms.md` + `example/` |
| 控件字段规范 | `knowledge/uicontrols/`（每控件一份） |
| 别的框架控件 → 我们哪个 | op `flythings_map_control`（带可直接粘的 json 片段） |
| 病症 → 权威文档 | `knowledge/devflow/symptom-index.md` |
| 流程级判断（顺序错了就返工） | 本仓 skill：`flythings-new-project` / `flythings-use-library` / `flythings-device-acceptance`（在 `.dsh/skills/`） |

## 4. 硬性纪律

- **没实测的不写结论**；写进文档的结论必须**带证据**（截图 / log 摘录 / 可复现命令）。
  仓里 `knowledge/` 有"待补证据"清单，别新增无证据的断言。
- **不静默**：读不到/不支持/降级，都要在返回值里显式说明并给**可执行的下一步**，
  不许返回空的成功。
- **改行为就补判据**：新增/修改功能要有用例；用例要能**抓住该 bug**（必要时应自证：
  把错法注回去看它是否变红）。
- **别弄丢用户的在制品**：`templates/DemoControls_V85X/**` 等常有人在改；
  提交前用 `git status` 确认自己只提交了本次相关文件。
- **不要删/改他人的业务代码**：用例里造"缺文件"场景只允许删**临时目录**内的文件
  （`tests/_util.py::rm_in_temp` 有守卫，真工程路径会被拒）。
- 提交信息写**归因与实测数字**（为什么改、改前改后各是多少），不写"优化/修复"这类空话。

## 5. 别误读的东西

- `README.md` 是对外门面；`AI-DEV-CAPABILITY-*.md`、`REVIEW-*.md`、`CONSOLIDATION*.md`、
  `TODO.md`、`WORK_PLAN.md` 是**评估/计划/复盘**，**不是规范**——里面的数字与结论会过时，
  以 `DESIGN_SPEC.md`、`op_spec.json`、`knowledge/` 为准。
- `components/` 与 `packages/` 的区别：前者是**我方自研可复用模块**，后者是**厂家注册表依赖包的用法**。
- `src/activity/` 由 ftu 生成（**禁建/禁改**）；业务只写 `src/logic/*.cc`；
  控件指针宏 `mXXXPtr` 由编译期生成，**禁止手写定义**。
