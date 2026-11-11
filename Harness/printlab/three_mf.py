"""Conservative local multipart 3MF geometry input, never an author print package.

Only the core mesh/assembly subset and explicit object/part extruder assignments
are accepted. Painted triangles, textures, external components and all author
printer/process/project settings require a separate reviewed import path.
"""
import collections
import json
import math
from pathlib import PurePosixPath
import stat
import xml.etree.ElementTree as ET
import zipfile
from . import core

NS = '{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}'
ALLOWED = {'[Content_Types].xml', '_rels/.rels', '3D/3dmodel.model', 'Metadata/model_settings.config'}


def _xml(data):
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise core.WorkflowError('DTD/entity declarations are not accepted in 3MF input')
    return ET.fromstring(data)


def inspect(path, filament_count):
    if type(filament_count) is not int or filament_count < 1:
        raise core.WorkflowError('Explicit filament profiles are required for 3MF input')
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            if len(names) != len(set(names)) or set(names) != ALLOWED:
                raise core.WorkflowError('3MF input supports only reviewed core geometry and model_settings; author G-code/project settings/textures/external parts are not accepted')
            if sum(i.file_size for i in z.infolist()) > 128*1024*1024:
                raise core.WorkflowError('3MF input exceeds the uncompressed size limit')
            for i in z.infolist():
                item=PurePosixPath(i.filename)
                if item.is_absolute() or '..' in item.parts or '\\' in i.filename or stat.S_ISLNK(i.external_attr >> 16):
                    raise core.WorkflowError('Unsafe 3MF package entry')
            model=_xml(z.read('3D/3dmodel.model'))
            settings=_xml(z.read('Metadata/model_settings.config'))
            rels=_xml(z.read('_rels/.rels'))
            types=_xml(z.read('[Content_Types].xml'))
        if model.tag != NS+'model' or model.get('unit','millimeter')!='millimeter':
            raise core.WorkflowError('3MF input requires the core model namespace and millimeter units')
        for rel in rels:
            if rel.get('TargetMode')=='External' or rel.get('Target','').lstrip('/')!='3D/3dmodel.model':
                raise core.WorkflowError('External or unexpected 3MF relationship')
        if len(rels)!=1:
            raise core.WorkflowError('Exactly one core-model relationship is required')
        if any(c.get('ContentType','').lower().find('gcode')>=0 for c in types):
            raise core.WorkflowError('Executable content type is not accepted')
        if any(c.tag not in {NS+'resources',NS+'build'} for c in model):
            raise core.WorkflowError('Unsupported model metadata/extensions require reviewed conversion')
        resources=model.find(NS+'resources');build=model.find(NS+'build')
        if resources is None or build is None or len(build)==0:
            raise core.WorkflowError('3MF input has no build geometry')
        objects={};meshes={};components={}
        for child in resources:
            if child.tag != NS+'object' or child.get('type','model')!='model':
                raise core.WorkflowError('Only core mesh/assembly resources are supported; painted/material-extension resources need reviewed conversion')
            oid=int(child.attrib['id'])
            if oid in objects or oid<1:
                raise core.WorkflowError('Duplicate or invalid 3MF object ID')
            if any(k not in {'id','type','name','partnumber'} for k in child.attrib):
                raise core.WorkflowError('3MF resource properties/material painting are not supported by this controlled input')
            objects[oid]=child
            if any(c.tag not in {NS+'mesh',NS+'components'} for c in child):
                raise core.WorkflowError('Unsupported object extensions require reviewed conversion')
            mesh=child.find(NS+'mesh');parts=child.find(NS+'components')
            if (mesh is None)==(parts is None):
                raise core.WorkflowError('Each 3MF object must contain one mesh or assembly')
            if mesh is not None:
                vertices=[tuple(float(v.attrib[k]) for k in ('x','y','z')) for v in mesh.findall(NS+'vertices/'+NS+'vertex')]
                if not vertices or any(not math.isfinite(n) for v in vertices for n in v):
                    raise core.WorkflowError('3MF contains non-finite or missing vertices')
                triangles=mesh.findall(NS+'triangles/'+NS+'triangle');edges=collections.Counter();directions=collections.Counter();volume=0.0
                for t in triangles:
                    if set(t.attrib)!={'v1','v2','v3'}:
                        raise core.WorkflowError('Triangle painting or unsupported attributes require reviewed conversion')
                    ids=tuple(int(t.attrib[k]) for k in ('v1','v2','v3'))
                    if len(set(ids))!=3 or min(ids)<0 or max(ids)>=len(vertices):
                        raise core.WorkflowError('3MF contains invalid triangle indices')
                    a,b,c=(vertices[i] for i in ids)
                    volume+=a[0]*(b[1]*c[2]-b[2]*c[1])+a[1]*(b[2]*c[0]-b[0]*c[2])+a[2]*(b[0]*c[1]-b[1]*c[0])
                    for u,v in zip(ids,ids[1:]+ids[:1]):
                        edges[tuple(sorted((u,v)))]+=1;directions[(u,v)]+=1
                if not triangles or any(n!=2 for n in edges.values()) or any(directions[(a,b)]!=directions[(b,a)] for a,b in edges) or abs(volume)<1e-10:
                    raise core.WorkflowError('3MF mesh must be closed, consistently wound and have nonzero volume')
                meshes[oid]={'vertices':len(vertices),'triangles':len(triangles)}
            else:
                components[oid]=list(parts)
        def transform(element):
            if any(k not in {'objectid','transform'} for k in element.attrib):
                raise core.WorkflowError('External component attributes are not accepted')
            if 'transform' in element.attrib:
                vals=[float(v) for v in element.attrib['transform'].split()]
                if len(vals)!=12 or not all(math.isfinite(n) for n in vals):
                    raise core.WorkflowError('Invalid 3MF component/build transform')
                det=vals[0]*(vals[4]*vals[8]-vals[5]*vals[7])-vals[1]*(vals[3]*vals[8]-vals[5]*vals[6])+vals[2]*(vals[3]*vals[7]-vals[4]*vals[6])
                if abs(det)<1e-12:
                    raise core.WorkflowError('Singular 3MF transform')
        def descendants(oid,stack=()):
            if oid not in objects or oid in stack:
                raise core.WorkflowError('Missing or cyclic 3MF component reference')
            if oid in meshes:return {oid}
            result=set()
            for c in components[oid]:
                if c.tag!=NS+'component':raise core.WorkflowError('Unexpected component element')
                transform(c);result.update(descendants(int(c.attrib['objectid']),stack+(oid,)))
            if not result:raise core.WorkflowError('Empty 3MF assembly')
            return result
        built=set()
        for item in build:
            if item.tag!=NS+'item':raise core.WorkflowError('Unexpected 3MF build item')
            transform(item)
            instance=descendants(int(item.attrib['objectid']))
            if built & instance:
                raise core.WorkflowError('Reused mesh instances need reviewed per-instance filament mapping')
            built.update(instance)
        if settings.tag!='config' or any(c.tag!='object' for c in settings):
            raise core.WorkflowError('Controlled model_settings may contain only explicit object/part assignments')
        assignments={}
        for obj in settings:
            oid=int(obj.attrib['id'])
            if set(obj.attrib)!={'id'} or oid not in objects:
                raise core.WorkflowError('Invalid model_settings object')
            def metadata(element):
                vals={}
                for child in element:
                    if child.tag=='part':continue
                    if child.tag!='metadata' or set(child.attrib)!={'key','value'} or child.get('key') not in {'extruder','name'} or child.get('key') in vals:
                        raise core.WorkflowError('Unsafe or unsupported model_settings field')
                    vals[child.get('key')]=child.get('value')
                return vals
            values=metadata(obj)
            if 'extruder' in values:
                for mesh_id in descendants(oid):assignments[mesh_id]=int(values['extruder'])
            for part in obj.findall('part'):
                if set(part.attrib)-{'id','subtype'} or part.get('subtype','normal_part')!='normal_part':
                    raise core.WorkflowError('Only normal mesh parts are supported')
                part_id=int(part.attrib['id'])
                if part_id not in descendants(oid):raise core.WorkflowError('Assigned part is not inside its object')
                part_values=metadata(part)
                if 'extruder' not in part_values:raise core.WorkflowError('Each part needs an explicit filament assignment')
                assignments[part_id]=int(part_values['extruder'])
        if set(assignments)!=built or any(not 1<=v<=filament_count for v in assignments.values()):
            raise core.WorkflowError('Every built mesh needs a valid explicit filament-profile assignment')
        return {'kind':'controlled_core_3mf','mesh_count':len(built),'meshes':{str(k):meshes[k] for k in sorted(built)},
                'object_filament_assignments':{str(k):assignments[k] for k in sorted(assignments)},
                'limitations':['core meshes/assemblies only','no painted triangles/textures/author project settings','actual multicolor slicer output must still be checked']}
    except (zipfile.BadZipFile,ET.ParseError,KeyError,ValueError,TypeError,IndexError) as exc:
        if isinstance(exc,core.WorkflowError):raise
        raise core.WorkflowError('Invalid controlled 3MF input: '+str(exc)) from exc


def validate_plate_object_count(path, expected_count, plate=1):
    """Reject a preserved single-plate layout if slicing omits or skips any object."""
    with zipfile.ZipFile(path) as archive:
        root = _xml(archive.read('Metadata/slice_info.config'))
        bbox_rows = json.loads(archive.read(f'Metadata/plate_{plate}.json')).get('bbox_objects', [])
    # Studio includes its generated wipe tower in the bbox inventory. It is
    # not an input model; exclude only the reserved identity AND exact name.
    towers = [r for r in bbox_rows if r.get('id') == 1000 and r.get('name') == 'wipe_tower']
    if len(towers) > 1:
        raise core.WorkflowError('Duplicate wipe tower identities in preserved layout')
    bbox_rows = [r for r in bbox_rows if not (r.get('id') == 1000 and r.get('name') == 'wipe_tower')]
    plates = [p for p in root.findall('.//plate') if any(m.get('key') == 'index' and m.get('value') == str(plate) for m in p.findall('metadata'))]
    if len(plates) != 1:
        raise core.WorkflowError('Preserved layout has no unambiguous selected plate')
    rows = plates[0].findall('object')
    # Bambu CLI --arrange 0 omits XML object rows but emits per-object sliced
    # bounding boxes in plate_N.json. Require the latter in both modes.
    if len(bbox_rows) != expected_count or len({r.get('id') for r in bbox_rows}) != expected_count or (rows and (len(rows) != expected_count or any(r.get('skipped') != 'false' for r in rows))):
        raise core.WorkflowError(f'Preserved layout object count mismatch: expected {expected_count}, sliced {len(bbox_rows)}; do not print an incomplete plate')


def validate_slice_output(path, inspection, plate=1):
    """Prove every assigned material survives slicing with positive usage.

    This does not prove placement/appearance; final sliced preview remains part
    of design review. It prevents silently accepting an all-one-material export.
    """
    try:
        with zipfile.ZipFile(path) as z:
            root=_xml(z.read('Metadata/slice_info.config'))
        plates=[p for p in root.findall('.//plate') if any(m.get('key')=='index' and m.get('value')==str(plate) for m in p.findall('metadata'))]
        if len(plates)!=1:
            raise core.WorkflowError('Controlled 3MF slice has no unambiguous selected plate')
        used=set()
        usage_rows={}
        for row in plates[0].findall('.//filament'):
            amounts=[float(row.get(k,'0')) for k in ('used_g','used_m')]
            if any(math.isfinite(v) and v>0 for v in amounts):
                fid=int(row.attrib['id'])
                if fid in usage_rows:
                    raise core.WorkflowError('Duplicate sliced material usage identity')
                used.add(fid)
                usage_rows[fid]=row
        expected=set(inspection['object_filament_assignments'].values())
        if not expected <= used:
            raise core.WorkflowError('Sliced material usage differs from controlled object assignments; inspect actual multicolor output before approval')
        # A separately selected support/interface filament is allowed only when
        # the generated archive explicitly declares it and confirms no object use.
        # Missing body materials or support material leaking into an object still fail.
        extra=used-expected
        if extra:
            with zipfile.ZipFile(path) as z:
                settings=json.loads(z.read('Metadata/project_settings.config'))
            if str(settings.get('enable_support'))!='1':
                raise core.WorkflowError('Extra sliced material requires enabled, explicit support settings')
            declared={int(settings.get(k,0)) for k in ('support_filament','support_interface_filament')}
            for fid in extra:
                row=usage_rows[fid]
                if fid not in declared or row.get('used_for_object')!='false' or row.get('used_for_support')!='true':
                    raise core.WorkflowError('Extra sliced material is not verified support-only usage')
    except (KeyError,ValueError,ET.ParseError,zipfile.BadZipFile) as exc:
        if isinstance(exc,core.WorkflowError):raise
        raise core.WorkflowError('Cannot verify controlled 3MF sliced material usage: '+str(exc)) from exc
