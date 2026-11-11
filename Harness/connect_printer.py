#!/usr/bin/env python3
"""Register the user-identified local X2D in Bambuddy and read status. Never prints."""
import argparse
import ipaddress
import json
import os
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ip', required=True, help='IP read by the user from the printer screen')
    args = parser.parse_args()
    address = ipaddress.ip_address(args.ip)
    if not address.is_private or address.is_loopback or address.is_multicast:
        parser.error('Use the private LAN address shown on the actual printer')
    private = ROOT / 'Runtime/private'
    saved = json.loads((private / 'printer-discovery.json').read_text())
    admin = json.loads((private / 'bambuddy-admin.json').read_text())
    cfgpath = ROOT / 'Runtime/config.json'
    cfg = json.loads(cfgpath.read_text())
    with httpx.Client(base_url=cfg['bambuddy_url'] + '/api/v1/', trust_env=False, timeout=20) as c:
        result = c.post('auth/login', json=admin); result.raise_for_status()
        c.headers['Authorization'] = 'Bearer ' + result.json()['access_token']
        result = c.get('printers/'); result.raise_for_status()
        existing = [p for p in result.json() if p.get('serial_number') == saved['serial']]
        if existing:
            printer = existing[0]
            if printer.get('ip_address') != args.ip:
                raise RuntimeError('An existing printer has another address; inspect before modifying its connection')
        else:
            result = c.post('printers/', json={'name':'PrintLab X2D','model':'X2D','ip_address':args.ip,
                'serial_number':saved['serial'],'access_code':saved['access_code'],'auto_archive':True})
            result.raise_for_status(); printer = result.json()
        cfg['printer_id'] = printer['id']; cfgpath.write_text(json.dumps(cfg,indent=2)+'\n')
        saved['ip_address'] = args.ip
        (private / 'printer-discovery.json').write_text(json.dumps(saved));os.chmod(private / 'printer-discovery.json',0o600)
        status = {}
        for _ in range(8):
            result = c.get(f"printers/{printer['id']}/status");result.raise_for_status();status=result.json()
            if status.get('connected'):break
            time.sleep(2)
        # Raw status may contain identifiers; keep it in the private area.
        target = private / 'printer-first-status.json'; target.write_text(json.dumps(status,ensure_ascii=False,indent=2));os.chmod(target,0o600)
        print(json.dumps({'registered':True,'printer_id':printer['id'],'connected':status.get('connected',False),
            'state':status.get('state'),'firmware_version':status.get('firmware_version'),
            'ams_count':len(status.get('ams') or []),'physical_print_performed':False},ensure_ascii=False))


if __name__ == '__main__':
    main()
