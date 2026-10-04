---
id: devflow-symptom-index
title: 现场症状索引（用户原话 → 机制/规范 → 权威文档，由 symptom_spec.json 派生）
category: devflow
status: review
confidence: manual
verified_at: 2026-10-04
stale_days: 180
origin: derived
source: 由 symptom_spec.json 派生（scripts/gen_symptom_doc.py）
needs_evidence: false
platforms: []
tags: [现场症状, 症状索引, 切一下才显示, 拖不动, 点了没反应, 界面文件乱码, 推上去没效果, 图标发糊, 图片有锯齿, client_id 互踢, 串口收不全, 半包重组, 第二次进页面空白, 改了没生效, 控件谁盖谁, 有哪些字段]
evidence:
  - cmd: python scripts/gen_symptom_doc.py --check
    expect: rc=0（本页与 symptom_spec.json 一致）
---
# 现场症状索引（用户原话 → 机制 → 规范 → 权威文档）

> ⚠️ **本页是派生物，不要手改**（由 `symptom_spec.json` 派生，`--check` 进闸门）。
> 新增症状请改注册表：`symptom_spec.json`。
> 
> 用法：用户描述的是**症状**，本页把症状落到**机制与规范**，并给权威文档。
> 先按「能不能从设计端消灭」判断：能在判据/工具/模板层消灭的坑，不该只留记录。

## 切一下才显示 / 切页回来后界面不对 / 切到别的页再切回来才对 / 返回再进页面内容就不对了 / 第二次进页面显示空白 / 界面要切一下才刷新 / 改了数据界面没变

- **机制**：整屏 window 切换走的是重绘而不是重建；控件值在进入前写、或没触发重绘，画面就停在旧帧。
- **规范**：页面数据在 onUI_show() 里写，并显式触发重绘；不要只在构造/首次加载时写。
- **权威文档**：`knowledge/devflow/activity-code-skeleton.md`
- **怎么复验**：真机连续「进入 → 返回 → 再进入」，看 logcat 的 onUI_show 与画面是否一致（截图连抓两帧取第二张）。

## 拖不动 / 点了没反应 / 不跟手 / 一拖就卡死

- **机制**：触摸分发只发给 touchable=true 的控件；可交互控件若没显式打开触摸，事件根本不进回调。另有回调里做耗时活（滚动时逐行调用）会表现为卡死。
- **规范**：交互控件 json 必须显式 touchable=true；obtainListItemData_* 等高频回调里禁止耗时操作。
- **权威文档**：`knowledge/uicontrols/touch-events.md`
- **怎么复验**：真机注入点击/拖拽（bin_tools/<平台>/touch），看 logcat 是否收到对应回调。

## 点了屏幕没反应坐标都是0 / 注入点击没反应

- **机制**：注入用的设备节点/协议与真机不匹配时，坐标回读为 0 —— 是**注入没生效**，不是界面没响应。
- **规范**：坐标回读为 0 先判注入通道（bin_tools 的 touch 会自动判协议）；别据此断定控件问题。
- **权威文档**：`knowledge/devflow/touch-inject-autotest.md`
- **怎么复验**：跑 bin_tools/<平台>/touch tap x y，看返回与 logcat 是否收到事件。

## 界面文件打开是乱码 / 界面文件看不懂 / 界面文件是二进制看不懂怎么办 / json 和 ftu 什么关系

- **机制**：设备加载的是 .ftu（fui pack 的编译产物）；.json 才是可读布局源。
- **规范**：改布局改 .json 再 pack；要读现有界面用 fui unpack（MCP op：flythings_fui_unpack）反解析成 json，不要直接编辑二进制。
- **权威文档**：`knowledge/devflow/ftu-json-pipeline.md`
- **怎么复验**：fui unpack <x.ftu> → 得到同名 json，字段可读。

## 推上去没效果 / 设备上还是旧的 / 改了像没改 / 推了个新包上去屏幕还是旧的没变化

- **机制**：推送成功 ≠ 设备在跑新版：同名旧程序/旧库仍可被加载（如 SD 上的 EasyUI.cfg 劫持、名字相同覆盖失败）。
- **规范**：推送后必须比对设备侧与本地产物（md5 或大小），staleOnDevice=true 即设备旧版，按升级/重推处理。
- **权威文档**：`knowledge/devflow/device-deploy-budget.md`
- **怎么复验**：走 build_ui_flow 的设备侧比对；或设备上直接量文件大小/时间戳。

## OOM 杀 zkgui / 程序莫名退出/被杀

- **机制**：小内存板上资源（图/字体/视频缓冲）超预算时被内核 OOM 杀；进程名 zkgui 从 logcat 可见。
- **规范**：先看体积预算（图/字体/包），再谈功能；上机前用 flythings_device_preflight 体检。
- **权威文档**：`knowledge/devflow/device-deploy-budget.md`
- **怎么复验**：logcat 搜 oom/lowmemorykiller，对照 preflight 的体积读数。

## 图标发糊 / 图标看着发糊有锯齿 / 图片有锯齿 / 图被拉长/变形 / 弧线毛边 / 半透明圆点被拉长

- **机制**：引擎对「图 ≠ 控件盒」是拉伸不报错；二值 mask 当 α 用会把圆弧过渡压成硬阶梯。
- **规范**：自动生成切图尺寸必须严格等于控件盒（圆角/圆弧走超采样 + 面积平均），形状外真透明。
- **权威文档**：`knowledge/devflow/ui-layout-verify.md`
- **怎么复验**：python ui_tools/check_all.py <项目>（第 21/22/23 项：AA/倒角/底板）+ 真机截图比对。

## 预览的效果和真机对不上 / 文字位置摆的不对 / 预览只能看第一页

- **机制**：预览分两档：HTML 预览稿（只谈布局意图）与**引擎等价渲染**（真机同口径）；拿前者当真机比必然对不上。
- **规范**：要对齐真机就用 flythings_ui_visual 的 render/render_check（引擎等价 + 像素 diff），别用 HTML 稿验收。
- **权威文档**：`knowledge/devflow/wysiwyg-render-spec.md`
- **怎么复验**：render_check：渲染图 vs 真机截图逐像素比对（容差见工具默认）。

## 控件谁盖谁是由什么决定的 / 控件叠在一起的时候谁在上面 / 图比控件大的时候是怎么画的 / 分隔线压住了按钮点不动

- **机制**：层序由 json 结构与声明顺序决定（后声明在上）；图大于控件盒时按控件盒裁/拉伸；上层控件会吃掉下层触摸。
- **规范**：先声明在下层；装饰线不要盖在交互控件上（盖住 = 点不动）；图尺寸对齐控件盒。
- **权威文档**：`knowledge/uicontrols/json-layer-rules.md`
- **怎么复验**：真机注入点击被盖控件区域，看 logcat 收到的是谁的回调。

## 内容滚不到底最后一行看不到 / 边缘效果怎么设置 / 拖到头没有反馈

- **机制**：滚动范围/边缘效果由控件字段决定（而非内容自动）；字段没配到位就滚不到最后一行。
- **规范**：按 scroll-drag-interaction-spec 的取值表配 dragMaxDis / edgeEffect / autoRollback / rollSpeed。
- **权威文档**：`knowledge/uicontrols/scroll-drag-interaction-spec.md`
- **怎么复验**：真机拖到最后，看最后一行是否完整可见 + 回弹表现。

## seekbar 有哪些字段 / circlebar 支持哪些属性 / 视频控件有哪些配置项 / 控件有哪些字段

- **机制**：字段真源是注册表 ui_schema.json（每类型 100% 交集 = 必写键），不是散文。
- **规范**：问字段/类型/默认值 → 走 flythings_ui_schema（注册表）与派生字段表；别从散文里抄。
- **权威文档**：`knowledge/uicontrols/layout-audit.md`
- **怎么复验**：python ui_tools/check_all.py <项目> 第 14 项（字段全集对账）应无缺键。

## 列表行数据怎么填 / listview 的三个回调怎么写 / window 的 showWnd 怎么用 / 画布怎么画圆 / 二维码怎么生成 / 摄像头预览怎么做 / play 接口怎么播视频 / 定时器怎么用 / 选中某个词怎么取到

- **机制**：控件代码 API（回调名/签名）由注册表 callbacks 段定义；散文里只讲原理。
- **规范**：问 API/回调 → 走 widget-code-api 速查与 flythings_ui_schema 的 callbacks；桩由工具补（flythings_gen_logic_stub），别手写重复定义。
- **权威文档**：`knowledge/uicontrols/widget-code-api.md`
- **怎么复验**：fun build 后 src/logic/<页>Logic.cc 里回调桩齐、无重复定义。

## android的SeekBar用什么替代 / 我原来用Qt现在换FlyThings 控件怎么对应 / 小程序控件能直接搬过来吗 / Android 控件在我们平台怎么对应 / 有没有对应的控件还是得自己写

- **机制**：跨框架控件是靠映射表（mcp_control_map.json，L1~L5 等价级）落的，不是凭名字猜。
- **规范**：先走 flythings_map_control 查映射（有 L1/L2 就直接用）；平台真缺才做自定义控件包（components/ui_v1/<源控件名>/）。
- **权威文档**：`knowledge/uicontrols/control-mapping-capability.md`
- **怎么复验**：op 查到 L1~L5 命中，或 gap-list.md 有对应缺口编号。

## 缺口级别 L1 到 L5 / 控件映射规则 / 3D 效果能实现吗 / tab 页签怎么做

- **机制**：L1~L5 是映射等价级（L1 直接对应 → L5 明说不支持）；缺口由 gap-list 编号管理。
- **规范**：看控件映射速查表 + gap-list 缺口编号，别用「应该能」判断。
- **权威文档**：`knowledge/uicontrols/framework-control-mapping.md`
- **怎么复验**：对照 mcp_control_map.json 的级别字段与 gap-list.md 编号。

## 下拉选择框怎么做 / 标签页怎么做 / 选择器弹出选择怎么做 / 列表拖拽排序支持吗 / 有没有图表控件

- **机制**：部分现代控件平台没有原生件，但可用基础件组合（L2）或已有组件包。
- **规范**：先查 gui-controls-gap 的缺口表与 ui_v1 组件（Chart/Calendar/TabView）；写明是「组合实现」还是「真缺」。
- **权威文档**：`knowledge/devflow/gui-controls-gap.md`
- **怎么复验**：op 查询无 L1/L2 命中 + gap-list.md 有缺口编号才算真缺。

## 跑一下看效果 / 更新到设备 / 推送到设备 / 推到板子上跑

- **机制**：「跑一下」在嵌入式里对应多条不同链路：调试推送（launch）/ 固化升级（update.img）/ 出包，混起来就调错工具。
- **规范**：先分清场景：临时调试 = build_ui_flow(launch)；要断电重启还在 = 固化升级（upgrade-pack-image）。
- **权威文档**：`knowledge/devflow/deploy-scene-map.md`
- **怎么复验**：看用的是哪个 op/脚本，以及设备侧产物是否持久（断电重启后仍在）。

## 字体文件放哪才能打进包里生效 / 换了字体没生效

- **机制**：字库有「打包内 / 设备侧」两条通路，放错位置就不生效；且设备字库是裁剪字库。
- **规范**：按 custom-font-config 放字库并用 flythings_device_preflight 体检（字库覆盖/体积）。
- **权威文档**：`knowledge/devflow/package-properties-easyui-cfg.md`
- **怎么复验**：preflight 的字库体检项 + 真机看特殊字符是否显示。

## 界面刷新太频繁 / CPU 占用高怎么排查 / 主线程卡

- **机制**：高频回调里做重活/全量刷新会把主线程占满（utime+stime 持续高、日志静止 = 假死）。
- **规范**：高频回调只做轻量活；刷新走 setInvalid 而非重建；排查先看 /proc/<pid>/stat 增量。
- **权威文档**：`knowledge/uicontrols/high-frequency-callback-perf.md`
- **怎么复验**：真机量 /proc/<pid>/stat 的 utime+stime 增量（>50% 且日志静止 = 卡）。

## 屏保是谁触发的怎么关掉 / 屏幕自己黑了

- **机制**：系统级窗口（statusbar/navibar/screensaver/IME）由框架管理，不在业务页面里。
- **规范**：按 system-windows 的开关口径配置/关闭，别在业务页里自绘。
- **权威文档**：`knowledge/uicontrols/system-windows.md`
- **怎么复验**：真机静置观察触发时间，对照配置项。

## 双分辨率同时出一套怎么搞 / 换面板分辨率怎么适配

- **机制**：分辨率是工程属性；同一套设计稿要出两个分辨率需要布局分层（ui/<分辨率>/）或走适配流程。
- **规范**：按 resolution-adapt 流程做，别手工缩放 json；改分辨率后跑 scale_audit。
- **权威文档**：`knowledge/devflow/platform-translate.md`
- **怎么复验**：两套分辨率各跑 check_all + scale_audit（FAIL 必须 0）。

## 能不能照抄 Android 的控件用法 / 反编译so拿接口行不行 / 别的框架的写法能直接用吗

- **机制**：本平台是预编译闭源 UI 库，源码/头文件里没有字段与回调语义；跨框架类推会引入错误的字段用法。
- **规范**：只允许两个来源：MCP 知识库 + 官方文档站；查不到就标「未收录」，不猜不类推、不反编译。
- **权威文档**：`knowledge/uicontrols/retrieval-boundary.md`
- **怎么复验**：检索结果 quality=low_confidence/no_hit 时按边界处置（不得拿沾边片段当依据）。

## 控件太多选不到，能不能按名字搜索控件 / 编辑器找不到某个控件

- **机制**：页内控件多时，可视化编辑器（flythings_ui_visual action=editor）目前只能靠拖拽/看图找，没有按名字检索。
- **规范**：暂时用 json 里控件键名（<类型>__<序号> / caption）定位；**已登记为工具改进项**（给编辑器加控件搜索）。
- **权威文档**：`knowledge/devflow/ui-editor-usage.md`
- **怎么复验**：改进项落地后：编辑器里输入控件名能直接定位并高亮。

