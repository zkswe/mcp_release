# -*- coding: utf-8 -*-
"""工具链能力声明 + json↔ftu 往返契约。

背景：
  - `fui.exe unpack` 在「随仓库分发的 toolchain/fui.exe」里是空壳（调用回通用错误、不产文件），
    而开发机上的 C:\\zkswe\\fun\\fui.exe 支持：`unpack <in.ftu> [out.json]`。
    project_tools._fui_supports_unpack() 用 `fui.exe help` 探测（help 里有没有 unpack 行），
    工具链据此决定「能否直接编辑 ftu」——探测错了就会要么白报错、要么静默产空文件。
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
        r = U.jcall('flythings_fui_pack', {'json_path': src})
        self.assertTrue(r['ok'], r)
        ftu = os.path.join(self.tmp, 'main.ftu')
        self.assertTrue(os.path.isfile(ftu))
        return ftu

    def _try_unpack(self, ftu, out_json=None):
        """按真实 CLI 形式解包，返回 (rc, 产出的 json 路径或 None)。

        fui unpack 的真实用法（--help 自述）：`unpack <input.ftu> [output.json]`；
        只给 input 时解到同目录同名 json。⚠️ 传目录会 FATAL。
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


if __name__ == '__main__':
    unittest.main(verbosity=2)
