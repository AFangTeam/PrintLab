import importlib.util
import json
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('printlab_profile_resolver',Path(__file__).parents[1]/'resolve_bambu_profiles.py')
resolver=importlib.util.module_from_spec(spec);spec.loader.exec_module(resolver)


def put(root,name,**fields):
 p=root/(name+'.json');p.write_text(json.dumps({'name':name,**fields}));return p


def test_inherits_ordered_includes_then_own_values(tmp_path):
 put(tmp_path,'base',machine_start_gcode='M109 S205',field='base')
 put(tmp_path,'start',instantiation='false',machine_start_gcode='M109 S[target]',field='include')
 profile=put(tmp_path,'X2D',inherits='base',include=['start'],field='own')
 output=tmp_path/'candidate'/'machine.json'
 receipt=resolver.write_candidate(profile,output)
 result=json.loads(output.read_text())
 assert result['machine_start_gcode']=='M109 S[target]' and result['field']=='own'
 assert result['name']=='X2D' and 'include' not in result and 'inherits' not in result
 assert len(receipt['source_files'])==3
 assert receipt['output_sha256']==resolver.digest(output)
 with pytest.raises(ValueError,match='already exists'):resolver.write_candidate(profile,output)


def test_missing_or_cyclic_references_fail(tmp_path):
 put(tmp_path,'a',include=['b']);r=resolver.ProfileResolver(tmp_path)
 with pytest.raises(ValueError,match='Missing'):r.resolve('a')
 put(tmp_path,'b',inherits='a');r=resolver.ProfileResolver(tmp_path)
 with pytest.raises(ValueError,match='Cyclic'):r.resolve('a')


def test_installed_candidate_preserves_real_x2d_templates():
 p=(Path(__file__).resolve().parents[2] / 'Library/Devices/X2D/SlicerProfiles/02.08.02.61/validated-native-v2/machine.json')
 if not p.exists():pytest.skip('Installed official profile candidate unavailable')
 data=json.loads(p.read_text());provenance=json.loads(p.with_suffix('.sources.json').read_text())
 assert 'X2D start gcode' in data['machine_start_gcode']
 assert 'M109 S205' not in data['machine_start_gcode']
 assert len(provenance['source_files'])==8
 assert provenance['output_sha256']==resolver.digest(p)


def test_all_native_candidate_source_hashes_match():
 root=(Path(__file__).resolve().parents[2] / 'Library/Devices/X2D/SlicerProfiles/02.08.02.61/validated-native-v2')
 if not root.exists():pytest.skip('Installed official profile candidates unavailable')
 for receipt_path in root.glob('*.sources.json'):
  receipt=json.loads(receipt_path.read_text())
  output=receipt_path.with_name(receipt_path.name.replace('.sources.json','.json'))
  data=json.loads(output.read_text())
  assert not data.get('inherits') and not data.get('include')
  assert receipt['output_sha256']==resolver.digest(output)
  for source in receipt['source_files']:
   assert source['sha256']==resolver.digest(Path(source['path']))
  if 'selection_source' in receipt:
   source=receipt['selection_source'];assert source['sha256']==resolver.digest(Path(source['path']))
