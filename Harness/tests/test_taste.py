import pytest

from printlab import core, taste, bambuddy


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'ROOT', tmp_path)
    monkeypatch.setattr(bambuddy, 'inventory', lambda: {'items': []})
    core.new_project('Choice archive')
    p = core.project_path('P001')
    (p / 'Preview/A.png').write_bytes(b'original image A')
    (p / 'Preview/B.png').write_bytes(b'original image B')
    return p


def manifest():
    return {'id': 'round-01', 'stage': 'shape', 'outcome': 'selected',
            'options': [{'id': 'A', 'images': ['Preview/A.png']}, {'id': 'B', 'images': ['Preview/B.png']}],
            'selected_option_ids': ['A'], 'user_feedback': {'quote': 'A', 'source': 'Synthetic user fixture', 'reason': None}}


def test_full_round_survives_source_changes_and_cold_session(lab):
    m = manifest()
    first = taste.record('P001', m)
    assert taste.record('P001', m)['reused']
    (lab / 'Preview/A.png').write_bytes(b'new model preview')
    (lab / 'Preview/B.png').unlink()
    result = core.context('P001')['taste']
    assert result['total'] == 1 and result['recent'][0]['option_count'] == 2
    path = core.ROOT / first['path']
    saved = core.read_json(path / 'record.json')
    assert (path / saved['options'][0]['assets'][0]['snapshot']).read_bytes() == b'original image A'
    assert saved['manifest']['user_feedback']['reason'] is None
    assert saved['print_authorized'] is False


def test_correction_appends_and_does_not_turn_nonselection_into_dislike(lab):
    m = manifest()
    first = taste.record('P001', m)
    m['selected_option_ids'] = ['B']
    with pytest.raises(core.WorkflowError, match='overwriting'):
        taste.record('P001', m)
    m.update(id='round-02', supersedes=first['id'])
    taste.record('P001', m)
    result = taste.summary('P001')
    assert result['total'] == 2
    assert result['recent'][1]['supersedes'] == first['id']
    original = core.read_json(core.ROOT / result['recent'][0]['record'])
    assert original['manifest']['selected_option_ids'] == ['A']
    assert 'not evidence of dislike' in original['unselected_meaning']


@pytest.mark.parametrize('change', [
    {'selected_option_ids': ['missing']}, {'user_feedback': {}},
    {'options': [{'id': 'A', 'images': ['../../outside.png']}, {'id': 'B', 'images': ['Preview/B.png']}]},
])
def test_invalid_or_unattributed_choice_leaves_no_archive(lab, change):
    m = manifest(); m.update(change)
    with pytest.raises(core.WorkflowError):
        taste.record('P001', m)
    assert taste.summary()['total'] == 0


def test_none_and_multiple_choices_and_snapshot_tamper(lab):
    m = manifest(); m.update(selected_option_ids=[], outcome='none')
    taste.record('P001', m)
    m.update(id='round-02', selected_option_ids=['A', 'B'], outcome='selected')
    result = taste.record('P001', m)
    assert taste.summary()['total'] == 2
    (core.ROOT / result['path'] / 'option-1-1.png').write_bytes(b'changed archive')
    with pytest.raises(core.WorkflowError, match='changed'):
        taste.summary()


def test_library_choices_do_not_create_fake_projects(lab):
    m = manifest()
    for option in m['options']:
        option['images'] = [(lab / option['images'][0]).relative_to(core.ROOT).as_posix()]
    result = taste.record('library', m)
    assert result['id'].startswith('Library-')
    assert taste.summary('library')['total'] == 1
    assert taste.summary('P001')['total'] == 0
