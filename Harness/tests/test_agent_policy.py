"""Cold-session propagation uses local files and never starts a printer."""
import shutil

from printlab import core, bambuddy


def test_new_project_inherits_shared_model_policy_and_remix_handoff(tmp_path, monkeypatch):
    template = core.ROOT / 'Templates/Project'
    shutil.copytree(template, tmp_path / 'Templates/Project')
    monkeypatch.setattr(core, 'ROOT', tmp_path)
    monkeypatch.setattr(bambuddy, 'inventory', lambda: {'items': [], 'status': 'test_no_transport'})
    policy_path = tmp_path / 'Context/agent-policy.json'
    core.write_json(policy_path, {'default_modeling_model': 'gpt-6.1-terra', 'print_authorized': False})
    core.new_project('Existing model remix')
    project = core.project_path('P001')
    assert (project / 'Review/remix-plan.md').is_file()
    assert '尚未核实' in (project / 'Review/model-routing.md').read_text()
    # Defaults do not fabricate evidence that a modeling task actually ran.
    assert not (project / 'Review/model-routing.json').exists()
    first = {d['path']: d for d in core.context('P001')['documents']}
    assert 'gpt-6.1-terra' in first['Context/agent-policy.json']['text']
    assert 'Project/P001-Existing-model-remix/Review/remix-plan.md' in first
    assert core.read_json(project / 'project.json')['status'] == 'designing'
    # A fresh session reloads shared changes and preserves separate actual-run evidence.
    core.write_json(project / 'Review/model-routing.json', {'model': 'historical-model', 'verified': True})
    core.write_json(policy_path, {'default_modeling_model': 'future-user-choice', 'print_authorized': False})
    second = {d['path']: d for d in core.context('P001')['documents']}
    assert 'future-user-choice' in second['Context/agent-policy.json']['text']
    assert first['Context/agent-policy.json']['sha256'] != second['Context/agent-policy.json']['sha256']
    route = second['Project/P001-Existing-model-remix/Review/model-routing.json']['text']
    assert 'historical-model' in route
