"""Build and slice disposable projects through the normal CLI. Never connects a printer."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'Harness'))
from resolve_bambu_profiles import write_candidate

MACHINES = [('A1', 'A1', 'A1'), ('A1 mini', 'A1M', 'A1M'),
            ('P1S', 'X1C', 'P1S 0.4 nozzle'), ('X1 Carbon', 'X1C', 'X1C')]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cad-python', required=True)
    parser.add_argument('--blender', required=True)
    parser.add_argument('--slicer', required=True)
    parser.add_argument('--profiles', required=True)
    args = parser.parse_args()
    output = ROOT / 'Runtime/verification'
    output.mkdir(parents=True, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory(prefix='PrintLab machine matrix ') as temporary:
        workspace = Path(temporary).resolve()
        (workspace / 'Runtime').mkdir()
        config = {'cad_python': args.cad_python, 'blender_path': args.blender,
                  'slicer_path': args.slicer, 'slicer_profiles_path': args.profiles,
                  'printer_id': None}
        (workspace / 'Runtime/config.json').write_text(json.dumps(config), encoding='utf-8')
        environment = {**os.environ, 'PRINTLAB_ROOT': str(workspace),
                       'PYTHONPATH': str(ROOT / 'Harness'), 'PYTHONUTF8': '1'}
        def call(*arguments):
            result = subprocess.run([sys.executable, '-m', 'printlab.cli', *arguments],
                env=environment, capture_output=True, text=True, encoding='utf-8', timeout=600)
            if result.returncode:
                for logfile in workspace.rglob('*.log'):
                    destination = output / 'machine-matrix-failure' / logfile.relative_to(workspace)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(logfile, destination)
                raise RuntimeError(f'{arguments[0]} failed: {result.stderr}')
            return json.loads(result.stdout)

        for model, process, filament in MACHINES:
            project = call('new', f'{model} 软件验收', '--brief', '离线测试，实际设备与耗材尚未配置')
            directory = workspace / 'Project' / f"{project['id']}-{project['slug']}"
            design = directory / 'Design/v001'
            design.mkdir()
            (design / 'model.py').write_text(
                'import cadquery as cq\ndef build(params):\n    return cq.Workplane("XY").box(10, 10, 4)\n', encoding='utf-8')
            (design / 'params.json').write_text(json.dumps({'expected_dimensions_mm': [10, 10, 4]}), encoding='utf-8')
            card = call('workspace', 'show', 'device')
            changes = workspace / 'device-facts.json'
            changes.write_text(json.dumps({'model': model}), encoding='utf-8')
            updated = call('workspace', 'device', '--file', str(changes), '--source', 'Isolated software fixture',
                           '--expect-sha', card['sha256'] or 'missing')
            call('workspace', 'profile', '--name', f'Bambu Lab {model} 0.4 nozzle', '--expect-sha', updated['sha256'])
            call('constraints', 'capture', project['id'], '--source', 'Offline matrix fixture', '--expect-sha', 'missing')
            build = call('build', project['id'], '--revision', 'v001', '--engine', 'cadquery')
            assert build['verified'] and build['checks']['within_configured_print_volume']
            presets = directory / 'Review/profiles'
            presets.mkdir()
            for kind, name in [('machine', f'Bambu Lab {model} 0.4 nozzle'),
                               ('process', f'0.20mm Standard @BBL {process}'),
                               ('filament', f'Bambu PLA Basic @BBL {filament}')]:
                write_candidate(Path(args.profiles) / 'BBL' / kind / (name + '.json'), presets / (kind + '.json'))
            job = call('slice', project['id'], '--machine', str(presets / 'machine.json'),
                       '--process', str(presets / 'process.json'), '--filament', str(presets / 'filament.json'),
                       '--bed-type', 'Textured PEI Plate')
            assert job['startup_audit']['ok'] and job['trial_only']
            assert job['sliced_printer_model'] == f'Bambu Lab {model}'
            assert not list(directory.rglob('approval.json')) and not list(directory.rglob('dispatch.json'))
            evidence = output / 'machine-matrix' / model.replace(' ', '-')
            evidence.mkdir(parents=True, exist_ok=True)
            for name in ('build.json', 'model.stl'):
                shutil.copy2(directory / 'Exports/v001' / name, evidence / name)
            shutil.copy2(directory / 'Print' / job['id'] / job['artifact'], evidence / 'offline-probe.gcode.3mf')
            result = {'model': model, 'build_verified': build['verified'],
                      'envelope_mm': build['target_build_envelope']['dimensions_mm'],
                      'slice_model': job['sliced_printer_model'], 'startup_check': job['startup_audit']['ok'],
                      'trial_only': job['trial_only'], 'printer_contacted': False}
            results.append(result)
            print(json.dumps(result), flush=True)
    (output / 'machine-matrix.json').write_text(json.dumps({'ok': True, 'results': results}, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
