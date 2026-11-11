import json
import zipfile
import pytest
from printlab import core, three_mf

def package(tmp_path, rows):
    p=tmp_path/'slice.3mf'
    with zipfile.ZipFile(p,'w') as z:
        z.writestr('Metadata/slice_info.config','<config><plate><metadata key="index" value="1"/></plate></config>')
        z.writestr('Metadata/plate_1.json',json.dumps({'bbox_objects':rows}))
    return p

def test_generated_tower_is_not_an_extra_model(tmp_path):
    p=package(tmp_path,[{'id':26,'name':'cage'},{'id':1000,'name':'wipe_tower'}])
    three_mf.validate_plate_object_count(p,1)

@pytest.mark.parametrize('rows',[
    [{'id':1000,'name':'wipe_tower'}],
    [{'id':26,'name':'cage'},{'id':27,'name':'wipe_tower'}],
    [{'id':26,'name':'cage'},{'id':1000,'name':'extra_model'}],
    [{'id':26,'name':'cage'},{'id':1000,'name':'wipe_tower'},{'id':1000,'name':'wipe_tower'}],
])
def test_missing_or_unexpected_models_still_block(tmp_path,rows):
    with pytest.raises(core.WorkflowError):
        three_mf.validate_plate_object_count(package(tmp_path,rows),1)
