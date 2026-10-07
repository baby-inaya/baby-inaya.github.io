"""Saved deletion and compression choices must survive later imports."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import build_media
from optimize_media import safe_path, restore_rotation, validate_video, video_rotation
from build_playback import video_probe


class OptimizationPolicyTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg required')
    def test_portrait_rotation_repair_preserves_encoded_picture(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'portrait.mp4'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                            'testsrc2=s=96x64:d=0.4', '-c:v', 'libx264', '-y', str(path)],
                           check=True, capture_output=True)
            metadata = video_probe(path)
            metadata['streams'][0]['side_data_list'] = [{'rotation': -90}]
            def packet_hash():
                return subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path),
                                       '-map', '0:v:0', '-c', 'copy', '-f', 'streamhash', '-'],
                                      check=True, capture_output=True).stdout
            before = packet_hash()
            with self.assertRaisesRegex(ValueError, 'orientation'):
                validate_video(path, metadata, preserve_dimensions=True)
            self.assertTrue(restore_rotation(path, metadata))
            self.assertEqual(video_rotation(video_probe(path)), 270)
            self.assertEqual(packet_hash(), before)
            validate_video(path, metadata, preserve_dimensions=True)
            self.assertFalse(restore_rotation(path, metadata))

    def test_paths_cannot_escape_repo_or_enter_git(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.assertEqual(safe_path('videos/clip.mp4', root), root / 'videos/clip.mp4')
            with self.assertRaises(ValueError): safe_path('../outside.mp4', root)
            with self.assertRaises(ValueError): safe_path('.git/objects/object', root)

    @unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg required')
    def test_size_limit_and_saved_replacement_survive_repeat_import(self):
        previous_root = build_media.ROOT
        with tempfile.TemporaryDirectory() as folder:
            parent = Path(folder)
            root, source = parent / 'repo', parent / 'source'
            (root / 'videos').mkdir(parents=True)
            (root / 'media').mkdir()
            (root / 'thumbnails').mkdir()
            source.mkdir()
            original, replacement = source / 'original.mp4', root / 'videos/kept.mp4'
            for path, color in [(original, 'red'), (replacement, 'blue')]:
                subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', f'color=c={color}:s=64x48:d=0.4',
                                '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-y', str(path)], check=True, capture_output=True)
            original_hash = build_media.sha256_file(original)
            replacement_hash = build_media.sha256_file(replacement)
            limit = 5000
            (source / 'too-big.mp4').write_bytes(b'x' * (limit + 1))
            item = {'id': 'stable-favorite-id', 'src': 'videos/kept.mp4', 'type': 'video',
                    'sha256': replacement_hash, 'title': 'Our saved caption', 'date': '2025-07-12',
                    'album': 'Our album', 'filename': 'original.mp4'}
            build_media.atomic_json(root / 'media/optimization-state.json', {
                'maxImportBytes': limit, 'replacements': {original_hash: {'path': item['src'], 'item': item}}})
            try:
                build_media.ROOT = root
                with contextlib.redirect_stdout(io.StringIO()):
                    build_media.main(['--source', str(source), '--skip-playback'])
                library = json.loads((root / 'media/library.json').read_text(encoding='utf-8'))
                report = json.loads((root / 'media/import-report.json').read_text(encoding='utf-8'))
                self.assertEqual(len(library['items']), 1)
                self.assertEqual(library['items'][0]['id'], 'stable-favorite-id')
                self.assertEqual(library['items'][0]['album'], 'Our album')
                self.assertEqual(report['summary']['sourceFilesSkippedBySizeLimit'], 1)
                self.assertEqual(report['summary']['compressedCopiesReused'], 1)
                self.assertEqual(report['summary']['copiedFiles'], 0)
                self.assertFalse(report['allSourceContentRepresented'])
                self.assertTrue(report['allEligibleSourceContentRepresented'])
                self.assertEqual(build_media.sha256_file(original), original_hash)
            finally:
                build_media.ROOT = previous_root


if __name__ == '__main__':
    unittest.main()
