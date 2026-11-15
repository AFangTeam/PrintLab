import copy
import uuid

import httpx
import pytest

from printlab import bambuddy, core, native, prepared, queue_sender, studio_bridge, workbench
from test_prepared import setup


@pytest.fixture
def queue_setup(setup, monkeypatch):
    project, directory, job, base, _, write_archive, settings = setup
    job.update(sliced_printer_model='Bambu Lab A1')
    job['mapping'].update(transport='bambuddy_queue', extruder_mapping=[0])
    job['mapping'].pop('fts_installed')
    settings.update(physical_extruder_map=[0], printer_model='Bambu Lab A1')
    write_archive()
    job['artifact_sha256'] = core.digest(directory / job['artifact'])
    core.write_json(directory / 'job.json', job)
    core.write_json(core.ROOT / 'Library/Devices/X2D/device.json', {
        'model': 'A1', 'user_confirmed': {'build_plate_description': 'Textured PEI Plate'}})
    core.write_json(core.ROOT / 'Runtime/private/bambuddy.json', {'write_api_key': 'synthetic-test-only'})
    base.live.update(state='IDLE', awaiting_plate_clear=False, sdcard=True, ams_extruder_map={})
    base.live['nozzles'] = base.live['nozzles'][:1]

    class Client:
        def __init__(self):
            self.posts = []
            self.queue = None
            self.start_timeout = False
            self.metadata = {'id': 7, 'model': 'A1'}

        def get(self, path):
            if path == 'printers/7':
                return self.metadata
            if path == 'queue/':
                return [copy.deepcopy(self.queue)] if self.queue else []
            if path == 'queue/9':
                return copy.deepcopy(self.queue)
            return base.get(path)

        def post(self, path, **kwargs):
            self.posts.append(path)
            if path == 'library/files':
                return {'id': 8}
            if path == 'queue/':
                self.queue = {'id': 9, 'status': 'pending', **kwargs['json']}
                return self.queue
            if path == 'queue/9/start':
                if self.start_timeout:
                    raise httpx.ReadTimeout('Simulated uncertain queue response')
                self.queue.update(status='printing', manual_start=False)
                base.live.update(state='RUNNING', current_print='Jone.gcode')
                return {'ok': True}
            raise AssertionError(path)

        def close(self):
            pass

    client = Client()
    monkeypatch.setattr(bambuddy, 'Client', lambda *args, **kwargs: client)
    monkeypatch.setattr(native, 'run_client', lambda *args: {'ok': True, 'executed': False,
        'inspection': {'nozzleDiameters': [.4], 'nozzleTypes': ['hardened_steel']}})
    monkeypatch.setattr(studio_bridge, 'dispatch', lambda *args: pytest.fail('Queue route must use the queue adapter'))
    prepared.register('P001', 'Jone')
    return client, base, directory


def start_once():
    report = workbench.check('P001', 'Jone', owner='owner')
    assert report['ready'], report['blockers']
    operation = workbench.start('P001', 'Jone', owner='owner', check_token=report['check_token'],
        plate_clear=True, request_id=str(uuid.uuid4()), launch=workbench._run)
    return workbench.operation(operation['id'], 'owner')


def test_workbench_queue_starts_once_and_reads_exact_task(queue_setup):
    client, base, directory = queue_setup
    operation = start_once()
    assert operation['state'] == 'observed', operation
    assert client.posts == ['library/files', 'queue/', 'queue/9/start']
    assert core.read_json(directory / 'dispatch.json')['queue_id'] == 9
    with pytest.raises(core.WorkflowError):
        queue_sender.dispatch('P001', 'Jone')
    assert len(client.posts) == 3
    base.live['current_print'] = 'someone-elses-task.gcode'
    assert not bambuddy.reconcile('P001', 'Jone')['matching_task']


def test_workbench_queue_timeout_is_unknown_and_never_replayed(queue_setup):
    client, base, directory = queue_setup
    client.start_timeout = True
    operation = start_once()
    assert operation['state'] == 'unknown'
    assert (directory / 'dispatch.json').exists()
    workbench.reconcile_operation(operation['id'], 'owner')
    assert client.posts.count('queue/9/start') == 1
    assert not workbench.check('P001', 'Jone')['ready']


def test_queue_readiness_requires_current_machine_storage_and_credentials(queue_setup):
    client, base, directory = queue_setup
    client.metadata['model'] = 'P1S'
    assert not workbench.check('P001', 'Jone')['ready']
    client.metadata['model'] = 'A1'
    base.live['sdcard'] = False
    assert not workbench.check('P001', 'Jone')['ready']
    base.live['sdcard'] = True
    core.write_json(core.ROOT / 'Runtime/private/bambuddy.json', {})
    assert not workbench.check('P001', 'Jone')['ready']
    assert client.posts == []


@pytest.mark.parametrize('field,value', [
    ('id', 888), ('library_file_id', 888), ('printer_id', 888), ('plate_id', 2),
    ('manual_start', False), ('status', 'printing'), ('use_ams', False),
    ('ams_mapping', [3]), ('skip_filament_check', True), ('gcode_injection', True),
    ('confirm_outcome', False), ('use_ams', None), ('use_ams', 1),
])
def test_queue_mutation_cannot_start_or_erase_receipt(queue_setup, field, value):
    client, base, directory = queue_setup
    get = client.get
    def altered(path):
        result = get(path)
        if path == 'queue/9':
            result[field] = value
        return result
    client.get = altered
    operation = start_once()
    assert operation['state'] == 'unknown'
    assert client.posts == ['library/files', 'queue/']
    assert (directory / 'dispatch.json').exists()
    assert not workbench.check('P001', 'Jone')['ready']


def test_material_changed_during_upload_is_rechecked_before_start(queue_setup):
    client, base, directory = queue_setup
    post = client.post
    def changed(path, **kwargs):
        result = post(path, **kwargs)
        if path == 'queue/':
            base.live['ams'][0]['tray'][0]['tray_type'] = 'PLA'
        return result
    client.post = changed
    operation = start_once()
    assert operation['state'] == 'unknown'
    assert client.posts == ['library/files', 'queue/']
    assert 'start_requested_at' not in core.read_json(directory / 'dispatch.json')


def test_external_queue_never_advertises_sender_available(queue_setup):
    _, _, directory = queue_setup
    job = core.read_json(directory / 'job.json')
    job['mapping']['use_ams'] = False
    core.write_json(directory / 'job.json', job)
    result = queue_sender.capability({'project_id': 'P001', 'job_id': 'Jone',
        'device': {'state': 'IDLE'}, 'transport': {'sdcard': True}})
    assert not result['available']
    assert any('外挂' in reason for reason in result['blockers'])
