import zipfile
import json
import pytest
from printlab import core, three_mf

@pytest.mark.parametrize('count,skipped,passes', [(20,False,True),(16,False,False),(20,True,False),(21,False,False)])
def test_preserved_plate_rejects_omitted_or_skipped_parts(tmp_path,count,skipped,passes):
    path=tmp_path/'slice.3mf'
    rows=''.join(f'<object identify_id="{i}" skipped="{str(skipped and i==0).lower()}"/>' for i in range(count))
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('Metadata/slice_info.config','<config><plate><metadata key="index" value="1"/>'+rows+'</plate></config>')
        z.writestr('Metadata/plate_1.json',json.dumps({'bbox_objects':[{'id':i} for i in range(count)]}))
    if passes:three_mf.validate_plate_object_count(path,20)
    else:
        with pytest.raises(core.WorkflowError,match='count mismatch'):three_mf.validate_plate_object_count(path,20)
