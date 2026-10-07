# Upload batches

**Superseded for GitHub Pages:** these historical groups start with the largest
files and exceed the total Pages site limit. Batch 01 is already committed on
the local `codex/media-batches` branch; later working files have changed since
this plan was generated. Use `scripts/prepare_pages.py` and the main README for
the new smallest-first, complete Pages snapshot.

Prepared from commit `d8d24bddccf5fd06159e39aa6571a7a2750264f1`. All source files stay in their
existing folders; the text files list the exact paths in each group.

14 regular batches contain 1093 changed/new files,
totaling 13.59 GB. Every batch is below 990 MB before
Git compression. Batch 01 also includes this folder (2 MB reserved).

| Batch | Files | Payload |
| --- | ---: | ---: |
| 01 | 13 | 988.00 MB |
| 02 | 17 | 990.00 MB |
| 03 | 16 | 990.00 MB |
| 04 | 17 | 990.00 MB |
| 05 | 18 | 990.00 MB |
| 06 | 19 | 990.00 MB |
| 07 | 21 | 990.00 MB |
| 08 | 24 | 990.00 MB |
| 09 | 27 | 990.00 MB |
| 10 | 30 | 990.00 MB |
| 11 | 38 | 990.00 MB |
| 12 | 54 | 990.00 MB |
| 13 | 91 | 990.00 MB |
| 14 | 708 | 726.13 MB |

## Inspect and stage one batch

Run from the repository root:

```powershell
python scripts/stage_push_batch.py 1
python scripts/stage_push_batch.py 1 --stage
```

The staging helper verifies hashes and refuses to mix an already staged change
into a batch. It does not commit or push. Commit and push each batch before
staging the next one; committing everything and then pushing once would send
all those commits together. Rebuild this plan if any listed file changes.

## Large files held for last

`lage_files/` holds 38 files totaling 6.63 GB.
They are ignored by Git and excluded from every batch. Their hashes and original
paths are recorded in `media/large-files-relocation.json`. Gallery paths point
to their new local locations. Do not force-add this folder: files over GitHub's
100 MiB limit need a different storage arrangement before upload.

## Publishing constraint

These batches only divide Git transfers. They do not make this collection fit
GitHub Pages' 1 GB published-site limit. Uploading these batches to the Pages
branch would leave the deployment oversized, and the held files unavailable.
Decide on separate media hosting or a storage branch before pushing. The local
gallery remains complete. No commits or pushes were made when preparing this plan.
