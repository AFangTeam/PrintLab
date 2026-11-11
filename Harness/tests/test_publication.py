"""Synthetic local publication records only; no network, user authorization or upload."""
import base64
import copy
import datetime as dt
import json
from pathlib import Path
import zipfile

import pytest

from printlab import core, publication, cli


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'ROOT', tmp_path)
    core.new_project('Synthetic publication validation')
    p = core.project_path('P001')
    project = core.read_json(p / 'project.json')
    project['current_revision'] = 'v001'
    core.write_json(p / 'project.json', project)
    return p


def ref(p, path, data=b'SYNTHETIC TEST EVIDENCE, NOT AN ACTUAL PERMISSION'):
    f = p / path
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(data)
    return {'path': path, 'sha256': core.digest(f)}


def review(p):
    return {'status': 'verified', 'note': 'Synthetic reviewer statement for offline tests only',
            'checked_at': dt.datetime.now(dt.timezone.utc).date().isoformat(),
            'evidence': ref(p, 'Review/synthetic-proof.txt')}


def original(p):
    r = publication.template()
    model = ref(p, 'Exports/v001/model.stl', b'solid synthetic\nendsolid synthetic\n')
    photo = ref(p, 'Review/real-photo.png', base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6rV8AAAAASUVORK5CYII='))
    r.update(intent='public_upload', kind='original', revision='v001', title='Synthetic test model',
             classification_note='Synthetic from-scratch design', geometry_change='none',
             all_sources_reviewed=True, rights_review=review(p), commercial_use=False,
             output_license={'name': 'CC BY', 'url': 'https://creativecommons.org/licenses/by/4.0/'},
             platform_review={**review(p), 'tutorial_url': 'https://wiki.bambulab.com/en/makerworld/tutorials/how-to-upload-models',
                              'community_guidelines_url': 'https://makerworld.com/en/community-guidelines'},
             artifacts=[{**model, 'role': 'model', 'revision': 'v001'}],
             photos=[{**photo, 'kind': 'real_print_photo', 'revision': 'v001', 'artifact_sha256': model['sha256'], 'review': review(p),
                      'capture_origin': 'own_original', 'printed_result': 'complete', 'process': 'fdm', 'quality': 'acceptable',
                      'all_parts_visible': True, 'color_regions_match': True}],
             cover_photo=photo['path'],
             validation={'status': 'partial', 'verified_claims': ['Physical appearance only (synthetic)'],
                         'unverified': ['Fit and load capacity remain unverified'], 'review': review(p)})
    return r


def source(p, code='by-nc-sa', use='adapted_geometry'):
    return {'authors': ['Synthetic Author'], 'title': 'Synthetic source', 'url': 'https://example.org/source',
            'version': 'v1', 'use': use, 'license': {'name': 'CC ' + code.upper(), 'version': '4.0',
            'url': f'https://creativecommons.org/licenses/{code}/4.0/',
            'checked_at': dt.datetime.now(dt.timezone.utc).date().isoformat(), 'evidence': review(p)['evidence']},
            'output_compatibility': review(p)}


def save(p, r):
    core.write_json(p / publication.RECORD, r)
    return publication.check('P001')


def remix(p, code='by-nc-sa'):
    r = original(p)
    r.update(kind='remix', geometry_change='substantial', changes=['Synthetic substantial geometry change'], retained=['Synthetic mounting interface'], sources=[source(p, code)])
    r['output_license'] = {'name': 'CC ' + code.upper(), 'url': f'https://creativecommons.org/licenses/{code}/4.0/'}
    return r


def ids(result, status):
    return {x['id'] for x in result['checks'] if x['status'] == status}


def test_local_design_has_no_publication_gate(workspace):
    result = publication.check('P001')
    assert result['status'] == 'not_requested'
    assert not result['upload_authorized']
    with pytest.raises(core.WorkflowError, match='No public upload'):
        publication.prepare('P001')


def test_original_no_invented_author_permission_or_print_authorization(workspace):
    result = save(workspace, original(workspace))
    assert result['eligible_for_confirmation']
    assert 'original_author_permission' in ids(result, 'not_applicable')
    assert not result['upload_authorized'] and not result['uploaded']
    assert not list(workspace.rglob('approval.json'))
    assert core.read_json(workspace / 'project.json')['status'] == 'designing'


def test_cc_remix_does_not_need_extra_author_permission(workspace):
    result = save(workspace, remix(workspace))
    assert result['status'] == 'ready_for_confirmation'
    assert not result['upload_authorized']


@pytest.mark.parametrize('field,value,expected', [('commercial_use', True, 'source_1_nc'), ('geometry_change', 'minor', 'remix_substance')])
def test_real_restrictions_block_release(workspace, field, value, expected):
    r = remix(workspace)
    r[field] = value
    result = save(workspace, r)
    assert result['status'] == 'not_allowed'
    assert expected in ids(result, 'not_allowed')


def test_sa_and_multiple_sources_are_checked_individually(workspace):
    r = remix(workspace)
    r['output_license']['url'] = 'https://example.org/standard'
    r['sources'].append(source(workspace, 'by-nd'))
    result = save(workspace, r)
    assert {'source_1_sa', 'source_2_adaptation'} <= ids(result, 'not_allowed')


def test_nd_blocks_public_adaptation_but_not_private_design(workspace):
    r = remix(workspace, 'by-nd')
    assert 'source_1_adaptation' in ids(save(workspace, r), 'not_allowed')
    r['intent'] = 'local_only'
    assert save(workspace, r)['status'] == 'not_requested'


def test_extra_permission_requires_evidence_and_exact_scope(workspace):
    r = remix(workspace, 'by-nd')
    r['sources'][0]['additional_permission'] = {**review(workspace), 'covers': ['redistribution'],
                                             'source_url': 'https://example.org/source', 'grantor': 'Synthetic Author'}
    assert 'source_1_adaptation' in ids(save(workspace, r), 'not_allowed')
    r['sources'][0]['additional_permission']['covers'].append('adaptation')
    assert save(workspace, r)['eligible_for_confirmation']
    r['sources'][0]['additional_permission']['evidence']['sha256'] = '0' * 64
    assert not save(workspace, r)['eligible_for_confirmation']


def test_unknown_standard_and_exclusive_licenses_never_default_to_allowed(workspace):
    r = remix(workspace)
    lic = r['sources'][0]['license']
    lic.update(name='Standard Digital File License', url='https://example.org/standard', version='observed date')
    assert 'source_1_adaptation' in ids(save(workspace, r), 'missing')
    lic['review'] = review(workspace)
    lic['permissions'] = {'adaptation': False, 'redistribution': True}
    assert 'source_1_adaptation' in ids(save(workspace, r), 'not_allowed')


def test_ai_style_and_reexport_do_not_launder_originality(workspace):
    r = original(workspace)
    r.update(classification_note='AI stylization and re-export', sources=[source(workspace)])
    assert 'originality' in ids(save(workspace, r), 'not_allowed')


@pytest.mark.parametrize('mutate', ['concept', 'revision', 'file_hash', 'photo_hash', 'review', 'platform'])
def test_missing_or_mismatched_evidence_blocks_release(workspace, mutate):
    r = original(workspace)
    if mutate == 'concept': r['photos'][0]['kind'] = 'ai_concept'
    elif mutate == 'revision': r['revision'] = 'v000'
    elif mutate == 'file_hash': r['artifacts'][0]['sha256'] = '0' * 64
    elif mutate == 'photo_hash': r['photos'][0]['artifact_sha256'] = '0' * 64
    elif mutate == 'review': r['validation']['review'] = {}
    elif mutate == 'platform': r['platform_review']['status'] = 'unavailable'
    result = save(workspace, r)
    assert result['status'] == 'awaiting_evidence' and not result['eligible_for_confirmation']


def profile(p):
    target = p / 'Exports/v001/profile.3mf'
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, 'w') as z:
        z.writestr('3D/3dmodel.model', '<model xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"><build><item objectid="1"/></build></model>')
        z.writestr('Metadata/model_settings.config', '<config><object id="1"><metadata key="extruder" value="1"/></object></config>')
        z.writestr('Metadata/project_settings.config', json.dumps({'filament_settings_id': ['Synthetic'], 'filament_colour': ['#FFFFFF'], 'printer_model': 'Bambu Lab X2D'}))
    return {'path': 'Exports/v001/profile.3mf', 'sha256': core.digest(target), 'role': 'print_profile', 'revision': 'v001'}


def test_print_profile_needs_target_exact_profile_photo_and_geometry(workspace):
    r = original(workspace)
    r.update(kind='print_profile', target_model_url='https://example.org/source', sources=[source(workspace, 'by-nd', 'unchanged_geometry')])
    r['artifacts'] = [profile(workspace)]
    r['profile_review'] = {**review(workspace), 'comparison': 'first_profile', 'benefit': 'Synthetic first profile',
                           'title_description_match': True, 'time_claims_supported': True}
    photo = r['photos'][0]
    photo.update(artifact_sha256=r['artifacts'][0]['sha256'])
    assert not save(workspace, r)['eligible_for_confirmation']
    photo['profile_sha256'] = r['artifacts'][0]['sha256']
    assert save(workspace, r)['eligible_for_confirmation']
    r['geometry_change'] = 'minor'
    assert 'profile_geometry' in ids(save(workspace, r), 'not_allowed')


def test_sliced_package_is_not_a_publishable_print_profile(workspace):
    r = original(workspace)
    a = profile(workspace)
    with zipfile.ZipFile(workspace / a['path'], 'a') as z: z.writestr('Metadata/plate_1.gcode', 'M104 S0')
    a['sha256'] = core.digest(workspace / a['path'])
    r['artifacts'] = [a]
    assert 'profile_1' in ids(save(workspace, r), 'missing')


def test_prepare_archives_blocked_drafts_and_preserves_prior_packets(workspace):
    r = remix(workspace, 'by-nd')
    save(workspace, r)
    a = publication.prepare('P001')
    b = publication.prepare('P001')
    assert a['status'] == 'not_allowed' and a['package'] != b['package']
    packet = Path(a['package'])
    assert set(x.name for x in packet.iterdir()) == {'manifest.json', 'check.json', 'record.json', 'review.md', 'description-draft.md'}
    assert 'Synthetic Author' in (packet / 'description-draft.md').read_text()
    assert not a['upload_authorized'] and not a['uploaded']
    manifest = core.read_json(packet / 'manifest.json')
    assert all(core.digest(packet / k) == v for k, v in manifest['files'].items())


def test_changed_files_invalidate_check_and_fingerprint(workspace):
    r = original(workspace)
    before = save(workspace, r)
    (workspace / r['artifacts'][0]['path']).write_text('different bytes')
    after = publication.check('P001')
    assert before['fingerprint'] != after['fingerprint']
    assert not after['eligible_for_confirmation']


def test_path_escape_and_symlink_cannot_be_publication_evidence(workspace, tmp_path):
    r = original(workspace)
    r['artifacts'][0]['path'] = '../../Runtime/private/secret'
    assert not save(workspace, r)['eligible_for_confirmation']
    outside = tmp_path / 'secret'
    outside.write_text('not publishable')
    (workspace / 'Review/link').symlink_to(outside)
    r['rights_review']['evidence'] = {'path': 'Review/link', 'sha256': core.digest(outside)}
    assert not save(workspace, r)['eligible_for_confirmation']


def test_cli_failure_status_and_no_upload_command(workspace, capsys):
    publication.init('P001', 'remix')
    assert cli.main(['publish', 'check', 'P001']) == 2
    assert json.loads(capsys.readouterr().out)['uploaded'] is False
    with pytest.raises(SystemExit): cli.parser().parse_args(['publish', 'upload', 'P001'])


def test_init_preserves_existing_record(workspace):
    r = original(workspace)
    save(workspace, r)
    publication.init('P001', 'remix')
    assert core.read_json(workspace / publication.RECORD) == r


@pytest.mark.parametrize('field,value', [('printed_result', 'unfinished'), ('capture_origin', 'third_party'),
                                        ('color_regions_match', False), ('quality', 'failed')])
def test_unfinished_or_borrowed_or_mismatched_photos_fail(workspace, field, value):
    r = original(workspace)
    r['photos'][0][field] = value
    assert not save(workspace, r)['eligible_for_confirmation']


def test_duplicate_profile_cannot_become_a_new_publication(workspace):
    r = original(workspace)
    r['artifacts'].append(profile(workspace))
    r['profile_review'] = {**review(workspace), 'comparison': 'minor_without_benefit', 'benefit': 'Only replaced red with blue'}
    assert 'profile_value' in ids(save(workspace, r), 'not_allowed')


def test_new_template_is_inactive_and_context_uses_shared_check(workspace, monkeypatch):
    from printlab import bambuddy
    monkeypatch.setattr(bambuddy, 'inventory', lambda: {'state': 'isolated test'})
    template_path = core.ROOT / 'Templates/Project/Review/Publication/record.json'
    core.write_json(template_path, publication.template())
    core.new_project('Synthetic local-only template')
    p = core.project_path('P002')
    assert core.read_json(p / publication.RECORD)['intent'] == 'local_only'
    assert core.context('P002')['publication']['status'] == 'not_requested'
    publication.init('P002', 'original')
    assert core.read_json(p / publication.RECORD)['kind'] == 'original'
    assert core.context('P002')['publication']['status'] == 'awaiting_evidence'


def test_check_and_prepare_never_use_network(workspace, monkeypatch):
    import httpx
    import socket
    def forbidden(*args, **kwargs):
        raise AssertionError('Publication preflight must stay local')
    monkeypatch.setattr(httpx.Client, '__init__', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    save(workspace, original(workspace))
    assert publication.prepare('P001')['uploaded'] is False


def test_changed_record_cannot_be_frozen_as_an_older_review(workspace, monkeypatch):
    r = original(workspace)
    save(workspace, r)
    real_check = publication.check
    def changing(pid):
        result = real_check(pid)
        changed = copy.deepcopy(r)
        changed['title'] = 'Changed after check'
        core.write_json(workspace / publication.RECORD, changed)
        return result
    monkeypatch.setattr(publication, 'check', changing)
    with pytest.raises(core.WorkflowError, match='record changed'):
        publication.prepare('P001')


def test_cc_version_and_extra_permission_source_must_match(workspace):
    r = remix(workspace)
    r['sources'][0]['license']['version'] = '3.0'
    assert 'source_1_version' in ids(save(workspace, r), 'missing')
    r = remix(workspace, 'by-nd')
    r['sources'][0]['additional_permission'] = {**review(workspace), 'grantor': 'Other person',
                                               'source_url': 'https://example.org/other', 'covers': ['adaptation']}
    assert 'source_1_adaptation' in ids(save(workspace, r), 'not_allowed')


def test_failed_physical_review_cannot_be_claimed_as_passed(workspace):
    r = original(workspace)
    r['validation']['status'] = 'passed'
    project = core.read_json(workspace / 'project.json')
    project['status'] = 'needs_changes'
    core.write_json(workspace / 'project.json', project)
    assert 'validation_conflict' in ids(save(workspace, r), 'not_allowed')


def test_init_and_packet_output_reject_symlink_directories(workspace, tmp_path):
    outside = tmp_path / 'external-publication'
    outside.mkdir()
    (workspace / 'Review/Publication').symlink_to(outside, target_is_directory=True)
    with pytest.raises(core.WorkflowError, match='Symbolic'):
        publication.init('P001')
    (workspace / 'Review/Publication').unlink()
    save(workspace, original(workspace))
    (workspace / 'Review/Publication/Packages').symlink_to(outside, target_is_directory=True)
    with pytest.raises(core.WorkflowError, match='Symbolic'):
        publication.prepare('P001')
    assert not list(outside.iterdir())
