"""Inspect or stage one prepared batch without committing or pushing it."""
import argparse
import json
import subprocess
from build_media import ROOT, sha256_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('number', type=int)
    parser.add_argument('--stage', action='store_true')
    args = parser.parse_args()
    plan = json.loads((ROOT / 'push_batches/plan.json').read_text(encoding='utf-8'))
    batch = next((b for b in plan['batches'] if b['number'] == args.number), None)
    if batch is None:
        parser.error('Unknown batch number')
    paths = []
    total = 0
    for row in batch['files']:
        path = (ROOT / row['path']).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():
            raise ValueError('Missing or invalid file: ' + row['path'])
        if path.stat().st_size != row['bytes'] or sha256_file(path) != row['sha256']:
            raise ValueError('File changed; rebuild the batch plan: ' + row['path'])
        paths.append(row['path'])
        total += row['bytes']
    if args.number == 1:
        paths.extend(p.relative_to(ROOT).as_posix() for p in (ROOT / 'push_batches').rglob('*') if p.is_file())
        total += sum(p.stat().st_size for p in (ROOT / 'push_batches').rglob('*') if p.is_file())
    if total >= plan['batchLimitBytes']:
        raise ValueError('Batch exceeds its size budget')
    print(f'Batch {args.number:02}: {len(paths)} files, {total/1e6:.2f} MB; hashes verified.')
    if args.stage:
        if subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=ROOT).returncode:
            raise RuntimeError('The index already contains changes. Commit or unstage them first.')
        subprocess.run(['git', '--literal-pathspecs', 'add', '--pathspec-from-file=-',
                        '--pathspec-file-nul'], input=('\0'.join(paths)+'\0').encode(), cwd=ROOT, check=True)
        print('Staged only. Review and commit this batch before pushing it.')


if __name__ == '__main__':
    main()
