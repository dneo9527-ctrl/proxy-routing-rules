"""Trusted, manually installed data publisher; never execute code from a checkout."""
import argparse
import ctypes
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import urllib.request

KINDS = ("reject", "direct", "residential", "proxy")
DOMAIN = re.compile(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
SHA = re.compile(r"[0-9a-f]{40}\Z")
BASE = Path('/opt/1panel/www/sites/3x-panel/index/routing')
DATA = Path('/opt/1panel/data/routing-rules-sync')
RELEASES = DATA / 'releases'
STATE = DATA / 'state.json'
PUBLIC = 'https://x.dvp.us.ci:2053/routing/'
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_file(path, limit=262144):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError('Invalid rule data file')
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Oversized rule data')
    return data


def parse(text):
    rules = []
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith(("#", "//", ";")):
            continue
        parts = line.split(',')
        if len(parts) != 2 or parts[0] not in ('DOMAIN', 'DOMAIN-SUFFIX'):
            raise ValueError('Line %d: invalid rule syntax' % number)
        if not DOMAIN.fullmatch(parts[1]):
            raise ValueError('Line %d: invalid domain' % number)
        rule = tuple(parts)
        if rule in rules:
            raise ValueError('Duplicate rule at line %d' % number)
        rules.append(rule)
    if not rules:
        raise ValueError('Empty ruleset')
    return rules


def overlaps(a, b):
    return (a[1] == b[1] or
            (a[0] == 'DOMAIN-SUFFIX' and b[1].endswith('.' + a[1])) or
            (b[0] == 'DOMAIN-SUFFIX' and a[1].endswith('.' + b[1])))


def validate(texts):
    parsed = {kind: parse(texts[kind]) for kind in KINDS}
    for index, kind in enumerate(KINDS):
        for other in KINDS[index + 1:]:
            if any(overlaps(a, b) for a in parsed[kind] for b in parsed[other]):
                raise ValueError('Cross-list overlap: %s/%s' % (kind, other))
    return parsed


def read_bundle(bundle):
    source = bundle / 'rules'
    if source.is_symlink() or not source.is_dir():
        raise ValueError('Rules directory must be a real directory')
    data = {kind: read_file(source / (kind + '.list')) for kind in KINDS}
    texts = {kind: value.decode('utf-8') for kind, value in data.items()}
    if sum(len(text.splitlines()) for text in texts.values()) > 4096:
        raise ValueError('Too many domain rules')
    parsed = validate(texts)
    manifest = json.loads(read_file(bundle / 'manifest.json'))
    if manifest.get('schema') != 1 or set(manifest['rules']) != set(KINDS):
        raise ValueError('Invalid manifest')
    for kind in KINDS:
        item = manifest['rules'][kind]
        if (item['path'] != 'rules/' + kind + '.list' or
                item['sha256'] != digest(data[kind]) or
                item['count'] != len(parsed[kind])):
            raise ValueError('Manifest mismatch: ' + kind)
    provenance = json.loads(read_file(bundle / 'publication.json'))
    if (provenance.get('schema') != 1 or
            not SHA.fullmatch(provenance.get('source_commit', '')) or
            type(provenance.get('workflow_run')) is not int or provenance['workflow_run'] <= 0):
        raise ValueError('Invalid CI provenance')
    return data, provenance


def verify_ci(provenance):
    request = urllib.request.Request(
        'https://api.github.com/repos/dneo9527-ctrl/proxy-routing-rules/actions/runs/'
        + str(provenance['workflow_run']),
        headers={'User-Agent': 'personal-routing-sync', 'Accept': 'application/vnd.github+json'})
    with OPENER.open(request, timeout=20) as response:
        result = json.loads(response.read(1048576))
    if not (result.get('head_sha') == provenance['source_commit'] and
            result.get('head_branch') == 'main' and
            result.get('path') == '.github/workflows/validate.yml' and
            result.get('event') in ('push', 'workflow_dispatch') and
            result.get('status') == 'completed' and result.get('conclusion') == 'success'):
        raise ValueError('Source CI is not successful; keep previous rules')


def atomic_write(path, content, mode=0o644):
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def public_check(data):
    for kind in KINDS:
        request = urllib.request.Request(PUBLIC + kind + '.list', headers={'Cache-Control': 'no-cache'})
        with OPENER.open(request, timeout=15) as response:
            if response.status != 200 or response.read(262145) != data[kind]:
                raise ValueError('Public verification failed: ' + kind)


def atomic_json(path, value):
    temporary = path.with_suffix('.tmp')
    try:
        with temporary.open('w') as stream:
            json.dump(value, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def exchange(a, b):
    """Atomically exchange two directories on the same filesystem."""
    libc = ctypes.CDLL(None, use_errno=True)
    if hasattr(libc, 'renameat2'):
        function = libc.renameat2
        function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        result = function(-100, os.fsencode(a), -100, os.fsencode(b), 2)
    elif hasattr(libc, 'renamex_np'):
        function = libc.renamex_np
        function.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        result = function(os.fsencode(a), os.fsencode(b), 2)
    else:
        raise RuntimeError('Atomic directory exchange is unavailable')
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def hashes(base):
    return {k: digest(read_file(base / (k + '.list'))) for k in KINDS}


def recover(base):
    pending = STATE.with_name('pending.json')
    if pending.exists():
        item = json.loads(pending.read_text())
        stage = Path(item['stage'])
        if stage.parent != base.parent or not stage.name.startswith('.routing-next-') or stage.is_symlink():
            raise ValueError('Invalid recovery directory')
        live = hashes(base)
        if live == item['new_hashes'] and stage.exists():
            if hashes(stage) != item['old_hashes']:
                raise ValueError('Recovery backup mismatch')
            exchange(base, stage)
        elif live != item['old_hashes']:
            raise ValueError('Rules changed during interrupted publication')
        # Restore matching state as well when interrupted after the state write.
        if item['state_before']:
            atomic_json(STATE, item['state_before'])
        else:
            STATE.unlink(missing_ok=True)
        pending.unlink()
        if stage.exists():
            shutil.rmtree(stage)


def publish(bundle, sha, base=BASE, verify=public_check, ci=verify_ci):
    if not SHA.fullmatch(sha):
        raise ValueError('Invalid release SHA')
    recover(base)
    data, provenance = read_bundle(bundle)
    ci(provenance)
    RELEASES.mkdir(parents=True, exist_ok=True)
    current = {kind: read_file(base / (kind + '.list')) for kind in KINDS}
    state_before = json.loads(STATE.read_text()) if STATE.exists() else {}
    if state_before:
        verify_current(base)
    previous_id = state_before.get('release_commit', 'bootstrap-' + datetime.date.today().strftime('%Y%m%d'))
    previous_backup = RELEASES / previous_id
    if not previous_backup.exists():
        previous_backup.mkdir(parents=True)
        for kind, content in current.items():
            atomic_write(previous_backup / (kind + '.list'), content)
    target = RELEASES / sha
    if target.exists():
        if target.is_symlink() or any(read_file(target / (k + '.list')) != data[k] for k in KINDS):
            raise ValueError('Existing release was changed')
    else:
        staging = Path(tempfile.mkdtemp(prefix='.staging-', dir=RELEASES))
        try:
            staging.chmod(0o755)
            for kind, content in data.items():
                path = staging / (kind + '.list')
                with path.open('wb') as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                path.chmod(0o644)
            atomic_json(staging / 'release.json', {'release_commit': sha, **provenance,
                'sha256': {k: digest(v) for k, v in data.items()}})
            staging.rename(target)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    pending = STATE.with_name('pending.json')
    stage = Path(tempfile.mkdtemp(prefix='.routing-next-', dir=base.parent))
    stage.chmod(0o755)
    for kind, content in data.items():
        atomic_write(stage / (kind + '.list'), content)
    atomic_json(pending, {'stage': str(stage), 'state_before': state_before,
                         'old_hashes': {k: digest(v) for k, v in current.items()},
                         'new_hashes': {k: digest(v) for k, v in data.items()}})
    try:
        exchange(base, stage)
        verify(data)
        state = {'release_commit': sha, **provenance,
                 'previous': previous_id,
                 'published_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 'sha256': {k: digest(v) for k, v in data.items()}}
        atomic_json(STATE, state)
        pending.unlink()
        shutil.rmtree(stage)
    except BaseException:
        recover(base)
        raise
    # Only prune our completed releases; retain current, previous and recent versions.
    keep = {sha, previous_id}
    if state.get('previous'):
        keep.add(state['previous'])
    candidates = sorted((p for p in RELEASES.iterdir() if SHA.fullmatch(p.name)
                         and p.is_dir() and not p.is_symlink() and (p / 'release.json').is_file()),
                        key=lambda p: p.stat().st_mtime, reverse=True)
    keep.update(p.name for p in candidates[:5])
    for path in candidates:
        if path.name not in keep:
            shutil.rmtree(path)
    return state


def verify_current(base=BASE):
    recover(base)
    state = json.loads(STATE.read_text())
    if not SHA.fullmatch(state['release_commit']):
        raise ValueError('Invalid current state')
    for kind in KINDS:
        if digest(read_file(base / (kind + '.list'))) != state['sha256'][kind]:
            raise ValueError('Current rules were changed outside GitHub')
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sha')
    parser.add_argument('--verify-current', action='store_true')
    args = parser.parse_args()
    if args.verify_current:
        state = verify_current()
    else:
        candidate = (DATA / 'git' / 'candidate').resolve(strict=True)
        if not candidate.is_relative_to((DATA / 'git').resolve()) or candidate.name != args.sha:
            raise ValueError('Candidate checkout does not match requested SHA')
        state = publish(candidate, args.sha)
    print(json.dumps({'status': 'verified', **state}))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__, 'detail': str(error)}))
        raise SystemExit(1)
