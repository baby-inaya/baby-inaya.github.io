"""Prepare bounded Git upload groups; never commit or push anything."""
import json
from pathlib import Path
import subprocess
from build_media import ROOT, atomic_json, sha256_file, utc_now

LIMIT = 990_000_000


def main():
    pending = set()
    for arguments in [('diff', 'HEAD', '--name-only', '-z'),
                      ('ls-files', '--others', '--exclude-standard', '-z')]:
        output = subprocess.check_output(['git', *arguments], cwd=ROOT).decode()
        pending.update(p for p in output.split('\0') if p)
    rows = []
    for relative in sorted(pending):
        if relative.startswith(('push_batches/', 'lage_files/')):
            continue
        path = ROOT / relative
        if not path.is_file():
            raise ValueError('Handle deleted paths separately: ' + relative)
        size = path.stat().st_size
        if size > 100_000_000:
            raise ValueError('Large file must be held back: ' + relative)
        rows.append({'path': relative, 'bytes': size, 'sha256': sha256_file(path)})
    # Largest-first packing keeps the batch count low. Reserve room in the first
    # batch for these generated instructions and manifests.
    batches = [{'bytes': 0, 'files': []}]
    for row in sorted(rows, key=lambda r: (-r['bytes'], r['path'])):
        for index, batch in enumerate(batches):
            capacity = LIMIT - (2_000_000 if index == 0 else 0)
            if batch['bytes'] + row['bytes'] <= capacity:
                break
        else:
            batch = {'bytes': 0, 'files': []}
            batches.append(batch)
        batch['files'].append(row)
        batch['bytes'] += row['bytes']
    destination = ROOT / 'push_batches'
    destination.mkdir(exist_ok=True)
    for index, batch in enumerate(batches, 1):
        batch['number'] = index
        batch['files'].sort(key=lambda row: row['path'])
        (destination / f'batch-{index:02}.txt').write_text(
            '\n'.join(row['path'] for row in batch['files']) + '\n', encoding='utf-8')
    held = [{'path': p.relative_to(ROOT).as_posix(), 'bytes': p.stat().st_size}
            for p in sorted((ROOT / 'lage_files').rglob('*')) if p.is_file()]
    plan = {'createdAt': utc_now(), 'baseCommit': subprocess.check_output(
                ['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip(),
            'batchLimitBytes': LIMIT, 'batches': batches, 'heldForLast': held,
            'pendingBytes': sum(row['bytes'] for row in rows)}
    atomic_json(destination / 'plan.json', plan)
    table = '\n'.join(f'| {b["number"]:02} | {len(b["files"])} | {b["bytes"]/1e6:.2f} MB |'
                      for b in batches)
    (destination / 'README.md').write_text(f'''# Upload batches

Prepared from commit `{plan['baseCommit']}`. All source files stay in their
existing folders; the text files list the exact paths in each group.

{len(batches)} regular batches contain {len(rows)} changed/new files,
totaling {plan['pendingBytes']/1e9:.2f} GB. Every batch is below 990 MB before
Git compression. Batch 01 also includes this folder (2 MB reserved).

| Batch | Files | Payload |
| --- | ---: | ---: |
{table}

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

`lage_files/` holds {len(held)} files totaling {sum(r['bytes'] for r in held)/1e9:.2f} GB.
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
''', encoding='utf-8')
    print(f'{len(batches)} batches; {len(rows)} files; {plan["pendingBytes"]/1e9:.2f} GB')
    print(table)


if __name__ == '__main__':
    main()
