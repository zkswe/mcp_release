# -*- coding: utf-8 -*-
"""用户侧知识层（kb_local）：本地层 / 项目层 的存储、front-matter 读写、脱敏导出。

铁律（钟工 2026-09-29 口径）
----------------------------
**绝不写 MCP 安装目录** —— 那是版本物（升级会覆盖、可能只读、还会污染发布物）。
用户生长出来的知识默认落 ① 本地层 / ② 项目层；要进总账只能走「脱敏补丁包」或
「只动 knowledge/inbox/** 的 PR」，且必须过「去重 + 复验 + 问法登记」三关 + 人工签字。

三层存储
--------
  ① 本地层（用户私有，不提交）  `$FLYTHINGS_KB_DIR` 或 `~/.flythings/kb_local/`
       inbox/<yyyymmdd-HHMM>-<slug>.md   候选条目（front-matter status=draft）
       kb_candidates.jsonl               候选流水（机读）
       _logs/no_hit.jsonl                检索未命中日志（生长燃料）
       exports/                          脱敏补丁包
       kb_index.local.json               本地清单（生成物）
  ② 项目层（随项目 git 走）      `<项目>/docs/kb/`（同结构，可提交）
  ③ 总账层（我方 open 版仓）     `<MCP 安装目录>/knowledge/`（**只读**，由维护者维护）

状态机（写死）
--------------
  status: draft → review → verified ；失败复验 → stale ；被取代 → deprecated
  只有 `verified` 允许进检索索引与发布；`draft/review` 只在候选区可见、**不当依据**。
  晋升只能由「机器复验通过」或「人工签字」触发 —— **AI 不能自评通过**。
"""
import hashlib
import io
import json
import os
import re
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
TOTAL_KB = os.path.join(BASE, 'knowledge')
SCHEMA_VERSION = 1

STATUSES = ('draft', 'review', 'verified', 'stale', 'deprecated')
CONFIDENCE = ('real-device', 'offline', 'manual', 'unverified')
EVIDENCE_KINDS = ('real-device', 'offline', 'manual')

# front-matter 必填字段（门禁据此判；缺一即 FAIL）
REQUIRED_FIELDS = ('id', 'title', 'category', 'status', 'confidence', 'verified_at',
                   'stale_days', 'origin', 'source')

# 派生文档（生成物）：front-matter 由生成器拥有 —— --retags / --fix-states / kb_verify --apply
# 都不许改它（否则与生成器输出漂移 → --check 必红）
DERIVED_DOCS = ('knowledge/hardware/hardware-models.md',)

# 可索引状态（draft = 候选区，不进索引/检索；review = 可检索但必带标注；verified = 已验证）
INDEXABLE_STATUS = ('verified', 'review')
# 证据字段：`ran_at` / `output_sha256` 由 kb_verify --apply 自动写；`artifact` = 证据文件
# （截图/日志/对比表等，观察类判据靠它，否则方法论类知识永远无法自证）
EVIDENCE_KEYS = ('kind', 'cmd', 'artifact', 'expect_rc', 'expect_contains', 'ran_at',
                 'output_sha256', 'timeout', 'note')

# tags 合规：**只允许检索词**（禁止反引号/星号/尖括号/分号等 markdown 碎片混入索引）
# 背景（2026-09-29 提报发现）：P1 首轮抽取把正文碎片（`<包名`、`**`、`检索词：…`）当 tags 写进 33/85 篇。
_TAG_BAD = re.compile(r'[`*<>{}|\\"\'’“”·→←;；:：,，。、（）()\[\]【】「」!！?？]')
_TAG_PREFIX = re.compile(r'^(检索词|检索导引|见|如)\s*[:：]?\s*')
MAX_TAGS = 16
MAX_TAG_LEN = 14


def clean_tag(tag):
    """把候选 tag 洗成合规检索词；不合规回 ''（调用方丢弃）。单一实现，抽取与门禁共用。"""
    t = re.sub(r'\s+', ' ', str(tag or '').strip().strip('`*_ '))
    t = _TAG_PREFIX.sub('', t).strip()
    if len(t) < 2 or len(t) > MAX_TAG_LEN or _TAG_BAD.search(t):
        return ''
    return t


def tag_problems(tags):
    """返回不合规的 tag 列表（门禁用；空列表 = 合规）。"""
    bad = []
    for t in (tags or []):
        if not isinstance(t, str) or clean_tag(t) != t:
            bad.append(t)
    if len(tags or []) > MAX_TAGS:
        bad.append('（共 %d 个，超过 %d）' % (len(tags or []), MAX_TAGS))
    return bad

_META_SCALARS = ('id', 'title', 'category', 'status', 'confidence', 'verified_at',
                 'reviewed_by', 'reviewed_at', 'machine_verified_at', 'stale_days',
                 'origin', 'source', 'needs_evidence', 'supersedes',
                 'merged_into', 'applies_to_mcp')
_META_LISTS = ('platforms', 'tags', 'related')
_FM_RE = re.compile(r'\A---\s*\n(.*?)\n---\s*\n', re.S)


def _now():
    return time.strftime('%Y-%m-%d %H:%M:%S')


def today():
    return time.strftime('%Y-%m-%d')


def slugify(text, limit=48):
    s = re.sub(r'[^0-9A-Za-z\u4e00-\u9fff]+', '-', str(text or '').strip()).strip('-')
    return (s[:limit] or 'entry').lower()


def kb_dir(override=''):
    """本地层目录（**不在 MCP 安装目录里**）。"""
    if override:
        return os.path.abspath(override)
    env = (os.environ.get('FLYTHINGS_KB_DIR') or '').strip()
    if env:
        return os.path.abspath(env)
    return os.path.join(os.path.expanduser('~'), '.flythings', 'kb_local')


def project_dir(project_root):
    """项目层目录：<项目>/docs/kb（随项目 git 提交）。"""
    if not project_root:
        return ''
    return os.path.join(os.path.abspath(project_root), 'docs', 'kb')


def total_dir():
    """总账层目录（只读用途）。"""
    return TOTAL_KB


def layer_dir(layer='local', override='', project_root=''):
    if str(layer).startswith('proj'):
        return project_dir(project_root)
    return kb_dir(override)


def inbox_dir(d):
    return os.path.join(d, 'inbox')


def _ensure(d):
    for sub in ('inbox', '_logs', 'exports'):
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    return d


# ── front-matter 解析 / 生成 ────────────────────────────────────────────────
def _parse_scalar(v):
    v = v.strip()
    if v in ('true', 'True'):
        return True
    if v in ('false', 'False'):
        return False
    if v in ('null', '~', ''):
        return None
    if re.fullmatch(r'-?\d+', v):
        return int(v)
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1]
    return v


def _parse_list(v):
    v = v.strip()
    if not v.startswith('['):
        return [x.strip() for x in v.split(',') if x.strip()]
    inner = v[1:-1].strip()
    if not inner:
        return []
    return [x.strip().strip('"').strip("'") for x in inner.split(',') if x.strip()]


def parse_front_matter(text):
    """→ (meta:dict, body:str, err:str)。没有 front-matter → meta={} err=''（调用方判）。"""
    m = _FM_RE.match(str(text or ''))
    if not m:
        return {}, str(text or ''), ''
    meta, err = {}, ''
    cur = None
    for raw in m.group(1).split('\n'):
        if not raw.strip() or raw.strip().startswith('#'):
            continue
        if raw.startswith((' ', '\t')):                     # 列表项 / 子字段
            line = raw.strip()
            if line.startswith('- ') and cur:
                if not isinstance(meta.get(cur), list):
                    meta[cur] = []
                item = line[2:].strip()
                if item.startswith('{'):
                    item = item[1:-1] if item.endswith('}') else item[1:]
                if ':' in item:                              # {kind: x, cmd: y} 行内形态
                    kv = {}
                    for part in re.split(r',\s*(?=[\w_]+:)', item):
                        if ':' in part:
                            k, v = part.split(':', 1)
                            kv[k.strip()] = _parse_scalar(v)
                    meta[cur].append(kv)
                else:
                    meta[cur].append(_parse_scalar(item))
            continue
        if ':' not in raw:
            err = err or 'front-matter 行不认识: %s' % raw.strip()
            continue
        k, v = raw.split(':', 1)
        k, v = k.strip(), v.strip()
        if v == '':
            meta[k] = []
            cur = k
            meta.setdefault('_sections', [])
            meta['_sections'] = meta.get('_sections', []) + [k]
            continue
        if v.startswith('['):
            meta[k] = _parse_list(v)
        elif v.startswith('{'):
            kv = {}
            inner = v[1:-1].strip()
            if inner:
                for part in inner.split(','):
                    if ':' in part:
                        kk, vv = part.split(':', 1)
                        kv[kk.strip()] = _parse_scalar(vv)
            meta[k] = kv
        else:
            meta[k] = _parse_scalar(v)
        cur = None
    # 空列表节（evidence: 后没跟任何 "- "）还原成 []
    for k in meta.get('_sections', []):
        if meta.get(k) == []:
            meta[k] = []
    meta.pop('_sections', None)
    return meta, str(text or '')[m.end():], err


def _yaml_val(v):
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if v is None:
        return 'null'
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    if re.search(r'[:#\[\]{}]', s) or s != s.strip():
        return '"%s"' % s.replace('"', '\\"')
    return s


def dump_front_matter(meta, body):
    """meta → 文本块 + 正文（字段顺序稳定，便于 diff/去重）。"""
    lines = ['---']
    for k in _META_SCALARS:
        if meta.get(k) is not None and meta.get(k) != '':
            lines.append('%s: %s' % (k, _yaml_val(meta[k])))
    for k in _META_LISTS:
        if meta.get(k) is not None:
            lines.append('%s: [%s]' % (k, ', '.join(str(x) for x in meta[k])))
    ev = meta.get('evidence') or []
    if ev:
        lines.append('evidence:')
        for e in ev:
            if isinstance(e, dict):
                parts = ', '.join('%s: %s' % (kk, _yaml_val(vv)) for kk, vv in e.items())
                lines.append('  - {%s}' % parts)
            else:
                lines.append('  - %s' % _yaml_val(e))
    else:
        lines.append('evidence: []')
    for k in ('supersedes', 'merged_into', 'applies_to'):
        if meta.get(k):
            if isinstance(meta[k], dict):
                lines.append('%s: {%s}' % (k, ', '.join('%s: %s' % (a, _yaml_val(b))
                                                        for a, b in meta[k].items())))
            else:
                lines.append('%s: %s' % (k, _yaml_val(meta[k])))
    lines.append('---')
    return '\n'.join(lines) + '\n' + str(body or '').lstrip('\n')


def validate_meta(meta, path=''):
    """门禁用：必填字段 + 状态/置信度取值 + verified 必须有证据或显式登记待补。"""
    errs = []
    for k in REQUIRED_FIELDS:
        if meta.get(k) in (None, '', []):
            errs.append('缺必填字段 %s' % k)
    if meta.get('status') and meta['status'] not in STATUSES:
        errs.append('status=%s 不合法（%s）' % (meta['status'], '/'.join(STATUSES)))
    if meta.get('confidence') and meta['confidence'] not in CONFIDENCE:
        errs.append('confidence=%s 不合法（%s）' % (meta['confidence'], '/'.join(CONFIDENCE)))
    ev = meta.get('evidence') or []
    if meta.get('status') == 'verified':
        # P0-1/P0-3/P0-4：verified 必须「有可执行判据」**且**「有人审或机器复验过」
        hard = [e for e in ev if isinstance(e, dict) and (e.get('cmd') or e.get('artifact'))]
        if not hard:
            errs.append('status=verified 但没有带 cmd/artifact 的 evidence（不许口头结论当已验证）')
        if not (meta.get('reviewed_by') or meta.get('machine_verified_at')):
            errs.append('status=verified 但无 reviewed_by / machine_verified_at（晋升必须有签字或机器复验）')
    bad_tags = tag_problems(meta.get('tags'))
    if bad_tags:
        errs.append('tags 不合规（只允许检索词，禁 markdown 碎片）: %s' % bad_tags[:4])
    for e in ev:
        if isinstance(e, dict):
            if not (e.get('cmd') or e.get('artifact')):
                errs.append('evidence 缺 cmd/artifact')
            if e.get('kind') and e['kind'] not in EVIDENCE_KINDS:
                errs.append('evidence.kind=%s 不合法' % e['kind'])
            art = str(e.get('artifact') or '').strip()
            if art and art not in ('-', 'n/a'):
                p2 = os.path.join(BASE, art.replace('/', os.sep))
                if not os.path.exists(p2):
                    errs.append('evidence.artifact 不存在: %s（证据文件丢了就不算证据）' % art)
    return errs


def indexable(meta):
    """能不能进检索索引：**无 front-matter 的（如 knowledge/README.md）照旧保留**；
    只有显式写了非可索引状态（draft/deprecated）的才挡。"""
    if not meta:
        return True
    return (meta.get('status') or '') in INDEXABLE_STATUS


def evidence_level(meta):
    ev = [e for e in (meta.get('evidence') or []) if isinstance(e, dict)]
    if any(e.get('cmd') or e.get('artifact') for e in ev):
        return 'has-evidence'
    return 'manual-only' if meta.get('needs_evidence') else 'none'


# ── 指纹（去重） ────────────────────────────────────────────────────────────
_SYM = re.compile(r'[\s,，。;；:：!！?？"\'`、。]+')


def normalize_symptom(text):
    """归一化症状词：去标点/空格/大小写，便于"同一件事"判重。"""
    return _SYM.sub('', str(text or '')).lower()


def fingerprint(meta):
    """指纹 = 归一化标题 + 关键命令 + 平台（**不含正文**，正文措辞会漂）。"""
    ev = meta.get('evidence') or []
    cmds = ' '.join(str(e.get('cmd', '')) for e in ev if isinstance(e, dict))
    plats = ','.join(sorted(str(x) for x in (meta.get('platforms') or [])))
    raw = '|'.join([normalize_symptom(meta.get('title')), normalize_symptom(cmds),
                    normalize_symptom(plats)])
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]


def find_duplicate(meta, extra_indexes=(), kb_override='', project_root='', notes=None):
    """在 本地层/项目层/总账清单 + 候选区(inbox) 里找同指纹或同 id 的条目（防重复文档）。

    notes：候选项读不了时不静默 —— 逐条记进 notes（调用方回给用户）。
    """
    fp, eid = fingerprint(meta), meta.get('id')
    for idx in list(extra_indexes) + [local_index_path(kb_dir(kb_override))]:
        d = load_json(idx)
        for doc in (d.get('docs') or []):
            if doc.get('fingerprint') == fp or (eid and doc.get('id') == eid):
                return {'path': doc.get('path') or doc.get('file'), 'id': doc.get('id'),
                        'origin': doc.get('origin'), 'why': ('同 id' if doc.get('id') == eid
                                                             else '同指纹')}
    # 候选区（inbox）里的 md —— 索引还没生成时也必须能判重
    dirs = [inbox_dir(kb_dir(kb_override))]
    if project_root:
        dirs.append(inbox_dir(project_dir(project_root)))
    for d in dirs:
        if not d or not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.endswith('.md'):
                continue
            try:
                raw = io.open(os.path.join(d, f), encoding='utf-8').read()
            except OSError as e:
                if notes is not None:
                    notes.append('候选项 %s 读不了（已跳过判重）：%s' % (f, e))
                continue
            m, _b, _e = parse_front_matter(raw)
            if m and (fingerprint(m) == fp or (eid and m.get('id') == eid)):
                return {'path': os.path.join(d, f), 'id': m.get('id'),
                        'origin': m.get('origin'), 'why': '同指纹（候选区已有）'}
    return None


# ── 捕获（写本地层/项目层） ──────────────────────────────────────────────────
def capture(title, body='', category='devflow', platforms=(), tags=(), evidence=(),
            source='', layer='local', project_root='', kb_override='', severity='normal',
            status='draft'):
    """把一条现场结论落成**候选条目**（默认写本地层，绝不写安装目录）。

    返回 {success, id, path, fingerprint, duplicateOf, layer, ...}；
    命中已有条目 → 报 duplicateOf 并提示"合并"而不是新建。
    """
    res = {'success': False, 'op': 'flythings_knowledge_capture', 'warnings': []}
    notes = res['warnings']
    title = str(title or '').strip()
    if not title:
        res['error'] = '缺 title（一句话说清"现象/结论"）'
        return res
    d = layer_dir(layer, kb_override, project_root)
    if not d:
        res['error'] = 'layer=project 需要 project_root'
        return res
    meta = {
        'id': '%s-%s' % (slugify(category or 'devflow', 16), slugify(title)),
        'title': title, 'category': category or 'devflow',
        'platforms': list(platforms or []), 'tags': list(tags or []),
        'status': status, 'confidence': 'unverified', 'verified_at': today(),
        'stale_days': 180, 'origin': ('project' if str(layer).startswith('proj') else 'local'),
        'source': source or ('capture@%s' % today()), 'needs_evidence': True,
        'evidence': [e if isinstance(e, dict) else {'kind': 'manual', 'cmd': str(e)}
                     for e in (evidence or [])],
        'severity': severity,
    }
    dup = find_duplicate(meta, extra_indexes=[os.path.join(total_dir(), 'kb_index.json')],
                         kb_override=kb_override, project_root=project_root, notes=notes)
    if dup:
        res.update(success=True, duplicate=True, duplicateOf=dup, id=meta['id'],
                   layer=meta['origin'],
                   hint=('已有同主题条目（%s），**请合并**：在该条目追加平台矩阵/新证据/复现日期，'
                         '不要新建第二篇' % dup.get('path')))
        return res
    _ensure(d)
    fname = '%s-%s.md' % (time.strftime('%Y%m%d-%H%M'), slugify(title))
    path = os.path.join(inbox_dir(d), fname)
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(dump_front_matter(meta, '# %s\n\n%s\n' % (title, body or '（待补：现象/根因/判据）')))
    row = dict(meta, path=path, fingerprint=fingerprint(meta), captured_at=_now(),
               layer=meta['origin'])
    with io.open(os.path.join(d, 'kb_candidates.jsonl'), 'a', encoding='utf-8') as f:
        f.write(json.dumps(row, ensure_ascii=False) + '\n')
    res.update(success=True, duplicate=False, id=meta['id'], path=path, layer=meta['origin'],
               fingerprint=row['fingerprint'], status=meta['status'],
               hint=('下一步：补 evidence（cmd + 期望）→ scripts/kb_verify.py 复验 → '
                     'status=verified 后才进检索；晋升需人工签字（AI 不能自评）'))
    return res


# ── 未命中日志（生长燃料） ───────────────────────────────────────────────────
def log_no_hit(query, quality='no_hit', hits=(), k=3, kb_override=''):
    """检索未命中/低置信落盘（本地层）。日志在用户自己机器上，只用于生成 gaps 清单。"""
    d = _ensure(kb_dir(kb_override))
    row = {'ts': _now(), 'query': str(query or '')[:300],
           'qnorm': normalize_symptom(query)[:200],
           'quality': quality, 'k': int(k), 'topHits': [str(h) for h in list(hits)[:3]]}
    try:
        with io.open(os.path.join(d, '_logs', 'no_hit.jsonl'), 'a', encoding='utf-8') as f:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
    except OSError as e:
        return {'logged': False, 'error': str(e)}
    return {'logged': True, 'file': os.path.join(d, '_logs', 'no_hit.jsonl')}


def read_jsonl(path):
    out = []
    if not os.path.isfile(path):
        return out
    for line in io.open(path, encoding='utf-8'):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            out.append({'_parseError': line[:120]})
    return out


def gaps(limit=20, kb_override=''):
    """未命中的聚合（谁在反复问、问不到什么）→ 直接当下一批写作清单。"""
    d = kb_dir(kb_override)
    rows = read_jsonl(os.path.join(d, '_logs', 'no_hit.jsonl'))
    agg = {}
    for r in rows:
        key = r.get('qnorm') or normalize_symptom(r.get('query'))
        if not key:
            continue
        a = agg.setdefault(key, {'query': r.get('query', ''), 'count': 0,
                                 'first': r.get('ts', ''), 'last': r.get('ts', '')})
        a['count'] += 1
        a['last'] = r.get('ts', '') or a['last']
    items = sorted(agg.values(), key=lambda x: (-x['count'], x['query']))[:int(limit)]
    return {'success': True, 'op': 'kb_local.gaps', 'totalLogged': len(rows),
            'uniqueGaps': len(agg), 'items': items, 'logFile':
            os.path.join(d, '_logs', 'no_hit.jsonl')}


def gaps_markdown(g, generated_at=''):
    lines = ['# 知识缺口清单（kb_gaps）', '',
             '> 由 `scripts/kb_gaps.py` 从「检索未命中日志」生成 —— **用户真的问不到的东西**就是下一批写作清单。',
             '> 生成时间：%s ｜ 累计未命中 %d 次 / 去重后 %d 条' % (generated_at or _now(),
                                                                   g.get('totalLogged', 0),
                                                                   g.get('uniqueGaps', 0)), '',
             '| # | 问法（归一化前最后形态） | 次数 | 首次 | 最近 |', '|---|---|---|---|---|']
    for i, it in enumerate(g.get('items', []), 1):
        lines.append('| %d | %s | %d | %s | %s |' % (i, it['query'].replace('|', '\\|'),
                                                     it['count'], it['first'], it['last']))
    if not g.get('items'):
        lines.append('| - | （暂无未命中记录） | 0 | - | - |')
    lines += ['', '## 写法（P1 后的标准动作）',
              '1. 挑一条缺口 → `flythings_knowledge_capture(...)` 落候选（本地层）；',
              '2. 补 `evidence`（可执行命令 + 期望）→ `python scripts/kb_verify.py` 复验；',
              '3. 登记 ≥5 条问法（含 ≥1 反例）到 `scripts/check_retrieval.py`；',
              '4. `python scripts/kb_grow.py`（P2）或人工复核 → `status=verified` 才进检索。', '']
    return '\n'.join(lines)


# ── 脱敏与导出（补丁包） ─────────────────────────────────────────────────────
_IPV4 = re.compile(r'\b\d{1,3}(?:\.\d{1,3}){3}(?::\d{2,5})?\b')
_WINPATH = re.compile(r'[A-Za-z]:[\\/][^\s\'"]+')
_UNIXHOME = re.compile(r'/(?:home|Users|srv|opt|data|mnt|workspace|var|root)/[^\s\'"]*')
_CRED = re.compile(r'(?i)\b(?:password|passwd|pwd|token|secret|accesskey|apikey)\b\s*[:=]\s*\S+')
_HOST = re.compile(r'\bDESKTOP-[A-Z0-9]{4,}\b')
_PHONE = re.compile(r'\b1[3-9]\d{9}\b')


def anonymize(text):
    """脱敏：内网/公网 IP、本机路径、凭据、主机名、手机号 → 占位符。返回 (文本, 命中数)。"""
    s = str(text or '')
    n = 0
    for rx, rep in ((_IPV4, '<IP>'), (_WINPATH, '<PATH>'), (_UNIXHOME, '<PATH>'),
                    (_CRED, '<REDACTED>'), (_HOST, '<HOST>'), (_PHONE, '<PHONE>')):
        s, k = rx.subn(rep, s)
        n += k
    return s, n


def export_pack(out='', scope='inbox', layer='local', project_root='', kb_override='',
                internal=False, include_total=False):
    """导出**脱敏补丁包**（回流通道 A）。

    scope: inbox（候选）| verified（本地已晋升）| all
    默认脱敏且不可关：要导出未脱敏内容必须 `internal=True`（仅供总账维护者自用）。
    """
    res = {'success': False, 'op': 'flythings_knowledge_export'}
    d = layer_dir(layer, kb_override, project_root)
    if not d or not os.path.isdir(d):
        res['error'] = ('没有可导出的条目（本地层目录还不存在：%s）—— 先 '
                        'flythings_knowledge_capture 落一条' % d)
        return res
    entries, scrubbed_total = [], 0
    paths = []
    if scope in ('inbox', 'all'):
        paths += [os.path.join(inbox_dir(d), f) for f in sorted(os.listdir(inbox_dir(d)))
                  if f.endswith('.md')] if os.path.isdir(inbox_dir(d)) else []
    if scope in ('verified', 'all'):
        paths += [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith('.md')]
    if include_total:
        for sub in ('devflow', 'uicontrols', 'hardware', 'esl', 't113-car', 'v85x'):
            p = os.path.join(total_dir(), sub)
            if os.path.isdir(p):
                paths += [os.path.join(p, f) for f in sorted(os.listdir(p)) if f.endswith('.md')]
    for p in paths:
        try:
            raw = io.open(p, encoding='utf-8').read()
        except OSError as e:
            res.setdefault('warnings', []).append('%s 读不了: %s' % (p, e))
            continue
        meta, body, ferr = parse_front_matter(raw)
        clean, n = anonymize(raw)
        scrubbed_total += n
        entries.append({'file': os.path.basename(p), 'id': meta.get('id'),
                        'category': meta.get('category'), 'status': meta.get('status'),
                        'confidence': meta.get('confidence'), 'fingerprint': fingerprint(meta),
                        'sha256': hashlib.sha256(clean.encode('utf-8')).hexdigest(),
                        'body': clean if internal else clean,
                        'frontMatterError': ferr})
    if not entries:
        res['error'] = '没有可导出的条目（scope=%s，目录 %s）' % (scope, d)
        return res
    if not internal:
        pack_body = json.dumps(entries, ensure_ascii=False)     # 已逐条脱敏
    else:
        pack_body = json.dumps(entries, ensure_ascii=False)
        res['warning'] = 'internal=True：本次导出**未额外保护**，仅供总账维护者自用，禁止外发'
    pack = {'schema': SCHEMA_VERSION, 'kind': 'kb-contrib', 'createdAt': _now(),
            'mcpVersion': _pkg_version(), 'origin': {'layer': layer},
            'anonymized': not internal, 'scrubbedHits': scrubbed_total,
            'entryCount': len(entries), 'entries': entries}
    text = json.dumps(pack, ensure_ascii=False, indent=1)
    pack['checksum'] = hashlib.sha256(text.encode('utf-8')).hexdigest()[:32]
    text = json.dumps(pack, ensure_ascii=False, indent=1)
    if not out:
        out = os.path.join(_ensure(d), 'exports',
                           'kb-contrib-%s.json' % time.strftime('%Y%m%d-%H%M%S'))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with io.open(out, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    res.update(success=True, pack=out, entries=len(entries), scrubbed=scrubbed_total,
               anonymized=not internal, checksum=pack['checksum'], bytes=len(text.encode('utf-8')),
               hint=('交回方式：把该文件发回（邮件/共享盘/工单），或直接对 open 版仓提 PR '
                     '（只改 knowledge/inbox/**）。总账侧会跑 去重 → 复验 → 问法登记 → 人工签字'))
    return res


def local_docs(kb_override='', project_root=''):
    """本地层/项目层里**可索引**的文档（P0-2：用户 capture 的知识必须自己能搜到）。

    返回 [{path(带 kb_local/ 前缀), abs, meta, sha256, origin}]；draft/deprecated 不算。
    """
    out = []
    roots = [(kb_dir(kb_override), 'local')]
    pd = project_dir(project_root) if project_root else ''
    if pd:
        roots.append((pd, 'project'))
    for d, origin in roots:
        if not d or not os.path.isdir(d):
            continue
        cand = [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith('.md')]
        inbox = inbox_dir(d)
        if os.path.isdir(inbox):
            cand += [os.path.join(inbox, f) for f in sorted(os.listdir(inbox))
                     if f.endswith('.md')]
        for p in cand:
            try:
                raw = io.open(p, encoding='utf-8').read()
            except OSError as e:
                out.append({'path': '', 'abs': p, 'error': '读不了: %s' % e})
                continue
            meta, _body, _err = parse_front_matter(raw)
            if not indexable(meta):
                continue
            rel = os.path.relpath(p, d).replace(os.sep, '/')
            out.append({'path': 'kb_local/%s/%s' % (origin, rel), 'abs': p, 'meta': meta,
                        'sha256': hashlib.sha256(raw.encode('utf-8')).hexdigest(),
                        'origin': origin, 'bytes': len(raw.encode('utf-8'))})
    return out


def build_local_index(kb_override='', project_root=''):
    """生成本地层机读清单 `kb_index.local.json`（与总账 kb_index.json 同形状的子集）。"""
    docs, counts = [], {'total': 0, 'byStatus': {}, 'withEvidence': 0, 'manualOnly': 0,
                        'byOrigin': {}}
    for d in local_docs(kb_override, project_root):
        if not d.get('path'):
            continue
        meta = d['meta']
        st = meta.get('status') or 'draft'
        lvl = evidence_level(meta)
        docs.append({'id': meta.get('id'), 'path': d['path'], 'title': meta.get('title'),
                     'category': meta.get('category'), 'status': st,
                     'evidenceLevel': lvl, 'origin': d['origin'],
                     'verified_at': meta.get('verified_at'),
                     'fingerprint': fingerprint(meta), 'sha256': d['sha256'],
                     'abs': d['abs'], 'bytes': d.get('bytes', 0)})
        counts['total'] += 1
        counts['byStatus'][st] = counts['byStatus'].get(st, 0) + 1
        counts['byOrigin'][d['origin']] = counts['byOrigin'].get(d['origin'], 0) + 1
        if lvl == 'has-evidence':
            counts['withEvidence'] += 1
        elif lvl == 'manual-only':
            counts['manualOnly'] += 1
    idx = {'meta': {'schema': SCHEMA_VERSION, 'built_at': _now(), 'layer': 'local',
                    'doc_count': counts['total']}, 'summary': counts, 'docs': docs}
    d = _ensure(kb_dir(kb_override))
    write_json(local_index_path(d), idx)
    return idx


def _pkg_version():
    try:
        import kb_tools
        return kb_tools.MCP_VERSION
    except Exception as e:
        return 'unknown(%s)' % type(e).__name__


# ── 清单读写 ────────────────────────────────────────────────────────────────
def local_index_path(d):
    return os.path.join(d, 'kb_index.local.json')


def load_json(path):
    if not os.path.isfile(path):
        return {}
    try:
        return json.load(io.open(path, encoding='utf-8'))
    except (ValueError, OSError) as e:
        return {'_error': str(e), 'path': path}


def write_json(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    return path


def _main(argv):
    import argparse
    ap = argparse.ArgumentParser(description='用户侧知识层（capture / export / gaps / log-no-hit）')
    sub = ap.add_subparsers(dest='cmd')
    c = sub.add_parser('capture')
    c.add_argument('title')
    c.add_argument('--body', default='')
    c.add_argument('--category', default='devflow')
    c.add_argument('--platforms', default='')
    c.add_argument('--source', default='')
    c.add_argument('--project', default='')
    c.add_argument('--layer', default='local')
    e = sub.add_parser('export')
    e.add_argument('--out', default='')
    e.add_argument('--scope', default='inbox')
    e.add_argument('--project', default='')
    e.add_argument('--internal', action='store_true')
    g = sub.add_parser('gaps')
    g.add_argument('--limit', type=int, default=20)
    g.add_argument('--out', default='')
    a = ap.parse_args(argv[1:])
    if a.cmd == 'capture':
        r = capture(a.title, a.body, a.category,
                    [x for x in a.platforms.split(',') if x], source=a.source,
                    project_root=a.project, layer=a.layer)
    elif a.cmd == 'export':
        r = export_pack(a.out, a.scope, project_root=a.project, internal=a.internal)
    elif a.cmd == 'gaps':
        g = gaps(a.limit)
        md = gaps_markdown(g)
        if a.out:
            with io.open(a.out, 'w', encoding='utf-8', newline='\n') as f:
                f.write(md)
            print('saved ->', a.out)
        r = g
    else:
        ap.print_help()
        return 1
    print(json.dumps({k: v for k, v in r.items() if k != 'items'} |
                     ({'items': r['items']} if 'items' in r else {}),
                     ensure_ascii=False, indent=1))
    return 0 if r.get('success', True) else 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(_main(sys.argv))
