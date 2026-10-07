"""Safety and end-to-end checks for the original-media import pipeline."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import build_media
import build_playback


class ImportSafetyTests(unittest.TestCase):
    def test_capture_dates_are_valid_and_do_not_use_copy_time(self):
        self.assertEqual(build_media.validated_date('VID_20251021_191323'), '2025-10-21')
        self.assertEqual(build_media.validated_date('2025-08-07 22-56-06'), '2025-08-07')
        self.assertEqual(build_media.validated_date('2024:02:29 10:12:20'), '2024-02-29')
        self.assertIsNone(build_media.validated_date('2025-02-29'))
        self.assertIsNone(build_media.validated_date('a saved memory'))

    def test_copy_never_clobbers_colliding_names(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, destination = root / 'source.jpg', root / 'existing.jpg'
            source.write_bytes(b'new original bytes')
            destination.write_bytes(b'old original bytes')
            digest = build_media.sha256_file(source)
            chosen = build_media.safe_destination(destination, digest)
            self.assertNotEqual(chosen, destination)
            build_media.copy_verified(source, chosen, digest)
            self.assertEqual(destination.read_bytes(), b'old original bytes')
            self.assertEqual(source.read_bytes(), chosen.read_bytes())
            self.assertFalse(build_media.copy_verified(source, chosen, digest))
            with self.assertRaises(RuntimeError):
                build_media.copy_verified(source, destination, digest)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg/ffprobe required')
    def test_import_deduplicates_and_refresh_is_idempotent(self):
        original_root = build_media.ROOT
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            repository, source = root / 'repo', root / 'source'
            (repository / 'images').mkdir(parents=True)
            (repository / 'media').mkdir()
            (source / 'album').mkdir(parents=True)
            existing = repository / 'images' / 'IMG_20250101_120000.jpg'
            new_photo = source / 'album' / 'IMG_20250202_120000.jpg'
            video = source / 'album' / 'VID_20250303_120000.mp4'
            for path, color in ((existing, 'pink'), (new_photo, 'blue')):
                subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', f'color=c={color}:s=64x48',
                                '-frames:v', '1', '-y', str(path)], check=True, capture_output=True)
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=green:s=64x48:d=0.5',
                            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-y', str(video)], check=True, capture_output=True)
            shutil.copy2(existing, source / 'different filename.jpg')
            shutil.copy2(new_photo, source / 'same content again.jpg')
            before_hash = build_media.sha256_file(existing)
            try:
                build_media.ROOT = repository
                with contextlib.redirect_stdout(io.StringIO()):
                    build_media.main(['--source', str(source), '--workers', '2'])
                library = json.loads((repository / 'media/library.json').read_text(encoding='utf-8'))
                report = json.loads((repository / 'media/import-report.json').read_text(encoding='utf-8'))
                self.assertEqual(len(library['items']), 3)
                self.assertEqual(report['summary']['sourceFiles'], 4)
                self.assertEqual(report['summary']['copiedFiles'], 2)
                self.assertTrue(report['allSourceContentRepresented'])
                self.assertEqual(build_media.sha256_file(existing), before_hash)
                for item in library['items']:
                    self.assertTrue((repository / item['src']).is_file())
                    self.assertTrue((repository / item['thumbnail']).is_file())
                    self.assertEqual((item['previewWidth'], item['previewHeight']), (64, 48))
                rotated = {'thumbnail': library['items'][0]['thumbnail'], 'width': 48, 'height': 64}
                build_media.normalize_item_dimensions(rotated, repository)
                self.assertEqual((rotated['width'], rotated['height']), (64, 48))
                imported_hashes = {item['sha256'] for item in library['items']}
                with contextlib.redirect_stdout(io.StringIO()):
                    build_media.main(['--source', str(source), '--workers', '2'])
                second = json.loads((repository / 'media/import-report.json').read_text(encoding='utf-8'))
                self.assertEqual(second['summary']['copiedFiles'], 0)
                self.assertEqual(second['summary']['preExistingFilesVerifiedUnchanged'], 3)
                with contextlib.redirect_stdout(io.StringIO()):
                    build_media.main(['--workers', '2'])
                rebuilt = json.loads((repository / 'media/library.json').read_text(encoding='utf-8'))
                self.assertEqual({item['sha256'] for item in rebuilt['items']}, imported_hashes)
                self.assertEqual(build_media.sha256_file(existing), before_hash)
                self.assertEqual(len(list(source.rglob('*.*'))), 4)
            finally:
                build_media.ROOT = original_root

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg/ffprobe required')
    def test_unsupported_video_gets_a_playable_copy_without_changing_original(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'videos').mkdir()
            source = root / 'videos' / 'original.mov'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=pink:s=96x64:d=0.5',
                            '-c:v', 'qtrle', '-pix_fmt', 'rgb24', '-y', str(source)], check=True, capture_output=True)
            digest = build_media.sha256_file(source)
            item = {'src': 'videos/original.mov', 'type': 'video', 'sha256': digest}
            with contextlib.redirect_stdout(io.StringIO()):
                report = build_playback.prepare_playback([item], root)
            self.assertFalse(report['failures'])
            self.assertEqual(len(report['created']), 1)
            self.assertNotEqual(item['playbackSrc'], item['src'])
            self.assertEqual(build_media.sha256_file(source), digest)
            output = build_playback.video_probe(root / item['playbackSrc'])
            stream = next(stream for stream in output['streams'] if stream['codec_type'] == 'video')
            self.assertEqual(stream['codec_name'], 'h264')
            self.assertEqual(stream['pix_fmt'], 'yuv420p')
            with contextlib.redirect_stdout(io.StringIO()):
                rerun = build_playback.prepare_playback([item], root)
            self.assertEqual(len(rerun['reused']), 1)
            self.assertFalse(rerun['created'])


if __name__ == '__main__':
    unittest.main()
