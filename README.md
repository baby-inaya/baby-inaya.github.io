# Inaya Mahnoor's memory book

A family scrapbook built with plain HTML, CSS, and JavaScript. The cream paper, berry accents, photograph cover, and monthly gallery adapt to phones, tablets, and desktops.

## Browse the collection

- Photos, little films, and personal favorites.
- Search by name, date, or album; filter by album and year.
- Monthly chapters, newest/oldest sorting, and 24 memories per page.
- A large viewer with keyboard navigation, photo swipes, and video controls.
- Small image previews; videos only load when opened.
- Favorites stay in the current browser, including across visits.

## Preview locally

From the repository folder:

```powershell
python scripts/serve.py
```

Open **http://127.0.0.1:8000**. The server supports video seeking and listens only on this computer. You can also open `index.html` directly; a local server gives the most consistent video behavior.

## Add more memories

Python 3.10+ and FFmpeg/ffprobe must be on PATH for importing or converting media.
Preparing a Pages snapshot only requires Python 3.10+.

Import new photos and videos from the Videos folder:

```powershell
python scripts/build_media.py --source "C:\Users\User\Videos"
```

Or place files in `images/` and `videos/`, using subfolders for albums, then run:

```powershell
python scripts/build_media.py
```

The builder checks file contents, avoids duplicates, handles name collisions, generates previews, and refreshes `media/library.js`. Folder contents are discovered **when this command runs**; a static webpage cannot scan folders by itself.

The saved size policy skips source files over **1,000,000,000 bytes (1 GB)**. Previously compressed source files are recognized, so reimporting does not restore their larger copies. Source files outside this repository are never changed.

Camera filenames and capture metadata provide dates. Unknown dates appear under “Timeless little moments.” Albums come from folder names. See [Adding memories](media/ADDING-MEMORIES.md) for details.

## Video compression and the size limit

```powershell
python scripts/optimize_media.py
python scripts/optimize_media.py --apply
```

The first command previews the plan. `--apply` deletes repo media larger than 1 GB and compresses remaining videos over 100 MB with **H.264, CRF 20, preset veryfast, AAC 192 kbps, and MP4 faststart**. Resolution and frame rate are preserved for these CRF conversions. CRF is lossy; the setting aims for a close visual match, not identical pixels. The first batch used preset `fast`; subsequent runs default to `veryfast`. Use `--preset fast` or `--preset medium` for slower encoding.

Existing smaller viewing copies of oversized originals are retained where available. Those earlier copies are up to 720p and are distinct from the full-resolution CRF 20 conversions. Files without such copies are removed from the gallery when the size limit is applied.

A replacement must be smaller, have matching duration, dimensions, and display orientation, retain audio, and decode successfully. Otherwise the existing file stays. Completed conversions are recorded and skipped on reruns.

Videos with unsupported browser codecs also get a separate compatible playback copy when the catalog is built. The download button always points to the retained file for that memory.

## Project files

```text
index.html, style.css, script.js     Website
images/, videos/                    Retained photos and videos
thumbnails/                         Small gallery previews
media/library.js, library.json      Generated gallery catalog
media/playback/                     Browser-compatible video copies
media/optimization-state.json       Size policy and replacement mappings
media/optimization-report.json      Deletions and compression results
scripts/build_media.py              Import and rebuild the catalog
scripts/optimize_media.py           Apply the requested size/compression rules
scripts/serve.py                    Local preview server
```

`media/import-report.json` and `media/original-media-baseline.json` record the initial import before the later deletion/compression request. `media/optimization-report.json` records subsequent changes. Keep the state files: they prevent repeat imports from undoing compression.

## Verification

```powershell
python -m unittest discover -s scripts -p "test_*.py" -v
```

Tests cover content deduplication, filename collisions, import preservation, browser playback conversion, saved size rules, and HTTP byte ranges. The site has no npm dependencies or build step.

## Publishing

GitHub Pages has a [1 GB published-site limit](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits).
GitHub rejects individual Git files [larger than 100 MiB](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github).
Splitting the collection into upload batches does not reduce the final site size.

Prepare a complete, bounded snapshot from the full local collection:

```powershell
python scripts/prepare_pages.py
python scripts/prepare_pages.py --apply
```

The first command previews the selection. The second copies it to the ignored
`qa-output/pages/` folder. It refuses to overwrite an existing export; use a new
`--output qa-output/pages-next` folder for another snapshot. The default total
budget is 999,000,000 bytes, including a 2 MB reserve for generated metadata.
The final snapshot is verified against this budget and the Pages limit.

The exporter includes the website, source scripts and documentation, then selects
the smallest complete memories first. Each memory keeps its retained original,
thumbnail, and any required browser playback copy. The published catalogs list
only included memories, so photos, playback, downloads, and counts stay consistent.
The local collection, full catalogs, and existing Git index remain unchanged.
No image or video is recompressed. The export includes `.nojekyll` so GitHub
Pages serves the files directly, including filenames that begin with underscores.

`media/pages-selection.json` inside the export records what was included or held
back. Local import history, logs, old upload batches, and unused media are not
part of the snapshot. Keep the full collection and its maintenance state files
in this original checkout; a clone of the published snapshot is only the selected
collection.

The existing `codex/media-batches` branch contains a large first upload batch.
It is unsuitable as the base of this Pages snapshot. The prepared
`codex/pages-first-publish` branch starts from the existing GitHub `main` history
and contains the bounded site in one new commit. Preparing a commit is separate
from pushing or enabling Pages; no force push is needed.

Do not use `git add .` in the full collection to prepare a Pages upload: that
would include many gigabytes that the site cannot host. Future snapshots should
replace the selected collection, with their catalog and size verified together.

Files above 100 MB remain in the ignored `lage_files/` folder. The full local
gallery can display them, but they are excluded from the Pages export. Publishing
all memories at their current quality requires separate media hosting.
