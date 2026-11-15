"""Route planning must not connect, write credentials, approve, or send."""
import json
import pytest
from printlab import bambuddy, cli, core, dispatch_plan


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'ROOT', tmp_path)
    monkeypatch.setattr(bambuddy, 'Client', lambda *a, **k: pytest.fail('Planning must be offline'))


@pytest.mark.parametrize('model', ['A1', 'Bambu Lab A1 mini', 'P1S', 'X1C'])
def test_supported_ams_recommends_only_relevant_permission(model):
    result = dispatch_plan.plan(model=model, feeding='ams')
    assert result['preferred_route'] == 'bambuddy_queue'
    assert result['next_step'] == 'explain_required_permissions'
    assert result['permissions_to_recommend']
    assert result['ready_to_print'] is False
    assert list(core.ROOT.iterdir()) == []


@pytest.mark.parametrize('options', [
    {'model': 'A1', 'feeding': 'external'},
    {'model': 'X2D', 'feeding': 'ams'},
    {'model': 'Unknown future printer', 'feeding': 'ams'},
    {'model': 'A1', 'feeding': 'ams', 'permission': 'declined'},
    {'model': 'A1', 'feeding': 'ams', 'keep_cloud': True},
])
def test_unsupported_or_declined_skips_bambuddy_permission_requests(options):
    result = dispatch_plan.plan(**options)
    assert result['preferred_route'] == 'official_studio'
    assert result['permissions_to_recommend'] == []
    assert result['next_step'] == 'prepare_studio_fallback'
    assert result['ready_to_print'] is False


def test_saved_permission_does_not_trigger_another_permission_question():
    result = dispatch_plan.plan(model='A1', feeding='ams', permission='granted')
    assert result['next_step'] == 'check_connection_readonly'
    assert result['permissions_to_recommend'] == []
    assert not result['ready_to_print']


def test_unknown_feeding_never_assumes_ams():
    core.write_json(core.ROOT / 'Library/Devices/X2D/device.json', {'model': 'A1', 'ams': [{}]})
    result = dispatch_plan.plan()
    assert result['preferred_route'] is None
    assert result['next_step'] == 'confirm_missing_facts'
    assert result['model_source'] == 'device_card_not_live'


def test_cli_routes_external_without_network_or_writes(capsys):
    assert cli.main(['dispatch-plan', '--model', 'A1', '--feeding', 'external']) in (None, 0)
    result = json.loads(capsys.readouterr().out)
    assert result['preferred_route'] == 'official_studio'
    assert list(core.ROOT.iterdir()) == []
