"""Exercise the compiled macOS helper's actual IPC parser. Never asks for permissions or sends."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--helper', required=True, type=Path)
    args = parser.parse_args()
    helper = args.helper.resolve(strict=True)
    cases = ['canonical', 'system_alias', 'stale', 'loose_file', 'loose_parent',
             'file_symlink', 'parent_symlink', 'existing_response', 'dangling_response']
    # macOS CI may redirect TMPDIR outside /private. Exercise the actual alias
    # under /tmp regardless of the runner's unrelated temporary directory.
    with tempfile.TemporaryDirectory(prefix='PrintLab IPC tests ', dir='/tmp') as temporary:
        root = Path(temporary).resolve()
        for case in cases:
            private = root / case
            private.mkdir(mode=0o700)
            request = private / 'request.json'
            response = private / 'response.json'
            identity = str(uuid.uuid4())
            request.write_text(json.dumps({'request_id': identity,
                'created_at': time.time() - (200 if case == 'stale' else 0), 'args': ['probe']}))
            request.chmod(0o600)
            if case == 'system_alias':
                # Foundation canonicalizes these in the opposite direction to
                # pathlib.resolve. Both spellings of a real private dir work.
                assert str(root).startswith('/private/'), root
                request = Path(str(request).removeprefix('/private'))
                response = Path(str(response).removeprefix('/private'))
            elif case == 'loose_file':
                request.chmod(0o644)
            elif case == 'loose_parent':
                private.chmod(0o755)
            elif case == 'file_symlink':
                actual = private / 'actual.json'
                request.rename(actual)
                request.symlink_to(actual)
            elif case == 'parent_symlink':
                alias = root / 'linked-parent'
                alias.symlink_to(private, target_is_directory=True)
                request, response = alias / 'request.json', alias / 'response.json'
            elif case == 'existing_response':
                response.write_text('must stay unchanged')
            elif case == 'dangling_response':
                response.symlink_to(private / 'missing-target')
            result = subprocess.run([str(helper), '--ipc', str(request), str(response)],
                                    capture_output=True, text=True, timeout=20)
            if case in {'canonical', 'system_alias'}:
                assert result.returncode == 0, (case, result.stdout, result.stderr)
                data = json.loads(response.read_text())
                assert data['ok'] and data['request_id'] == identity
                assert response.stat().st_mode & 0o777 == 0o600
                assert 'command_sent' not in data
            else:
                assert result.returncode != 0, case
                assert json.loads(result.stdout)['ok'] is False, case
                if case == 'existing_response':
                    assert response.read_text() == 'must stay unchanged'
                elif case == 'dangling_response':
                    assert response.is_symlink() and not response.exists()
                else:
                    assert not response.exists(), case
            print(json.dumps({'case': case, 'passed': True}), flush=True)
    print(json.dumps({'ok': True, 'cases': len(cases), 'printer_contacted': False}))


if __name__ == '__main__':
    main()
