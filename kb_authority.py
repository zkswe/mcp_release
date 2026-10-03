# -*- coding: utf-8 -*-
"""权威口径注册表加载器（概念 → 权威文档），唯一消费入口。

真源 = `knowledge/authority_map.json`。解决的痛点：一条铁律常被十几到三十篇文档**各自复述**
（措辞不同、没有逐字重复），于是「哪一篇才算权威」不明确——AI 命中哪篇就信哪篇，口径容易漂。
本表给每个概念指定一个权威文档；`kb_tools.knowledge_search` 命中时把 `authority` 附在返回体里。

设计纪律（与 ui_schema_loader / op_spec_loader / platform_cap_loader 同构）：
  **消费方一律从注册表派生，禁止再抄一份。**
  `canonical` 必须落在**检索范围内**（`kb_index_roots` 的 ROOTS）——否则 AI 拿到指针也搜不到，
  这是 validate() 强制的一条硬约束（比"文件存在"更强：存在但不在索引里 = 等于没有）。

容错：注册表缺失/损坏/查询了不存在的概念 → 抛 AuthorityError（带路径或概念名），不静默。

用法：
    import kb_authority as au
    au.for_query('图片尺寸和控件盒对不上')   # → [{concept,title,canonical,rule,ops}]
    au.validate()                            # 自检问题列表（空 = 合规）
"""
import io
import json
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
MAP_PATH = os.path.join(BASE, 'knowledge', 'authority_map.json')
MAX_HITS = 3

_CACHE = None


class AuthorityError(RuntimeError):
    """注册表缺失 / 损坏 / 查询不存在的概念。消息里永远带路径或概念名。"""


def load():
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    if not os.path.isfile(MAP_PATH):
        raise AuthorityError('权威口径注册表缺失: %s（authority_map.json 必须随包分发）' % MAP_PATH)
    try:
        with io.open(MAP_PATH, encoding='utf-8') as f:
            reg = json.load(f)
    except Exception as e:
        raise AuthorityError('权威口径注册表解析失败: %s（%s: %s）'
                             % (MAP_PATH, type(e).__name__, e))
    if not isinstance(reg.get('concepts'), dict):
        raise AuthorityError('权威口径注册表缺少 concepts 段: %s' % MAP_PATH)
    _CACHE = reg
    return reg


def concepts():
    return sorted(load()['concepts'].keys())


def spec(name):
    c = load()['concepts'].get(name)
    if not isinstance(c, dict):
        raise AuthorityError('%s 未登记进 knowledge/authority_map.json' % name)
    return c


def _norm(s):
    return re.sub(r'[\s，。；：、（）()\[\]`*|/>\-—→「」]+', '', (s or '')).lower()


def _shingles(s, n=4):
    return {s[i:i + n] for i in range(max(0, len(s) - n + 1))}


def _hit_norm(a, query):
    """别名是否该算命中：子串命中，或 4 字滑窗覆盖率 ≥0.75（容忍中间插词，如
    『有没有现成的包』对上『有没有现成的 MQTT 包』）。返回命中强度（越大越具体），未命中 0。"""
    if not a or len(a) < 2:
        return 0
    if a in query:
        return len(a) + 10
    if len(a) < 4:
        return 0
    sh = _shingles(a)
    cover = len(sh & _shingles(query)) / float(len(sh))
    return int(len(a) * cover) if cover >= 0.75 else 0


def alias_hit(alias, query):
    """别名/触发词是否命中查询 → 命中强度（0 = 未命中）。**归一化在内部做**，调用方传原话即可。

    两个消费方：① 知识权威归属（`for_query`，别名 → 权威文档）
    ② 工具路由分级筛选（`mcp_server._find`，触发词 → 候选 op）。
    两边都必须"容忍中间插词"（『有没有现成的包』要对上『有没有现成的 MQTT 包』）——
    所以判据只有这一份，别再写第二个匹配器。
    """
    return _hit_norm(_norm(alias), _norm(query))


def weak_chars_hit(alias, query):
    """弱命中：别名的字**都出现**在查询里（不计顺序），且首字在 —— 容忍口语里的插词/改序。

    为什么需要第三档：短触发词（『加包』『装个包』）够不着滑窗阈值，而用户会说
    「加个 mqtt 包」——子串对不上、滑窗又不成立。弱命中只给 1 分（远低于子串/滑窗），
    用来"别一条都不命中"，不是用来定胜负的。
    """
    a, q = _norm(alias), _norm(query)
    if len(a) < 2 or a[0] not in q:
        return 0
    return 1 if all(c in q for c in set(a)) else 0


def for_query(query):
    """查询命中若干概念的别名时，返回权威提示（最多 MAX_HITS 条；按命中强度降序）。"""
    q = _norm(query)
    if not q:
        return []
    hits = []
    for name, c in load()['concepts'].items():
        best = 0
        for alias in c.get('aliases') or []:
            best = max(best, _hit_norm(_norm(alias), q))
        if best:
            hits.append((best, name, c))
    hits.sort(key=lambda t: -t[0])
    out = []
    for _score, name, c in hits[:MAX_HITS]:
        out.append({'concept': name, 'title': c.get('title'),
                    'canonical': c.get('canonical'), 'rule': c.get('rule'),
                    'ops': list(c.get('ops') or []), 'note': '权威口径以 canonical 为准'})
    return out


def validate():
    """自检：canonical 存在**且在检索范围内**、aliases 非空且不撞车、ops 存在。返回问题列表。"""
    errs = []
    reg = load()
    if not str(reg.get('authority') or '').strip():
        errs.append('缺少 authority 声明')
    indexed = None
    try:
        import kb_index_roots as bir
        indexed = bir.repo_rel_docs(BASE)
    except Exception as e:
        errs.append('读不到检索范围（kb_index_roots：%s: %s）' % (type(e).__name__, e))
    ops_defined = None
    try:
        import kb_tools as kt
        ops_defined = set(getattr(kt, 'OP_NAMES', ()))
    except Exception as e:
        errs.append('读不到 op 名单（kb_tools：%s: %s）' % (type(e).__name__, e))
    alias_owner = {}
    for name, c in sorted(reg['concepts'].items()):
        canon = c.get('canonical')
        if not canon:
            errs.append('%s: 缺 canonical' % name)
        else:
            if not os.path.isfile(os.path.join(BASE, canon)):
                errs.append('%s: canonical 文件不存在: %s' % (name, canon))
            elif indexed is not None and canon not in indexed:
                errs.append('%s: canonical 不在检索范围内（AI 拿到也搜不到）: %s' % (name, canon))
        if not (c.get('aliases') or []):
            errs.append('%s: 没有 aliases' % name)
        for a in c.get('aliases') or []:
            k = _norm(a)
            if k in alias_owner and alias_owner[k] != name:
                errs.append('别名 %r 被两个概念认领：%s / %s' % (a, alias_owner[k], name))
            alias_owner[k] = name
        for op in c.get('ops') or []:
            if ops_defined is not None and op not in ops_defined:
                errs.append('%s: ops 里的 %s 不在 kb_tools.OP_NAMES' % (name, op))
    return errs


if __name__ == '__main__':
    print('权威口径：%d 个概念' % len(concepts()))
    for n in concepts():
        c = spec(n)
        print('  %-22s → %-52s [%d 别名 / %d op]'
              % (n, c['canonical'], len(c.get('aliases') or []), len(c.get('ops') or [])))
    errs = validate()
    print('自检：%s' % ('通过' if not errs else '\n  ' + '\n  '.join(errs)))
