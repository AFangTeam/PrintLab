#!/usr/bin/env python3
"""Resolve installed Bambu profile inheritance and ordered includes without editing originals.

BambuStudio PresetBundle.cpp applies inherited values, then ordered includes,
then the profile's own values. Pure gcode template includes contribute their
explicit keys (not a fresh generic-machine default). Provenance stays separate.
"""
import argparse
import hashlib
import json
from pathlib import Path

META = {'inherits', 'include'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ProfileResolver:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.files = {}
        for p in sorted(self.directory.glob('*.json')):
            if p.is_symlink():
                raise ValueError('Symlink profile is not allowed')
            data = json.loads(p.read_text(encoding="utf-8"))
            for name in {p.stem, data.get('name')} - {None, ''}:
                if name in self.files and self.files[name] != p:
                    raise ValueError('Ambiguous profile name: '+name)
                self.files[name] = p
        self.sources = {}
        self.cache = {}

    def resolve(self, name, stack=()):
        if name in stack:
            raise ValueError('Cyclic profile references: '+' -> '.join((*stack,name)))
        if name not in self.files:
            raise ValueError('Missing profile reference: '+str(name))
        if name in self.cache:
            return dict(self.cache[name])
        path = self.files[name]
        data = json.loads(path.read_text(encoding="utf-8"))
        self.sources[str(path)] = {'path':str(path),'sha256':digest(path)}
        parent = data.get('inherits')
        if parent and not isinstance(parent,str):
            raise ValueError('inherits must identify one named profile')
        result = self.resolve(parent, (*stack,name)) if parent else {}
        includes = data.get('include', [])
        if isinstance(includes,str): includes=[includes]
        if not isinstance(includes,list) or any(not isinstance(i,str) or not i for i in includes):
            raise ValueError('include must contain named profiles')
        for include in includes:
            values = self.resolve(include, (*stack,name))
            result.update({k:v for k,v in values.items() if k not in {'name','instantiation','type','from'}})
        result.update({k:v for k,v in data.items() if k not in META})
        self.cache[name] = dict(result)
        return result


def write_candidate(profile, output):
    profile=Path(profile).resolve(); output=Path(output)
    if output.exists() or output.with_suffix('.sources.json').exists():
        raise ValueError('Candidate output already exists; preserve it and use a new version')
    resolver=ProfileResolver(profile.parent)
    result=resolver.resolve(profile.stem)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n', encoding="utf-8")
    receipt={'schema_version':1,'profile':str(profile),'output_sha256':digest(output),'merge_order':'inherits -> ordered includes -> own explicit values','source_files':list(resolver.sources.values()),'scope':'configuration candidate, not print approval or physical validation','source_reference':'https://github.com/bambulab/BambuStudio/blob/master/src/libslic3r/PresetBundle.cpp'}
    output.with_suffix('.sources.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n', encoding="utf-8")
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('profile');p.add_argument('--output',required=True)
    a=p.parse_args(); print(json.dumps(write_candidate(a.profile,a.output),ensure_ascii=False,indent=2))
