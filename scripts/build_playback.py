#!/usr/bin/env python3
"""Create browser-friendly video copies while preserving every full-size original.

Called automatically by build_media.py; can also be run on its own.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from fractions import Fraction
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent.parent
SAFE_VIDEO_CODECS = {'h264'}
SAFE_PIXEL_FORMATS = {'yuv420p', 'yuvj420p'}
SAFE_AUDIO_CODECS = {'aac', 'mp3'}


def video_probe(path: Path):
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)],
                            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=90)
    if result.returncode:
        raise RuntimeError(result.stderr.strip()[-600:] or 'ffprobe failed')
    return json.loads(result.stdout)


def needs_playback_copy(path: Path, metadata):
    video = next((s for s in metadata.get('streams', []) if s.get('codec_type') == 'video'), {})
    audio = next((s for s in metadata.get('streams', []) if s.get('codec_type') == 'audio'), None)
    video_safe = video.get('codec_name') in SAFE_VIDEO_CODECS and video.get('pix_fmt') in SAFE_PIXEL_FORMATS
    audio_safe = audio is None or audio.get('codec_name') in SAFE_AUDIO_CODECS
    container_safe = path.suffix.lower() in {'.mp4', '.m4v'}
    # Always make a compact streaming copy, including browser-compatible originals.
    return True, False, False


def make_playback_copy(source, destination, metadata, video_safe, audio_safe):
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.stem + '.encoding.mp4')
    command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-threads', '2',
               '-filter_threads', '2', '-i', str(source), '-map', '0:v:0', '-map', '0:a:0?',
               '-map_metadata', '-1', '-sn', '-dn']
    if video_safe:
        command += ['-c:v', 'copy']
    else:
        command += ['-vf', "scale=w='if(gte(iw,ih),min(854,iw),min(480,iw))':h='if(gte(iw,ih),min(480,ih),min(854,ih))':force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1",
                    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '30', '-maxrate', '750k', '-bufsize', '1500k', '-pix_fmt', 'yuv420p', '-threads', '2']
        video = next((s for s in metadata.get('streams', []) if s.get('codec_type') == 'video'), {})
        try:
            if float(Fraction(video.get('avg_frame_rate', '30'))) > 30:
                command += ['-r', '30']
        except (ValueError, ZeroDivisionError):
            pass
    command += ['-c:a', 'copy'] if audio_safe else ['-c:a', 'aac', '-b:a', '64k', '-ac', '2']
    command += ['-movflags', '+faststart', '-max_muxing_queue_size', '2048', '-y', str(temporary)]
    started = time.monotonic()
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    while process.poll() is None:
        try:
            _, stderr = process.communicate(timeout=25)
        except subprocess.TimeoutExpired:
            print(f'  Encoding {source.name} ({int(time.monotonic() - started)}s elapsed)', flush=True)
            continue
        break
    else:
        _, stderr = process.communicate()
    if process.returncode:
        raise RuntimeError(stderr.decode('utf-8', errors='replace')[-1200:] or 'ffmpeg conversion failed')
    result = video_probe(temporary)
    output_video = next((s for s in result.get('streams', []) if s.get('codec_type') == 'video'), {})
    if output_video.get('codec_name') != 'h264' or output_video.get('pix_fmt') not in SAFE_PIXEL_FORMATS:
        raise RuntimeError('Playback copy failed H.264 validation')
    expected_duration = float(metadata.get('format', {}).get('duration', 0) or 0)
    actual_duration = float(result.get('format', {}).get('duration', 0) or 0)
    if expected_duration and abs(expected_duration - actual_duration) > max(1, expected_duration * .01):
        raise RuntimeError(f'Playback duration differs from original: {expected_duration} vs {actual_duration}')
    temporary.replace(destination)
    return result


def prepare_playback(items, root=ROOT, workers=3):
    videos = [item for item in items if item['type'] == 'video']
    report = {'generatedAt': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'videos': len(videos),
              'created': [], 'reused': [], 'native': [], 'failures': [], 'codecs': {}}
    plans = []
    codecs = Counter()
    for item in videos:
        source = root / item['src']
        try:
            metadata = video_probe(source)
            video = next((s for s in metadata.get('streams', []) if s.get('codec_type') == 'video'), {})
            item['codec'] = video.get('codec_name')
            codecs[item['codec'] or 'unknown'] += 1
            needed, video_safe, audio_safe = needs_playback_copy(source, metadata)
            if needed:
                plans.append((item, source, metadata, video_safe, audio_safe))
            else:
                item['playbackSrc'] = item['src']
                item['playbackFormat'] = 'original'
                report['native'].append(item['src'])
        except Exception as error:
            report['failures'].append({'src': item['src'], 'error': str(error)})
    report['codecs'] = dict(codecs)
    print(f'Video codecs: {dict(codecs)}. Browser copies needed: {len(plans)}/{len(videos)}.', flush=True)
    def process_plan(index, plan):
        item, source, metadata, video_safe, audio_safe = plan
        relative = f'media/playback/{item["sha256"][:24]}.mp4'
        destination = root / relative
        try:
            if destination.is_file() and destination.stat().st_size:
                existing = video_probe(destination)
                existing_video = next((s for s in existing.get('streams', []) if s.get('codec_type') == 'video'), {})
                if existing_video.get('codec_name') != 'h264':
                    raise RuntimeError(f'Existing playback copy is not valid H.264: {relative}')
                report['reused'].append(relative)
                print(f'[{index}/{len(plans)}] Browser copy reused: {source.name}', flush=True)
            else:
                print(f'[{index}/{len(plans)}] {"Remuxing" if video_safe else "Encoding"} {item["codec"]}: {source.name}', flush=True)
                make_playback_copy(source, destination, metadata, video_safe, audio_safe)
                report['created'].append({'original': item['src'], 'playback': relative, 'bytes': destination.stat().st_size})
            item['playbackSrc'] = relative
            item['playbackFormat'] = 'H.264 MP4'
            item['playbackBytes'] = destination.stat().st_size
        except Exception as error:
            report['failures'].append({'src': item['src'], 'error': str(error)})
            print(f'  Browser copy failed; original preserved: {error}', flush=True)
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 4))) as executor:
        futures = [executor.submit(process_plan, index, plan) for index, plan in enumerate(plans, 1)]
        for future in as_completed(futures):
            future.result()
    report_path = root / 'media' / 'playback-report.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=int, default=3, help='Concurrent conversions (default: 3, maximum: 4)')
    args = parser.parse_args()
    path = ROOT / 'media' / 'library.json'
    library = json.loads(path.read_text(encoding='utf-8'))
    report = prepare_playback(library['items'], workers=args.workers)
    from build_media import normalize_item_dimensions
    for item in library['items']:
        normalize_item_dimensions(item, ROOT)
    path.write_text(json.dumps(library, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (ROOT / 'media' / 'library.js').write_text('/* Generated by scripts/build_media.py. */\nwindow.MEDIA_LIBRARY = ' + json.dumps(library, ensure_ascii=False, separators=(',', ':')) + ';\n', encoding='utf-8')
    print(f'Playback complete: {len(report["created"])} created, {len(report["reused"])} reused, {len(report["failures"])} failures.', flush=True)
    return 1 if report['failures'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
