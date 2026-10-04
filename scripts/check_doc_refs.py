# -*- coding: utf-8 -*-
"""文档指针健康：扫全仓引用的 `knowledge/...md` 路径是否真实存在（死指针 = AI 被误导）。

为什么要有它（2026-10-02）：摸 B2「知识散落收敛」时先扫了一遍指针，立刻抓到 2 处**真死指针**——
`knowledge/devflow/design.md` 被 `icon-library.md` / `scrollwindow-layout-checklist.md` 引用，
但该文档早已不存在（字库限制的口径后来搬到了 `custom-font-config.md`）。AI 拿到这种指针会
去搜一个搜不到的文档，比没有指针更糟。

判据（2026-10-03 扩展）：仓库内所有 .md/.py/.json/.bat/.txt 里出现的**仓内根相对路径**
必须指向真实文件。当前扫描的前缀：
  · `knowledge/`（原有，行为与本扩展前完全一致）
  · `ui_tools/` `components/` `packages/` `templates/` `demos/` `bin_tools/` `toolchain/`
  · `scripts/` —— **仅当引用方不在 `components/` 下**（组件文档里的 `scripts/x.py` 是**组件相对**，合法）

**不扫**这三类（天然仓外/临时/历史，扫了全是噪声）：
  · `projects/` —— 仓外样例工程（`SampleUI-New` / `SmartPanel_HA` 等，页面把它们当"校准源"）
  · `workspace/` —— 本地工作区（`workspace/references/kb/…` 是入库前的源，不入库）
  · `tools/` —— 本仓 `tools/...` → 仓根 重排**之前**的布局（2026-09 前），页面引用它属历史叙述

为什么加这三条前缀（2026-10-03）：本仓经历过 `tools/...` → 仓根的重排，页面里留着**26 处**
那个时代的示例路径（如 `tools/ui_tools/json2img.py`，实际在 `ui_tools/`）——死路径会让 AI
去执行一个不存在的脚本。只扫 `knowledge/` 时这类全都漏掉了。
允许的例外（在 ALLOW 里写明理由）：
  · 历史上存在过的文档 —— 在 CHANGELOG / VERSION_HISTORY / features_recent.json 里出现（那是"当年"的记录）
  · 负例测试的假路径 —— 在 tests/ 下（故意构造的不存在路径）
  · 按需生成的报告 —— `knowledge/_reports/`（.gitignore，跑门禁时才生成）

用法：
    python scripts/check_doc_refs.py            # 人读报告（有死指针退出码 1）
    python scripts/check_doc_refs.py --json     # 机器可读
"""
import argparse
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

REF_RE = re.compile(r'knowledge/[A-Za-z0-9_\-/]+\.[a-z]{2,4}')
# 扩展：仓内根相对前缀（左/右边界都钉住，防后缀误匹配与截断扩展名）
ROOT_PREFIXES = ('ui_tools/', 'components/', 'packages/', 'templates/', 'demos/',
                 'bin_tools/', 'toolchain/', 'scripts/')
REF_RE_ROOT = re.compile(
    r'(?<![A-Za-z0-9_/])(?:%s)[A-Za-z0-9_\-/.]*?'
    r'\.(?:py|md|json|sh|ps1|bat|cfg|properties|c|h|cpp|cc|ttf|ttc|png|jpg|jpeg|exe|'
    r'txt|yml|yaml|cmake|xml)(?![A-Za-z0-9_])'
    % '|'.join(re.escape(p) for p in ROOT_PREFIXES))
SKIP_DIRS = {'__pycache__', '.git', 'temp', '.workbuddy', 'models', 'node_modules', 'i18n'}
# 生成物：内容是派生的，扫它们的指针没有意义
SKIP_FILES = {'rag_index.json', 'knowledge/kb_index.json', 'tools_manifest.json',
              'knowledge/_reports/kb_health.md',
              # 自引用：本脚本的 docstring/白名单里必然出现"死指针示例"（如 design.md、knowledge/a.md），
              # 扫自己会自我报错
              'scripts/check_doc_refs.py'}
# 例外：文件 → 理由
ALLOW_FILE = {
    'CHANGELOG.md': '历史版本记录：指向的是"当年存在过"的文档（当时确实有）',
    'VERSION_HISTORY.md': '同上（版本史，不做回溯修正）',
    'features_recent.json': '同上（近期特性快照；其中 bring-up 文档按"底层过程不入库"已被有意移出知识库）',
    'CONSOLIDATION.md': '归集方案正文会**讨论**已删/不存在的文档路径（如被修掉的死指针），那是叙述不是引用',
    
}
ALLOW_PREFIX = {
    'tests/': '负例测试故意构造不存在的路径（如 knowledge/a.md、no-such-doc.md）',
}
# 例外：被引用的路径前缀 → 理由
ALLOW_PATH_PREFIX = {
    'knowledge/_reports/': '按需生成的报告目录（.gitignore，跑门禁时才生成）',
}
# 例外：个别"看着像路径、其实不是文件指针"的引用（逐条取证过）
ALLOW_REF = {
    'components/platforms.md':
        '集体引用（指 components/ 下那 16 篇 platforms.md），不是单个文件；'
        '出现在 gen_manifest 的注释与用例 docstring 里（2026-10-03 取证）',
    'scripts/verify_lib_symbols.py':
        '**组件相对**路径：`components_catalog.py` 里以组件目录为基准用它（`_has(d, p)`），'
        '不是仓根路径；派生页 components-catalog.md 照抄同一字符串（2026-10-03 取证）',
    'scripts/release_scope.json':
        '**release 分支**才带的文件（拿 master 跑时本就没有）；check_consistency 的注释已写明这一点'
        '（2026-10-03 取证）',
}


def scan():
    hits = {}          # ref → [(file, lineno, text)]
    for root, dirs, files in os.walk(BASE):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            if not fn.endswith(('.md', '.py', '.json', '.bat', '.txt', '.sh')):
                continue
            rel = os.path.relpath(os.path.join(root, fn), BASE).replace('\\', '/')
            if rel in SKIP_FILES:
                continue
            try:
                text = io.open(os.path.join(root, fn), encoding='utf-8', errors='replace').read()
            except OSError as e:
                print('[warn] 读不了 %s（%s），已跳过' % (rel, e.strerror or e))
                continue
            for i, ln in enumerate(text.split('\n'), 1):
                for m in REF_RE.findall(ln) + REF_RE_ROOT.findall(ln):
                    cand = m.rstrip('.,;:)）]')
                    if os.path.isfile(os.path.join(BASE, cand.replace('/', os.sep))):
                        continue
                    if os.path.isdir(os.path.join(BASE, cand.replace('/', os.sep))):
                        continue                      # 目录引用（如 tools/zkshot/）不算死
                    if cand.startswith('scripts/') and rel.startswith('components/'):
                        continue                      # 组件相对路径，合法
                    hits.setdefault(cand, []).append((rel, i, ln.strip()[:110]))
    return hits


def classify(hits):
    real, allowed = [], []
    for ref, refs in sorted(hits.items()):
        why = None
        if ref in ALLOW_REF:
            why = ALLOW_REF[ref]
        elif any(ref.startswith(p) for p in ALLOW_PATH_PREFIX):
            why = ALLOW_PATH_PREFIX[[p for p in ALLOW_PATH_PREFIX if ref.startswith(p)][0]]
        elif refs and all(f in ALLOW_FILE for f, _i, _t in refs):
            why = ALLOW_FILE[refs[0][0]]
        elif refs and all(any(f.startswith(p) for p in ALLOW_PREFIX) for f, _i, _t in refs):
            why = ALLOW_PREFIX[[p for p in ALLOW_PREFIX
                                if refs[0][0].startswith(p)][0]]
        (allowed if why else real).append({'ref': ref, 'why': why, 'refs': refs})
    return real, allowed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    real, allowed = classify(scan())
    if a.json:
        print(json.dumps({'dangling': real, 'allowed': allowed}, ensure_ascii=False, indent=2))
        return 1 if real else 0
    n_ref = sum(len(r['refs']) for r in real)
    print('文档指针体检：死指针 %d 个路径 / %d 处引用；白名单放过 %d 个路径'
          % (len(real), n_ref, len(allowed)))
    for r in real:
        print('  [FAIL] %s' % r['ref'])
        for f, i, t in r['refs'][:3]:
            print('         %s:%d  %s' % (f, i, t))
    if allowed and not real:
        for r in allowed:
            print('  [allow] %s —— %s' % (r['ref'], r['why']))
    if real:
        print('[FAIL] 有死指针：指向不存在的文档会让 AI 去搜一个搜不到的东西，'
              '请改指真实文档或删掉该从句')
        return 1
    print('[PASS] 无死指针（%d 个白名单路径均有理由）' % len(allowed))
    return 0


if __name__ == '__main__':
    sys.exit(main())
