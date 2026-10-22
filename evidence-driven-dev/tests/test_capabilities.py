"""Plugin inventory must complement repo-only skills/list without treating cache as installation."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import capabilities


class PluginDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = Path(self.tmp.name)
        self.package = self.cache / 'curated' / 'superpowers' / '6.4.2'
        manifest = self.package / '.codex-plugin/plugin.json'
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({'name': 'superpowers', 'version': '6.4.2', 'skills': './skills/'}), encoding='utf-8')
        skill = self.package / 'skills/systematic-debugging/SKILL.md'
        skill.parent.mkdir(parents=True)
        skill.write_text('---\nname: systematic-debugging\ndescription: Diagnose bugs\n---\n# Debugging\n', encoding='utf-8')
        self.plugin = {'name': 'superpowers', 'pluginId': 'superpowers@curated', 'marketplaceName': 'curated',
                       'version': '6.4.2', 'installed': True, 'enabled': True}

    def discover(self):
        return capabilities.plugin_skills({'installed': [self.plugin]}, self.cache)

    def test_enabled_installed_plugin_resolves_declared_skills(self):
        items, errors = self.discover()
        self.assertEqual(errors, [])
        self.assertEqual([x['name'] for x in items], ['superpowers:systematic-debugging'])
        self.assertTrue(items[0]['enabled'] and items[0]['readable'])
        self.assertEqual(items[0]['version'], '6.4.2')
        self.assertTrue(Path(items[0]['path']).is_file())
        self.assertEqual(items[0]['discovery'], 'installed-plugin-manifest')

    def test_cache_alone_or_disabled_plugin_is_not_available(self):
        self.assertEqual(capabilities.plugin_skills({'installed': []}, self.cache)[0], [])
        for key in ('installed', 'enabled'):
            with self.subTest(key=key):
                self.plugin[key] = False
                self.assertEqual(self.discover()[0], [])
                self.plugin[key] = True

    def test_wrong_version_is_not_silently_replaced_by_cached_version(self):
        self.plugin['version'] = '9.9.9'
        items, errors = self.discover()
        self.assertEqual(items, [])
        self.assertTrue(errors)

    def test_manifest_path_traversal_is_diagnostic(self):
        p = self.package / '.codex-plugin/plugin.json'
        p.write_text(json.dumps({'name': 'superpowers', 'version': '6.4.2', 'skills': '../../../outside'}), encoding='utf-8')
        items, errors = self.discover()
        self.assertEqual(items, [])
        self.assertTrue(errors)

    def test_invalid_metadata_and_wrong_json_types_are_diagnostic(self):
        self.plugin['marketplaceName'] = '../escape'
        items, errors = self.discover()
        self.assertEqual(items, [])
        self.assertTrue(errors)
        items, errors = capabilities.plugin_skills([], self.cache)
        self.assertEqual(items, [])
        self.assertTrue(errors)

if __name__ == '__main__':
    unittest.main()
