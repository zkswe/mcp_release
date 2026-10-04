# -*- coding: utf-8 -*-
"""生成 tools_manifest.json（工具/平台/知识规模 的机器可读快照，单一事实来源的派生产物）。

设计（v0.27.33，回应检讨报告 §2.1「工具信息散落在 6 处、全靠人肉同步」）：事实来源只有 3 个，且都在代码里：
    ① 工具的存在 / 参数 = kb_tools.py 的 OP_NAMES + 函数签名 + docstring 首行
       （AST 离线解析，不导入 kb_tools，无需 mcp/onnx 依赖）
    ② 平台矩阵 = platforms.py（PLATFORMS）
    ③ 风险分级 / 分类 / 流程阶段 = **本文件顶部的 RISK / CATEGORY / STAGE 表**（人工维护，唯一一处）
产出：
    tools_manifest.json = 上面三者的**只读快照**，给文档/外部客户端/检查脚本消费。
    ⚠️ 不要手改 tools_manifest.json；改代码或本文件的表，再重新生成。

用法（在 MCP 根目录或任意位置）：
    python scripts/gen_manifest.py            # 写入 tools_manifest.json
    python scripts/gen_manifest.py --check    # 只比对（漂移即退出码 1，check_consistency.py 调用）
    python scripts/gen_manifest.py --out X    # 指定输出
"""
import argparse
import ast
import io
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
DEFAULT_OUT = os.path.join(BASE, 'tools_manifest.json')
import op_spec_loader as _osl                       # noqa: E402  op 契约唯一真源（stdlib only）

# ---- 风险分级（read=只读；write=写本地文件；device=会碰真机）-----------------------------
# ⚠️ 值不在这里维护：唯一真源 = op_spec.json（op 契约注册表）的 risk 字段，下面三行是派生。
# 判定口径：默认参数下会不会动本机文件 / 会不会连真机。
#  - read   ：不写盘、不连设备（检索、解析、校验、查询）
#  - write  ：会生成/覆盖本机文件（json/ftu/图片/预览稿/Manifest）
#  - device ：会连真机（adb push / launch / 注入触摸 / 抓屏）
RISK = {op: _osl.risk(op) for op in _osl.registered()}

# ---- 分类（给文档/AI 分组用）——派生自 op_spec.json 的 category 字段 --------------------
CATEGORY = {op: _osl.category(op) for op in _osl.registered()}

# ---- 流程阶段（给意图闸门分组用）——派生自 op_spec.json 的 stage 字段 -------------------
# 目的（2026-09-21，需求方口径「A. 用户没给设计流程/界面，AI 必须先走原型设计、界面设计」）：
# 意图闸门注入的工具目录要**按阶段分组**，让模型看到「现在就该用哪些、哪些要等确认后」，
# 而不是一张平铺清单（平铺时 AI 最自然的动作就是直接 create_project）。
#   - design：设计阶段就该用（只读检索/解析/校验 + 设计产物生成：原型 -> json -> 确认稿）
#   - build ：确认之后 / 建工程 / 编译部署 / 依赖 / 多语言 / 设备动作
#   - other ：与流程阶段无关（版本、元信息、硬件查询）
# 只影响闸门注入的分组文案，不影响任何 op 的行为。
STAGE = {op: _osl.stage(op) for op in _osl.registered()}

# 命令行名词表（**只登记当前在用的命令**，旧名一律不登记）。
# 为什么不登记 fyx / fuse：它们已不在当前工具链里，登记进常驻 manifest 只会让 AI
# 以为还有这些命令可调（实测：本仓库找不到任何 fyx 实体）。老工程为什么仍带 fuse 痕迹
# （`.fuse/` 产物目录、`FUSE_BUILD` 宏、`~/.fuse` 注册表路径）属**兼容识别知识**，
# 见 knowledge/devflow/cli-fun-toolchain.md —— 那是「要认识的老形态」，不是「可调的命令」。
# 已废弃 CLI 名清单见 check_consistency.stage_cli_names（再登记进来会红）。
CLI_NAMES = {
    'fun': 'FlyThings 工程工具（create/install/build/launch，<项目>/.fsc/<平台>/ 下；09-28 前为 .fun/）',
    'fui': 'FTU 布局工具：pack（json → ftu）/ unpack（ftu → json）双向下；随包 fui 自 v0.27.91 起含 unpack（旧版只有 pack）',
}


def _kb_ast():
    src = io.open(os.path.join(BASE, 'kb_tools.py'), encoding='utf-8').read()
    return ast.parse(src)


def _const_str(module, name):
    for n in module.body:
        if isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == name for t in n.targets):
            try:
                return ast.literal_eval(n.value)
            except (ValueError, SyntaxError):
                return None
    return None


def collect():
    tree = _kb_ast()
    op_names = _const_str(tree, 'OP_NAMES') or ()
    version = _const_str(tree, 'MCP_VERSION') or ''
    build = _const_str(tree, 'MCP_BUILD') or ''
    defined = {n.name: n for n in tree.body
               if isinstance(n, ast.FunctionDef) and n.name.startswith('flythings_')
               and n.name != 'flythings_kb'}
    missing = sorted(set(op_names) - set(defined))
    extra = sorted(set(defined) - set(op_names))
    if missing or extra:
        raise SystemExit('OP_NAMES vs 函数定义不一致  missing=%s extra=%s' % (missing, extra))
    unclassified = sorted(set(op_names) - set(RISK) | set(op_names) - set(CATEGORY)
                          | set(op_names) - set(STAGE))
    if unclassified:
        raise SystemExit('以下 op 未登记进 op_spec.json 的 risk/category/stage（请改注册表）：%s' % unclassified)

    ops = []
    for name in op_names:
        node = defined[name]
        doc = (ast.get_docstring(node) or '').strip().splitlines()
        brief = (doc[0] if doc else '')[:90]
        args = [a.arg for a in node.args.args if a.arg not in ('ctx', 'self')]
        ops.append({'op': name, 'brief': brief, 'args': args,
                    'risk': RISK[name], 'category': CATEGORY[name],
                    'stage': STAGE[name],
                    # 触发词（用户会怎么说 → 选这个 op）：工具面**分层**后 description 只带常驻面，
                    # 这份索引是「选哪个工具」的另一处入口（资源 flythings://tools / 意图闸门），
                    # 两处都得能按口语选工具，否则 AI 只能靠 brief 猜。
                    'triggers': list(_osl.spec(name).get('triggers') or [])})
    ops.sort(key=lambda o: o['op'])

    import platforms as _pl
    plats = _pl.describe()

    # 知识规模：knowledge/（随仓库分发）+ wiki（本地完整库，clone 后可能没有）
    #
    # ⚠️ 口径（2026-10-04 干净检出实测）：**跳过 `_` 前缀目录**（`_reports` / `_logs`）。
    # 那些是 .gitignore 的派生产物（体检看板、全检报告、未核清单），**每台机器各不相同**：
    # 记进 `knowledgeFiles` 会让这个字段随环境漂（实测同一提交：有报告的机器 119、
    # 干净检出 115），而 `gen_manifest --check` 比的是"生成结果 vs 入库快照" →
    # **在干净检出上必然红**（这正是本仓反复治的"门禁依赖未入库产物"同款病）。
    # 只统计随仓分发的那些 md（下方 ragChunks/ragPaths 来自随仓 `rag_index.json`，同样可复现）。
    knowledge_dir = os.path.join(BASE, 'knowledge')
    kb_files = []
    if os.path.isdir(knowledge_dir):
        for r, ds, fs in os.walk(knowledge_dir):
            ds[:] = [d for d in ds if not d.startswith('_')]
            kb_files += [os.path.join(r, f) for f in fs if f.endswith('.md')]
    rag_paths, rag_chunks = [], 0
    ragp = os.path.join(BASE, 'rag_index.json')
    if os.path.isfile(ragp):
        try:
            idx = json.load(io.open(ragp, encoding='utf-8'))
            chunks = idx.get('chunks', [])
            rag_chunks = len(chunks)
            rag_paths = sorted({c.get('path', '') for c in chunks if c.get('path')})
        except (ValueError, OSError):
            rag_paths, rag_chunks = [], 0
    # wiki = 「既不在仓库真源声明的索引范围里、也不是用户本地层」的那些 chunk 路径。
    #
    # ⚠️ 旧口径是 `not p.startswith('knowledge/')` —— 那是把「非 knowledge 前缀」当成了 wiki。
    # 索引范围收编 components/platforms.md（2026-10-02 B1.3）之后这个口径就错了：
    # 那 16 篇是**仓库内**文档，却被算进 wikiFiles；本仓再加 packages/（2026-10-03）会变成 41。
    # 更硬的后果在门禁侧：check_consistency 的 `wiki page count` 拿 manifest.docs.wikiFiles
    # 与**真实 wiki 篇数**比，于是在有本机 wiki 的机器上（发布前必跑）必然对不上 = 假红。
    # wiki 篇数 = **从 wiki 根真源直接数**（2026-10-05 改口径）。
    #
    # 旧口径是「索引里既不在仓库真源声明里、也不是本地层的 chunk」—— 那在"wiki 不进索引"
    # 之后会恒为 0（实测 manifest=0 而 real=122 → 门禁 `wiki page count` 假红）。
    # 现在 wiki 已随 open 仓分发（`wiki/flythings/`），所以它该跟 `knowledge/` 一样按**磁盘真源**数：
    # 门禁侧 `check_consistency` 比的是"真实 wiki 篇数"，两边同源才不会漂。
    wiki_root = os.path.join(BASE, 'wiki', 'flythings')
    wiki_files = 0
    if os.path.isdir(wiki_root):
        for r, ds, fs in os.walk(wiki_root):
            ds[:] = [d for d in ds if not d.startswith('_')]
            wiki_files += sum(1 for f in fs if f.endswith('.md'))

    return {
        'schema': 1,
        'generatedBy': 'scripts/gen_manifest.py',
        'note': '只读快照：改代码或 gen_manifest.py 的 RISK/CATEGORY/STAGE 表后重新生成，勿手改本文件',
        'version': version,
        'build': build,
        'toolCount': len(ops),
        'cli': CLI_NAMES,
        'platforms': plats,
        'ops': ops,
        'docs': {
            'knowledgeFiles': len(kb_files),
            'wikiFiles': wiki_files,
            'ragChunks': rag_chunks,
            'ragPaths': len(rag_paths),
        },
    }


def dumps(data):
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False) + '\n'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=DEFAULT_OUT)
    ap.add_argument('--check', action='store_true', help='只比对，不一致退出码 1')
    a = ap.parse_args()
    want = dumps(collect())
    if a.check:
        if not os.path.isfile(a.out):
            print('[FAIL] tools_manifest.json missing: %s' % a.out)
            return 1
        cur = io.open(a.out, encoding='utf-8').read()
        if cur != want:
            print('[FAIL] tools_manifest.json 与代码/表不一致（漂移）')
            try:
                cj, wj = json.loads(cur), json.loads(want)
                cm = {o['op']: o for o in cj.get('ops', [])}
                wm = {o['op']: o for o in wj.get('ops', [])}
                for op in sorted(set(cm) | set(wm)):
                    if op not in cm:
                        print('   missing op: %s' % op)
                    elif op not in wm:
                        print('   stale op: %s' % op)
                    elif cm[op] != wm[op]:
                        print('   meta drift %s: %s -> %s' % (op, cm[op], wm[op]))
                for k in ('version', 'build', 'toolCount', 'platforms', 'docs'):
                    if cj.get(k) != wj.get(k):
                        print('   %s: %s -> %s' % (k, cj.get(k), wj.get(k)))
            except ValueError:
                print('   （当前文件不是合法 JSON）')
            print('   fix: python scripts/gen_manifest.py')
            return 1
        print('[PASS] tools_manifest.json in sync (%s, %d ops)'
              % (json.loads(cur)['version'], json.loads(cur)['toolCount']))
        return 0
    io.open(a.out, 'w', encoding='utf-8', newline='\n').write(want)
    d = json.loads(want)
    print('manifest -> %s (%s, %d ops, %d platforms)'
          % (a.out, d['version'], d['toolCount'], len(d['platforms'])))
    return 0


if __name__ == '__main__':
    sys.exit(main())
