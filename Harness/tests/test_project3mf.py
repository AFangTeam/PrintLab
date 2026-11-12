import json
import zipfile

import pytest

from printlab import core, project3mf


def project_archive(path, full=True, gcode=False, model_name='Bambu Lab X2D'):
    ns = 'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
    model = f'<model xmlns="{ns}"><resources/><build><item objectid="1"/></build></model>'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('3D/3dmodel.model', model)
        z.writestr('Metadata/model_settings.config', '<config><object id="1"><part id="1"><metadata key="extruder" value="1"/></part></object></config>')
        if full:
            z.writestr('Metadata/project_settings.config', json.dumps({
                'printer_model': model_name,
                'curr_bed_type': 'Textured PEI Plate',
                'filament_settings_id': ['Bambu PETG Matte @BBL X2D 0.4 nozzle'],
                'filament_colour': ['#5AA6A3'],
            }))
        if gcode:
            z.writestr('Metadata/plate_1.gcode', 'G1 X1')


def test_editable_project_requires_full_studio_config(tmp_path):
    path = tmp_path / 'core.3mf'
    project_archive(path, full=False)
    with pytest.raises(core.WorkflowError, match='complete Bambu Studio'):
        project3mf.inspect(path)


def test_editable_project_rejects_sliced_package(tmp_path):
    path = tmp_path / 'sliced.3mf'
    project_archive(path, gcode=True)
    with pytest.raises(core.WorkflowError, match='sliced G-code'):
        project3mf.inspect(path)


def test_editable_project_reports_machine_bed_and_filament(tmp_path):
    path = tmp_path / 'project.3mf'
    project_archive(path)
    data = project3mf.inspect(path, 1)
    assert data['printer_model'] == 'Bambu Lab X2D'
    assert data['bed_type'] == 'Textured PEI Plate'
    assert data['studio_project_config_present'] is True


@pytest.mark.parametrize('model', ['Bambu Lab A1', 'Bambu Lab A1 mini', 'Bambu Lab P1S', 'Bambu Lab X1 Carbon'])
def test_editable_project_keeps_the_actual_machine(tmp_path, model):
    path = tmp_path / 'project.3mf'
    project_archive(path, model_name=model)
    assert project3mf.inspect(path)['printer_model'] == model


def test_editable_project_requires_identified_machine(tmp_path):
    path = tmp_path / 'project.3mf'
    project_archive(path, model_name='')
    with pytest.raises(core.WorkflowError, match='target printer'):
        project3mf.inspect(path)
