import json
import xml.etree.ElementTree as ET
import zipfile
import pytest
from printlab import core, manual_project


def make_slice(path, *, objects=4, outside='false', green_group='0', support_id='GFS05', support_is_object='false'):
    root = ET.Element('config')
    plate = ET.SubElement(root, 'plate')
    ET.SubElement(plate, 'metadata', key='index', value='1')
    ET.SubElement(plate, 'metadata', key='outside', value=outside)
    for _ in range(objects):
        ET.SubElement(plate, 'object', skipped='false')
    for group, extruder in [('0', '1'), ('1', '2')]:
        ET.SubElement(plate, 'nozzle', id=group, extruder_id=extruder)
    for i, group, identifier, obj in [('1','0','GFA01','true'),('2',green_group,'GFA01','true'),('3','1',support_id,support_is_object)]:
        ET.SubElement(plate, 'filament', id=i, group_id=group, tray_info_idx=identifier, used_for_object=obj, used_g='1')
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('Metadata/slice_info.config', ET.tostring(root))
        z.writestr('Metadata/project_settings.config', json.dumps({'filament_is_support':['0','0','1']}))


def test_manual_output_accepts_correct_four_objects_and_route(tmp_path):
    f=tmp_path/'good.3mf'; make_slice(f)
    assert manual_project.validate_output(f)['logical_nozzle_map']==[1,1,2]


@pytest.mark.parametrize('change', [
    {'objects':3}, {'outside':'true'}, {'green_group':'1'},
    {'support_id':'GFA01'}, {'support_is_object':'true'},
])
def test_manual_output_rejects_missing_or_misrouted_parts(tmp_path, change):
    f=tmp_path/'bad.3mf'; make_slice(f, **change)
    with pytest.raises(core.WorkflowError):
        manual_project.validate_output(f)


def test_main_variant_requires_three_and_original_route(tmp_path):
    f=tmp_path/'main.3mf'; make_slice(f, objects=3)
    assert manual_project.validate_output(f, variant='main-without-front')['object_count']==3
    with pytest.raises(core.WorkflowError):
        manual_project.validate_output(f)
    for change in ({'objects':4}, {'objects':2}, {'objects':3,'green_group':'1'},
                   {'objects':3,'support_is_object':'true'}, {'objects':3,'outside':'true'}):
        make_slice(f, **change)
        with pytest.raises(core.WorkflowError):
            manual_project.validate_output(f, variant='main-without-front')
    with pytest.raises(core.WorkflowError):
        manual_project.validate_output(f, variant='arbitrary')


def test_subset_retains_exact_main_build_and_mesh_payloads():
    ns='http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
    model=ET.Element('{'+ns+'}model');resources=ET.SubElement(model,'{'+ns+'}resources');build=ET.SubElement(model,'{'+ns+'}build')
    settings=ET.Element('config');plate=ET.SubElement(settings,'plate')
    for oid in ['2','5','7','9']:
        ET.SubElement(resources,'{'+ns+'}object',id=oid)
        ET.SubElement(build,'{'+ns+'}item',objectid=oid,transform='1 0 0 0 1 0 0 0 1 8 9 10')
        obj=ET.SubElement(settings,'object',id=oid)
        ET.SubElement(obj,'metadata',key='extruder',value='2' if oid=='2' else '1')
        ET.SubElement(obj,'part',id='1' if oid=='2' else oid)
        inst=ET.SubElement(plate,'model_instance');ET.SubElement(inst,'metadata',key='object_id',value=oid)
    files={'3D/3dmodel.model':ET.tostring(model),'Metadata/model_settings.config':ET.tostring(settings),'3D/Objects/mesh.model':b'unchanged'}
    replacements,count=manual_project.select_plate(files,'main-without-front')
    assert count==3 and '3D/Objects/mesh.model' not in replacements
    changed=ET.fromstring(replacements['3D/3dmodel.model'])
    assert [n.get('objectid') for n in changed.find('{'+ns+'}build')]==['5','7','9']
    assert all(n.get('transform')=='1 0 0 0 1 0 0 0 1 8 9 10' for n in changed.find('{'+ns+'}build'))
    build[0].set('objectid','99');files['3D/3dmodel.model']=ET.tostring(model)
    with pytest.raises(core.WorkflowError):manual_project.select_plate(files,'main-without-front')


def test_front_subset_bed_alignment_and_unchanged_mesh():
    ns = '{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}'
    model = ET.Element(ns+'model')
    resources = ET.SubElement(model, ns+'resources')
    build = ET.SubElement(model, ns+'build')
    settings = ET.Element('config'); plate = ET.SubElement(settings, 'plate')
    for oid in ['2', '5', '7', '9']:
        ET.SubElement(resources, ns+'object', id=oid)
        ET.SubElement(build, ns+'item', objectid=oid)
        obj = ET.SubElement(settings, 'object', id=oid)
        ET.SubElement(obj, 'metadata', key='extruder', value='2' if oid == '2' else '1')
        ET.SubElement(obj, 'part', id='1' if oid == '2' else oid)
        inst = ET.SubElement(plate, 'model_instance')
        ET.SubElement(inst, 'metadata', key='object_id', value=oid)
    mesh = ET.Element(ns+'model')
    for y in [-3, 4]: ET.SubElement(mesh, ns+'vertex', x='0', y=str(y), z='0')
    files = {'3D/3dmodel.model': ET.tostring(model),
             'Metadata/model_settings.config': ET.tostring(settings),
             '3D/Objects/object_1.model': ET.tostring(mesh)}
    original = files.copy()
    changes, count = manual_project.select_plate(files, 'front-flat')
    assert files == original and count == 1
    assert '3D/Objects/object_1.model' not in changes
    selected = ET.fromstring(changes['3D/3dmodel.model'])
    items = list(selected.find(ns+'build'))
    assert len(items) == 1 and items[0].get('objectid') == '2'
    assert items[0].get('transform') == '1 0 0 0 0 1 0 -1 0 128 128 3.0'
    assert [n.get('id') for n in selected.find(ns+'resources')] == ['2']
    selected_settings = ET.fromstring(changes['Metadata/model_settings.config'])
    assert [o.get('id') for o in selected_settings.findall('object')] == ['2']
    assert len(selected_settings.findall('plate/model_instance')) == 1


@pytest.mark.parametrize('bad', [None, 'extra_body', 'wrong_nozzle', 'support_as_body', 'wrong_skeleton', 'missing_support'])
def test_front_output_validates_only_selected_materials(tmp_path, bad):
    f = tmp_path/'front.3mf'; make_slice(f, objects=1)
    with zipfile.ZipFile(f) as z:
        root = ET.fromstring(z.read('Metadata/slice_info.config'))
        settings = json.loads(z.read('Metadata/project_settings.config'))
    p = root.find('plate')
    if bad != 'extra_body': p.remove(p.find("filament[@id='1']"))
    settings['support_filament'] = '1' if bad == 'wrong_skeleton' else '2'
    if bad == 'wrong_nozzle': p.find("filament[@id='2']").set('group_id', '1')
    if bad == 'support_as_body': p.find("filament[@id='3']").set('used_for_object', 'true')
    if bad == 'missing_support': p.remove(p.find("filament[@id='3']"))
    with zipfile.ZipFile(f, 'w') as z:
        z.writestr('Metadata/slice_info.config', ET.tostring(root))
        z.writestr('Metadata/project_settings.config', json.dumps(settings))
    if bad:
        with pytest.raises(core.WorkflowError): manual_project.validate_output(f, variant='front-flat')
    else:
        assert manual_project.validate_output(f, variant='front-flat')['object_count'] == 1
