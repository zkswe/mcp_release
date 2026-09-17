# -*- coding: utf-8 -*-
"""依赖/install 诊断契约（v0.27.83）：

为什么要有（事故背景）：
  - 老工程 Manifest 缺 `base-utility` → `fun build` 报的是编译错误
    `fatal error: base/functional.h: No such file or directory`，用户以为是代码问题；
  - `flythings_build_ui_flow` 里 `fun install` 失败**故意不阻断**，但原先只写在 steps 里
    → 顶层返回体没有任何信号，排查被带偏。
钉住三件事：
  ① 代码 / fun 生成的 generated/*.h 引用 base 头文件 + Manifest 未声明 base-utility → 必须报出
     （check_project_deps 的 missingDependencies / validate_project 的 missing_framework_dependency）；
  ② 声明过或已被传递依赖解析到 → 不许报（不制造误报：实测 easyui 会带出 base-utility）；
  ③ build_ui_flow：install 失败要有顶层 warnings（且**不阻断** build）；缺基础头要在 build 前点明。
"""
import json
import os
import shutil
import unittest
from unittest import mock

import _util as U

import package_tools as pkgtools      # _util 已把 MCP 根目录加进 sys.path
import project_tools as pt

MF_NO_BASE = ('<?xml version="1.0" encoding="UTF-8"?>\n'
              '<manifest platform="Z21">\n'
              '    <dependencies enableOnPlatforms="Z21">\n'
              '        <package id="easyui" version="2.6.0"/>\n'
              '    </dependencies>\n'
              '</manifest>\n')
MF_WITH_BASE = MF_NO_BASE.replace(
    '</dependencies>',
    '        <package id="base-utility" version="^10.0.0"/>\n    </dependencies>')
LOGIC_WITH_BASE = '#include <base/functional.h>\n\nvoid onUI_init() {}\n'


def _mk(root, manifest, logic=None, with_ftu=True, lock=None, fun_json=None):
    """造一个最小 FlyThings 工程骨架。"""
    os.makedirs(os.path.join(root, 'src', 'logic'), exist_ok=True)
    os.makedirs(os.path.join(root, 'ui'), exist_ok=True)
    U.write(os.path.join(root, 'Manifest.xml'), manifest)
    U.write(os.path.join(root, 'src', 'Main.cpp'), 'int main() { return 0; }\n')
    if logic is not None:
        U.write(os.path.join(root, 'src', 'logic', 'mainLogic.cc'), logic)
    if with_ftu:
        open(os.path.join(root, 'ui', 'main.ftu'), 'wb').write(b'ZKSR')   # 内容无关，存在即 UI 工程
    if lock:
        U.write(os.path.join(root, '.fun-lock.json'), json.dumps(lock, ensure_ascii=False))
    if fun_json:
        U.write(os.path.join(root, 'fun.json'), json.dumps(fun_json, ensure_ascii=False))
    return root


LOCK_WITH_BASE = {'lockfileVersion': 3, 'dependencies': {'z21': {
    'easyui': {'version': '^2.2.0', 'exactVersion': '2.6.0'},
    'base-utility': {'version': '^10.9.3', 'exactVersion': '10.9.3'}}}}


class TestFrameworkDepCheck(unittest.TestCase):
    """A：依赖体检 —— base 头文件 ↔ base-utility 声明。"""

    def setUp(self):
        self.tmp = U.project()

    def tearDown(self):
        U.cleanup(self.tmp)

    def test_missing_base_utility_reported(self):
        """反例：代码 #include <base/functional.h> 且 Manifest 缺 base-utility → 必须报。"""
        _mk(self.tmp, MF_NO_BASE, logic=LOGIC_WITH_BASE)
        r = U.jcall('flythings_check_project_deps', {'project_root': self.tmp})
        self.assertTrue(r['ok'], r)
        fw = [m for m in r['missingDependencies'] if m.get('kind') == 'framework']
        self.assertTrue(fw, '未报出框架基础依赖缺失: %s' % r['missingDependencies'])
        self.assertIn('base-utility', fw[0]['recommendedPackages'])
        self.assertEqual(fw[0]['include'], 'base/functional.h')
        self.assertIn('add_package', fw[0]['hint'])
        self.assertIn('fun install', fw[0]['hint'])
        # 证据要能指到具体文件
        self.assertEqual(fw[0]['evidence'][0]['file'], 'src/logic/mainLogic.cc')

    def test_validate_project_reports_error(self):
        """validate_project 要给出明确错误项 + 可照做的修复提示。"""
        _mk(self.tmp, MF_NO_BASE, logic=LOGIC_WITH_BASE)
        r = U.jcall('flythings_validate_project', {'project_root': self.tmp})
        hits = [e for e in r.get('errors', []) if e['type'] == 'missing_framework_dependency']
        self.assertTrue(hits, 'validate_project 未报 missing_framework_dependency: %s' % r.get('errors'))
        self.assertIn('base-utility', hits[0]['msg'])
        self.assertIn('base/functional.h', hits[0]['msg'])
        self.assertIn('add_package', hits[0]['hint'])

    def test_declared_base_utility_not_reported(self):
        """正例：Manifest 声明了 base-utility → 不报（哪怕代码引用了 base 头文件）。"""
        _mk(self.tmp, MF_WITH_BASE, logic=LOGIC_WITH_BASE)
        r = U.jcall('flythings_check_project_deps', {'project_root': self.tmp})
        self.assertEqual([m for m in r['missingDependencies'] if m.get('kind') == 'framework'], [])
        v = U.jcall('flythings_validate_project', {'project_root': self.tmp})
        self.assertEqual([e for e in v.get('errors', [])
                          if e['type'] == 'missing_framework_dependency'], [])

    def test_transitively_resolved_not_reported(self):
        """正例：Manifest 没写、但 .fun-lock.json 里已解析到（传递依赖装上）→ 不报。"""
        _mk(self.tmp, MF_NO_BASE, logic=LOGIC_WITH_BASE, lock=LOCK_WITH_BASE)
        r = U.jcall('flythings_check_project_deps', {'project_root': self.tmp})
        self.assertEqual([m for m in r['missingDependencies'] if m.get('kind') == 'framework'], [])
        dep = r['frameworkDeps'][0]
        self.assertTrue(dep['resolved'], dep)
        self.assertIn('.fun-lock.json', dep['resolvedEvidence'])

    def test_ui_project_without_declaration_reported(self):
        """UI 工程（fun 会生成 generated/*.h）即使当前没有 base 引用，缺包也要报。"""
        _mk(self.tmp, MF_NO_BASE, with_ftu=True)
        r = U.jcall('flythings_validate_project', {'project_root': self.tmp})
        self.assertTrue([e for e in r.get('errors', [])
                         if e['type'] == 'missing_framework_dependency'], r.get('errors'))

    def test_bin_project_not_reported(self):
        """可执行工程（fun create --type bin）不适用 → 不报（防误报）。"""
        _mk(self.tmp, MF_NO_BASE, with_ftu=False, fun_json={'type': 'executable'})
        s = pkgtools.framework_dep_status(self.tmp)
        self.assertTrue(s['ok'], s['missing'])

    def test_base_http_client_header_is_not_base_utility(self):
        """`base/` 前缀不是 base-utility 独占：base/http_*.h（base-http-client）不算。"""
        dep = pkgtools.FRAMEWORK_DEPS[0]
        self.assertFalse(pkgtools._is_framework_header(dep, 'base/http_client.h'))
        self.assertFalse(pkgtools._is_framework_header(dep, 'base/json_object.h'))
        self.assertTrue(pkgtools._is_framework_header(dep, 'base/functional.h'))
        self.assertTrue(pkgtools._is_framework_header(dep, 'base/file.h'))

    def test_generated_headers_are_scanned(self):
        """证据来源必须含 fun 生成的 generated/*.h（老工程第一次 build 就靠它）。"""
        _mk(self.tmp, MF_NO_BASE, with_ftu=True)
        g = os.path.join(self.tmp, '.fun', 'z21', 'generated')
        os.makedirs(g, exist_ok=True)
        U.write(os.path.join(g, 'event_dispatcher.h'),
                '// Auto-generated by fun\n#include <base/functional.h>\n')
        s = pkgtools.framework_dep_status(self.tmp)
        self.assertFalse(s['ok'], s)
        self.assertEqual(s['missing'][0]['evidence'][0]['file'],
                         '.fun/z21/generated/event_dispatcher.h')


def _fake_fun(install_ok=True, build_ok=True, build_detail=''):
    def f(cmd, project_dir, **kw):
        if cmd == 'install':
            return {'success': install_ok, 'returncode': 0 if install_ok else 1,
                    'stdout': 'install ok' if install_ok else '',
                    'stderr': '' if install_ok else 'FATAL network unreachable'}
        if cmd == 'build':
            return {'success': build_ok, 'returncode': 0 if build_ok else 1,
                    'stdout': '', 'stderr': '' if build_ok else build_detail}
        return {'success': True, 'stdout': '', 'stderr': ''}
    return f


class TestBuildFlowInstallGuard(unittest.TestCase):
    """B：build_ui_flow 不再静默（install 失败 / 基础头缺包）。"""

    def setUp(self):
        self.tmp = U.project()
        self.mf = os.path.join(self.tmp, 'Manifest.xml')

    def tearDown(self):
        U.cleanup(self.tmp)

    def _flow(self, manifest=MF_WITH_BASE):
        """造一个「时间戳一致（不触发 pack）」的工程 → 跑 build_ui_flow。

        ⚠️ v0.27.84 起 `with_launch` 默认 True（build → 探测 → 推设备）。本文件盯的是
        **install/依赖诊断**，与设备无关，所以显式传 `with_launch=False` 保持离线、
        **不是**把断言放宽（新默认行为由 tests/test_adb_resolve.py 独立钉住）。
        """
        _mk(self.tmp, manifest, with_ftu=True)
        page = os.path.join(self.tmp, 'ui', 'main.json')
        U.write(page, '{}')
        ftu = os.path.join(self.tmp, 'ui', 'main.ftu')
        # ftu 比 json 新 1 秒（<30s）→ 不 pack、也不误判「开发者改过 ftu」
        os.utime(ftu, (os.path.getmtime(page) + 1,) * 2)
        return U.jcall('flythings_build_ui_flow',
                       {'project_root': self.tmp, 'with_launch': False})

    def test_clean_project_has_no_warnings(self):
        """正例（模板新工程口径）：声明齐全 + 流程成功 → 顶层不许有 warnings。"""
        with mock.patch.object(pt, '_run_fun', _fake_fun()):
            r = self._flow(MF_WITH_BASE)
        self.assertTrue(r['ok'], r)
        self.assertFalse(r.get('warnings'), '正常路径出现噪音: %s' % r.get('warnings'))
        self.assertEqual([s for s in r['steps'] if s['step'] == 'check_framework_deps'], [],
                         '正常路径不该加体检 step')

    def test_install_failure_surfaces_warning(self):
        """install 失败 → 顶层 warnings 明说原因（且不阻断 build）。"""
        with mock.patch.object(pt, '_run_fun', _fake_fun(install_ok=False)):
            r = self._flow(MF_WITH_BASE)
        self.assertTrue(r['ok'], r)
        w = ' '.join(r.get('warnings', []))
        self.assertIn('fun install 失败', w)
        self.assertIn('base-utility', w)
        self.assertIn('fun install', w)
        self.assertTrue(any(s['step'] == 'fun build' and s['success'] for s in r['steps']),
                        'install 失败后必须继续 build（离线场景不能全挂）')

    def test_missing_base_utility_preflight(self):
        """缺 base-utility → build 前点明「依赖未装/缺包」，并有 fix。"""
        with mock.patch.object(pt, '_run_fun', _fake_fun()):
            r = self._flow(MF_NO_BASE)
        w = ' '.join(r.get('warnings', []))
        self.assertIn('依赖未装/缺包', w)
        self.assertIn('base-utility', w)
        self.assertIn('add_package', w)
        fw = [s for s in r['steps'] if s['step'] == 'check_framework_deps']
        self.assertTrue(fw and fw[0]['success'] is False, r['steps'])
        self.assertIn('base-utility', fw[0]['fix'])

    def test_build_failure_translated_when_base_header_missing(self):
        """ninja 报 base/functional.h 找不到 → 错误被翻译成「依赖未装/缺包」。"""
        detail = ('fatal error: base/functional.h: No such file or directory\n'
                  'compilation terminated.')
        with mock.patch.object(pt, '_run_fun', _fake_fun(build_ok=False, build_detail=detail)):
            r = self._flow(MF_NO_BASE)
        self.assertFalse(r['ok'], r)
        msg = r['error']['msg'] if isinstance(r['error'], dict) else str(r['error'])
        self.assertIn('依赖未装/缺包', msg)
        self.assertIn('base-utility', msg)
        self.assertTrue(r.get('warnings'), 'build 失败时也要带上 warnings')


if __name__ == '__main__':
    unittest.main(verbosity=2)
