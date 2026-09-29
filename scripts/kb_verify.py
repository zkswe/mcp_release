# -*- coding: utf-8 -*-
"""知识复验器（P1）：按 front-matter 的 `evidence` 真跑一遍判据，写回状态。

用法：
    python scripts/kb_verify.py                     # 只跑 **offline** 证据（CI 用，零设备）
    python scripts/kb_verify.py --scope all         # 含 real-device（需 --device）
    python scripts/kb_verify.py --device 198.51.100.9:5555 --scope all
    python scripts/kb_verify.py --apply             # 结果写回 md（失败 → status=stale）
    python scripts/kb_verify.py --report out.json   # 报告落盘（默认 knowledge/_reports/）

证据类型（kind）：
    offline      → 本地跑 cmd；判 expect_rc（默认 0）+ expect_contains（可选）
    real-device  → 需 --device，cmd 里的 `%DEVICE%` 会替换成设备序列号
    manual       → **不算通过**，只统计（显式登记"为什么不能自动验"，禁止当通过）

红线：复验只在**维护者侧**跑；报告只落 `knowledge/_reports/`（gitignore），不回写用户数据。
"""
import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
import kb_local as kbl          # noqa: E402

REPORT_DIR = os.path.join(kbl.TOTAL_KB, '_reports')


def _docs(scope='offline', target=''):
    """待复验文档：**证据以文件为准**。

    根因（本轮自指环 bug）：kb_verify 原先从 `kb_index.json` 快照读 evidence，
    而 `--apply` 又会改文件 → 索引滞后时把旧证据当现状（且旧证据是自检索引的命令，
    写入元数据后必破）→ 自造循环。改为逐篇从 md 读 meta。
    """
    idx = kbl.load_json(os.path.join(kbl.TOTAL_KB, 'kb_index.json'))
    out = []
    for d in idx.get('docs') or []:
        if target and target not in (d.get('id'), d.get('path')):
            continue
        p = os.path.join(BASE, (d.get('path') or '').replace('/', os.sep))
        if os.path.isfile(p):
            try:
                meta, _b, _e = kbl.parse_front_matter(io.open(p, encoding='utf-8').read())
            except OSError as e:
                d = dict(d, readError=str(e))
            else:
                d = dict(d, evidence=meta.get('evidence') or [],
                         status=meta.get('status'),
                         needsEvidence=meta.get('needs_evidence'),
                         derived=(d.get('path') in kbl.DERIVED_DOCS),
                         id=meta.get('id') or d.get('id'))
        out.append(d)
    return out


def _run_cmd(cmd, timeout=120):
    try:
        r = subprocess.run(cmd, shell=True, cwd=BASE, capture_output=True, text=True,
                           timeout=timeout, encoding='utf-8', errors='replace')
        return r.returncode, (r.stdout or ''), (r.stderr or '')
    except subprocess.TimeoutExpired:
        return 124, '', 'timeout > %ss' % timeout
    except OSError as e:
        return 127, '', str(e)


def _adb_path():
    """解析随仓 adb（真机证据里用 `%ADB%` 占位，避免依赖宿主机 PATH）。"""
    try:
        sys.path.insert(0, BASE)
        import adb_tools
        return adb_tools.resolve_adb() or 'adb'
    except Exception as e:                      # 解析不了就退回 PATH 里的 adb，并留痕
        return 'adb'


def verify_entry(doc, device='', apply=False, allow_device=False):
    ev = doc.get('evidence') or []
    rel = doc.get('path')
    path = os.path.join(BASE, rel) if rel else ''
    res = {'id': doc.get('id'), 'path': rel, 'checks': [], 'status': 'skipped',
           'reason': ''}
    if not ev:
        res['reason'] = '没有 evidence（needs_evidence=%s）' % doc.get('needsEvidence')
        return res
    verdicts = []
    for i, e in enumerate(ev, 1):
        if not isinstance(e, dict):
            e = {'kind': 'manual', 'cmd': str(e)}
        kind = e.get('kind') or 'offline'
        cmd = e.get('cmd') or ''
        item = {'index': i, 'kind': kind, 'cmd': cmd, 'result': 'skip', 'detail': ''}
        if kind == 'manual':
            item['result'] = 'manual'
            item['detail'] = '人工判据（不自动跑，也不算通过）'
        elif e.get('artifact') and not cmd:
            # P0-3：观察类判据（截图/日志/对比表）——文件在且哈希可复算就算过
            art = str(e['artifact'])
            p2 = os.path.join(BASE, art.replace('/', os.sep))
            if os.path.isfile(p2):
                sha = hashlib.sha256(io.open(p2, 'rb').read()).hexdigest()
                item.update(result='pass', artifactSha256=sha,
                            detail='artifact 存在，sha256=%s…' % sha[:16])
                verdicts.append(True)
            else:
                item.update(result='fail', detail='artifact 不存在: %s' % art)
                verdicts.append(False)
        elif kind == 'real-device':
            if not (allow_device and device):
                item['result'] = 'skip'
                item['detail'] = '需真机：传 --device <serial> 且 --scope all'
            else:
                c = cmd.replace('%DEVICE%', device).replace('%ADB%', _adb_path())
                rc, out, err = _run_cmd(c, timeout=int(e.get('timeout', 180)))
                ok = rc == int(e.get('expect_rc', 0)) and (e.get('expect_contains') or '') \
                    in (out + err)
                item.update(result='pass' if ok else 'fail', rc=rc,
                            detail=(out + err).strip()[-300:],
                            cmdResolved=c)
                verdicts.append(ok)
        else:
            rc, out, err = _run_cmd(cmd.replace('%DEVICE%', device).replace('%ADB%', _adb_path()),
                                    timeout=int(e.get('timeout', 120)))
            ok = rc == int(e.get('expect_rc', 0)) and (e.get('expect_contains') or '') \
                in (out + err)
            item.update(result='pass' if ok else 'fail', rc=rc,
                        outputSha256=hashlib.sha256((out + err).encode('utf-8')).hexdigest(),
                        detail=(out + err).strip()[-300:])
            verdicts.append(ok)
        res['checks'].append(item)
    if any(v is False for v in verdicts):
        res['status'] = 'fail'
    elif verdicts and all(verdicts):
        res['status'] = 'pass'
    elif any(c['result'] == 'manual' for c in res['checks']):
        res['status'] = 'manual'
    else:
        res['status'] = 'skipped'
        res['reason'] = res['reason'] or '证据未在本轮范围内（真机项需 --device）'
    if apply and path and os.path.isfile(path) and not doc.get('derived'):
        _apply(path, res)
    return res


def _apply(path, res):
    """把复验结果写回 front-matter：pass → verified_at + **machine_verified_at**（机器签字）
    + 逐条 evidence 落 `ran_at / output_sha256`（可复算）；fail → status=stale。"""
    raw = io.open(path, encoding='utf-8').read()
    meta, body, _err = kbl.parse_front_matter(raw)
    if not meta:
        return
    if res['status'] == 'pass':
        meta['verified_at'] = kbl.today()
        meta['needs_evidence'] = False
        meta['machine_verified_at'] = kbl._now()      # P0-4：机器签字（与人签 reviewed_by 等价留痕）
        if meta.get('status') == 'stale':
            meta['status'] = 'verified'
        ev = meta.get('evidence') or []
        for i, e in enumerate(ev):
            if not isinstance(e, dict) or i >= len(res.get('checks') or []):
                continue
            chk = res['checks'][i]
            if chk.get('result') == 'pass':
                e['ran_at'] = kbl._now()
                sha = chk.get('outputSha256') or chk.get('artifactSha256')
                if sha:
                    e['output_sha256'] = sha
        meta['evidence'] = ev
    elif res['status'] == 'fail':
        meta['status'] = 'stale'
        meta['last_failed_at'] = kbl.today()
    else:
        return
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(kbl.dump_front_matter(meta, body))


def run(scope='offline', target='', device='', apply=False, report=''):
    docs = _docs(scope, target)
    if scope == 'backlog':
        # P2：不跑，只列「待补判据」队列（无问法优先）——这就是写作/补证据的工单
        q = sorted([{'id': d.get('id'), 'path': d.get('path'), 'category': d.get('category'),
                     'hasQueries': bool(d.get('hasQueries')),
                     'freshness': d.get('freshness')} for d in docs],
                   key=lambda x: (x['hasQueries'], x['path'] or ''))
        payload = {'verifiedAt': kbl._now(), 'scope': scope, 'summary': {'backlog': len(q)},
                   'backlog': q, 'docs': []}
        if not report:
            report = os.path.join(REPORT_DIR, 'kb_verify.json')
        kbl.write_json(report, payload)
        return payload, report
    if scope == 'stale':
        # P2 时效：只复验过期/接近过期的条目
        docs = [d for d in docs if (d.get('freshness') or '') in ('stale', 'aging')]
    allow_dev = scope in ('all', 'real-device')
    out = []
    for d in docs:
        out.append(verify_entry(d, device=device, apply=apply, allow_device=allow_dev))
    counts = {'pass': 0, 'fail': 0, 'skipped': 0, 'manual': 0}
    for r in out:
        counts[r['status']] = counts.get(r['status'], 0) + 1
    payload = {'verifiedAt': kbl._now(), 'scope': scope, 'device': device, 'apply': apply,
               'summary': counts, 'docs': out}
    if not report:
        report = os.path.join(REPORT_DIR, 'kb_verify.json')
    kbl.write_json(report, payload)
    return payload, report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scope', default='offline',
                    choices=['offline', 'all', 'real-device', 'stale', 'backlog'])
    ap.add_argument('--target', default='')
    ap.add_argument('--device', default='')
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--report', default='')
    a = ap.parse_args()
    payload, report = run(a.scope, a.target, a.device, a.apply, a.report)
    s = payload['summary']
    print('=' * 72)
    print('kb_verify  scope=%s device=%s apply=%s' % (a.scope, a.device or '-', a.apply))
    if a.scope == 'backlog':
        print('  待补判据队列：%d 篇（无问法优先）' % s.get('backlog', 0))
        for b in payload['backlog'][:12]:
            print('   - %-50s 有问法=%s %s' % (b['path'], b['hasQueries'], b['freshness']))
        print('  报告 ->', report)
        return 0
    print('  通过 %d ｜ 失败 %d ｜ 跳过 %d ｜ 人工判据 %d' % (s.get('pass', 0), s.get('fail', 0),
                                                        s.get('skipped', 0), s.get('manual', 0)))
    for r in payload['docs']:
        if r['status'] in ('fail', 'manual') or any(c['result'] == 'pass'
                                                   for c in r['checks']):
            print('  [%-7s] %-46s %s' % (r['status'], (r.get('id') or '?')[:44],
                                         '；'.join('%s:%s' % (c['kind'], c['result'])
                                                   for c in r['checks'])))
    print('  报告 ->', report)
    return 1 if s.get('fail') else 0


if __name__ == '__main__':
    sys.exit(main())
