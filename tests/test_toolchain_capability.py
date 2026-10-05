# -*- coding: utf-8 -*-
"""工具链能力声明 + json↔ftu 往返契约。

背景：
  - 随包 `toolchain/fui.exe` 自 v0.27.91 起**含 unpack**（`unpack <in.ftu> [out.json]`，传目录=批量解）；
旧版随包 fui 只有 pack、unpack 是空壳。project_tools._fui_supports_unpack() 用 `fui.exe help`
探测（help 里有没有 unpack 行），工具链据此决定「能否直接读/编辑 ftu」——探测错了就会要么白报错、
要么静默产空文件。下面用例同时钉住「能力声明=实际」与 `flythings_fui_unpack` 的默认不覆盖语义。
  - 检讨报告 §3.5 要求有 fui pack/unpack 往返用例（防「pack 出来的 ftu 解不回等价 json」）。
"""
import io
import json
import os
import shutil
import subprocess
import unittest

import _util as U


class TestFuiCapability(unittest.TestCase):
    def setUp(self):
        self.tmp = U.project()

    def tearDown(self):
        U.cleanup(self.tmp)

    def _pack(self):
        src = os.path.join(self.tmp, 'main.json')
        shutil.copy(U.fixture('main.json'), src)
        r = U.jcall('flythings_fui_pack', U.bypass_gates({'json_path': src}))
        self.assertTrue(r['ok'], r)
        ftu = os.path.join(self.tmp, 'main.ftu')
        self.assertTrue(os.path.isfile(ftu))
        return ftu

    def _try_unpack(self, ftu, out_json=None):
        """按真实 CLI 形式解包，返回 (rc, 产出的 json 路径或 None)。

        fui unpack 的真实用法（`fui help` 自述）：`unpack <input> [<output>]`；
只给 input 时解到同目录同名 json。**传目录也可以**（批量解该目录下的 .ftu）——
2026-10-03 实测 `fui unpack <dir>` rc=0 且解出了 json；改前这里写「⚠️ 传目录会 FATAL」，
与生产代码 3 处传目录（`project_tools._run_fui` / `_sync_ftu_to_json` / `check_all`）矛盾，
是条**陈旧注释**（会误导后来者去"修"本来正常的代码）。
        """
        import project_tools as pt
        args = [pt.FUI_EXE, 'unpack', ftu] + ([out_json] if out_json else [])
        try:
            r = subprocess.run(args, capture_output=True, text=True, timeout=60,
                               stdin=subprocess.DEVNULL, encoding='utf-8', errors='replace')
        except Exception:
            return 1, None
        cand = out_json or os.path.splitext(ftu)[0] + '.json'
        if r.returncode == 0 and os.path.isfile(cand):
            return 0, cand
        return r.returncode, None

    def test_capability_claim_matches_reality(self):
        """双向钉住：声称能用必须真能解出 json；声称不能用必须真解不出。"""
        import project_tools as pt
        ftu = self._pack()
        target = os.path.join(self.tmp, 'out.json')
        rc, got = self._try_unpack(ftu, target)
        works = rc == 0 and got is not None
        claim = bool(pt._fui_supports_unpack())
        self.assertEqual(claim, works,
                         'fui unpack 能力声明与实际不符（claim=%s works=%s，FUI_EXE=%s）：'
                         'claim=False 但真能解 → 修 _fui_supports_unpack()；'
                         'claim=True 却解不出 → 别让工具依赖 unpack'
                         % (claim, works, pt.FUI_EXE))
        if got:
            os.remove(got)

    def test_probe_distinguishes_failure_from_capability_absence(self):
        """「探测失败」≠「能力缺失」（2026-10-03 修）。

        改前是 `except Exception: _cached = False` —— 文件找不到 / 不可执行 / 超时
        全被报成「当前 fui.exe 不含 unpack」，**会把人送去换 fui（方向是错的）**；
        而且**失败结论会被缓存**：一次 15s 超时就让整个进程从此认定不能 unpack。
        现在：原因分类写清、失败不缓存（可重试）。
        """
        import project_tools as pt
        ok, why = pt._fui_probe(os.path.join(self.tmp, 'no-such-fui.exe'))
        self.assertFalse(ok)
        self.assertTrue(why.startswith('探测失败'), '必须报「探测失败」而不是「不含 unpack」：%s' % why)
        self.assertIn('找不到可执行文件', why)
        # 关键：失败**不缓存** —— 随后真实 fui 的结论不受影响（否则会话被一次超时废掉）
        self.assertTrue(pt._fui_supports_unpack(),
                        '探测失败被缓存了：一次失败不该让整个进程认定不能 unpack')
        # 统一文案要带实际二进制路径（工程带多份 fui 时才知道是哪个）
        self.assertIn(pt.FUI_EXE, pt._fui_no_unpack_msg())

    def test_roundtrip_json_ftu_json(self):
        """json → ftu → json 语义等价（fui 不支持 unpack 的 build 上跳过）。"""
        import project_tools as pt
        if not pt._fui_supports_unpack():
            self.skipTest('本 build 的 fui.exe 不含 unpack（%s）' % pt.FUI_EXE)
        ftu = self._pack()
        target = os.path.join(self.tmp, 'roundtrip.json')
        rc, got = self._try_unpack(ftu, target)
        self.assertEqual(rc, 0, 'unpack 失败（rc=%s）' % rc)
        a = json.loads(io.open(os.path.join(self.tmp, 'main.json'), encoding='utf-8').read())
        b = json.loads(io.open(got, encoding='utf-8').read())

        def flat(o, pre=''):
            out = {}
            if isinstance(o, dict):
                for k, v in o.items():
                    out.update(flat(v, pre + '/' + str(k)))
            elif isinstance(o, list):
                for i, v in enumerate(o):
                    out.update(flat(v, pre + '[%d]' % i))
            else:
                out[pre] = o
            return out
        fa, fb = flat(a), flat(b)
        diff = [k for k in sorted(set(fa) | set(fb)) if fa.get(k) != fb.get(k)]
        self.assertEqual(diff[:8], [], '往返后字段不一致（%d 处）' % len(diff))

    def test_edit_ftu_needs_json_when_unpack_unavailable(self):
        """无 unpack 时：同目录没有 json 就必须明确报错（不能假装成功/产空 ftu）。"""
        import project_tools as pt
        if pt._fui_supports_unpack():
            self.skipTest('本 build 支持 unpack，另有分支')
        ftu = self._pack()
        os.remove(os.path.join(self.tmp, 'main.json'))
        r = U.jcall('flythings_edit_ftu',
                    {'ftu_path': ftu, 'operations': '[{"op":"set","target":"textview__1",'
                                                   '"props":{"text":"x"}}]'})
        self.assertFalse(r['ok'], '没有 json 源时不该假装成功')
        self.assertIn('json', json.dumps(r, ensure_ascii=False).lower())


class TestFuiUnpackOp(unittest.TestCase):
    """`flythings_fui_unpack`（v0.27.91）：ftu → json。默认**覆盖**同目录同名 json（ftu 为真源）。"""

    def setUp(self):
        self.tmp = U.project()
        self.src = os.path.join(self.tmp, 'main.json')
        shutil.copy(U.fixture('main.json'), self.src)

    def tearDown(self):
        U.cleanup(self.tmp)

    def _pack(self):
        r = U.jcall('flythings_fui_pack', U.bypass_gates({'json_path': self.src}))
        self.assertTrue(r['ok'], r)
        return os.path.join(self.tmp, 'main.ftu')

    def test_unpack_default_overwrites_same_json(self):
        import project_tools as pt
        ftu = self._pack()
        if not pt._fui_supports_unpack():
            self.skipTest('本 build 的 fui.exe 不含 unpack（%s）' % pt.FUI_EXE)
        # 改 json 但不 pack（模拟「json 与 ftu 不同步」）→ 默认 unpack 必须被 ftu 覆盖回去
        data = json.loads(io.open(self.src, encoding='utf-8').read())
        data['textview__999'] = {'id': 999, 'caption': 'unittest-marker', 'position': {}}
        U.write(self.src, json.dumps(data, ensure_ascii=False, indent=2))
        r = U.jcall('flythings_fui_unpack', {'ftu_path': ftu})
        self.assertTrue(r['ok'], r)
        self.assertEqual(os.path.abspath(r['jsonPath']), os.path.abspath(self.src),
                         '默认应写回同目录同名 json')
        self.assertTrue(r['overwritten'])
        after = json.loads(io.open(self.src, encoding='utf-8').read())
        self.assertNotIn('textview__999', after, '默认以 ftu 为真源覆盖 json')
        self.assertIn(r['jsonPath'], r['affectedFiles'])

    def test_unpack_overwrite_false_keeps_json_source(self):
        import project_tools as pt
        ftu = self._pack()
        before = io.open(self.src, encoding='utf-8').read()
        if not pt._fui_supports_unpack():
            self.skipTest('本 build 的 fui.exe 不含 unpack（%s）' % pt.FUI_EXE)
        r = U.jcall('flythings_fui_unpack', {'ftu_path': ftu, 'overwrite': False})
        self.assertTrue(r['ok'], r)
        self.assertEqual(os.path.basename(r['jsonPath']), 'main.unpacked.json')
        self.assertFalse(r['overwritten'])
        self.assertEqual(io.open(self.src, encoding='utf-8').read(), before,
                         'overwrite=False 时不得改动同目录 json 源')
        # 再解一次 → 换序号，仍不覆盖
        r2 = U.jcall('flythings_fui_unpack', {'ftu_path': ftu, 'overwrite': False})
        self.assertTrue(r2['ok'], r2)
        self.assertNotEqual(r2['jsonPath'], r['jsonPath'])

    def test_unpack_rejects_non_ftu_and_missing(self):
        r = U.jcall('flythings_fui_unpack', {'ftu_path': self.src})
        self.assertFalse(r['ok'], r)
        self.assertIn('.ftu', json.dumps(r, ensure_ascii=False))
        r2 = U.jcall('flythings_fui_unpack', {'ftu_path': os.path.join(self.tmp, 'nope.ftu')})
        self.assertFalse(r2['ok'], r2)

    def test_unpack_to_explicit_output_path(self):
        import project_tools as pt
        ftu = self._pack()
        if not pt._fui_supports_unpack():
            self.skipTest('本 build 的 fui.exe 不含 unpack（%s）' % pt.FUI_EXE)
        before = io.open(self.src, encoding='utf-8').read()
        out = os.path.join(self.tmp, 'elsewhere', 'copy.json')
        r = U.jcall('flythings_fui_unpack', {'ftu_path': ftu, 'output_json': out})
        self.assertTrue(r['ok'], r)
        self.assertTrue(os.path.isfile(out))
        self.assertEqual(io.open(self.src, encoding='utf-8').read(), before,
                         'output_json 指定路径时不动同目录 json')

    def test_edit_ftu_unpacks_when_json_missing(self):
        """v0.27.91：只有 ftu 没 json 时，edit_ftu 自动 unpack 出编辑源（旧版 fui 则明确报错）。"""
        import project_tools as pt
        ftu = self._pack()
        if not pt._fui_supports_unpack():
            self.skipTest('本 build 的 fui.exe 不含 unpack（%s）' % pt.FUI_EXE)
        os.remove(self.src)
        r = U.jcall('flythings_edit_ftu',
                    {'ftu_path': ftu, 'operations': '[{"op":"set","target":"textview__1",'
                                                   '"props":{"x":7}}]'})
        self.assertTrue(r['ok'], r)
        self.assertTrue(r.get('unpackedSource'), '应声明编辑源来自 unpack')
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, 'main.json')))


class TestFtuJsonAutoSyncRules(unittest.TestCase):
    """2026-09-18 口径：ftu → json 只在两种情形自动做 ——
    ① 只有 ftu 没有 json → 直接转；② ftu 比 json 新「分钟级」(≥60s，用户/IDE 编辑过) → 转同步；
    ③ 其余情况**不做**ftu→json（json 是布局源，只需 json→ftu）。"""

    def setUp(self):
        self.tmp = U.project()
        self.src = os.path.join(self.tmp, 'ui', 'main.json')   # 时间戳检查扫的是 <工程>/ui/
        shutil.copy(U.fixture('main.json'), self.src)

    def tearDown(self):
        U.cleanup(self.tmp)

    def _pack(self):
        r = U.jcall('flythings_fui_pack', U.bypass_gates({'json_path': self.src}))
        self.assertTrue(r['ok'], r)
        return os.path.join(self.tmp, 'ui', 'main.ftu')

    def _need_unpack(self, pt):
        if not pt._fui_supports_unpack():
            self.skipTest('本 build 的 fui.exe 不含 unpack（%s）' % pt.FUI_EXE)

    def test_rule1_ftu_only_is_converted_directly(self):
        import project_tools as pt
        self._need_unpack(pt)
        self._pack()
        os.remove(self.src)
        ts = pt._ui_timestamp_check(self.tmp)
        self.assertEqual(ts['ftuOnly'], ['main.ftu'], ts)
        r = pt._sync_ftu_to_json(self.tmp)
        self.assertEqual(r['failed'], [], r)
        self.assertIn('main.ftu', r['synced'])
        self.assertIn('ftuOnly', r['syncedDetail'][0]['why'])
        self.assertTrue(os.path.isfile(self.src), '规则①：只有 ftu 时应直接转出 json')

    def test_rule2_minute_level_newer_ftu_is_synced(self):
        import project_tools as pt
        self._need_unpack(pt)
        ftu = self._pack()
        jt = os.path.getmtime(self.src)
        os.utime(ftu, (jt + 300, jt + 300))          # ftu 比 json 新 5 分钟（IDE 编辑过）
        ts = pt._ui_timestamp_check(self.tmp)
        self.assertEqual([d['ftu'] for d in ts['devModified']], ['main.ftu'], ts)
        r = pt._sync_ftu_to_json(self.tmp)
        self.assertIn('main.ftu', r['synced'])
        self.assertIn('devModified', r['syncedDetail'][0]['why'])

    def test_rule3_few_seconds_delta_is_not_synced(self):
        import project_tools as pt
        ftu = self._pack()
        jt = os.path.getmtime(self.src)
        os.utime(ftu, (jt + 5, jt + 5))              # 只新 5 秒 = pack 正常抖动
        before = io.open(self.src, encoding='utf-8').read()
        ts = pt._ui_timestamp_check(self.tmp)
        self.assertEqual(ts['devModified'], [], ts)
        r = pt._sync_ftu_to_json(self.tmp)
        self.assertEqual(r['synced'], [], r)
        self.assertTrue(r['skipped'], r)
        self.assertEqual(io.open(self.src, encoding='utf-8').read(), before,
                         '规则③：ftu 只新几秒 → 不做 ftu→json')

    def test_rule3b_json_newer_is_not_synced(self):
        import project_tools as pt
        ftu = self._pack()
        t = os.path.getmtime(ftu) + 300
        os.utime(self.src, (t, t))                   # json 比 ftu 新 → stale，不是 ftu→json 的场景
        ts = pt._ui_timestamp_check(self.tmp)
        self.assertTrue(ts['stale'], ts)
        r = pt._sync_ftu_to_json(self.tmp)
        self.assertEqual(r['synced'], [], r)
        self.assertTrue(r['skipped'], r)

    def test_threshold_is_minute_level(self):
        import inspect
        import project_tools as pt
        d = inspect.signature(pt._ui_timestamp_check).parameters['dev_threshold'].default
        self.assertGreaterEqual(d, 60, 'ftu→json 的触发阈值必须是「分钟级」(≥60s)，当前 %s' % d)

    def test_rule1_broken_ftu_reports_error_to_user(self):
        """异常 ftu（不是合法 ftu/已损坏）→ **必须报错并告知用户**（09:14），不静默跳过。"""
        import project_tools as pt
        os.remove(self.src)                       # 「只有 ftu 没有 json」场景
        with open(os.path.join(self.tmp, 'ui', 'main.ftu'), 'wb') as f:
            f.write(b'ZKSR')                      # 占位/损坏的 ftu
        ts = pt._ui_timestamp_check(self.tmp)
        self.assertEqual(ts['ftuOnly'], ['main.ftu'], ts)
        r = pt._sync_ftu_to_json(self.tmp)
        self.assertTrue(r['failed'], r)
        self.assertEqual(r['synced'], [], r)
        blob = json.dumps(r, ensure_ascii=False)
        self.assertIn('main.ftu', blob)
        self.assertIn('hint', blob)               # 必须带「怎么办」的指引
        # 端到端：build_ui_flow 在 ①.5 就应明确失败（不会走到 fun install/build）
        b = U.jcall('flythings_build_ui_flow',
                       U.bypass_gates({'project_root': self.tmp, 'with_launch': False}))
        self.assertFalse(b['ok'], b)
        self.assertIn('main.ftu', json.dumps(b, ensure_ascii=False))


class TestLayoutAudit(unittest.TestCase):
    """`flythings_layout_audit`：从 json 静态判定层叠/遮挡/触摸穿透（不靠截图）。"""

    def setUp(self):
        self.tmp = U.project()

    def tearDown(self):
        U.cleanup(self.tmp)

    def _page(self, obj, name='main.json'):
        U.write(os.path.join(self.tmp, 'ui', name), json.dumps(obj, ensure_ascii=False))

    def _base(self, **kw):
        d = {'id': 0, 'resolution': {'width': 1000, 'height': 600},
             'position': {'left': 0, 'top': 0, 'width': 1000, 'height': 600}}
        d.update(kw)
        return d

    def test_clean_layout_has_no_findings(self):
        self._page(self._base(**{
            'window__1': {'id': 1, 'position': {'left': 0, 'top': 0, 'width': 1000, 'height': 600},
                          'button__2': {'id': 2, 'caption': 'OK', 'touchable': True,
                                        'position': {'left': 10, 'top': 10, 'width': 100, 'height': 40}}}}))
        r = U.jcall('flythings_layout_audit', {'project_root': self.tmp})
        self.assertTrue(r['ok'], r)
        self.assertEqual(r['summary']['findings'], 0, r)

    def test_overlap_and_touch_steal_detected(self):
        # 同层：遮罩（更早定义、touchable）完整覆盖按钮 → 触摸被抢
        self._page(self._base(**{
            'window__1': {'id': 1, 'position': {'left': 0, 'top': 0, 'width': 1000, 'height': 600},
                          'button__2': {'id': 2, 'caption': 'mask', 'touchable': True, 'touchPass': False,
                                        'position': {'left': 0, 'top': 0, 'width': 1000, 'height': 600}},
                          'button__3': {'id': 3, 'caption': 'OK', 'touchable': True,
                                        'position': {'left': 100, 'top': 100, 'width': 120, 'height': 48}}}}))
        r = U.jcall('flythings_layout_audit', {'project_root': self.tmp})
        kinds = [f['kind'] for p in r['pages'] for f in p['findings']]
        self.assertIn('touch_steal', kinds, r)
        self.assertIn('fullscreen_layer', kinds, r)
        f0 = [f for p in r['pages'] for f in p['findings'] if f['kind'] == 'touch_steal'][0]
        self.assertIn('button__3', f0['control'])
        self.assertIn('button__2', f0['by'])
        self.assertTrue(f0['fix'])

    def test_missing_touch_pass_flagged(self):
        # 装饰件（touchable:false、无 touchPass）压住可交互控件 → 提示补 touchPass
        self._page(self._base(**{
            'window__1': {'id': 1, 'position': {'left': 0, 'top': 0, 'width': 1000, 'height': 600},
                          'textview__2': {'id': 2, 'caption': 'deco', 'touchable': False,
                                          'position': {'left': 0, 'top': 0, 'width': 400, 'height': 40}},
                          'button__3': {'id': 3, 'caption': 'OK', 'touchable': True,
                                        'position': {'left': 10, 'top': 10, 'width': 120, 'height': 48}}}}))
        r = U.jcall('flythings_layout_audit', {'project_root': self.tmp})
        kinds = [f['kind'] for p in r['pages'] for f in p['findings']]
        self.assertIn('pass_through_missing', kinds, r)

    def test_page_filter(self):
        self._page(self._base(**{'button__1': {'id': 1, 'caption': 'a', 'touchable': True,
                                               'position': {'left': 0, 'top': 0, 'width': 50, 'height': 50}}}), 'a.json')
        self._page(self._base(**{'button__1': {'id': 1, 'caption': 'b', 'touchable': True,
                                               'position': {'left': 0, 'top': 0, 'width': 50, 'height': 50}}}), 'b.json')
        r = U.jcall('flythings_layout_audit', {'project_root': self.tmp, 'page': 'b.json'})
        self.assertTrue(r['ok'], r)
        self.assertEqual([p['file'] for p in r['pages']], ['b.json'], r)


if __name__ == '__main__':
    unittest.main(verbosity=2)
