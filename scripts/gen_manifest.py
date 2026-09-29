# -*- coding: utf-8 -*-
"""生成 tools_manifest.json（工具/平台/知识规模 的机器可读快照，单一事实来源的派生产物）。

设计（v0.27.33，回应检讨报告 §2.1「工具信息散落在 6 处、全靠人肉同步」）：
  事实来源只有 3 个，且都在代码里：
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

# ---- 事实来源③：风险分级（read=只读；write=写本地文件；device=会碰真机）---------------
# 判定口径：默认参数下会不会动本机文件 / 会不会连真机。
#  - read   ：不写盘、不连设备（检索、解析、校验、查询）
#  - write  ：会生成/覆盖本机文件（json/ftu/图片/预览稿/Manifest）
#  - device ：会连真机（adb push / launch / 注入触摸 / 抓屏）
RISK = {
    'flythings_get_version': 'read',
    'flythings_knowledge_search': 'read',
    'flythings_hardware_info': 'read',
    'flythings_map_control': 'read',
    'flythings_read_json': 'read',
    'flythings_layout_audit': 'read',
    'flythings_get_project_spec': 'read',
    'flythings_validate_project': 'read',
    'flythings_check_project_deps': 'read',
    'flythings_verify_assets': 'read',
    'flythings_list_packages': 'read',
    'flythings_query_package': 'read',
    'flythings_package_search': 'read',
    'flythings_get_package_api': 'read',
    'flythings_resolve_dependencies': 'read',
    'flythings_i18n_scan': 'read',
    'flythings_fui_pack': 'write',
    'flythings_fui_unpack': 'write',
    'flythings_edit_ftu': 'write',
    'flythings_ui_preview': 'write',
    'flythings_html_to_json': 'write',
    'flythings_ui_visual': 'write',
    'flythings_generate_ui_assets': 'write',
    'flythings_attach_cli_tools': 'write',
    'flythings_create_project': 'write',
    'flythings_create_bin_project': 'write',
    'flythings_i18n_add_language': 'write',
    'flythings_i18n_export': 'write',
    'flythings_i18n_import': 'write',
    'flythings_i18n_refactor': 'write',
    'flythings_i18n_to_json': 'write',
    'flythings_add_package': 'write',
    'flythings_manifest': 'write',
    'flythings_build_ui_flow': 'device',
    'flythings_pack_upgrade': 'write',
    'flythings_device_screenshot': 'device',
    'flythings_gen_ui_test': 'device',
    'flythings_test_run': 'device',
    'flythings_selfcheck': 'device',
    'flythings_bugreport': 'write',
}

# ---- 事实来源③：分类（给文档/AI 分组用）---------------------------------------------
CATEGORY = {
    'flythings_get_version': 'kbase',
    'flythings_knowledge_search': 'kbase',
    'flythings_hardware_info': 'kbase',
    'flythings_map_control': 'layout',
    'flythings_read_json': 'layout',
    'flythings_layout_audit': 'layout',
    'flythings_get_project_spec': 'layout',
    'flythings_validate_project': 'layout',
    'flythings_check_project_deps': 'project',
    'flythings_verify_assets': 'layout',
    'flythings_html_to_json': 'layout',
    'flythings_ui_preview': 'layout',
    'flythings_ui_visual': 'ui-visual',
    'flythings_fui_pack': 'layout',
    'flythings_fui_unpack': 'layout',
    'flythings_edit_ftu': 'layout',
    'flythings_create_project': 'project',
    'flythings_create_bin_project': 'project',
    'flythings_attach_cli_tools': 'project',
    'flythings_build_ui_flow': 'build',
    'flythings_pack_upgrade': 'build',
    'flythings_generate_ui_assets': 'assets',
    'flythings_i18n_scan': 'i18n',
    'flythings_i18n_add_language': 'i18n',
    'flythings_i18n_export': 'i18n',
    'flythings_i18n_import': 'i18n',
    'flythings_i18n_refactor': 'i18n',
    'flythings_i18n_to_json': 'i18n',
    'flythings_list_packages': 'package',
    'flythings_query_package': 'package',
    'flythings_package_search': 'package',
    'flythings_get_package_api': 'package',
    'flythings_resolve_dependencies': 'package',
    'flythings_add_package': 'package',
    'flythings_manifest': 'package',
    'flythings_device_screenshot': 'device',
    'flythings_gen_ui_test': 'device',
    'flythings_test_run': 'device',
    'flythings_selfcheck': 'device',
    'flythings_bugreport': 'device',
}

# ---- 事实来源③：流程阶段（给意图闸门分组用；人工维护，唯一一处）-------------------------
# 目的（2026-09-21，钟工口径「A. 用户没给设计流程/界面，AI 必须先走原型设计、界面设计」）：
# 意图闸门注入的工具目录要**按阶段分组**，让模型看到「现在就该用哪些、哪些要等确认后」，
# 而不是一张平铺清单（平铺时 AI 最自然的动作就是直接 create_project）。
#   - design：设计阶段就该用（只读检索/解析/校验 + 设计产物生成：原型 -> json -> 确认稿）
#   - build ：确认之后 / 建工程 / 编译部署 / 依赖 / 多语言 / 设备动作
#   - other ：与流程阶段无关（版本、元信息、硬件查询）
# 只影响闸门注入的分组文案，不影响任何 op 的行为。
STAGE = {
    # 设计阶段（现在就该用）
    'flythings_knowledge_search': 'design',
    'flythings_map_control': 'design',
    'flythings_read_json': 'design',
    'flythings_layout_audit': 'design',
    'flythings_get_project_spec': 'design',
    'flythings_validate_project': 'design',
    'flythings_ui_preview': 'design',
    'flythings_html_to_json': 'design',
    'flythings_ui_visual': 'design',
    'flythings_generate_ui_assets': 'design',
    # 确认后才用（建工程 / 编译部署 / 依赖 / 设备）
    'flythings_create_project': 'build',
    'flythings_create_bin_project': 'build',
    'flythings_attach_cli_tools': 'build',
    'flythings_build_ui_flow': 'build',
    'flythings_pack_upgrade': 'build',
    'flythings_fui_pack': 'build',
    'flythings_fui_unpack': 'build',
    'flythings_edit_ftu': 'build',
    'flythings_verify_assets': 'build',
    'flythings_check_project_deps': 'build',
    'flythings_manifest': 'build',
    'flythings_add_package': 'build',
    'flythings_list_packages': 'build',
    'flythings_query_package': 'build',
    'flythings_package_search': 'build',
    'flythings_get_package_api': 'build',
    'flythings_resolve_dependencies': 'build',
    'flythings_i18n_scan': 'build',
    'flythings_i18n_add_language': 'build',
    'flythings_i18n_export': 'build',
    'flythings_i18n_import': 'build',
    'flythings_i18n_refactor': 'build',
    'flythings_i18n_to_json': 'build',
    'flythings_device_screenshot': 'build',
    'flythings_gen_ui_test': 'build',
    'flythings_test_run': 'build',
    'flythings_selfcheck': 'build',
    'flythings_bugreport': 'build',
    # 与流程阶段无关
    'flythings_get_version': 'other',
    'flythings_hardware_info': 'other',
}

# 命令行名词表（回应检讨 §2.4：仓库里 fun / fui / fyx / fuse 四种提法容易混）
CLI_NAMES = {
    'fun': 'FlyThings 工程工具（create/install/build/launch，<项目>/.fsc/<平台>/ 下；09-28 前为 .fun/）',
    'fui': 'FTU 布局工具：pack（json → ftu）/ unpack（ftu → json）双向下；随包 fui 自 v0.27.91 起含 unpack（旧版只有 pack）',
    'fyx': '旧版打包/发布 CLI 名（历史遗留，等价于 fun 的早期名）',
    'fuse': '本机 workspace 的引擎 CLI（projects/fuse.exe，非本仓库内置）',
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
        raise SystemExit('以下 op 未登记 risk/category/stage（请在本脚本表里补）：%s' % unclassified)

    ops = []
    for name in op_names:
        node = defined[name]
        doc = (ast.get_docstring(node) or '').strip().splitlines()
        brief = (doc[0] if doc else '')[:90]
        args = [a.arg for a in node.args.args if a.arg not in ('ctx', 'self')]
        ops.append({'op': name, 'brief': brief, 'args': args,
                    'risk': RISK[name], 'category': CATEGORY[name],
                    'stage': STAGE[name]})
    ops.sort(key=lambda o: o['op'])

    import platforms as _pl
    plats = _pl.describe()

    # 知识规模：knowledge/（随仓库分发）+ wiki（本地完整库，clone 后可能没有）
    knowledge_dir = os.path.join(BASE, 'knowledge')
    kb_files = [os.path.join(r, f) for r, _, fs in os.walk(knowledge_dir)
                for f in fs if f.endswith('.md')] if os.path.isdir(knowledge_dir) else []
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
    wiki_paths = [p for p in rag_paths if not p.startswith('knowledge/')]

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
            'wikiFiles': len(wiki_paths),
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
