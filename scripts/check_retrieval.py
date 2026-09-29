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
        'name': '设备抓屏',
        'min_top1': 2,
        'queries': [
            'Z20 屏幕截图怎么抓', '抓屏 双缓冲 pan 抓到旧画面', '真机截图颜色红蓝反了',
            '抓视频层某一帧 vdec 通道', 'device_screenshot 抓不到图怎么办',
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
        # 已知 2 条未进 top-3（真记录，不调阈值凑数）：`视频层怎么叠加` → v85x/videoview-transparent-window.md
        # 与 `stb 系列头文件库能用吗` → wiki/system/virtual_eeprom.md；跟进手段 = 给这两条写更具体的
        # 同义问法或把答案拆进对应子文档（P2 的 gap 驱动写作）
        'max_miss': 2,
        'queries': [
            'FlyThings 怎么做自定义渲染', '想用 LVGL 怎么办', '能不能用 cairo/SDL',
            '直接写 framebuffer 可以吗', '离屏渲染成图再显示', '视频层怎么叠加',
            'releaseLayer 是什么', '复杂动画性能不够', '自绘指针表怎么做',
            'stb 系列头文件库能用吗',
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
