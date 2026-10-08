#!/usr/bin/env python3
"""Safely import original photos/videos and build the static memory library.

Requires Python 3.10+ and ffmpeg/ffprobe on PATH. No Python packages are needed.
Run: python scripts/build_media.py --source "C:\\Users\\User\\Videos"
Later: put originals in images/ or videos/ and run python scripts/build_media.py
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import time

PHOTO_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.heic', '.heif', '.avif', '.bmp', '.tif', '.tiff'}
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.m4v', '.avi', '.mkv', '.webm', '.3gp', '.mts', '.m2ts', '.mpeg', '.mpg'}
MEDIA_EXTENSIONS = PHOTO_EXTENSIONS | VIDEO_EXTENSIONS
ROOT = Path(__file__).resolve().parent.parent
CHUNK_SIZE = 8 * 1024 * 1024


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def media_files(folder: Path):
    """List originals only. Never follow symlink directories or generated assets."""
    if not folder.is_dir():
        return []
    found = []
    for directory, dirs, files in os.walk(folder, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in {'.git', 'node_modules', 'thumbnails', '.cache'}
                         and not (Path(directory) / d).is_symlink())
        for name in sorted(files):
            path = Path(directory) / name
            if path.suffix.lower() in MEDIA_EXTENSIONS and not path.is_symlink():
                found.append(path)
    return found


def sha256_file(path: Path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(CHUNK_SIZE), b''):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def safe_destination(destination: Path, digest: str):
    """Keep both different files when names collide, without overwriting either."""
    if not destination.exists():
        return destination
    if destination.is_file() and sha256_file(destination) == digest:
        return destination
    stem, suffix = destination.stem, destination.suffix
    for width in (12, 20, 32, 64):
        candidate = destination.with_name(f'{stem}--{digest[:width]}{suffix}')
        if not candidate.exists() or (candidate.is_file() and sha256_file(candidate) == digest):
            return candidate
    raise RuntimeError(f'Cannot create a safe unique path for {destination}')


def copy_verified(source: Path, destination: Path, expected_hash: str):
    """Copy with exclusive creation, verify stored bytes, retain source timestamps."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if sha256_file(destination) == expected_hash:
            return False
        raise RuntimeError(f'Refusing to overwrite {destination}')
    temporary = destination.with_name(destination.name + '.importing')
    if temporary.exists():
        # A stopped run may leave a partial file; choose a new temporary name.
        temporary = destination.with_name(destination.name + f'.{time.time_ns()}.importing')
    source_stat = source.stat()
    try:
        with source.open('rb') as reader, temporary.open('xb') as writer:
            shutil.copyfileobj(reader, writer, CHUNK_SIZE)
            writer.flush()
            os.fsync(writer.fileno())
        if sha256_file(temporary) != expected_hash:
            raise RuntimeError(f'Copy verification failed or source changed: {source}')
        if source.stat().st_size != source_stat.st_size or source.stat().st_mtime_ns != source_stat.st_mtime_ns:
            raise RuntimeError(f'Source changed while importing: {source}')
        shutil.copystat(source, temporary)
        # Windows rename never overwrites an existing destination.
        if destination.exists():
            raise RuntimeError(f'Destination appeared during import: {destination}')
        temporary.rename(destination)
        return True
    except BaseException:
        # Keep partial files for diagnosis; they never enter the media catalog.
        raise


def validated_date(value):
    if not value:
        return None
    value = str(value)
    match = re.search(r'(?<!\d)(20\d{2})[-_:]?(0[1-9]|1[0-2])[-_:]?([0-2]\d|3[01])(?!\d)', value)
    if not match:
        # Compact dates are normally followed by an underscore or a time.
        match = re.search(r'(?<!\d)(20\d{2})(0[1-9]|1[0-2])([0-2]\d|3[01])', value)
    if match:
        try:
            return datetime(*(int(part) for part in match.groups())).date().isoformat()
        except ValueError:
            pass
    return None


def jpeg_capture_date(path: Path):
    """Read EXIF DateTimeOriginal without a third-party imaging dependency."""
    if path.suffix.lower() not in {'.jpg', '.jpeg'}:
        return None
    try:
        with path.open('rb') as stream:
            if stream.read(2) != b'\xff\xd8':
                return None
            for _ in range(100):
                marker = stream.read(2)
                if len(marker) != 2 or marker[0] != 255 or marker[1] in (0xda, 0xd9):
                    break
                length_raw = stream.read(2)
                if len(length_raw) != 2:
                    break
                length = struct.unpack('>H', length_raw)[0] - 2
                block = stream.read(length)
                if marker == b'\xff\xe1' and block.startswith(b'Exif\x00\x00'):
                    data = block[6:]
                    endian = '<' if data[:2] == b'II' else '>'
                    def u16(offset): return struct.unpack_from(endian + 'H', data, offset)[0]
                    def u32(offset): return struct.unpack_from(endian + 'I', data, offset)[0]
                    def entries(offset):
                        for index in range(u16(offset)):
                            start = offset + 2 + index * 12
                            yield u16(start), u16(start + 2), u32(start + 4), u32(start + 8)
                    fallback = None
                    exif_offset = None
                    for tag, kind, count, offset in entries(u32(4)):
                        if tag == 0x8769: exif_offset = offset
                        if tag == 0x0132 and kind == 2:
                            fallback = validated_date(data[offset:offset + count].decode('ascii', errors='ignore'))
                    if exif_offset:
                        for tag, kind, count, offset in entries(exif_offset):
                            if tag in (0x9003, 0x9004) and kind == 2:
                                date = validated_date(data[offset:offset + count].decode('ascii', errors='ignore'))
                                if date: return date
                    return fallback
    except (OSError, ValueError, struct.error, IndexError):
        pass
    return None


def jpeg_dimensions(path: Path):
    """Read stored preview dimensions to account for camera EXIF rotation."""
    try:
        with path.open('rb') as stream:
            if stream.read(2) != b'\xff\xd8':
                return None
            while True:
                marker = stream.read(2)
                if len(marker) != 2 or marker[0] != 255 or marker[1] in (0xda, 0xd9):
                    return None
                length_raw = stream.read(2)
                if len(length_raw) != 2:
                    return None
                length = struct.unpack('>H', length_raw)[0] - 2
                if marker[1] in {0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf}:
                    _, height, width = struct.unpack('>BHH', stream.read(5))
                    return width, height
                stream.seek(length, 1)
    except (OSError, ValueError, struct.error):
        return None


def normalize_item_dimensions(item, root=ROOT):
    dimensions = jpeg_dimensions(root / item.get('thumbnail', ''))
    if dimensions:
        item['previewWidth'], item['previewHeight'] = dimensions
        width, height = item.get('width'), item.get('height')
        if width and height and (width > height) != (dimensions[0] > dimensions[1]):
            item['width'], item['height'] = height, width
    return item


def probe(path: Path):
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)],
                            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=90)
    if result.returncode:
        raise RuntimeError(result.stderr.strip()[-800:] or 'ffprobe could not read this file')
    return json.loads(result.stdout)


def friendly_album(relative: str):
    parent = Path(relative).parent.name
    known = {'inaya mahanoor': 'Everyday moments', 'inaya prom dress': 'A special dress',
             'military meuseum': 'Military museum', '202602__': 'A special dress',
             'room e tripod diye kora': 'At home', 'from desktop': 'From the desktop',
             'pp export': 'Edited memories', 's26': 'Phone memories', "tamanna's phone": "Tamanna’s phone",
             'desktop': 'Desktop recordings', 'adobe audition 2024': 'Audition recordings'}
    if not parent or parent.lower() in {'images', 'videos', 'imported'}:
        return 'Everyday moments'
    return known.get(parent.lower(), parent.replace('_', ' ').replace('-', ' ').strip().capitalize())


def friendly_title(path: Path, date):
    stem = path.stem
    if re.match(r'^(IMG|VID|PXL|DSC|DSCF|DSCN|MOV)[_ -]?\d', stem, re.I) or re.match(r'^20\d{2}[-_]?[01]\d', stem):
        if date:
            captured = datetime.fromisoformat(date)
            return f'{captured.strftime("%B")} {captured.day}, {captured.year}'
        return 'A saved moment'
    return re.sub(r'\s+', ' ', stem.replace('_', ' ')).strip()


def generate_item(path, digest, provenance, old_item, force=False):
    relative = path.relative_to(ROOT).as_posix()
    kind = 'image' if path.suffix.lower() in PHOTO_EXTENSIONS else 'video'
    thumbnail_relative = old_item.get('thumbnail') if old_item and old_item.get('sha256') == digest else None
    thumbnail_relative = thumbnail_relative or f'thumbnails/{digest[:24]}.jpg'
    thumbnail = ROOT / thumbnail_relative
    if old_item and old_item.get('sha256') == digest and thumbnail.is_file() and not force:
        item = dict(old_item)
        item['src'] = relative
        return normalize_item_dimensions(item, ROOT), None
    warning = None
    metadata = {}
    try:
        metadata = probe(path)
    except Exception as error:
        warning = f'{relative}: metadata unavailable: {error}'
    streams = metadata.get('streams', [])
    video = next((s for s in streams if s.get('codec_type') == 'video'), {})
    width, height = video.get('width'), video.get('height')
    rotation = 0
    for side_data in video.get('side_data_list', []):
        rotation = side_data.get('rotation', rotation)
    if abs(float(rotation or 0)) % 180 == 90:
        width, height = height, width
    duration = None
    if kind == 'video':
        try: duration = round(float(metadata.get('format', {}).get('duration', video.get('duration'))), 2)
        except (ValueError, TypeError): pass
    date = validated_date(path.stem) or jpeg_capture_date(path)
    if not date:
        for container in [video, metadata.get('format', {})]:
            tags = container.get('tags', {})
            for key in ('date_time_original', 'DateTimeOriginal', 'com.apple.quicktime.creationdate', 'creation_time', 'date'):
                date = validated_date(tags.get(key))
                if date: break
            if date: break
    source_relative = provenance.get(digest, {}).get('sourceRelative', relative)
    item = {'id': digest[:24], 'src': relative, 'type': kind, 'thumbnail': thumbnail_relative,
            'title': friendly_title(path, date), 'filename': path.name, 'date': date,
            'album': friendly_album(source_relative), 'duration': duration, 'width': width,
            'height': height, 'bytes': path.stat().st_size, 'sha256': digest}
    if old_item and old_item.get('sha256') == digest:
        for field in ('id', 'title', 'filename', 'date', 'album'):
            if field in old_item:
                item[field] = old_item[field]
    if force or not thumbnail.is_file():
        thumbnail.parent.mkdir(parents=True, exist_ok=True)
        # Tiny previews are the only files loaded by the grid; originals stay intact.
        attempts = [min(1.0, duration / 4) if duration else 0.0, 0.0] if kind == 'video' else [0.0]
        for seek in dict.fromkeys(attempts):
            command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-threads', '1']
            if seek: command += ['-ss', str(seek)]
            command += ['-i', str(path), '-map', '0:v:0', '-frames:v', '1', '-vf',
                        "scale=w='min(480,iw)':h='min(480,ih)':force_original_aspect_ratio=decrease,setsar=1",
                        '-q:v', '7', '-threads', '1', '-y', str(thumbnail)]
            try:
                result = subprocess.run(command, capture_output=True, timeout=120)
                if result.returncode == 0 and thumbnail.is_file() and thumbnail.stat().st_size > 0:
                    break
            except subprocess.TimeoutExpired:
                pass
        if not thumbnail.is_file() or thumbnail.stat().st_size == 0:
            item['thumbnail'] = 'media/preview-unavailable.svg'
            warning = (warning + '\n' if warning else '') + f'{relative}: preview unavailable; original preserved'
    return normalize_item_dimensions(item, ROOT), warning


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, help='Recursively copy new photo/video content from this folder')
    parser.add_argument('--workers', type=int, default=4, help='Concurrent thumbnail workers (default: 4)')
    parser.add_argument('--force-previews', action='store_true', help='Rebuild all thumbnails and metadata')
    parser.add_argument('--verify', action='store_true', help='Rehash all originals instead of using unchanged-file cache')
    parser.add_argument('--skip-playback', action='store_true', help='Skip browser video copies for a quick catalog refresh')
    args = parser.parse_args(argv)
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        parser.error('Install ffmpeg and ffprobe and add them to PATH before running this script.')
    source = args.source.resolve() if args.source else None
    if source and not source.is_dir(): parser.error(f'Source directory does not exist: {source}')
    if source and (source == ROOT or ROOT in source.parents or source in ROOT.parents):
        parser.error('Source and repository must be separate directories, without nesting.')
    generated = utc_now()
    state_path = ROOT / 'media' / 'import-state.json'
    state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {'files': {}, 'provenance': {}}
    cache = state.get('files', {})
    provenance = state.get('provenance', {})
    optimization_path = ROOT / 'media' / 'optimization-state.json'
    optimization = json.loads(optimization_path.read_text(encoding='utf-8')) if optimization_path.exists() else {}
    replacements = optimization.get('replacements', {})
    import_limit = optimization.get('maxImportBytes')
    excluded = []
    replaced_source = []
    originals = media_files(ROOT / 'images') + media_files(ROOT / 'videos') + media_files(ROOT / 'lage_files')
    print(f'Existing originals: {len(originals)} ({sum(p.stat().st_size for p in originals) / 1024**3:.2f} GiB)', flush=True)
    existing_before = {}
    by_hash = {}
    file_cache = {}
    def inspect_file(path, allow_cache=True):
        relative = path.relative_to(ROOT).as_posix()
        stat = path.stat()
        old = cache.get(relative, {})
        digest = old.get('sha256') if allow_cache and not args.verify and old.get('bytes') == stat.st_size and old.get('mtimeNs') == stat.st_mtime_ns else None
        digest = digest or sha256_file(path)
        info = {'sha256': digest, 'bytes': stat.st_size, 'mtimeNs': stat.st_mtime_ns}
        file_cache[relative] = info
        return relative, info
    for path in originals:
        relative, info = inspect_file(path)
        existing_before[relative] = info.copy()
        by_hash.setdefault(info['sha256'], path)
    baseline = ROOT / 'media' / 'original-media-baseline.json'
    if not baseline.exists():
        atomic_json(baseline, {'createdAt': generated, 'files': existing_before})
    source_records = []
    imported = []
    skipped = []
    if source:
        candidates = media_files(source)
        print(f'Source media: {len(candidates)} ({sum(p.stat().st_size for p in candidates) / 1024**3:.2f} GiB). Hashing and importing...', flush=True)
        sizes = {}
        for digest, path in by_hash.items(): sizes.setdefault(path.stat().st_size, {})[digest] = path
        for index, path in enumerate(candidates, start=1):
            source_relative = path.relative_to(source).as_posix()
            size = path.stat().st_size
            if import_limit and size > import_limit:
                excluded.append({'source': source_relative, 'bytes': size, 'reason': 'Above the saved 1 GB import limit'})
                print(f'[{index}/{len(candidates)}] skipped by size limit: {source_relative}', flush=True)
                continue
            digest = sha256_file(path)
            replacement = replacements.get(digest)
            if replacement:
                replacement_path = (ROOT / replacement['path']).resolve()
                if replacement_path.is_relative_to(ROOT.resolve()) and replacement_path.is_file():
                    current_hash = sha256_file(replacement_path)
                    if current_hash == replacement['item']['sha256']:
                        replaced_source.append({'source': source_relative, 'destination': replacement['path'], 'originalSha256': digest})
                        print(f'[{index}/{len(candidates)}] compressed copy already present: {source_relative}', flush=True)
                        continue
            matches = sizes.get(size, {})
            destination = matches.get(digest)
            action = 'existing'
            if destination is None:
                category = 'images' if path.suffix.lower() in PHOTO_EXTENSIONS else 'videos'
                destination = safe_destination(ROOT / category / 'imported' / source_relative, digest)
                copied = copy_verified(path, destination, digest)
                by_hash[digest] = destination
                sizes.setdefault(size, {})[digest] = destination
                relative = destination.relative_to(ROOT).as_posix()
                destination_stat = destination.stat()
                file_cache[relative] = {'sha256': digest, 'bytes': destination_stat.st_size,
                                        'mtimeNs': destination_stat.st_mtime_ns}
                imported.append({'source': source_relative, 'destination': relative, 'sha256': digest, 'bytes': size})
                action = 'copied' if copied else 'existing'
            else:
                skipped.append({'source': source_relative, 'destination': destination.relative_to(ROOT).as_posix(), 'sha256': digest, 'bytes': size})
            provenance.setdefault(digest, {'sourceRelative': source_relative})
            source_records.append({'source': source_relative, 'destination': destination.relative_to(ROOT).as_posix(), 'sha256': digest, 'bytes': size})
            print(f'[{index}/{len(candidates)}] {action}: {source_relative}', flush=True)
            # Save progress so reruns can resume quickly after interruption.
            if index % 10 == 0:
                atomic_json(state_path, {'generatedAt': generated, 'files': file_cache, 'provenance': provenance})
    else:
        print('No source folder supplied: refreshing the existing library.', flush=True)
    atomic_json(state_path, {'generatedAt': generated, 'files': file_cache, 'provenance': provenance})
    library_path = ROOT / 'media' / 'library.json'
    previous = json.loads(library_path.read_text(encoding='utf-8')).get('items', []) if library_path.exists() else []
    old_items = {item.get('sha256'): item for item in previous}
    for replacement in replacements.values():
        saved_item = replacement.get('item', {})
        if saved_item.get('sha256'):
            old_items.setdefault(saved_item['sha256'], saved_item)
    print(f'Building metadata and previews for {len(by_hash)} unique memories...', flush=True)
    items, warnings = [], []
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 8))) as executor:
        futures = {executor.submit(generate_item, path, digest, provenance, old_items.get(digest), args.force_previews): path
                   for digest, path in by_hash.items()}
        for index, future in enumerate(as_completed(futures), 1):
            item, warning = future.result()
            items.append(item)
            if warning: warnings.append(warning)
            if index % 20 == 0 or index == len(futures):
                print(f'Previews ready: {index}/{len(futures)}', flush=True)
    items.sort(key=lambda item: (item['date'] or '', item['src']), reverse=True)
    if not args.skip_playback:
        from build_playback import prepare_playback
        playback_report = prepare_playback(items, ROOT)
        warnings.extend(f"{entry['src']}: browser playback copy failed: {entry['error']}" for entry in playback_report['failures'])
    library = {'generatedAt': generated, 'items': items}
    atomic_json(library_path, library)
    (ROOT / 'media' / 'library.js').write_text('/* Generated by scripts/build_media.py. */\nwindow.MEDIA_LIBRARY = ' + json.dumps(library, ensure_ascii=False, separators=(',', ':')) + ';\n', encoding='utf-8')
    print('Verifying that all pre-existing originals are unchanged...', flush=True)
    preserved = []
    for relative, before in existing_before.items():
        path = ROOT / relative
        after = sha256_file(path)
        if after != before['sha256']:
            raise RuntimeError(f'Pre-existing original changed: {relative}')
        preserved.append({'path': relative, 'sha256': after, 'bytes': path.stat().st_size})
    all_digests = {item['sha256'] for item in items}
    missing = [row for row in source_records if row['sha256'] not in all_digests]
    if missing: raise RuntimeError(f'{len(missing)} source files are not represented in the library')
    report = {'generatedAt': generated, 'source': str(source) if source else None,
              'summary': {'sourceFiles': len(source_records) + len(excluded) + len(replaced_source), 'sourceUniqueContent': len({r['sha256'] for r in source_records}),
                          'copiedFiles': len(imported), 'copiedBytes': sum(r['bytes'] for r in imported),
                          'duplicateSourceFilesSkipped': len(skipped), 'preExistingFilesVerifiedUnchanged': len(preserved),
                          'libraryItems': len(items), 'photos': sum(i['type'] == 'image' for i in items),
                          'videos': sum(i['type'] == 'video' for i in items), 'undatedItems': sum(not i['date'] for i in items),
                          'thumbnailWarnings': len(warnings), 'sourceFilesSkippedBySizeLimit': len(excluded),
                          'compressedCopiesReused': len(replaced_source)},
              'allEligibleSourceContentRepresented': not missing,
              'allSourceContentRepresented': not missing and not excluded,
              'preExistingOriginalsUnchanged': True, 'skippedByPolicy': excluded,
              'compressedCopiesReused': replaced_source,
              'imported': imported, 'duplicatesSkipped': skipped, 'sourceMedia': source_records,
              'preservedOriginals': preserved, 'warnings': warnings}
    report_name = 'import-report.json' if source else 'build-report.json'
    atomic_json(ROOT / 'media' / report_name, report)
    print(json.dumps(report['summary'], indent=2), flush=True)
    if warnings: print('\n'.join(warnings), flush=True)
    print(f'Library written to media/library.js. Report: media/{report_name}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
