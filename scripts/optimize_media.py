"""Apply the requested repo-only 1 GB limit, then compress large videos.

Run with --apply to change files. The default only prints the plan.
Source folders outside this repository are never modified.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from fractions import Fraction
import json
from pathlib import Path
import shutil
import subprocess
import threading
import time

from build_media import ROOT, atomic_json, sha256_file, utc_now
from build_playback import video_probe

LIMIT = 1_000_000_000
COMPRESS_OVER = 100_000_000
LOCK = threading.Lock()


def safe_path(relative, root=ROOT):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or path == root.resolve():
        raise ValueError(f'Path outside repository: {relative}')
    if path.is_relative_to((root / '.git').resolve()):
        raise ValueError('Git data is outside the media scope')
    return path


def write_library(library):
    library['generatedAt'] = utc_now()
    atomic_json(ROOT / 'media/library.json', library)
    js = ROOT / 'media/library.js'
    tmp = js.with_suffix('.js.tmp')
    tmp.write_text('/* Generated memory library. */\nwindow.MEDIA_LIBRARY = ' +
                   json.dumps(library, ensure_ascii=False, separators=(',', ':')) + ';\n', encoding='utf-8')
    tmp.replace(js)


def video_rotation(metadata):
    stream = next(s for s in metadata['streams'] if s.get('codec_type') == 'video')
    for side_data in stream.get('side_data_list', []):
        if 'rotation' in side_data:
            return float(side_data['rotation']) % 360
    return float(stream.get('tags', {}).get('rotate', 0)) % 360


def restore_rotation(path, source_metadata):
    """Keep portrait display metadata without encoding the picture again."""
    expected = video_rotation(source_metadata)
    if abs(video_rotation(video_probe(path)) - expected) < .01:
        return False
    temporary = path.with_name(path.stem + '.orientation.mp4')
    try:
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
                        '-display_rotation:v:0', str(expected), '-i', str(path),
                        '-map', '0:v:0', '-map', '0:a:0?', '-c', 'copy',
                        '-movflags', '+faststart', '-y', str(temporary)],
                       check=True, capture_output=True, timeout=300)
        if abs(video_rotation(video_probe(temporary)) - expected) >= .01:
            raise ValueError('Could not preserve video rotation')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def validate_video(path, source_metadata, preserve_dimensions=False):
    metadata = video_probe(path)
    stream = next(s for s in metadata['streams'] if s.get('codec_type') == 'video')
    source_stream = next(s for s in source_metadata['streams'] if s.get('codec_type') == 'video')
    duration = float(metadata['format'].get('duration', 0))
    expected = float(source_metadata['format'].get('duration', 0))
    if stream.get('codec_name') != 'h264' or stream.get('pix_fmt') not in {'yuv420p', 'yuvj420p'}:
        raise ValueError('Output is not browser-compatible H.264')
    if duration <= 0 or abs(duration - expected) > max(0.5, expected * 0.005):
        raise ValueError(f'Duration changed from {expected} to {duration}')
    if preserve_dimensions and (stream['width'], stream['height']) != (source_stream['width'], source_stream['height']):
        raise ValueError('Dimensions changed')
    if preserve_dimensions:
        if abs(video_rotation(metadata) - video_rotation(source_metadata)) >= .01:
            raise ValueError('Display orientation changed')
        before_rate = float(Fraction(source_stream.get('avg_frame_rate', '0')))
        after_rate = float(Fraction(stream.get('avg_frame_rate', '0')))
        if abs(before_rate - after_rate) > max(.02, before_rate * .001):
            raise ValueError(f'Frame rate changed from {before_rate} to {after_rate}')
    if any(s.get('codec_type') == 'audio' for s in source_metadata['streams']) and not any(s.get('codec_type') == 'audio' for s in metadata['streams']):
        raise ValueError('Audio missing')
    # Decode the whole result: container metadata alone cannot detect a truncated tail.
    result = subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-threads', '2', '-i', str(path),
                             '-map', '0:v:0', '-map', '0:a:0?', '-f', 'null', '-'],
                            capture_output=True, timeout=3600)
    if result.returncode:
        raise ValueError(result.stderr.decode(errors='replace')[-600:])
    return metadata


def update_item(item, destination, metadata, digest):
    stream = next(s for s in metadata['streams'] if s.get('codec_type') == 'video')
    item.update(src=destination.relative_to(ROOT).as_posix(), sha256=digest,
                bytes=destination.stat().st_size, codec='h264',
                playbackSrc=destination.relative_to(ROOT).as_posix(),
                playbackBytes=destination.stat().st_size, playbackFormat='H.264 MP4',
                width=stream['width'], height=stream['height'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--crf', type=int, default=20)
    parser.add_argument('--preset', choices=['veryfast', 'fast', 'medium'], default='veryfast')
    args = parser.parse_args()
    if not 0 <= args.crf <= 30:
        parser.error('CRF must be between 0 and 30')
    library = json.loads((ROOT / 'media/library.json').read_text(encoding='utf-8'))
    state_path = ROOT / 'media/optimization-state.json'
    state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {
        'maxImportBytes': LIMIT, 'deleted': [], 'replacements': {}, 'compression': {}}
    report_path = ROOT / 'media/optimization-report.json'
    report = json.loads(report_path.read_text(encoding='utf-8')) if report_path.exists() else {
        'startedAt': utc_now(), 'limitBytes': LIMIT, 'compressOverBytes': COMPRESS_OVER,
        'crf': args.crf, 'deleted': [], 'retainedCopies': [], 'compressed': [], 'keptUnchanged': [], 'failures': []}
    originals = [p for folder in ('images', 'videos', 'lage_files') for p in (ROOT / folder).rglob('*') if p.is_file() and not p.is_symlink()]
    oversize = [p for p in originals if p.stat().st_size > LIMIT]
    candidates = [i for i in library['items'] if i['type'] == 'video' and COMPRESS_OVER < safe_path(i['src']).stat().st_size <= LIMIT
                  and i['id'] not in state['compression']]
    print(f'{len(oversize)} files over 1 GB; {len(candidates)} other videos over 100 MB. CRF {args.crf}.', flush=True)
    if not args.apply:
        return
    # Snapshot contains metadata, not copies of the large files the user asked to remove.
    snapshot = ROOT / 'media/library-before-optimization.json'
    if not snapshot.exists(): atomic_json(snapshot, library)
    atomic_json(state_path, state)
    for source in oversize:
        source = safe_path(source.relative_to(ROOT))
        relative = source.relative_to(ROOT).as_posix()
        item = next((i for i in library['items'] if i['src'] == relative), None)
        digest = item['sha256'] if item else sha256_file(source)
        row = {'path': relative, 'bytes': source.stat().st_size, 'sha256': digest}
        retained = False
        if item and item.get('playbackSrc') and item['playbackSrc'] != relative:
            playback = safe_path(item['playbackSrc'])
            if playback.is_file() and playback.stat().st_size <= LIMIT:
                metadata = validate_video(playback, video_probe(source))
                destination = safe_path(f'videos/retained/{source.stem}--{item["id"][:12]}.mp4')
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    if sha256_file(destination) != sha256_file(playback): raise ValueError(f'Collision: {destination}')
                else: shutil.copy2(playback, destination)
                output_hash = sha256_file(destination)
                original_info = dict(item)
                update_item(item, destination, metadata, output_hash)
                state['replacements'][digest] = {'path': item['src'], 'item': dict(item), 'original': original_info}
                report['retainedCopies'].append({'original': relative, 'retained': item['src'], 'bytes': item['bytes']})
                retained = True
        if item and not retained:
            library['items'].remove(item)
        state['deleted'].append(row)
        report['deleted'].append(row)
        # Persist the decision before deletion so interrupted reruns don't reimport it.
        atomic_json(state_path, state)
        source.unlink()
        write_library(library)
        atomic_json(report_path, report)
        print(f'Deleted >1 GB: {relative}' + (' (smaller copy retained)' if retained else ''), flush=True)

    def compress(item):
        source = safe_path(item['src'])
        before = source.stat().st_size
        digest = item['sha256']
        metadata = video_probe(source)
        temporary = safe_path(f'media/encoding/{item["id"]}.mp4')
        temporary.parent.mkdir(parents=True, exist_ok=True)
        progress_file = temporary.with_suffix('.progress')
        command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-threads', '4', '-noautorotate',
                   '-i', str(source), '-map', '0:v:0', '-map', '0:a:0?', '-map_metadata', '0',
                   '-c:v', 'libx264', '-preset', args.preset, '-crf', str(args.crf), '-pix_fmt', 'yuv420p',
                   '-threads', '4', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart',
                   '-progress', str(progress_file), '-y', str(temporary)]
        print(f'Compressing: {source.name} ({before / 1e6:.1f} MB)', flush=True)
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        started = time.monotonic()
        grew_larger = False
        while True:
            try:
                _, stderr = process.communicate(timeout=20)
                break
            except subprocess.TimeoutExpired:
                # Reading the open file gives a current size on Windows too.
                if temporary.exists():
                    with temporary.open('rb') as output:
                        current_size = output.seek(0, 2)
                    if current_size >= before:
                        process.terminate()
                        _, stderr = process.communicate(timeout=30)
                        grew_larger = True
                        break
                progress = progress_file.read_text(errors='replace') if progress_file.exists() else ''
                fields = dict(line.split('=', 1) for line in progress.splitlines() if '=' in line)
                print(f'  {source.name}: {fields.get("out_time", "starting")}, {fields.get("speed", "")} ({int(time.monotonic() - started)}s elapsed)', flush=True)
        if process.returncode and not grew_larger:
            raise RuntimeError(stderr.decode(errors='replace')[-1000:])
        if not grew_larger and temporary.stat().st_size < before:
            restore_rotation(temporary, metadata)
        if grew_larger or temporary.stat().st_size >= before:
            temporary.unlink()
            return {'status': 'unchanged', 'id': item['id'], 'path': item['src'], 'bytes': before,
                    'crf': args.crf, 'preset': args.preset, 'reason': 'CRF output was not smaller'}
        output_meta = validate_video(temporary, metadata, preserve_dimensions=True)
        destination = source if source.suffix.lower() == '.mp4' else source.with_name(source.stem + f'--crf{args.crf}.mp4')
        if destination != source and destination.exists():
            raise RuntimeError(f'Output already exists: {destination}')
        output_hash = sha256_file(temporary)
        with LOCK:
            original_info = dict(item)
            temporary.replace(destination)
            if source != destination: source.unlink()
            update_item(item, destination, output_meta, output_hash)
            state['replacements'][digest] = {'path': item['src'], 'item': dict(item), 'original': original_info}
            row = {'status': 'compressed', 'id': item['id'], 'original': original_info['src'], 'path': item['src'],
                   'beforeBytes': before, 'afterBytes': item['bytes'], 'crf': args.crf, 'preset': args.preset}
            state['compression'][item['id']] = row
            report['compressed'].append(row)
            atomic_json(state_path, state)
            write_library(library)
            atomic_json(report_path, report)
        print(f'Compressed: {source.name}: {before / 1e6:.1f} -> {item["bytes"] / 1e6:.1f} MB', flush=True)
        return row

    with ThreadPoolExecutor(max_workers=max(1, min(3, args.workers))) as pool:
        futures = {pool.submit(compress, item): item for item in candidates}
        for future in as_completed(futures):
            item = futures[future]
            try:
                row = future.result()
                if row['status'] == 'unchanged':
                    with LOCK:
                        state['compression'][item['id']] = row
                        report['keptUnchanged'].append(row)
                        atomic_json(state_path, state)
                        atomic_json(report_path, report)
                    print(f'Kept smaller original: {item["src"]}', flush=True)
            except Exception as error:
                with LOCK:
                    report['failures'].append({'src': item['src'], 'error': str(error)})
                    atomic_json(report_path, report)
                print(f'Compression failed, source kept: {item["src"]}: {error}', flush=True)
    report['finishedAt'] = utc_now()
    report['summary'] = {'deletedOver1GB': len(report['deleted']), 'retainedSmallerCopies': len(report['retainedCopies']),
                         'compressed': len(report['compressed']), 'keptUnchanged': len(report['keptUnchanged']),
                         'failures': len(report['failures']), 'libraryItems': len(library['items']),
                         'deletedBytes': sum(r['bytes'] for r in report['deleted']),
                         'compressionSavedBytes': sum(r['beforeBytes'] - r['afterBytes'] for r in report['compressed'])}
    atomic_json(report_path, report)
    print(json.dumps(report['summary'], indent=2), flush=True)
    return 1 if report['failures'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
