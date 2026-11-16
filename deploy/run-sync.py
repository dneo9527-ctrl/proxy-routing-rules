"""1Panel task entry point. git-sync downloads; a fixed publisher activates data."""
import fcntl
import json
import os
from pathlib import Path
import pwd
import re
import subprocess

ROOT = Path('/opt/1panel/tools/routing-rules-sync')
DATA = Path('/opt/1panel/data/routing-rules-sync')
BASE = Path('/opt/1panel/www/sites/3x-panel/index/routing')
REPO = 'https://github.com/dneo9527-ctrl/proxy-routing-rules.git'
IMAGE = 'registry.k8s.io/git-sync/git-sync@sha256:a20644562fba94773e594885cb001aadb5a3172175f13ac1215e5b2033c9200e'


def run(argv, timeout=120, capture=False):
    return subprocess.run(argv, timeout=timeout, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None).stdout


def main():
    with (ROOT / 'run.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({'status': 'skipped', 'reason': 'already_running'}))
            return
        account = pwd.getpwnam('routing-sync')
        remote = run(['runuser', '-u', 'routing-sync', '--', 'git', '-c', 'core.hooksPath=/dev/null',
                      'ls-remote', REPO, 'refs/heads/release'], timeout=30, capture=True).split()
        if len(remote) != 2 or not re.fullmatch('[0-9a-f]{40}', remote[0]):
            raise ValueError('No validated release branch')
        sha = remote[0]
        state_path = DATA / 'state.json'
        if state_path.exists():
            state = json.loads(state_path.read_text())
            if state.get('release_commit') == sha:
                run(['python3', str(ROOT / 'publisher.py'), '--verify-current'], timeout=10, capture=True)
                print(json.dumps({'status': 'unchanged', 'release_commit': sha}))
                return
        run(['docker', 'run', '--rm', '--name', 'routing-git-sync-once',
             '--user', str(account.pw_uid) + ':' + str(account.pw_gid),
             '--memory=128m', '--cpus=0.25', '--pids-limit=64', '--read-only',
             '--cap-drop=ALL', '--security-opt=no-new-privileges',
             '--tmpfs', '/tmp:rw,nosuid,nodev,size=32m,mode=1777',
             '--mount', 'type=bind,src=' + str(DATA / 'git') + ',dst=' + str(DATA / 'git'),
             IMAGE, '--repo=' + REPO, '--root=' + str(DATA / 'git'), '--link=candidate', '--ref=' + sha,
             '--depth=1', '--one-time', '--submodules=off', '--max-failures=0',
             '--sync-timeout=60s', '--stale-worktree-timeout=1h',
             '--git-config=core.hooksPath:/dev/null'], timeout=80)
        run(['python3', str(ROOT / 'publisher.py'), '--sha', sha], timeout=100)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__, 'detail': str(error)}))
        raise SystemExit(1)
