# FlyThings MCP 后续工作安排计划

> 整理：2026-10-02 · 基线 v0.27.173（已推 gitee，门禁 39/39）
> 状态：✅ 已完成待提交 / 🤖 AI 可执行 / 👤 需需求方或需求方决策输入

---

## 一、已完成（在工作区未提交，随时可入库）

| 任务 | 内容 | 验证 |
|---|---|---|
| ✅ relpath 跨盘符 bug | `ui_tools/json2img.py:1224` 的 `os.path.relpath` 纯展示用途，跨盘符（C:\TEMP vs D:\工程）抛 ValueError 致 5 个测试失败；已加兜底回退绝对路径（同文件 ui_editor.py 已有同模式） | test_ui_visual_merge 21/21 过 |
| ✅ lint 白名单失效条目 | `configure.py#b462cc14d4` 站点已被改写为显式 print（非静默），从 whitelist 删除（3→2） | lint 无 FAIL 无 WARN |
| ✅ temp/ 入 .gitignore | 验证产物不再污染 git status | — |

> 以上 3 项改动文件：`.gitignore`、`ui_tools/json2img.py`、`scripts/silent_except_whitelist.txt`。门禁 39/39 全绿。**是否提交入库等你一句话。**

## 二、技术债（纯离线，AI 可直接做，约 2h）

| # | 任务 | 状态 | 说明 |
|---|---|---|---|
| 1 | docstring 预算顶爆（11996/12000） | 🤖 | 对最长 12-15 个 op 瘦身至 ≤9600（余量≥20%）；铁律/参数契约/检索词保留，展开叙述砍（knowledge 文档已有）；**未开工**（上次被叫停，kb_tools.py 无残留改动） |
| 2 | test_font_autoscan×10 失败 | 👤 | 唯一原因：指定 python 缺 fontTools，`pip install fontTools` 即绿；装不装你定 |
| 3 | 发射层 alignment 与注册表对齐 | 👤+🤖 | textview 0/36、button 5/37 等 5 处刻意差异，位模型两种写法真机都工作；需需求方给校准表裁决，AI 执行统一 |
| 4 | 35 篇 uicontrols 文档瘦身 | 🤖 随任务做 | 口径：注册表拥有字段/类型/默认值/判据，md 只留原理/流程/回调；不设专项，改到哪个控件瘦哪篇 |

## 三、真机链路加固（需接设备，1 个 session）

| # | 任务 | 状态 | 说明 |
|---|---|---|---|
| 5 | **launch 活性检查**：logcat 无 onUI_show 不报 launched:true | 🤖+设备 | 黑屏事件核心教训落地 |
| 6 | **fb0 抓屏陈旧帧检测**| 🤖+设备 | 应用不渲染时 fb0 显示旧帧（本次误诊元凶之一），截图带警告 |
| 7 | easyui 包 vs 设备运行时同源对账（getprop 指纹） | 🤖+设备 | build_ui_flow 前置告警 |
| 8 | 工程分辨率 vs 面板分辨率核对告警 | 🤖 | 480×480 灰窗事件防线，validate_project 加检查项 |
| 9 | fun launch cfg 修正（**touchDev 半项已闭环**） | 👤+🤖 | touchDev：工程 cfg **不再写触摸节点**（系统自识别）→ 工程侧无 event1/event4 可对错，该项失效；剩 `/tmp/tr 不存在` 待确认出厂口径 |
| 10 | translate_ui 交互：给了 out 默认落盘；res 默认跟随工程 | 🤖 | 契约测试同步 |

## 四、场景①④ 强化（推广 P0，细节见 SCENARIO_COVERAGE.md）

| # | 任务 | 状态 | 说明 |
|---|---|---|---|
| 11 | **C++ 回调桩生成 op**（场景④ 换皮→换功能） | 🤖 | 从 json 控件表生成 logic/*.cc 骨架；编译断链实测踩过，价值最高 |
| 12 | **页面模式库**knowledge/patterns/ ×6（仪表盘/温控/音乐/设置/摄像头/门禁） | 👤 选题确认 +🤖 制作 | 场景① 质量天花板；每模式 = md + 可 create 模板，各真机验证 1 个 |
| 13 | **场景 Skill 四件套**（idea-to-app/figma-import/migrate/reskin） | 🤖 起草 +👤 审 | 最高杠杆推广物，纯文档，全 agent 可加载 |

## 五、推广与生态（P1-P3，需团队排期）

| # | 任务 | 状态 | 说明 |
|---|---|---|---|
| 14 | MCP 市场上架（Smithery/glama/官方列表）+ 英文 README | 👤 账号与公开口径 +🤖 材料 | 指标：90 天安装 >100 |
| 15 | 翻译器框架化 + Android XML 翻译器 | 🤖 | 映射表驱动；之后 Qt QML |
| 16 | demo gallery（demos/ 8 工程配截图+索引）+「30 分钟想法到上机」视频脚本 | 🤖 | 配合宣传物料 |
| 17 | flythings-ai CLI 一条龙薄封装 | 🤖 | P2 |
| 18 | VSCode 插件（只做预览/补全/一键 launch，AI 走 MCP） | 👤 排期 | P2 |
| 19 | figma_to_json（Figma API 直连） | 🤖 | P3，宣传价值为主 |

---

## 需要你给的输入（本周）

1. 上面 3 项已完成改动**是否提交**（顺带可推 gitee）
2. fontTools 装不装（任务 2）
3. alignment 校准表找需求方裁决（任务 3）
4. 模式库 6 个选题确认（任务 12）
5. gitee 仓库公开/英文口径（任务 14）

## 建议执行顺序（下次开工）

任务 1（docstring，半小时）→ 任务 11（C++ 回调桩 op）→ 有设备时任务 5-7 一次做完 → 任务 12-13（推广弹药）
