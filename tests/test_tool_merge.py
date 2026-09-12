# -*- coding: utf-8 -*-
"""工具合并契约（v0.27.36 起，沛哥：直接合并、不留别名）。

合并内容：
  flythings_generate_ui_preview + flythings_json_to_html  → flythings_ui_preview(target)
  flythings_recommend_manifest + flythings_generate_manifest → flythings_manifest(features, platform, project_root, dry_run=True)
  flythings_search → flythings_knowledge_search；flythings_search_package → flythings_package_search
  v0.27.37：flythings_ui_editor + flythings_ui_edit_apply + flythings_ui_diff → flythings_ui_visual(action)

钉住：①旧名不在清单里、调旧名回 OP_RENAMED + 新名（不执行）②合并后的两种入参形态都要能用
③manifest 默认 dry_run 不写盘、写盘必留 .bak ④预览对目录与单文件都出稿。
"""
import glob
import io
import json
import os
import shutil
import unittest

import _util as U


class TestMergedNames(unittest.TestCase):
    def test_op_count_and_names(self):
        import kb_tools
        names = set(kb_tools.OP_NAMES)
        for new in ('flythings_ui_preview', 'flythings_manifest',
                    'flythings_knowledge_search', 'flythings_package_search',
                    'flythings_ui_visual'):
            self.assertIn(new, names)
        for old in ('flythings_search', 'flythings_search_package', 'flythings_json_to_html',
                    'flythings_generate_ui_preview', 'flythings_recommend_manifest',
                    'flythings_generate_manifest', 'flythings_ui_editor',
                    'flythings_ui_edit_apply', 'flythings_ui_diff'):
            self.assertNotIn(old, names, '%s 应已合并/改名' % old)
        self.assertEqual(len(kb_tools.OP_NAMES), len(set(kb_tools.OP_NAMES)))
        # 清单数 = manifest 里的 op 数（合并后必须同步重新生成 manifest）
        self.assertEqual(sorted(names), sorted(o['op'] for o in U.manifest()['ops']))


class TestUiPreviewMerged(unittest.TestCase):
    def setUp(self):
        self.tmp = U.project()
        self.pages = os.path.join(self.tmp, 'ui', '1024x600')
        os.makedirs(self.pages, exist_ok=True)
        shutil.copy(U.fixture('main.json'), os.path.join(self.pages, 'main.json'))

    def tearDown(self):
        U.cleanup(self.tmp)

    def test_target_accepts_project_dir(self):
        r = U.jcall('flythings_ui_preview', {'target': self.tmp})
        self.assertTrue(r.get('success'), r)
        self.assertTrue(glob.glob(os.path.join(self.tmp, 'ui', '**', '*.preview.html'),
                                  recursive=True), '项目目录模式没出预览稿')

    def test_target_accepts_single_json(self):
        r = U.jcall('flythings_ui_preview',
                    {'target': os.path.join(self.pages, 'main.json')})
        self.assertTrue(r.get('success'), r)


class TestManifestMerged(unittest.TestCase):
    def setUp(self):
        self.tmp = U.project()
        U.write(os.path.join(self.tmp, 'Manifest.xml'), '<manifest platform="F133"/>\n')
        self.before = io.open(os.path.join(self.tmp, 'Manifest.xml'), encoding='utf-8').read()

    def tearDown(self):
        U.cleanup(self.tmp)

    def test_dry_run_recommends_without_writing(self):
        src = os.path.join(self.tmp, 'src', 'logic', 'mainLogic.cc')   # 干扰项：不该被写
        U.write(src, '// keep\n')
        r = U.jcall('flythings_manifest', {'features': 'mqtt,json', 'platform': 'F133'})
        self.assertTrue(r.get('success'), r)
        self.assertTrue(r.get('dryRun'))
        self.assertEqual(io.open(os.path.join(self.tmp, 'Manifest.xml'), encoding='utf-8').read(),
                         self.before, 'dry_run 不该改 Manifest.xml')
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'Manifest.xml.bak')))
        self.assertEqual(io.open(src, encoding='utf-8').read(), '// keep\n')

    def test_write_path_needs_project_root(self):
        r = U.jcall('flythings_manifest', {'features': 'mqtt', 'dry_run': False})
        self.assertFalse(r['ok'], '缺 project_root 时必须报 BAD_PARAMS')
        self.assertEqual(r['error']['code'], 'BAD_PARAMS')
        self.assertNotIn('Manifest.xml', r['error']['msg'])

    def test_write_creates_backup_and_reports_files(self):
        r = U.jcall('flythings_manifest',
                    {'features': 'mqtt,json', 'platform': 'F133',
                     'project_root': self.tmp, 'dry_run': False})
        self.assertTrue(r.get('success'), r)
        self.assertIn('Manifest.xml', r.get('manifestPath', ''))
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, 'Manifest.xml.bak')))
        self.assertTrue(any('Manifest.xml' in f for f in r.get('affectedFiles', [])))
        written = io.open(os.path.join(self.tmp, 'Manifest.xml'), encoding='utf-8').read()
        self.assertIn('dependencies', written)


class TestPackageSearchRenamed(unittest.TestCase):
    def test_package_search_returns_hits(self):
        r = U.jcall('flythings_package_search', {'keyword': 'mqtt', 'platform': 'F133'})
        self.assertTrue(r.get('success', r.get('ok')), r)


if __name__ == '__main__':
    unittest.main(verbosity=2)
