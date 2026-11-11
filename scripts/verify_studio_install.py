"""Download official Studio independently and perform a disposable offline slice."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT/'Harness'))
from resolve_bambu_profiles import write_candidate
from printlab import core, inspection, slicer_guard

VERSION = '02.08.02.61'
ASSETS = {
    'darwin': ('Bambu_Studio_mac-v02.08.02.61-20260820225108.dmg',
               'cf648a95858fb630e1353c4987038df60d6caab693f18411fb95fb809f2d6926'),
    'win32': ('Bambu_Studio_win-v02.08.02.61-20260820225108.zip',
              '3faaa194a90a2e7defa39a6a63f5a654b8cdb762c6a98556cf771fba582229f5'),
}


def main():
    output = ROOT/'Runtime/verification'
    output.mkdir(parents=True, exist_ok=True)
    filename, expected = ASSETS[sys.platform]
    with tempfile.TemporaryDirectory(prefix='PrintLab Studio 中文 ') as temporary:
        root = Path(temporary)
        archive = root/filename
        url = f'https://github.com/bambulab/BambuStudio/releases/download/v{VERSION}/{filename}'
        with urllib.request.urlopen(url, timeout=180) as response, archive.open('wb') as target:
            while chunk := response.read(1024*1024):
                target.write(chunk)
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == expected, 'Studio package hash mismatch'
        mounted = False
        try:
            if sys.platform == 'darwin':
                mount = root/'mounted'
                subprocess.run(['hdiutil', 'attach', str(archive), '-nobrowse', '-readonly',
                                '-mountpoint', str(mount)], check=True, capture_output=True, timeout=120)
                mounted = True
                contents = mount/'BambuStudio.app/Contents'
                executable = contents/'MacOS/BambuStudio'
                profiles = contents/'Resources/profiles'
            else:
                extracted = root/'application'
                with zipfile.ZipFile(archive) as package:
                    package.extractall(extracted)
                executables = [path for path in extracted.rglob('*.exe') if path.name.lower() == 'bambu-studio.exe']
                assert len(executables) == 1, 'Expected one official Studio executable'
                executable = executables[0]
                profiles = executable.parent/'resources/profiles'
            result = slice_probe(root, executable, profiles, output)
            result.update(ok=True, os=sys.platform, studio_version=VERSION, package_sha256=expected,
                          printer_contacted=False, gui_login_verified=False,
                          installation='Official DMG mounted read-only' if mounted else 'Official portable ZIP extracted')
            (output/'studio-install.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
            print(json.dumps(result))
        finally:
            if mounted:
                subprocess.run(['hdiutil', 'detach', str(mount)], check=True, capture_output=True, timeout=60)


def slice_probe(root, executable, profiles, output):
    selected = [('machine', 'Bambu Lab X2D 0.4 nozzle'),
                ('process', '0.20mm Standard @BBL X2D'),
                ('filament', 'Bambu PLA Basic @BBL X2D 0.4 nozzle')]
    for kind, name in selected:
        write_candidate(profiles/'BBL'/kind/(name+'.json'), root/(kind+'.json'))
    process = json.loads((root/'process.json').read_text(encoding='utf-8'))
    process['curr_bed_type'] = 'Textured PEI Plate'
    (root/'process.json').write_text(json.dumps(process), encoding='utf-8')
    vertices = [(0,0,0), (10,0,0), (10,10,0), (0,10,0), (0,0,4), (10,0,4), (10,10,4), (0,10,4)]
    faces = [(0,2,1), (0,3,2), (4,5,6), (4,6,7), (0,1,5), (0,5,4),
             (1,2,6), (1,6,5), (2,3,7), (2,7,6), (3,0,4), (3,4,7)]
    with (root/'probe.stl').open('wb') as mesh:
        mesh.write(b'PrintLab disposable installation probe'.ljust(80, b' '))
        mesh.write(struct.pack('<I', len(faces)))
        for face in faces:
            coordinates = [coordinate for index in face for coordinate in vertices[index]]
            mesh.write(struct.pack('<12fH', 0, 0, 0, *coordinates, 0))
    artifact = root/'probe.gcode.3mf'
    command = [str(executable), '--datadir', str(root/'settings'), '--load-settings',
               str(root/'machine.json')+';'+str(root/'process.json'), '--load-filaments',
               str(root/'filament.json'), '--arrange', '1', '--slice', '1',
               '--export-3mf', str(artifact), str(root/'probe.stl')]
    with (output/'studio-slicing.log').open('w', encoding='utf-8') as log:
        subprocess.run(command, check=True, stdout=log, stderr=log, timeout=180)
    previous_root = core.ROOT
    try:
        core.ROOT = root
        core.write_json(root/'Runtime/config.json', {'slicer_profiles_path': str(profiles)})
        metadata = core.slice_metadata(artifact)
        assert metadata['sliced_printer_model'] == 'Bambu Lab X2D'
        assert metadata['curr_bed_type'] == 'Textured PEI Plate'
        assert metadata['sliced_filament_types'] == ['PLA']
        audit = slicer_guard.assert_safe_archive(artifact, 1)
        inspected = inspection.inspect(root, {'artifact': artifact.name,
                                              'artifact_sha256': core.digest(artifact), 'plate': 1})
        assert inspected['ok'] and inspected['executed'] is False
        return {'slice': metadata, 'startup_audit': audit, 'public_file_inspection': True}
    finally:
        core.ROOT = previous_root


if __name__ == '__main__':
    main()
