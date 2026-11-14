"""Actual sockets and CLI startup: a second workspace cannot share the port."""
import errno
from pathlib import Path
import socket
import subprocess
import sys

import pytest
import serve


@pytest.mark.parametrize('reuse_address', [False, True])
def test_listener_rejects_second_process(reuse_address):
    probe = '''
import socket, sys
with socket.socket() as sock:
    if sys.argv[2] == 'True':
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(('127.0.0.1', int(sys.argv[1])))
        sock.listen(1)
    except OSError as error:
        print(error.errno)
        sys.exit(7)
'''
    with serve.listening_socket('127.0.0.1', 0) as listener:
        port = listener.getsockname()[1]
        result = subprocess.run([sys.executable, '-c', probe, str(port), str(reuse_address)],
                                capture_output=True, text=True, timeout=10)
        assert result.returncode == 7, result.stderr
        assert int(result.stdout) in {errno.EADDRINUSE, errno.EACCES, 10048, 10013}


def test_cli_refuses_occupied_port_before_loading_workspace():
    with serve.listening_socket('127.0.0.1', 0) as listener:
        port = listener.getsockname()[1]
        result = subprocess.run([sys.executable, str(Path(serve.__file__)), 'studio', '--port', str(port)],
                                capture_output=True, text=True, timeout=10)
        assert result.returncode == 1
        assert f'Cannot listen on 127.0.0.1:{port}' in result.stderr
        assert 'use --port' in result.stderr
        assert 'Application startup' not in result.stderr


def test_listener_can_restart_on_released_port():
    with serve.listening_socket('127.0.0.1', 0) as listener:
        port = listener.getsockname()[1]
    with serve.listening_socket('127.0.0.1', port) as restarted:
        assert restarted.getsockname() == ('127.0.0.1', port)
