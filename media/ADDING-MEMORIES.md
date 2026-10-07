# Adding memories

## Import from a folder

Run from the repository with Python 3.10+ and FFmpeg/ffprobe on PATH:

```powershell
python scripts/build_media.py --source "C:\Users\User\Videos"
```

This scans subfolders for photos and videos, checks SHA-256 file hashes, and copies only new content. Original subfolders are retained under `images/imported/` and `videos/imported/`. Different files with the same name get a hash suffix. The source directory is never modified.

The saved policy skips files larger than **1,000,000,000 bytes (1 GB)**. Previously compressed content is recognized through `optimization-state.json`; repeated imports keep the smaller replacement.

## Add directly

Place photos in `images/` or videos in `videos/`, optionally in album subfolders, then run:

```powershell
python scripts/build_media.py
```

The command builds `library.js`, `library.json`, and JPEG thumbnails. The webpage needs this generated catalog to discover new files. Use `--force-previews` to regenerate thumbnails or `--verify` to rehash retained files.

Unsupported video codecs receive a browser-compatible H.264 playback copy, up to 720p. Compatible MOV files are repackaged as MP4. Use `--skip-playback` for a quick catalog refresh, then `python scripts/build_playback.py` to create missing browser copies.

## Compress and apply the size limit

```powershell
python scripts/optimize_media.py
python scripts/optimize_media.py --apply
```

The first command previews the plan. The second removes repo files above 1 GB and uses CRF 20 to compress remaining videos above 100 MB. Where an oversized original already has a smaller viewing copy, that copy is retained. Otherwise its gallery entry is removed. CRF conversions preserve resolution and frame rate; outputs replace files only when smaller and validated. See the [main README](../README.md) for the settings and quality tradeoffs.

## Dates and albums

- Dates come from filenames, then camera capture metadata. Unknown dates remain undated.
- Folder names become album names. Use clear subfolder names for new collections.
- Stable memory IDs preserve favorites across compression and catalog refreshes.
- Content duplicates appear once in the gallery.

## Records to keep

- `import-state.json`: file hashes and source-folder context.
- `optimization-state.json`: the size limit and original-to-compressed mappings.
- `optimization-report.json`: the deletion and compression results.
- `original-media-baseline.json` and `import-report.json`: the initial import history, before later optimization.
- `build-report.json`: the latest catalog refresh verification.
- `playback-report.json`: browser-copy conversion results.

Publish retained media, previews, and the generated catalog together on hosting that supports the collection. The reports are maintenance records, not required by the webpage.
