// Offline-only checks augment (never replace or weaken) the upstream inspector.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {execFileSync} from 'node:child_process';

export const sha256 = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
export const fileHash = file => sha256(fs.readFileSync(file));

export function treeHash(directory) {
  const hash=crypto.createHash('sha256');let files=0,bytes=0;
  function walk(dir) {
    for(const name of fs.readdirSync(dir).sort()) {
      const absolute=path.join(dir,name),relative=path.relative(directory,absolute),stat=fs.lstatSync(absolute);
      if(stat.isDirectory()){walk(absolute);continue}
      if(stat.isSymbolicLink()) {
        const target=fs.readlinkSync(absolute),resolved=fs.realpathSync(absolute);
        if(!resolved.startsWith(fs.realpathSync(directory)+path.sep))throw Error('Runtime dependency symlink escapes pinned tree');
        hash.update(`link\0${relative}\0${target}\0`);continue;
      }
      if(!stat.isFile())throw Error('Non-regular dependency in pinned tree');
      const content=fs.readFileSync(absolute);files++;bytes+=content.length;
      hash.update(`file\0${relative}\0${content.length}\0${sha256(content)}\0`);
    }
  }
  walk(directory);return {sha256:hash.digest('hex'),files,bytes};
}

export function verifyToolchain(root,manifest) {
  if(manifest.schema_version!==1)throw Error('Unrecognized native toolchain manifest');
  const commit=execFileSync('/usr/bin/git',['-C',path.join(root,'Runtime/vendor/bambu-printer-mcp'),'rev-parse','HEAD'],{encoding:'utf8'}).trim();
  if(commit!==manifest.vendor_commit)throw Error('Upstream native package revision changed');
  if(fs.realpathSync(process.execPath)!==fs.realpathSync(manifest.node.path)||process.version!==manifest.node.version||fileHash(process.execPath)!==manifest.node.sha256)throw Error('Node runtime differs from pinned native toolchain');
  for(const entry of manifest.files) {
    const file=path.isAbsolute(entry.path)?entry.path:path.join(root,entry.path);
    if(!fs.lstatSync(file).isFile()||fileHash(file)!==entry.sha256)throw Error(`Native toolchain integrity changed: ${entry.label}`);
  }
  for(const entry of manifest.trees) {
    if(treeHash(path.join(root,entry.path)).sha256!==entry.sha256)throw Error(`Native runtime dependencies changed: ${entry.label}`);
  }
  return {schema_version:1,manifest_sha256:fileHash(path.join(root,'Harness/native-toolchain.json')),package_version:manifest.package_version,vendor_commit:manifest.vendor_commit,node_version:manifest.node.version,plugin_version:manifest.plugin_version,integrity:'verified'};
}

function values(v){return Array.isArray(v)?v:typeof v==='string'?v.split(/[;,]/):[]}
export function selectedTemperature(settings,field,slot,count) {
  const raw=values(settings[field]);let index=slot;
  if(raw.length!==count) {
    const variants=values(settings.filament_extruder_variant),mapping=values(settings.filament_map),extruders=values(settings.extruder_type),flows=values(settings.nozzle_volume_type);
    if(!count||raw.length%count||variants.length!==raw.length||!flows.length||flows.some(v=>v!=='Standard'))return undefined;
    let variant='Direct Drive Standard';
    if(mapping.length||extruders.length) {
      const logical=Number(mapping[slot])-1;
      if(!Number.isInteger(logical)||logical<0||!extruders[logical]||!flows[logical])return undefined;
      variant=`${extruders[logical]} ${flows[logical]}`;
    }
    const size=raw.length/count,start=slot*size,found=[];
    for(let i=start;i<start+size;i++)if(variants[i]===variant)found.push(i);
    if(found.length!==1)return undefined;index=found[0];
  }
  const target=Number(raw[index]);return Number.isFinite(target)&&target>0?target:undefined;
}

function nozzleBindings(settings,count) {
  const logical=values(settings.filament_map),physical=values(settings.physical_extruder_map).map(Number);
  if(!logical.length&&!physical.length)return Array(count).fill(0);
  if(logical.length!==count||!physical.length||physical.some((v,i,a)=>!Number.isInteger(v)||v<0||v>=a.length)||new Set(physical).size!==physical.length)return undefined;
  if(logical.some(v=>!Number.isInteger(Number(v))||Number(v)<1||Number(v)>physical.length))return undefined;
  return logical.map(v=>physical[Number(v)-1]);
}
function parse(line) {
  line=line.replace(/\([^)]*\)/g,'').split(';',1)[0].trim().replace(/^N\d+\s*/i,'');
  const command=line.match(/^([GMT]\d+(?:\.\d+)?)(?=\s|[A-Z+-]|$)/i);
  if(!command)return null;
  const params={};for(const m of line.slice(command[0].length).matchAll(/([A-Z])\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))/gi))params[m[1].toUpperCase()]=Number(m[2]);
  return {command:command[1].toUpperCase(),params};
}

export function auditTemperatures(gcode,settings,inspection) {
  const events=[];let filament=inspection.materials?.length===1?0:undefined,pending;
  for(const [index,line] of gcode.split(/\r?\n/).entries()) {
    const parsed=parse(line);if(!parsed)continue;
    const {command:c,params:p}=parsed;
    if(/^T\d+$/.test(c)){const n=Number(c.slice(1));filament=n<inspection.materials.length?n:undefined;continue}
    if(c==='M620'&&p.S!==undefined)pending=Number.isInteger(p.S)&&p.S>=0&&p.S<inspection.materials.length?p.S:undefined;
    if(c==='M621'&&Number.isInteger(p.S)&&p.S>=0&&p.S<inspection.materials.length){filament=p.S;pending=undefined;}
    let targets=[];
    if(['M104','M109'].includes(c))targets=['S','R'];
    else if(c==='M620.1')targets=['T'];
    else if(c==='M620.10')targets=['T','P'];
    else if(c==='M620.17')targets=['S'];
    else if(['G150','G383','G383.3','M620.13'].includes(c))targets=['T'];
    else if(c==='M620.15')targets=['C'];
    for(const key of targets)if(Number.isFinite(p[key])) {
      const nozzle=['M104','M109'].includes(c)?p.T??p.N:c==='M620.17'?p.T:undefined;
      const slot=c==='M620.17'&&p.L>=0?p.L:c==='M620.10'?(p.A===1?pending??filament:p.A===0?filament:undefined):
        nozzle!==undefined?inspection.filamentNozzleIndices?.indexOf(nozzle):filament;
      events.push({line:index+1,command:c,parameter:key,target:p[key],filament:slot<0?undefined:slot,nozzle});
    }
  }
  const actualPeak=Math.max(0,...events.map(e=>e.target));
  const required=[];const issues=[];
  if(Math.abs(actualPeak-inspection.maxNozzleTemperature)>0.01)issues.push('Independent command coverage disagrees with the upstream nozzle peak; inspect unsupported vendor forms before dispatch');
  for(const slot of inspection.usedFilamentPositions||[]) {
    for(const field of ['nozzle_temperature_initial_layer','nozzle_temperature']) {
      const target=selectedTemperature(settings,field,slot,inspection.materials.length);
      if(target===undefined){issues.push(`Missing declared ${field} for filament ${slot+1}`);continue}
      const nozzle=inspection.filamentNozzleIndices?.[slot];
      const matches=events.filter(e=>e.command!=='M620.15'&&Math.abs(e.target-target)<0.01&&(e.filament===undefined||e.filament===slot)&&(e.nozzle===undefined||nozzle===undefined||e.nozzle===nozzle));
      required.push({filament:slot+1,field,target,nozzle_index:nozzle,found:matches.length>0,lines:matches.slice(0,8).map(e=>e.line)});
      if(!matches.length)issues.push(`Declared ${field} ${target} C for filament ${slot+1} does not appear in the selected plate's executable nozzle targets`);
    }
  }
  return {ok:issues.length===0,coverage:'declared-target-presence-and-upstream-peak',actual_max_nozzle_temperature:actualPeak,required_targets:required,temperature_commands:events.slice(0,100),issues,scope:'Command evidence only; not proof of physical temperature, extrusion, or full firmware execution semantics'};
}

export function auditStartup(gcode,settings,official) {
  const issues=[];
  for(const key of ['machine_start_gcode','machine_end_gcode','change_filament_gcode','layer_change_gcode','time_lapse_gcode']) {
    if(!official?.[key]||settings[key]!==official[key])issues.push(`X2D official ${key} differs or is missing`);
  }
  const lines=gcode.split(/\r?\n/),boundary=lines.findIndex(line=>line.trim()==='; CHANGE_LAYER');
  if(boundary<0)issues.push('Missing supported first-layer boundary');
  let selected,tool;const loads=[],heat=[],waits=[];
  const count=settings.filament_type?.length||0;
  const nozzles=nozzleBindings(settings,count);
  if(!nozzles)issues.push('Missing or ambiguous physical filament/nozzle mapping');
  for(let index=0;index<Math.max(0,boundary);index++) {
    const parsed=parse(lines[index]);if(!parsed)continue;
    const {command:c,params:p}=parsed;
    if(c==='M620'&&p.S!==undefined){selected=Number.isInteger(p.S)&&p.S>=0&&p.S<count?p.S:undefined;tool=undefined}
    if(/^T\d+$/.test(c))tool=Number(c.slice(1));
    if(c==='M621'&&selected!==undefined&&p.S===selected&&tool===selected)loads.push({line:index+1,filament_position:selected});
    if(['M104','M109'].includes(c)&&(p.S!==undefined||p.R!==undefined)) {
      const event={line:index+1,target:p.S??p.R,nozzle:p.T??p.N??nozzles?.[tool??0]};heat.push(event);if(c==='M109')waits.push(event);
    }
  }
  if(!loads.length)issues.push('Missing executable initial AMS M620 -> T -> M621 load sequence before first layer');
  else {
    const active=loads.at(-1).filament_position,target=selectedTemperature(settings,'nozzle_temperature_initial_layer',active,count),nozzle=nozzles?.[active];
    const activeHeat=heat.filter(e=>e.nozzle===nozzle),activeWaits=waits.filter(e=>e.nozzle===nozzle);
    if(!(target>0)||activeHeat.at(-1)?.target!==target||activeWaits.at(-1)?.target!==target)issues.push('Last executable nozzle target and wait before first layer must match declared material temperature');
  }
  return {ok:!issues.length,issues,first_layer_line:boundary<0?null:boundary+1,initial_ams_loads:loads,startup_nozzle_targets:heat,scope:'Command evidence only; not proof of physical feeding or extrusion'};
}

export function assertApproval(request,inspection,now=Date.now()) {
  const a=request.approval,age=now-Date.parse(a?.approved_at);
  if(a?.job_id!==request.job_id||a.plate_clear!==true||typeof a.confirmation!=='string'||!a.confirmation.trim()||!/^([a-f0-9]{64})$/.test(a.fingerprint||'')||!Number.isFinite(age)||age<0||age>1800000)throw Error('Fresh approval bound to this job and cleared plate is required');
  if(request.sha256!==inspection.sha256)throw Error('Approval request artifact does not match inspection');
}

export function approvalMessageMatches(message,serial,inspection,cancelledTask) {
  const base=`Start a checked print on ${inspection.model.toUpperCase()} (${serial})? Nozzles: ${inspection.nozzleDiameters.join(', ')} mm. Materials: ${inspection.materials.join(', ')}. Peak targets: nozzle ${inspection.maxNozzleTemperature}°C, bed ${inspection.maxBedTemperature}°C, chamber ${inspection.maxChamberTemperature}°C. File SHA-256: ${inspection.sha256}. Confirm the physical spool labels and that the build plate is clear.`;
  return message===base||message===base+' The printer reports FINISH: remove the previous part and debris before confirming.'||
    (!!cancelledTask && message===base+` The previous checked task ${cancelledTask} was explicitly cancelled. Confirm its part and debris have been removed before this new print.`);
}

export function redactText(value,secrets) {
  let text=typeof value==='string'?value:JSON.stringify(value);
  for(const secret of Object.values(secrets||{}).filter(v=>typeof v==='string'&&v.length>0)){
    for(const variant of new Set([secret,encodeURIComponent(secret),JSON.stringify(secret).slice(1,-1)]))text=text.split(variant).join('[redacted]');
  }
  return text;
}
