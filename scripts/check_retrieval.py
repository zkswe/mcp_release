# -*- coding: utf-8 -*-
"""检索质量回归（12 条真实问法）：滚轮/选择器类问题必须一次命中权威文档。

背景（2026-09-19 钟工口径「检索质量优化」）：轮子/选择器这类问题此前会命中
「官方 wiki 镜像里的 IDE 口径片段」或沾边文档，AI 拿不到我们自己的结论。
本脚本把「问法 → 期望权威文档」钉死成可重复执行的用例，防止回归。

用法：
  python scripts/check_retrieval.py            # 跑断言（进闸门）
  python scripts/check_retrieval.py --report   # 只打表格（做前后对比用）
  python scripts/check_retrieval.py --json out.json

判据（两条，硬）：
  ① 每条问法 top-3 里必须出现期望文档（否则该问法算 miss）；
  ② 至少 MIN_TOP1 条问法的 top-1 就是期望文档。
退出码 = 0 全绿 / 1 有 miss。
"""
import argparse
import io
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

CMD = 'knowledge/uicontrols/listview-wheel-picker.md'      # 本轮权威文档
CMD_SOFT = (CMD, 'knowledge/uicontrols/control-mapping-capability.md',
            'knowledge/uicontrols/framework-control-mapping.md')

# 12 条真实问法（客户/同事原话风格，含同义词与口语），expected = 期望 top-1 的权威文档
CASES = [
    ('滚轮怎么做', CMD),
    ('滚轮拖不动', CMD),
    ('选中条跟着行滚', CMD),
    ('picker-view 怎么实现', CMD),
    ('时间选择器怎么做', CMD),
    ('列表中间行高亮', CMD),
    ('滚轮惯性', CMD),
    ('时间滚轮怎么回读选中值', CMD),
    ('循环列表做选择器', CMD),
    ('时钟盘（TimePicker 圆形）怎么实现', CMD),
    ('NumberPicker 滚轮交互支持吗', CMD),
    ('日期时间选择器（时/分）怎么拼', CMD),
    # 同族别名问法：不要求 top-1，但不许 miss（top-3 必须命中）
    ('lv_roller 怎么用', CMD),
    ('LISTWHEEL 对应哪个控件', CMD),
    ('QTimeEdit 怎么做', CMD),
    ('picker mode=time 小程序怎么转', CMD),
]

# 对照组：与滚轮无关的其它问法—— 本轮调了检索实现（专名优先/别名扩展），
# 这组用来防「为了一个主题把别的主题调坏」。阈值取本轮实测值（9/11），留 1 条余量。
CONTROL = [
    ('HTML_SUBSET 控件映射 data-icon 图标', 'html-subset-quickref.md'),
    ('Z20 屏幕截图怎么抓', 'device-screenshot.md'),
    ('抓屏 双缓冲 pan 抓到旧画面', 'device-screenshot.md'),
    ('图片生成锯齿 只走三条路', 'ui-asset-rules.md'),
    ('可视化编辑器 拖完怎么回写 json', 'ui-editor-usage.md'),
    ('按钮长按 循环重复 怎么配', 'button-fields.md'),
    ('listview setSelection 没刷新', 'listview-fields.md'),
    ('json 字段必须全写 缺省漂移', 'json-field-mandatory.md'),
    ('deploy 到设备 抓不到 log', 'device-deploy-budget.md'),
    ('字体不显示 缺字', 'custom-font-config.md'),
    ('lv_obj 是什么', 'lvgl.md'),
    # 2026-09-19 新增：低对比度边缘 AA 坑条（浅色压浅底的锯齿/脏边）
    ('浅色选中条边界有锯齿 毛边', 'ui-asset-rules.md'),
    ('超采样缩回 LANCZOS 暗边', 'ui-asset-rules.md'),
    # 2026-09-23 新增：列表封面缓存条（新入库 `listview-image-cache.md`，防检索退化后 AI 找不到解法）
    ('列表封面卡 重复解码', 'listview-image-cache.md'),
    ('回页卡 封面列表', 'listview-image-cache.md'),
]
CONTROL_MIN = 9            # 实测 14/15（2026-09-23 加 2 条列表封面缓存条后由 12/13 → 14/15；低于 9 说明调参伤了其它主题）

MIN_TOP1 = 12          # 前 12 条主力问法要求 top-1 命中
TOPK = 3


def run(k=TOPK):
    import kb_tools
    rows = []
    for q, want in CASES:
        out = json.loads(kb_tools.flythings_knowledge_search(q, k=max(k, 5)))
        paths = [h['path'] for h in out.get('hits', [])]
        rank = paths.index(want) + 1 if want in paths else 0
        rows.append({
            'query': q,
            'quality': out.get('quality'),
            'coverage': out.get('coverage'),
            'retrieval': out.get('retrieval'),
            'top3': paths[:3],
            'rank': rank,
            'top1_ok': rank == 1,
            'hit_top3': 1 <= rank <= k,
            'doc_top1_any': any((p or '') == CMD for p in paths[:1]),
        })
    return rows


def run_control(k=TOPK):
    import kb_tools
    rows = []
    for q, want in CONTROL:
        out = json.loads(kb_tools.flythings_knowledge_search(q, k=k))
        paths = [h['path'] for h in out.get('hits', [])]
        rows.append({'query': q, 'want': want, 'top3': paths[:3],
                     'top3_ok': any(want in p for p in paths),
                     'rank': next((i + 1 for i, p in enumerate(paths) if want in p), 0)})
    return rows


def run(k=TOPK):
    import kb_tools
    rows = []
    for q, want in CASES:
        out = json.loads(kb_tools.flythings_knowledge_search(q, k=max(k, 5)))
        paths = [h['path'] for h in out.get('hits', [])]
        rank = paths.index(want) + 1 if want in paths else 0
        rows.append({
            'query': q,
            'quality': out.get('quality'),
            'coverage': out.get('coverage'),
            'retrieval': out.get('retrieval'),
            'top3': paths[:3],
            'rank': rank,
            'top1_ok': rank == 1,
            'hit_top3': 1 <= rank <= k,
            'doc_top1_any': any((p or '') == CMD for p in paths[:1]),
        })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--report', action='store_true', help='只打表格不判失败')
    ap.add_argument('--json', default='', help='把结果落 JSON（做前后对比）')
    ap.add_argument('--bm25', action='store_true',
                    help='强制降级 BM25（模拟无本地向量模型的机器，验证降级路也不 miss）')
    a = ap.parse_args()
    if a.bm25:
        import rag_search
        rag_search._get_embedder = lambda: None
        print('[degraded] 强制 BM25 模式（模拟模型不可用）')

    rows = run()
    n = len(rows)
    top1 = sum(1 for r in rows if r['top1_ok'])
    miss = sum(1 for r in rows if not r['hit_top3'])
    q_ok = sum(1 for r in rows if r['quality'] == 'ok')
    crows = run_control()
    c_ok = sum(1 for r in crows if r['top3_ok'])

    print('=' * 72)
    print('retrieval regression  (%d 问法, 期望文档 %s)' % (n, CMD))
    print('=' * 72)
    print('%-34s %-6s %-7s %-6s %s' % ('问法', 'quality', 'cover', 'rank', 'top1 片段'))
    for r in rows:
        t1 = (r['top3'][0] if r['top3'] else '-')
        print('%-34s %-6s %-7s %-6s %s' % (r['query'][:32], r['quality'],
                                           r['coverage'], '#' + str(r['rank']), t1))
    print('-' * 72)
    print('对照组（与滚轮无关的 %d 条问法，防调参副作用）：top-3 %d/%d'
          % (len(crows), c_ok, len(crows)))
    for r in crows:
        if not r['top3_ok']:
            print('  [ctrl-miss] %-30s %s' % (r['query'][:28],
                                              [p.split('/')[-1] for p in r['top3']]))
    print('-' * 72)
    print('top-1 命中期望文档: %d/%d    top-3 未命中(miss): %d    quality=ok: %d/%d'
          % (top1, n, miss, q_ok, n))

    if a.json:
        with io.open(a.json, 'w', encoding='utf-8') as f:
            json.dump({'top1': top1, 'n': n, 'miss': miss, 'quality_ok': q_ok,
                       'control_top3': c_ok, 'control_n': len(crows), 'rows': rows,
                       'control_rows': crows}, f, ensure_ascii=False, indent=1)
        print('saved ->', a.json)

    if a.report:
        return 0
    bad = []
    if miss:
        bad.append('top-3 未命中期望文档 %d 条: %s'
                   % (miss, ', '.join(r['query'] for r in rows if not r['hit_top3'])))
    if top1 < MIN_TOP1:
        bad.append('top-1 命中 %d < 要求 %d' % (top1, MIN_TOP1))
    if c_ok < CONTROL_MIN:
        bad.append('对照组 top-3 命中 %d < 要求 %d（检索实现被调坏了）' % (c_ok, CONTROL_MIN))
    for m in bad:
        print('[FAIL]', m)
    if bad:
        return 1
    print('[PASS] 检索回归全绿（top-1 %d/%d，对照组 %d/%d）' % (top1, n, c_ok, len(crows)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
