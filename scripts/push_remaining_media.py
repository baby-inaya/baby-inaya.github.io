"""Resume verified <=200 MB batches to main without changing the working index.

Run --prepare first, inspect qa-output/main-upload/plan.json, then --run.
Files over 100 MiB are reported, never split, deleted, or uploaded to paid LFS.
The first commit protects the bounded Pages gallery with Jekyll exclusions.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / 'qa-output/main-upload'
BASE = '9517664a67512e1fdf25cf23bf70654fcece90e4'
BUDGET = 200_000_000
MAX_FILE = 100 * 1024 * 1024
INDEX = STATE / 'index'
REF = 'refs/heads/main'


def git(*args, data=None, indexed=False, check=True):
    env = os.environ.copy()
    if indexed:
        env['GIT_INDEX_FILE'] = str(INDEX)
    env['GIT_TERMINAL_PROMPT'] = '0'
    result = subprocess.run(['git', '-c', 'core.autocrlf=false', '-c', 'gc.auto=0', *args],
                            cwd=ROOT, env=env, input=data, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, check=False)
    if check and result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace')[-4000:])
    return result


def save(name, data):
    path = STATE / name
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def tree_files(ref):
    entries = git('ls-tree', '-r', '-z', ref).stdout.decode().split('\0')
    return {entry.split('\t', 1)[1]: entry.split()[2] for entry in entries if entry}


def blob(data):
    return git('hash-object', '-w', '--stdin', data=data).stdout.decode().strip()


def set_entries(entries):
    data = ''.join(f'100644 {oid}\t{path}\0' for path, oid in entries.items()).encode()
    git('update-index', '-z', '--index-info', indexed=True, data=data)


def remote_main():
    return git('ls-remote', 'origin', REF).stdout.decode().split()[0]


def prepare():
    STATE.mkdir(parents=True, exist_ok=True)
    if (STATE / 'plan.json').exists():
        raise RuntimeError('An upload plan already exists; resume it with --run')
    baseline = tree_files(BASE)
    files = []
    for path in ROOT.rglob('*'):
        relative = path.relative_to(ROOT).as_posix()
        if relative.split('/')[0] in {'.git', 'qa-output'} or '__pycache__' in path.parts:
            continue
        if not path.is_file() or path.suffix in {'.log', '.pid', '.pyc'}:
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            raise RuntimeError('Unsafe source path: ' + relative)
        files.append((relative, path.stat().st_size))
    # The real file-size limit is 100 MiB, not 100 decimal MB.
    held = [{'path': path, 'bytes': size, 'reason': 'Exceeds GitHub 100 MiB; LFS allowance unverified'}
            for path, size in files if size > MAX_FILE]
    eligible = [(path, size) for path, size in files if size <= MAX_FILE]
    paths = '\0'.join(path for path, _ in eligible).encode() + b'\0'
    # Hash without writing objects yet. The index stays untouched.
    hashes = []
    for path, size in eligible:
        oid = git('hash-object', '--no-filters', '--', path).stdout.decode().strip()
        hashes.append((path, size, oid))
    pending = [{'path': path, 'bytes': size, 'oid': oid} for path, size, oid in hashes
               if baseline.get(path) != oid and path not in {'index.html', '_config.yml', '.nojekyll'}]
    batches = []
    current = {'bytes': 0, 'files': []}
    for row in sorted(pending, key=lambda row: (row['bytes'], row['path'])):
        if current['bytes'] + row['bytes'] > BUDGET and current['files']:
            batches.append(current)
            current = {'bytes': 0, 'files': []}
        current['files'].append(row)
        current['bytes'] += row['bytes']
    if current['files']:
        batches.append(current)
    published = json.loads(git('show', BASE + ':media/library.json').stdout)
    public_js = git('show', BASE + ':media/library.js').stdout
    (STATE / 'published-library.js').write_bytes(public_js)
    html = (ROOT / 'index.html').read_text(encoding='utf-8').replace('src="media/library.js"', 'src="media/published-library.js"')
    (STATE / 'index.html').write_text(html, encoding='utf-8')
    allowed = {'index.html', 'style.css', 'script.js', 'media/published-library.js'}
    allowed.add('thumbnails/1af580a7280316cb42c928db.jpg')
    for item in published['items']:
        allowed.update(item[key] for key in ('src', 'thumbnail', 'playbackSrc') if item.get(key))
    excluded = sorted({path for path, _ in files if path not in allowed} |
                      {path for path in baseline if path not in allowed} |
                      {'qa-output', 'lage_files', 'scripts', 'push_batches', 'node_modules', 'vendor',
                       'Gemfile', 'Gemfile.lock', 'UPLOAD-STATUS.md'})
    config = {'title': "Inaya's memory book", 'theme': None, 'plugins': [], 'exclude': excluded}
    (STATE / '_config.yml').write_text(json.dumps(config, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    allowed_bytes = sum((ROOT / path).stat().st_size for path in allowed if path != 'media/published-library.js') + len(public_js)
    assert allowed_bytes < 1_000_000_000
    plan = {'base': BASE, 'branch': 'main', 'batchBudgetBytes': BUDGET, 'batches': batches,
            'held': held, 'pendingBytes': sum(row['bytes'] for row in pending),
            'pendingFiles': len(pending), 'publishedBytes': allowed_bytes, 'publishedMemories': len(published['items'])}
    save('plan.json', plan)
    save('state.json', {'phase': 'prepared', 'completedBatches': 0, 'lastVerifiedRemote': BASE})
    print(json.dumps({k: v for k, v in plan.items() if k not in {'batches', 'held'}}, indent=2), flush=True)
    print(f'{len(batches)} batches; {len(held)} files require LFS allowance confirmation.', flush=True)


def commit(parent, message):
    tree = git('write-tree', indexed=True).stdout.decode().strip()
    name = git('log', '-1', '--format=%an', BASE).stdout.decode().strip()
    email = git('log', '-1', '--format=%ae', BASE).stdout.decode().strip()
    oid = git('-c', 'user.name=' + name, '-c', 'user.email=' + email,
              'commit-tree', tree, '-p', parent, data=message.encode()).stdout.decode().strip()
    old = git('rev-parse', REF).stdout.decode().strip()
    if git('merge-base', '--is-ancestor', old, parent, check=False).returncode:
        raise RuntimeError('Local main diverged; refusing to overwrite it')
    git('update-ref', REF, oid, old)
    return oid


def push(oid, state):
    current = remote_main()
    if current == oid:
        return
    if current != state['lastVerifiedRemote']:
        raise RuntimeError('Remote main changed independently; stopping safely')
    command = ['git', '-c', 'gc.auto=0', 'push', '--progress', 'origin', REF + ':' + REF]
    for attempt in range(3):
        print(f'Pushing {oid[:7]} (attempt {attempt + 1})', flush=True)
        result = subprocess.run(command, cwd=ROOT)
        if remote_main() == oid:
            return
        if result.returncode == 0:
            raise RuntimeError('Push returned success but remote verification failed')
        if attempt < 2:
            time.sleep(15 * (attempt + 1))
    raise RuntimeError('Push failed three times; the unpushed commit is preserved for resuming')


def run():
    plan = json.loads((STATE / 'plan.json').read_text(encoding='utf-8'))
    state = json.loads((STATE / 'state.json').read_text(encoding='utf-8'))
    original_index = hashlib.sha256((ROOT / '.git/index').read_bytes()).hexdigest()
    try:
        if state['phase'] == 'prepared':
            if remote_main() != plan['base']:
                raise RuntimeError('Remote main changed since planning')
            git('read-tree', plan['base'], indexed=True)
            set_entries({path: blob((STATE / name).read_bytes()) for path, name in
                         [('index.html', 'index.html'), ('_config.yml', '_config.yml'),
                          ('media/published-library.js', 'published-library.js')]})
            git('update-index', '--force-remove', '--', '.nojekyll', indexed=True)
            oid = commit(plan['base'], 'Keep the published gallery bounded during same-branch media uploads\n')
            state.update(phase='guard-pending', pendingCommit=oid)
            save('state.json', state)
        if state['phase'] == 'guard-pending':
            push(state['pendingCommit'], state)
            state.update(phase='guard-pushed', lastVerifiedRemote=state.pop('pendingCommit'))
            save('state.json', state)
            print('PAGES GUARD PUSHED. Verify the Pages build, then run --approve-guard.', flush=True)
            return
        if state['phase'] == 'guard-pushed':
            print('Waiting for --approve-guard after verifying the Pages deployment.', flush=True)
            return
        if state['phase'] == 'batch-pending':
            push(state['pendingCommit'], state)
            state.update(phase='uploading', completedBatches=state['completedBatches'] + 1,
                         lastVerifiedRemote=state.pop('pendingCommit'))
            save('state.json', state)
        for number in range(state['completedBatches'], len(plan['batches'])):
            batch = plan['batches'][number]
            if remote_main() != state['lastVerifiedRemote']:
                raise RuntimeError('Remote main changed independently')
            git('read-tree', state['lastVerifiedRemote'], indexed=True)
            entries = {}
            for row in batch['files']:
                path = ROOT / row['path']
                if path.stat().st_size != row['bytes']:
                    raise RuntimeError('Source changed: ' + row['path'])
                oid = git('hash-object', '-w', '--no-filters', '--', row['path']).stdout.decode().strip()
                if oid != row['oid']:
                    raise RuntimeError('Source content changed: ' + row['path'])
                entries[row['path']] = oid
            assert batch['bytes'] <= BUDGET
            set_entries(entries)
            message = f'Add remaining media batch {number + 1:02} of {len(plan["batches"]):02} [skip ci]\n\n{len(entries)} files; {batch["bytes"]:,} source bytes. Pages gallery unchanged.\n'
            oid = commit(state['lastVerifiedRemote'], message)
            state.update(phase='batch-pending', pendingCommit=oid)
            save('state.json', state)
            print(f'BATCH {number + 1}/{len(plan["batches"])}: {len(entries)} files, {batch["bytes"]/1e6:.2f} MB', flush=True)
            push(oid, state)
            state.update(phase='uploading', completedBatches=number + 1, lastVerifiedRemote=state.pop('pendingCommit'))
            save('state.json', state)
            print(f'VERIFIED BATCH {number + 1}/{len(plan["batches"])}: {oid}', flush=True)
        state['phase'] = 'regular-files-complete'
        save('state.json', state)
        print(f'All regular-file batches verified on main. {len(plan["held"])} oversized files remain local.', flush=True)
    except Exception as error:
        state['lastError'] = str(error)
        save('state.json', state)
        raise
    finally:
        assert hashlib.sha256((ROOT / '.git/index').read_bytes()).hexdigest() == original_index


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare', action='store_true')
    group.add_argument('--run', action='store_true')
    group.add_argument('--approve-guard', action='store_true')
    args = parser.parse_args()
    if args.prepare:
        prepare()
    elif args.approve_guard:
        state = json.loads((STATE / 'state.json').read_text())
        assert state['phase'] == 'guard-pushed'
        state['phase'] = 'uploading'
        save('state.json', state)
        run()
    else:
        run()
