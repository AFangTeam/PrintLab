"""Initialize an empty local workspace while preserving every existing file."""
from __future__ import annotations
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def write_new(path, value, private=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = 0o600 if private else 0o644
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    except FileExistsError:
        return False
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    return True


def main():
    for folder in ('Project', 'Runtime/private', 'Runtime/logs', 'Library/Devices/X2D',
                   'Library/Materials', 'Library/References', 'Library/Shopping',
                   'Library/Taste/Selections', 'Library/Prepared', 'Context'):
        (ROOT / folder).mkdir(parents=True, exist_ok=True)
    (ROOT / 'Runtime/private').chmod(0o700)
    for name in ('profile.md', 'taste.md', 'agent-policy.json'):
        destination = ROOT / 'Context' / name
        if not destination.exists():
            with destination.open('x', encoding='utf-8') as stream:
                stream.write((ROOT / 'config' / (name + '.example')).read_text())
    write_new(ROOT / 'Runtime/config.json', {
        'bambuddy_url': 'http://127.0.0.1:8017', 'printer_id': None,
        'cad_python': str(ROOT / 'Runtime/venv/bin/python'),
        'blender_path': '/Applications/Blender.app/Contents/MacOS/Blender',
        'slicer_path': '/Applications/BambuStudio.app/Contents/MacOS/BambuStudio',
        'studio_printer_name': None, 'tailscale_ip': None,
    })
    write_new(ROOT / 'Runtime/private/bambuddy.json', {'read_api_key': '', 'write_api_key': ''}, private=True)
    write_new(ROOT / 'Library/Devices/X2D/device.json', {
        'schema_version': 1, 'name': '待配置的拓竹打印机', 'model': None,
        'verification_status': 'unconfigured', 'user_confirmed': {},
        'installed': {}, 'unverified': ['机型、喷嘴、打印板、供料连接与材料待核对'],
    })
    installed = ROOT / 'Library/Devices/X2D/installed.md'
    if not installed.exists():
        installed.write_text('# 本机设备\n\n尚未连接。按 docs/SETUP.md 核对设备与耗材。\n')
    print('工作空间已初始化，现有配置与项目已保留。')


if __name__ == '__main__':
    main()
