"""Host paths and private-directory permissions for desktop workspaces."""
import csv
import os
from pathlib import Path
import shutil
import subprocess
import sys


def venv_python(directory):
    return Path(directory) / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')


def tool_defaults():
    if sys.platform == 'win32':
        programs = Path(os.environ.get('ProgramFiles', 'C:/Program Files'))
        slicer = shutil.which('bambu-studio.exe') or str(programs / 'Bambu Studio/bambu-studio.exe')
        blenders = sorted((programs / 'Blender Foundation').glob('Blender */blender.exe'), reverse=True)
        blender = shutil.which('blender.exe') or str(next(iter(blenders), programs / 'Blender Foundation/Blender/blender.exe'))
        return {'slicer_path': slicer, 'blender_path': blender,
                'slicer_profiles_path': str(Path(slicer).parent / 'resources/profiles')}
    return {'slicer_path': '/Applications/BambuStudio.app/Contents/MacOS/BambuStudio',
            'blender_path': '/Applications/Blender.app/Contents/MacOS/Blender',
            'slicer_profiles_path': '/Applications/BambuStudio.app/Contents/Resources/profiles'}


def profile_directory(config):
    if config.get('slicer_profiles_path'):
        return Path(config['slicer_profiles_path'])
    if sys.platform == 'win32' and config.get('slicer_path'):
        return Path(config['slicer_path']).parent / 'resources/profiles'
    return Path(tool_defaults()['slicer_profiles_path'])


def protect_directory(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform != 'win32':
        path.chmod(0o700)
        return
    identity = subprocess.check_output(['whoami', '/user', '/fo', 'csv', '/nh'], text=True)
    sid = next(csv.reader(identity.splitlines()))[1]
    subprocess.run(['icacls', str(path), '/inheritance:r', '/grant:r',
                    f'*{sid}:(OI)(CI)F', '*S-1-5-18:(OI)(CI)F'],
                   check=True, capture_output=True)
