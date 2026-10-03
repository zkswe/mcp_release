# -*- coding: utf-8 -*-
"""检索质量回归（**按文档分组 + 入库门禁**）。

背景
----
2026-09-19 起本脚本只覆盖「滚轮/选择器」一个主题（12 条问法钉死单篇权威文档）。
2026-09-29 审查报告 P0② 要求把它**通用化成入库门禁**：新增知识文档必须附 ≥5 条问法，
CI 对该文档的 top-3 命中做断言 —— 否则「文档写了、AI 检索不到」会静默腐化。

规则（对贡献者）
----------------
1. 新增/大改一篇知识文档 → **在本文件的 `GROUPS` 里加一组**：
   `{'doc': 'knowledge/.../<文档>.md', 'min_top1': N, 'queries': [≥5 条真实问法]}`
   · 问法要写「用户/同事会真的说出口的话」（含同义词、口语、常见错说法），可含 1~2 条**反例问法**
   · 每组 ≥`MIN_QUERIES_PER_GROUP` 条（结构化断言，低于即 FAIL）
2. 组的判据：该组全部问法 **top-3 必须命中该文档**（`max_miss` 个例外可显式声明）；
   top-1 命中数 ≥ `min_top1`（阈值留余量，取实测值 −1）
3. 与主题无关的对照组 `CONTROL`：防「为一个主题调坏别的主题」，只判阈值不判逐条

判据与退出码
------------
退出码 0 = 全绿；1 = 有 FAIL（结构化不达标 / 某组 top-3 miss 超限 / top-1 不足 / 对照组退化）。

用法
----
    python scripts/check_retrieval.py              # 断言（进闸门）
    python scripts/check_retrieval.py --report     # 只打表格（前后对比）
    python scripts/check_retrieval.py --json out.json
    python scripts/check_retrieval.py --bm25       # 强制降级 BM25（模拟无本地模型）
"""
import argparse
import io
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

TOPK = 3
MIN_QUERIES_PER_GROUP = 5

# --------------------------------------------------------------------------- #
# 分组用例：doc = 期望权威文档（相对仓库根）；queries = 真实问法
# --------------------------------------------------------------------------- #
GROUPS = [
    {
        'doc': 'knowledge/uicontrols/listview-wheel-picker.md',
        'name': '滚轮 / 选择器',
        'min_top1': 12,          # 实测 16 条里 top-1 命中 12+（2026-09-19 定稿）
        'queries': [
            '滚轮怎么做', '滚轮拖不动', '选中条跟着行滚', 'picker-view 怎么实现',
            '时间选择器怎么做', '列表中间行高亮', '滚轮惯性', '时间滚轮怎么回读选中值',
            '循环列表做选择器', '时钟盘（TimePicker 圆形）怎么实现',
            'NumberPicker 滚轮交互支持吗', '日期时间选择器（时/分）怎么拼',
            'lv_roller 怎么用', 'LISTWHEEL 对应哪个控件', 'QTimeEdit 怎么做',
            'picker mode=time 小程序怎么转',
        ],
    },
    {
        'doc': 'knowledge/uicontrols/listview-image-cache.md',
        'name': '列表封面缓存',
        'min_top1': 4,
        'queries': [
            '列表封面卡 重复解码', '回页卡 封面列表', 'listview 图片缓存怎么做',
            '列表滚动卡顿 封面重复解码', 'listview 封面 缓存 不生效',
        ],
    },
    {
        'doc': 'knowledge/devflow/dependency-package-docs.md',
        'name': '依赖包用法文档（包卡）',
        'min_top1': 5,
        # 第 1 条例外（2026-10-02，新增内置包总览页后被挤）：`Z20 的 openssl 和别的平台版本不一样`
        # → 现排 #4（本篇 0.0154 vs 榜首 builtin-packages.md 0.0262）。**榜首是更直接的答案**——
        # 那一页就是按包键列 openssl 等包的版本、并明说"同一包在不同包键上版本不同"；
        # 本篇管的是"包卡怎么读、Manifest 该声明哪些包"的口径。真记录，不调阈值。
        'max_miss': 1,
        'queries': [
            '依赖包说明不全 怎么看怎么用', 'package.yaml 包卡怎么读', '包卡 package.yaml 里的 api 签名怎么看',
            'Manifest 里该写哪个包和版本', 'Z20 的 openssl 和别的平台版本不一样',
            '不要凭记忆写包内 API 怎么校验',
        ],
    },
    {
        'doc': 'knowledge/devflow/package-verify-playbook.md',
        'name': '依赖包真机自动化验证套路',
        'min_top1': 2,
        # 第 1 条例外（2026-10-02，把 components/*/platforms.md 纳入检索后出现的**真实**挤出）：
        # `setprop ctl.restart zkswe 连续重启 黑屏 进程 D 状态` → 现排 #4（本篇 0.0310 vs 榜首
        # z20-86panel-upgrade 0.0323，分差 <5%）。榜首几篇都在讲同一件事（zkswe 重启/部署预算/
        # 部署一致性），属"多篇都答得通"；权威套路仍在本篇 top-5 内。**不是阈值问题，是真记录**。
        'max_miss': 1,
        'queries': [
            '依赖包怎么上真机验证', '包验证工程 自检 AUTO 一键跑完', '触摸注入 + logcat 取证 怎么组合',
            'setprop ctl.restart zkswe 连续重启 黑屏 进程 D 状态', 'Z21 上电 RTC 1970 HTTPS 证书失败',
            '依赖包验证 主机侧测试服务 HTTP WS 怎么搭',
        ],
    },
    {
        'doc': 'knowledge/devflow/ui-asset-rules.md',
        'name': '出图规范 / 抗锯齿',
        'min_top1': 2,
        'queries': [
            '图片生成锯齿 只走三条路', '浅色选中条边界有锯齿 毛边', '超采样缩回 LANCZOS 暗边',
            '切图尺寸和控件盒不一致', '图标改宽后变糊 要不要重采样',
        ],
    },
    {
        'doc': 'knowledge/devflow/device-screenshot.md',
        'name': '设备抓屏（工具与参数；「视频层该选哪个通道」归多媒体页）',
        'min_top1': 2,          # 实测 2/5（Z20 屏幕截图怎么抓 / 抓屏 scale crop rotate 参数怎么用）
        'max_miss': 3,          # 其余三条被同内容散文页或组件页接走（排 2 名内），答案仍完整
        'queries': [
            'Z20 屏幕截图怎么抓', '抓屏 双缓冲 pan 抓到旧画面', '真机截图颜色红蓝反了',
            '抓屏 scale crop rotate 参数怎么用', 'device_screenshot 抓不到图怎么办',
        ],
    },
    {
        'doc': 'knowledge/components/components-catalog.md',
        'name': '可复用组件目录（有没有现成的 / 依赖 / 示例，树派生）',
        'min_top1': 4,          # 实测 4/8 top-1，8 条全部 top-3 内
        # 注：另测「有没有现成的字体组件」「蓝牙组件怎么用」落 top-5 外 —— 它们的 top-1 是
        # 合法替代答案（字体 → custom-font-config.md；蓝牙跨平台 → platform-capability-matrix.md），
        # 所以没放进本组；本组只收「清单/依赖/示例」这类该由目录页回答的问法。
        'queries': [
            '有没有现成的可复用组件', '组件要依赖哪些包', '复用组件在哪看',
            '高斯模糊有现成的吗', '有没有现成的日历控件', '图表控件有吗',
            '传图组件有没有', '图标组件有吗',
        ],
    },
    {
        'doc': 'knowledge/devflow/reusable-components.md',
        'name': '组件化规范入口（规范在哪 / 四件套 / checklist）',
        'min_top1': 4,          # 实测 4/5 top-1
        'max_miss': 0,
        'queries': [
            '组件规范在哪看', '四件套是什么', '新增组件 checklist', '组件代码规范',
            '组件 platforms.md 写什么',
        ],
    },
    {
        'doc': 'knowledge/media/media-capability-index.md',
        'name': '多媒体能力（播放/录像/对讲/图层，唯一真源派生）',
        'min_top1': 6,          # 实测 6/8
        'max_miss': 1,          # 「拼墙抓不到画面」排 5 —— device-screenshot.md 有 vdec 通道细节，更具体
        'queries': [
            '视频播放用什么包', '摄像头预览怎么做', '录像怎么写进 TF 卡',
            '对讲怎么实现 录音和播放', '全屏动画性能不够怎么办', 'ffmpeg 在这块板上能用吗',
            '拼墙抓不到画面', '能不能不编译直接用设备上的库',
        ],
    },
    {
        'doc': 'knowledge/devflow/html-subset-quickref.md',
        'name': 'HTML 子集 → json',
        'min_top1': 2,
        'queries': [
            'HTML_SUBSET 控件映射 data-icon 图标', 'html 转 json 支持哪些标签',
            'data-bg 和 data-color 区别', '原型里的阴影圆角怎么转成切图',
            'html 原型转 json 丢了字符 看 warnings',
        ],
    },
    {
        'doc': 'knowledge/uicontrols/json-field-mandatory.md',
        'name': 'json 字段必写',
        'min_top1': 2,
        'queries': [
            'json 字段必须全写 缺省漂移', '布局 json 少写字段会怎样', '控件字段全集显式化',
            'beepEnable 要不要写', 'touchable 字段默认值',
        ],
    },
    {
        'doc': 'knowledge/devflow/selfcheck-and-bugreport.md',
        'name': '整机自检 / 缺陷单',
        'min_top1': 2,
        'queries': [
            '设备的整体状态怎么看 有没有一条命令出完整快照',
            '怎么把设备现在的状态和上次比一比 看什么变了',
            '我要给厂家提缺陷单 用什么格式 复现步骤怎么写',
            '蓝牙那栏 ok=false 是工具坏了吗',
            '提缺陷单要附证据 文件不存在会怎样',
        ],
    },
    {
        'doc': 'knowledge/devflow/custom-font-config.md',
        'name': '字库配置 / 缺字',
        'min_top1': 2,
        'queries': [
            '字体不显示 缺字', '字库怎么加进工程', '设备字库裁剪了哪些字符',
            '设备字库不支持 emoji 显示空白', '字体 ttf 放 resources 还是 /res',
        ],
    },
    {
        'doc': 'knowledge/devflow/device-test-run.md',
        'name': '多设备并行测试跑批 / 机读报告',
        'min_top1': 2,
        'queries': [
            '自动化测试怎么批量跑 多台设备一起跑一份用例', '测试报告能不能进 CI JUnit xml',
            '像素基线怎么建 首次怎么建基线', '比不到基线算过还是没过 no-baseline 什么意思',
            '测试用例 JSON 怎么写 action 有哪些', 'test_run 和 gen_ui_test 区别',
        ],
    },
    {
        'doc': 'knowledge/devflow/capability-boundaries.md',
        'name': '能力边界清单',
        'min_top1': 2,
        'queries': [
            'MCP 到底能做什么 能力边界在哪', '哪些知识不在 open 版 内部版有什么区别',
            '这个主题知识库没收录怎么办', '为什么不支持 V85X 深水区 / 车载方案类',
            '未收录就标未收录 不许拿沾边片段当依据',
        ],
    },
    {
        'doc': 'knowledge/devflow/kb-growth.md',
        'name': '知识库生长机制（采集/验证/检索）',
        'min_top1': 2,
        'queries': [
            '知识库怎么自动生长 现场结论怎么入库', 'capture 怎么用 候选区在哪 会不会写进安装目录',
            '未收录怎么办 知识缺口清单 kb_gaps', '知识怎么回流总账 脱敏补丁包 kb-contrib',
            '知识怎么复验 evidence 怎么写 verified 和 draft 区别',
        ],
    },
    {
        'doc': 'knowledge/devflow/open-source-stack-integration.md',
        'name': '开源库/协议栈接入（P1.5 review）',
        'min_top1': 5,          # 实测 6/10 → 留 1 条余量
        # 第 1 条例外（2026-10-02，同上）：`第三方 .so 放哪` → 现排 #4。榜首是
        # `components/blend2d/platforms.md`——那篇的矩阵列就是「库从哪来 / 依据」，对"库放哪"
        # 是个**合理**答案（但权威口径仍在本文 top-5）。真记录，不调阈值。
        'max_miss': 1,
        'queries': [
            '想用开源库怎么办', 'registry 里没有这个包', '自己编译的库怎么加进工程',
            'dlopen 找不到库', 'musl 和 glibc 有什么区别', '静态库太大怎么办',
            'SQLite 能用吗', '第三方 .so 放哪', 'undefined reference 链接错误',
            'ldd 看哪些库',
        ],
    },
    {
        'doc': 'knowledge/devflow/custom-render-paths.md',
        'name': '自定义渲染路径（P1.5 review）',
        'min_top1': 4,          # 实测 5/10 → 留 1 条余量
        # 已知 3 条未进 top-3（真记录，不调阈值凑数）：`视频层怎么叠加` → v85x/videoview-transparent-window.md、
        # `stb 系列头文件库能用吗` → wiki/system/virtual_eeprom.md（这两条是 P1.5 期就有的老账），
        # 新増 `复杂动画性能不够` → 被新增的「边界总纲」篇拽走（同族父子文档竞争：总纲只给结论，
        # 降本做法在本篇；两篇互链、答案都在 top-5）。跟进手段 = 后续把 3 条各自写更具体的同义问法或拆子文档
        # 第 4 条（2026-10-02，v0.27.171）：`想用 LVGL 怎么办` → 被新篇 translate-ui-lvgl.md 拽走——
        # LVGL 迁移问法命中 LVGL 翻译器专篇是**更优答案**（本组问的是自定义渲染，语义本就近似）
        'max_miss': 4,
        'queries': [
            'FlyThings 怎么做自定义渲染', '想用 LVGL 怎么办', '能不能用 cairo/SDL',
            '直接写 framebuffer 可以吗', '离屏渲染成图再显示', '视频层怎么叠加',
            'releaseLayer 是什么', '复杂动画性能不够', '自绘指针表怎么做',
            'stb 系列头文件库能用吗',
        ],
    },
    {
        'doc': 'knowledge/devflow/activity-lifecycle-spec.md',
        'name': '生命周期与代码接口契约（钩子/导航/铁律/控件 API）',
        # 派生物：源 lifecycle_spec.json（scripts/gen_lifecycle_doc.py）；
        # ⚠️ 实测（2026-10-02，索引已把本页收进来）：top-1 **3/9**、9 条**全部 top-5 内**。
        # top-1 常被同内容的散文页 activity-code-skeleton.md / widget-code-api.md 拿走 —— 那是
        # **合法替代答案**（同一事实的两种载体，AI 拿到哪篇都能答对），不是检索坏了。
        # 阈值**按实测登记、不调参凑数**：top-3 允许 2 条落外 ——
        # 「空闲超时怎么判才准」「按钮回调返回 true 还是 false」被骨架散文页的上下文压过（排 4/5），
        # 答案仍完整可读；若将来整体掉出 top-5，说明索引/内容真退化了。
        'min_top1': 3,
        'max_miss': 2,
        'queries': [
            'onUI_quit 里要做什么', '资源释放放 onUI_hide 还是 onUI_quit',
            '切页后回调还触发吗', '隐藏页的定时器还在跑吗', '空闲超时怎么判才准',
            '按钮回调返回 true 还是 false', 'onUI_init 什么时候调用',
            'ZKListView 有哪三个回调', 'goBack 会走 onUI_hide 吗',
        ],
    },
    {
        # 新增知识文档必须附 ≥5 条问法（P0② 通用化门禁）。
        # 本篇是**派生产物**（真源 = platform_capabilities.json，scripts/gen_platform_cap_doc.py 生成）。
        # 它存在的意义就是把「某组件在某平台能不能用」拉进检索范围——此前这份知识只存在于
        # components/*/platforms.md（15 篇 / 1779 行），而 RAG 只覆盖 knowledge/，AI 检索不到
        # （2026-10-02 实测：问「Z20 上能跑哪些组件」返回的全是不相干文档）。
        'doc': 'knowledge/devflow/platform-capability-matrix.md',
        'name': '平台能力矩阵（组件 × 平台 可用性）',
        'min_top1': 7,          # 实测 8 条里 top-1 命中 7
        # 边界（2026-10-02 实测并已按事实修正）：本组只收「**跨组件 / 选型总览**」类问法。
        # 组件**专属**问法（如 `ble 在 Z20 能用吗`）应命中该组件自己的 `components/*/platforms.md`
        # ——那是更权威的细节来源，本篇只是总览。原先把专属问法放本组是归属定错，已换成总览问法。
        'queries': [
            'Z20 上能跑哪些组件', 'F133 上能跑什么组件', '这组件在哪些平台可用',
            '平台能力矩阵', '跨平台移植前要查什么', 'F136 支持哪些组件',
            '所有组件都支持哪些平台 总览', '组件选型 先看哪个平台支持',
        ],
    },
    {
        # 新增知识文档必须附 ≥5 条问法（P0② 通用化门禁）。
        # 本篇是**派生产物**（真源 = package_catalog.json，scripts/gen_package_catalog_doc.py 生成），
        # 意义是把「内置了哪些包 / 什么版本」拉进检索范围——此前这份知识只在 json 里，AI 检索不到，
        # 选型时不知道能直接用现成包（2026-10-02 需求方指出）。
        'doc': 'knowledge/devflow/builtin-packages.md',
        'name': '内置依赖包总览（生态 / 版本 / 包名索引）',
        'min_top1': 8,          # 实测 8/8 top-1
        'queries': [
            '有哪些内置包', '有没有 MQTT 包', 'openssl 是什么版本', '内置了哪些依赖包',
            '这个平台上能直接用哪些包', '怎么给工程加个包', 'zlib 版本', '有没有 curl 包',
        ],
    },
    {
        'doc': 'knowledge/devflow/render-extension-boundary.md',
        'name': '渲染扩展能力边界（三层模型）',
        'min_top1': 11,         # 实测 12 条里 top-1 命中 12（2026-09-30，含需求方三次更正后的问法）→ 留 1 条余量
        'queries': [
            'FlyThings 能不能做 3D', '没有 GPU 能不能做动画特效',
            'canvas 画布能做到什么程度', '软件模拟 GPU 效果行不行',
            '我们只能软渲染吗', '渲染能力边界在哪',
            '非 3D 的效果都能做吗', 'FlyThings 视觉效果能做到什么程度',
            '动画计时必须用绝对时钟吗', '动画计时能不能用帧计数',
            '视频图层尺寸上限', 'GUI 层缩放有上限吗',
        ],
    },
    {
        'doc': 'knowledge/devflow/device-preinstalled-libs.md',
        'name': '设备自带库（免编译借用）',
        'min_top1': 4,          # 实测 6 条里 top-1 命中 5（2026-09-30 建组 A1 稿）
        'queries': [
            '设备上有哪些库', '想用的库设备上有没有', '能不能直接用不用自己编译',
            'nanovg 设备上有吗', 'dlopen 找不到库', '注册表里没有这个包是不是就没有',
        ],
    },
    {
        'doc': 'knowledge/uicontrols/extension-surface.md',
        'name': '扩展点总表',
        'min_top1': 5,          # 实测 10 条里 top-1 命中 6（2026-09-30 建组 A2 稿）→ 留 1 条余量
        # 已知 2 条未进 top-3（真记录，不调阈值凑数）：`差异化 UI 怎么做` → platform-translate/ui-layout-verify
        # （“差异化”是营销词，两篇都沾边）；`走哪条路` → custom-render-paths（问法太泛，答案本就在选路篇）。
        # 跟进：这两条改写成带主体的问法（如“想做平台没有的效果该走哪个扩展点”）后再进组。
        'max_miss': 2,
        'queries': [
            '能扩展什么', '想做平台没有的效果', '这个效果能不能实现',
            '差异化 UI 怎么做', '能不能自己画', '自绘控件怎么写',
            '图层能不能自己用', '走哪条路', '自绘性能够吗', '别的框架能做到这里能吗',
        ],
    },
    {
        'doc': 'knowledge/uicontrols/scrollwindow-layout-checklist.md',
        'name': 'scrollwindow 布局异常清单',
        'min_top1': 5,          # 2026-10-01 建组，实测 top-1 6/11 → 留 1 条余量
        # 实测 top-3 未命中 3 条（真记录，不调阈值凑数）：`滚动窗口怎么做`(rank4) /
        # `滑动窗口怎么做才不堆叠`(rank5) → 落在官方镜像 `scrollwindow.md`/`slidewindow.md`（泛问法，两篇都该看）；
        # `固定按钮跟着滚走了`(rank0) → 落 listview-wheel-picker（“跟着滚”被当滚轮语义）。
        # 跟进：这三条改写成带主体的问法（如“scrollwindow 里的底部按钮为什么跟着滚”）后再收紧。
        'max_miss': 3,
        'queries': [
            'scrollwindow 布局不对', '加了一行滚不到底', '滚动窗口最后一行看不到',
            '滚动窗口怎么做', '固定按钮跟着滚走了', '滚到底点行点错了',
            '行里图标被文字盖住了', '滑动窗口怎么做才不堆叠', 'scrollwindow 内层 window 要多高',
            'scrollwindow 反复返工', '内容堆叠怎么办',
        ],
    },
    {
        'doc': 'knowledge/devflow/deploy-consistency-check.md',
        'name': '部署一致性（新库旧界面）',
        'min_top1': 6,          # 2026-10-01 建组，实测 top-1 7/10 → 留 1 条余量
        # 实测 top-3 未命中 1 条（真记录）：`设备上跑的是哪一份`(rank0) → 落 upgrade-pack-image
        # （“哪一份”被当升级包语义）。跟进：改成“设备上跑的是哪一份 lib / 界面怎么对账”后再收紧。
        'max_miss': 1,
        'queries': [
            '改了像没改', '界面还是旧的', '推了没生效', 'resPath 和 startupLibPath',
            'EasyUI.cfg 优先级', '新库旧界面', 'lib 换了界面没换', '部署后自检',
            '覆盖层和固化区混搭', '设备上跑的是哪一份',
        ],
    },
    {
        'doc': 'knowledge/devflow/quickstart.md',
        'name': '新手快速上手（onboarding 总入口）',
        'min_top1': 7,          # 2026-10-02 建组（A3 任务），实测 8 条里 top-1 命中 8 → 留 1 条余量
        'queries': [
            '装完了接下来干什么', '新手怎么快速上手', '第一句话对 AI 说什么',
            '有没有入门教程', '拿到这个 MCP 第一步做什么', '第一周容易踩什么坑',
            '怎么快速跑通第一个界面', '新手从哪开始',
        ],
    },
    {
        'doc': 'knowledge/devflow/translate-ui-lvgl.md',
        'name': 'LVGL → FlyThings 界面迁移翻译',
        'min_top1': 4,          # 2026-10-02 建组（translate_ui v1）：实测 7 条 top-1 命中 4
        'max_miss': 2,          # 「D-xx 怎么出」归 platform-translate.md（方法论权威，合理）；
                                # 「温控面板 LVGL 界面搬过来」被 quickstart 总入口截走（泛问法）
        'queries': [
            'LVGL 工程怎么迁到 FlyThings', 'lvgl 代码转 ui json',
            'lv_label lv_slider 对应我们哪个控件', 'lv_chart 图表怎么迁移',
            '迁移降级清单 D-xx 怎么出', 'lv_obj_create 转成什么',
            '温控面板 LVGL 界面搬过来',
        ],
    },
    {
        'doc': 'knowledge/devflow/device-preflight-spec.md',
        'name': '上机前体检（分辨率/字库/体积）',
        'min_top1': 6,          # 2026-10-03 建组（域⑨ preflight v1）：实测 8 条 top-1 命中 7
        'max_miss': 1,          # 「设备上中文显示不出来」归 components/fonts/platforms.md ——
                                # 那是组件页（讲设备侧字库现状），属合理竞争者；判据/阈值在 spec 页
        'queries': [
            '上机之前要检查什么', '接上设备先看哪些东西',
            '屏幕分辨率和设计不一样怎么办', '屏比设计分辨率小会怎样',
            '设备上中文显示不出来', '要不要给工程放字库',
            '打包会不会超出 res 分区', '设计分辨率和面板分辨率不一致',
        ],
    },
    {
        'doc': 'knowledge/devflow/flow-index.md',
        'name': '开发流程（场景 × 动作两条轴）',
        'min_top1': 6,          # 2026-10-03 建组（域⑩ flows v1）：实测 8 条 top-1 命中 7
        'max_miss': 1,          # 「上机的步骤顺序」归 device-preflight-spec.md —— 题库里
                                # 「上机」在本仓特指**上机前体检**（判据页），属合理竞争者；
                                # 流程页排第 2，AI 仍能顺着走到。
        'queries': [
            '从零做个界面要走哪些步骤', '设计稿转界面的流程是什么',
            '换个框架搬工程按什么顺序', '改已有工程的步骤顺序',
            '开发完了怎么走验收', '整个开发流程有几条路',
            '上机的步骤顺序', '界面做完到上机中间要做什么',
        ],
    },
]

# 对照组：与上面主题无关的其它问法；want 用子串匹配（不要求 top-1）
CONTROL = [
    ('按钮长按 循环重复 怎么配', 'button-fields.md'),
    ('listview setSelection 没刷新', 'listview-fields.md'),
    ('deploy 到设备 抓不到 log', 'device-deploy-budget.md'),
    ('lv_obj 是什么', 'lvgl.md'),
    ('检索边界 不许套别的框架', 'retrieval-boundary.md'),
    ('触摸事件 压在控件上的装饰件', 'touch-events.md'),
    ('系统键盘盖住界面 收键盘', 'touch-inject-autotest.md'),
    ('fui unpack 反解析 ftu', 'ftu-json-pipeline.md'),
    ('升级包 update.img 怎么做', 'upgrade-pack-image.md'),
    ('多设备在线推到指定设备', 'cli-fun-toolchain.md'),
]
CONTROL_MIN = 6          # 实测 10 条里命中 ≥6（低于此说明调参伤了别的主题）


def _search(q, k):
    import kb_tools
    return json.loads(kb_tools.flythings_knowledge_search(q, k=k))


def run_group(g, k=TOPK):
    rows = []
    for q in g['queries']:
        out = _search(q, max(k, 5))
        paths = [h['path'] for h in out.get('hits', [])]
        rank = paths.index(g['doc']) + 1 if g['doc'] in paths else 0
        rows.append({'query': q, 'rank': rank, 'top1_ok': rank == 1,
                     'hit_top3': 1 <= rank <= k, 'quality': out.get('quality'),
                     'coverage': out.get('coverage'), 'top3': paths[:3]})
    return rows


def run_control(k=TOPK):
    rows = []
    for q, want in CONTROL:
        out = _search(q, k)
        paths = [h['path'] for h in out.get('hits', [])]
        rows.append({'query': q, 'want': want, 'top3': paths[:3],
                     'ok': any(want in p for p in paths)})
    return rows


def _unregistered_groups():
    """列出 knowledge/{devflow,uicontrols}/ 下没有登记问法的文档（只提示，不判失败）。"""
    have = {g['doc'] for g in GROUPS}
    out = []
    for sub in ('devflow', 'uicontrols'):
        d = os.path.join(BASE, 'knowledge', sub)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if f.endswith('.md') and 'knowledge/%s/%s' % (sub, f) not in have:
                out.append('knowledge/%s/%s' % (sub, f))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--report', action='store_true', help='只打表格，不判失败')
    ap.add_argument('--json', default='', help='结果落 JSON')
    ap.add_argument('--bm25', action='store_true', help='强制降级 BM25（模拟无本地向量模型）')
    a = ap.parse_args()
    if a.bm25:
        import rag_search
        rag_search._get_embedder = lambda: None
        print('[degraded] 强制 BM25 模式（模拟模型不可用）')

    bad, summary = [], []
    print('=' * 78)
    print('retrieval regression（按文档分组，共 %d 组）' % len(GROUPS))
    print('=' * 78)
    for g in GROUPS:
        # 结构化断言：组的问法条数
        if len(g['queries']) < MIN_QUERIES_PER_GROUP:
            bad.append('组「%s」问法只有 %d 条 < %d（入库门禁：新文档必须附 ≥%d 条问法）'
                       % (g['name'], len(g['queries']), MIN_QUERIES_PER_GROUP, MIN_QUERIES_PER_GROUP))
        if not os.path.isfile(os.path.join(BASE, g['doc'])):
            bad.append('组「%s」的 doc 不存在: %s' % (g['name'], g['doc']))
        rows = run_group(g)
        n = len(rows)
        top1 = sum(1 for r in rows if r['top1_ok'])
        miss = [r for r in rows if not r['hit_top3']]
        summary.append({'group': g['name'], 'doc': g['doc'], 'n': n, 'top1': top1,
                        'miss': len(miss), 'min_top1': g['min_top1'], 'rows': rows})
        print('%-26s doc=%-46s 问法=%2d top-1=%2d top-3miss=%d'
              % (g['name'], g['doc'].split('/')[-1], n, top1, len(miss)))
        for r in rows:
            flag = '   ' if r['hit_top3'] else ' !M'
            if not r['hit_top3'] or not r['top1_ok']:
                print('   %s %-34s #%-2s %s' % (flag, r['query'][:32], r['rank'],
                                                (r['top3'][0] if r['top3'] else '-')))
        if len(miss) > g.get('max_miss', 0):
            bad.append('组「%s」top-3 未命中 %d 条（允许 %d）: %s'
                       % (g['name'], len(miss), g.get('max_miss', 0),
               ', '.join(r['query'] for r in miss)))
        if top1 < g['min_top1']:
            bad.append('组「%s」top-1 命中 %d < 要求 %d' % (g['name'], top1, g['min_top1']))

    crows = run_control()
    c_ok = sum(1 for r in crows if r['ok'])
    print('-' * 78)
    print('对照组（无关主题 %d 条，防调参副作用）：top-3 %d/%d' % (len(crows), c_ok, len(crows)))
    for r in crows:
        if not r['ok']:
            print('   [ctrl-miss] %-30s got=%s' % (r['query'][:28],
                                                   [p.split('/')[-1] for p in r['top3']]))
    if c_ok < CONTROL_MIN:
        bad.append('对照组 top-3 命中 %d < 要求 %d（检索实现被调坏了）' % (c_ok, CONTROL_MIN))

    unr = _unregistered_groups()
    print('-' * 78)
    print('未登记问法的知识文档（提示，不算失败）：%d 篇（devflow/uicontrols）%s'
          % (len(unr), ('；例：' + ', '.join(os.path.basename(x) for x in unr[:6])) if unr else ''))

    if a.json:
        with io.open(a.json, 'w', encoding='utf-8') as f:
            json.dump({'groups': summary, 'control': crows, 'control_ok': c_ok,
                       'unregistered': unr, 'fail': bad}, f, ensure_ascii=False, indent=1)
        print('saved ->', a.json)

    if a.report:
        return 0
    for m in bad:
        print('[FAIL]', m)
    if bad:
        return 1
    tot_top1 = sum(s['top1'] for s in summary)
    tot_n = sum(s['n'] for s in summary)
    print('[PASS] 检索回归全绿（%d 组 / %d 问法，top-1 %d，对照组 %d/%d）'
          % (len(summary), tot_n, tot_top1, c_ok, len(crows)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
