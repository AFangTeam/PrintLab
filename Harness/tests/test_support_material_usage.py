"""Offline checks for a separate support filament; no device operations."""
import json
import zipfile
import pytest
from printlab import core, three_mf

def archive(tmp_path, *, interface=2, support=True, object_use='false', support_use='true', body=True):
    path=tmp_path/'slice.3mf'
    rows=('<filament id="1" used_g="10"/>' if body else '')
    rows+=f'<filament id="2" used_g="2" used_for_object="{object_use}" used_for_support="{support_use}"/>'
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('Metadata/slice_info.config',f'<config><plate><metadata key="index" value="1"/>{rows}</plate></config>')
        z.writestr('Metadata/project_settings.config',json.dumps({'enable_support':'1' if support else '0','support_filament':'1','support_interface_filament':str(interface)}))
    return path

def test_separate_declared_support_interface_is_allowed(tmp_path):
    three_mf.validate_slice_output(archive(tmp_path),{'object_filament_assignments':{'1':1}})

@pytest.mark.parametrize('changes',[
    {'interface':3}, {'support':False}, {'object_use':'true'},
    {'object_use':''}, {'support_use':'false'}, {'body':False},
])
def test_missing_body_or_unverified_extra_material_is_rejected(tmp_path,changes):
    with pytest.raises(core.WorkflowError):
        three_mf.validate_slice_output(archive(tmp_path,**changes),{'object_filament_assignments':{'1':1}})
