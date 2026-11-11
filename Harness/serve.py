#!/usr/bin/env python3
"""One service process, loopback + explicit private Tailscale listeners.

Direct sockets preserve WebSockets/camera streaming. Never binds 0.0.0.0.
"""
import argparse
import ipaddress
import json
import os
import socket
import subprocess
import sys
from pathlib import Path
import uvicorn

ROOT = Path(__file__).resolve().parent.parent


def main():
    p = argparse.ArgumentParser()
    p.add_argument('service', choices=['studio', 'bambuddy'])
    p.add_argument('--port', type=int, help='Override the default service port')
    args = p.parse_args()
    port = args.port if args.port is not None else (8018 if args.service == 'studio' else 8017)
    if not 1 <= port <= 65535:
        p.error('port must be between 1 and 65535')
    if args.service == 'studio':
        os.environ['PRINTLAB_STUDIO_PORT'] = str(port)
    module = 'printlab.api:app' if args.service == 'studio' else 'backend.app.main:app'
    sys.path.insert(0, str(ROOT / ('Harness' if args.service == 'studio' else 'Runtime/vendor/bambuddy')))
    hosts = ['127.0.0.1']
    try:
        # macOS app CLI can be unavailable to launchd even while Tailscale is online.
        # The installer records the observed address; it is not a public bind.
        cfg = json.loads((ROOT/'Runtime/config.json').read_text())
        ip = cfg.get('tailscale_ip')
        if not ip:
            raise ValueError('No remote listener configured')
        if ipaddress.ip_address(ip) in ipaddress.ip_network('100.64.0.0/10'):
            hosts.append(ip)
    except (OSError, ValueError, subprocess.SubprocessError):
        print('Listening on localhost only.',flush=True)
    sockets=[]
    try:
        for host in hosts:
            sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            try:
                sock.bind((host,port));sock.listen(2048);sockets.append(sock)
            except OSError:
                sock.close()
                if host == '127.0.0.1':raise
                print('Private Tailscale address not available; restart when network returns.',flush=True)
        config=uvicorn.Config(module,loop='asyncio',host='127.0.0.1',port=port,proxy_headers=False)
        uvicorn.Server(config).run(sockets=sockets)
    finally:
        for sock in sockets:sock.close()


if __name__=='__main__':
    main()
