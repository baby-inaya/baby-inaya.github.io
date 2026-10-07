"""Verify that a Pages snapshot is complete, bounded, and non-destructive."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import prepare_pages


class PagesExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for relative in ('style.css', 'script.js', '.gitignore', 'README.md',
                         'media/ADDING-MEMORIES.md', 'media/preview-unavailable.svg',
                         'scripts/helper.py', 'illustration.svg'):
            self.put(relative, b'support')
        self.put('index.html', b'<img src="thumbnails/cover.jpg"><script src="media/library.js"></script>')
        self.put('thumbnails/cover.jpg', b'cover')

    def put(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def item(self, name, size, playback_size=None):
        source = f'images/{name}.jpg' if playback_size is None else f'videos/{name}.mov'
        thumbnail = f'thumbnails/{name}.jpg'
        self.put(source, bytes([size % 255]) * size)
        self.put(thumbnail, b'preview')
        item = {'id': name, 'type': 'image' if playback_size is None else 'video',
                'src': source, 'thumbnail': thumbnail, 'title': name}
        if playback_size is not None:
            item['playbackSrc'] = f'media/playback/{name}.mp4'
            self.put(item['playbackSrc'], b'v' * playback_size)
        return item

    def catalog(self, items):
        self.put('media/library.json', json.dumps({'generatedAt': 'original', 'items': items}).encode())

    def test_smallest_complete_packages_selected_and_catalog_order_preserved(self):
        large = self.item('large', 7000)
        middle = self.item('middle', 900, 1000)
        small = self.item('small', 1000)
        self.catalog([large, middle, small])
        base = sum(prepare_pages.base_files(self.root).values())
        plan = prepare_pages.make_plan(self.root, budget=base + 3000 + 10000, reserve=10000)
        self.assertEqual([i['id'] for i in plan['library']['items']], ['middle', 'small'])
        self.assertIn(middle['src'], plan['files'])
        self.assertIn(middle['playbackSrc'], plan['files'])
        self.assertIn(middle['thumbnail'], plan['files'])
        self.assertNotIn(large['src'], plan['files'])
        self.assertIn('thumbnails/cover.jpg', plan['files'])
        self.assertLessEqual(plan['report']['totalBytes'], plan['report']['budgetBytes'])

    def test_held_oversized_and_missing_packages_are_excluded(self):
        held = self.item('held', 12)
        held['src'] = 'lage_files/held.mp4'
        self.put(held['src'], b'held')
        large = self.item('large', 500)
        with (self.root / large['src']).open('r+b') as stream:
            stream.truncate(prepare_pages.MAX_FILE_BYTES + 1)
        missing = self.item('missing', 4)
        (self.root / missing['thumbnail']).unlink()
        valid = self.item('valid', 4)
        self.catalog([held, large, missing, valid])
        plan = prepare_pages.make_plan(self.root, budget=100000, reserve=10000)
        self.assertEqual([i['id'] for i in plan['library']['items']], ['valid'])
        self.assertEqual(len(plan['report']['excluded']), 3)
        reasons = ' '.join(row['reason'] for row in plan['report']['excluded'])
        self.assertIn('lage_files', reasons)
        self.assertIn('100 MiB', reasons)
        self.assertIn('Missing dependency', reasons)

    def test_unsafe_paths_and_git_internals_are_rejected(self):
        for relative in ('../private.jpg', '/absolute.jpg', 'C:/private.jpg', '.git/config', 'a\\b.jpg'):
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                prepare_pages.source_path(self.root, relative)
        item = self.item('safe', 8)
        item['src'] = '../private.jpg'
        self.catalog([item])
        with self.assertRaises(ValueError):
            prepare_pages.make_plan(self.root)

    def test_output_requires_new_ignored_inside_repository_directory(self):
        for destination in (self.root, self.root.parent / 'outside', self.root / '.git/new'):
            with self.subTest(destination=destination), self.assertRaises(ValueError):
                prepare_pages.validate_output(self.root, destination)
        (self.root / 'existing').mkdir()
        with self.assertRaisesRegex(ValueError, 'already exists'):
            prepare_pages.validate_output(self.root, self.root / 'existing')
        with patch('prepare_pages.subprocess.run') as command:
            command.return_value.returncode = 1
            with self.assertRaisesRegex(ValueError, 'ignored by Git'):
                prepare_pages.validate_output(self.root, self.root / 'unignored')
            command.return_value.returncode = 0
            self.assertEqual(prepare_pages.validate_output(self.root, 'qa-output/new'), self.root / 'qa-output/new')

    def test_budget_cannot_exceed_pages_limit(self):
        with self.assertRaisesRegex(ValueError, '1 GB site limit'):
            prepare_pages.make_plan(self.root, budget=1_000_000_001)

    def test_export_matches_manifest_and_does_not_change_originals(self):
        item = self.item('film', 400, 200)
        self.catalog([item])
        before = {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        plan = prepare_pages.make_plan(self.root, budget=100000, reserve=20000)
        with patch('prepare_pages.subprocess.run') as command:
            command.return_value.returncode = 0
            output = prepare_pages.export_plan(plan, self.root / 'qa-output/pages')
        for relative, data in before.items():
            self.assertEqual((self.root / relative).read_bytes(), data)
        report = json.loads((output / 'media/pages-selection.json').read_text())
        actual = sum(path.stat().st_size for path in output.rglob('*') if path.is_file())
        self.assertEqual(actual, report['totalBytes'])
        self.assertLessEqual(actual, report['budgetBytes'])
        self.assertTrue((output / '.nojekyll').is_file())
        for row in report['files'] + report['generatedFiles']:
            self.assertEqual((output / row['path']).stat().st_size, row['bytes'])
        for key in ('src', 'thumbnail', 'playbackSrc'):
            self.assertEqual((output / item[key]).read_bytes(), (self.root / item[key]).read_bytes())
        javascript = (output / 'media/library.js').read_text()
        encoded = javascript.split('window.MEDIA_LIBRARY = ', 1)[1].rsplit(';', 1)[0]
        self.assertEqual(json.loads(encoded), json.loads((output / 'media/library.json').read_text()))


if __name__ == '__main__':
    unittest.main()
