import copy

import httpx
import pytest

from printlab import core, material_intake


class InventoryClient:
    def __init__(self):
        self.rows = []
        self.posts = 0
        self.timeout = False
        self.persist = True

    def get(self, path):
        if path == 'inventory/spools':
            return copy.deepcopy(self.rows)
        return copy.deepcopy(next(row for row in self.rows if path == f"inventory/spools/{row['id']}"))

    def post(self, path, json):
        assert path == 'inventory/spools'
        self.posts += 1
        row = {'id': len(self.rows) + 1, **json}
        if self.persist:
            self.rows.append(row)
        if self.timeout:
            raise httpx.ReadTimeout('Simulated uncertain response')
        return copy.deepcopy(row)

    def close(self):
        pass


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'ROOT', tmp_path)
    return InventoryClient()


def register(client, request='spool-1', spool=None):
    return material_intake.register(spool or {'material': 'PLA', 'color_name': '白色'},
                                    'User confirmed this spool', request, lambda write: client)


def test_register_readback_replay_and_unknown_weight(client):
    first = register(client)
    assert not first['replayed'] and first['spool']['id'] == 1
    assert first['spool']['actual_remaining_weight'] is None
    assert first['spool']['quantity_basis'] == 'unknown'
    assert register(client)['replayed']
    assert client.posts == 1
    with pytest.raises(core.WorkflowError, match='another spool'):
        register(client, spool={'material': 'PETG'})
    second = register(client, request='spool-2')
    assert second['spool']['id'] == 2


def test_timeout_reconciles_without_second_post(client):
    client.timeout = True
    with pytest.raises(httpx.ReadTimeout):
        register(client)
    assert register(client)['replayed']
    assert client.posts == 1


def test_uncertain_empty_result_and_changed_service_do_not_retry(client):
    client.timeout, client.persist = True, False
    with pytest.raises(httpx.ReadTimeout):
        register(client)
    with pytest.raises(core.WorkflowError, match='unresolved'):
        register(client)
    assert client.posts == 1
    core.write_json(core.ROOT / 'Runtime/config.json', {'bambuddy_url': 'http://127.0.0.1:9999'})
    with pytest.raises(core.WorkflowError, match='another spool or service'):
        register(client)


def test_input_validation_and_post_registration_edits(client):
    for spool in ({'material': ''}, {'material': 'PLA', 'label_weight': -1},
                  {'material': 'PLA', 'rgba': 'white'}, {'material': 'PLA', 'access_code': 'secret'}):
        with pytest.raises(core.WorkflowError):
            register(client, spool=spool)
    assert client.posts == 0
    register(client)
    client.rows[0]['color_name'] = '黑色'
    with pytest.raises(core.WorkflowError, match='changed'):
        register(client)
    assert client.posts == 1
