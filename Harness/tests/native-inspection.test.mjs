import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {auditTemperatures,auditStartup,assertApproval,approvalMessageMatches,redactText,treeHash} from '../native-inspection.mjs';
const sha='a'.repeat(64),now=Date.now();
const inspection={model:'x2d',materials:['PETG'],usedFilamentPositions:[0],filamentNozzleIndices:[1],nozzleDiameters:[0.4,0.4],maxNozzleTemperature:245,maxBedTemperature:70,maxChamberTemperature:0,sha256:sha};
const settings={nozzle_temperature:['245'],nozzle_temperature_initial_layer:['245']};

test('startup requires real ordered AMS load, official templates and final correct heat/wait',()=>{
 const official=Object.fromEntries(['machine_start_gcode','machine_end_gcode','change_filament_gcode','layer_change_gcode','time_lapse_gcode'].map(key=>[key,'synthetic '+key]));
 const config={...official,...settings,filament_type:['PETG']};
 const g='M620 S0A\nT0\nM621 S0A\nM109 S245\n; CHANGE_LAYER\nG1 E1';
 assert.equal(auditStartup(g,config,official).ok,true);
 for(const bad of [g.replace('M620 S0A','; M620 S0A'),g.replace('T0','T1'),g.replace('M621 S0A','M621 S1A'),g.replace('; CHANGE_LAYER','M104 S205\n; CHANGE_LAYER')])assert.equal(auditStartup(bad,config,official).ok,false);
 assert.equal(auditStartup(g,{...config,machine_end_gcode:'simplified'},official).ok,false);
});

test('actual 205 is rejected when profile declares 245, without changing any limits',()=>{
 const r=auditTemperatures('; nozzle_temperature = 245\nM109 S205;\nG1 X20 Y20 E2\nM104 S0',settings,{...inspection,maxNozzleTemperature:205});
 assert.equal(r.ok,false);assert.equal(r.actual_max_nozzle_temperature,205);assert.equal(r.required_targets[0].found,false);assert.match(r.issues.join(' '),/245 C/);
});
test('explicit X2D physical nozzle and vendor targets match, duration is not heat',()=>{
 const r=auditTemperatures('M620.17 S245 L0 T1\nM104 T1 S245 N1\nG383.3 T140 L0\nSYNC T10000 R0\nM9711 M0 E1 S11 C10 O0 T15000\nM109 T1 S245\nM104 S0',settings,inspection);
 assert.equal(r.ok,true);assert.equal(r.actual_max_nozzle_temperature,245);assert.equal(r.temperature_commands.length,5);
});
test('temperature on a different physical nozzle is not a matching material target',()=>{
 assert.equal(auditTemperatures('M109 T0 S245',settings,inspection).ok,false);
});
test('upstream target from an unhandled command fails closed',()=>{
 assert.equal(auditTemperatures('M109 S245\nM104.99 S290',settings,{...inspection,maxNozzleTemperature:290}).ok,false);
});
test('missing required target metadata does not silently pass',()=>{
 assert.equal(auditTemperatures('M109 S245',{},inspection).ok,false);
});
test('job-bound fresh approval rejects a different job, future timestamp or expired approval',()=>{
 const request={job_id:'Jtest',sha256:sha,approval:{job_id:'Jtest',approved_at:new Date(now).toISOString(),fingerprint:'b'.repeat(64),confirmation:'User approved this task',plate_clear:true}};
 assert.doesNotThrow(()=>assertApproval(request,inspection,now));
 for(const change of [{job_id:'Jother'},{approved_at:new Date(now+1).toISOString()},{approved_at:new Date(now-1800001).toISOString()},{plate_clear:false},{fingerprint:''}])assert.throws(()=>assertApproval({...request,approval:{...request.approval,...change}},inspection,now));
});
test('only exact checked-file prompt can reuse the existing approval',()=>{
 const message=`Start a checked print on X2D (TEST-SERIAL)? Nozzles: 0.4, 0.4 mm. Materials: PETG. Peak targets: nozzle 245°C, bed 70°C, chamber 0°C. File SHA-256: ${sha}. Confirm the physical spool labels and that the build plate is clear.`;
 assert.equal(approvalMessageMatches(message,'TEST-SERIAL',inspection),true);
 assert.equal(approvalMessageMatches(message+' The printer reports FINISH: remove the previous part and debris before confirming.','TEST-SERIAL',inspection),true);
 const task='checked-01234567-0123-0123-0123-0123456789ab-Jold';
 const cancelled=message+` The previous checked task ${task} was explicitly cancelled. Confirm its part and debris have been removed before this new print.`;
 assert.equal(approvalMessageMatches(cancelled,'TEST-SERIAL',inspection,task),true);
 assert.equal(approvalMessageMatches(cancelled,'TEST-SERIAL',inspection,'another-task'),false);
 assert.equal(approvalMessageMatches(cancelled,'TEST-SERIAL',inspection),false);
 for(const bad of [message+' Previously cleared hardware codes: test',message.replace(sha,'c'.repeat(64)),message.replace('TEST-SERIAL','OTHER'),message.replace('245°C','300°C')])assert.equal(approvalMessageMatches(bad,'TEST-SERIAL',inspection),false);
});
test('redaction handles absent, empty and encoded credentials',()=>{
 assert.equal(redactText('plain',{ip:undefined,empty:''}),'plain');
 const r=redactText('s3cr/et s3cr%2Fet',{token:'s3cr/et'});assert.equal(r,'[redacted] [redacted]');
});
test('dependency tree pin changes on altered bytes, filenames or escaping links',()=>{
 const temp=fs.mkdtempSync(path.join(os.tmpdir(),'printlab-tree-test-'));
 try{fs.writeFileSync(path.join(temp,'a.js'),'one');const a=treeHash(temp).sha256;fs.writeFileSync(path.join(temp,'a.js'),'two');assert.notEqual(treeHash(temp).sha256,a);fs.symlinkSync('/etc/hosts',path.join(temp,'escape'));assert.throws(()=>treeHash(temp),/escapes/)}finally{fs.rmSync(temp,{recursive:true,force:true})}
});


test('dual nozzle grouped Bowden selection and inactive cooling preserve per-nozzle checks',()=>{
 const variants=['Direct Drive Standard','Direct Drive High Flow','Direct Drive E3D High Flow','Bowden Standard','Bowden High Flow','Bowden E3D High Flow'];
 const official=Object.fromEntries(['machine_start_gcode','machine_end_gcode','change_filament_gcode','layer_change_gcode','time_lapse_gcode'].map(k=>[k,'synthetic '+k]));
 const s={...official,filament_type:['PLA','PETG'],filament_map:['1','2'],physical_extruder_map:['1','0'],extruder_type:['Direct Drive','Bowden'],nozzle_volume_type:['Standard','Standard'],filament_extruder_variant:[...variants,...variants],nozzle_temperature_initial_layer:[...Array(6).fill(220),...Array(6).fill(245)],nozzle_temperature:[...Array(6).fill(220),245,250,250,250,250,250]};
 const i={materials:['PLA','PETG'],usedFilamentPositions:[0,1],filamentNozzleIndices:[1,0],maxNozzleTemperature:270};
 const g='M620 S0A\nT0\nM621 S0A\nM109 S220\nM104 T0 S25 N0\n; CHANGE_LAYER\nG1 E1\nM620 S1A\nM620.17 T0 S245 L1\nM620.10 A1 T270 P250\n';
 assert.equal(auditStartup(g,s,official).ok,true);assert.equal(auditTemperatures(g,s,i).ok,true);
 for(const bad of [g.replace('M109 S220','M109 S205'),g.replace('; CHANGE_LAYER','M104 T1 S205 N0\n; CHANGE_LAYER'),g.replace('M620 S0A','; M620 S0A')])assert.equal(auditStartup(bad,s,official).ok,false);
 assert.equal(auditTemperatures(g.replace('P250','P205'),s,i).ok,false);
 assert.equal(auditStartup(g,{...s,filament_map:['1','3']},official).ok,false);
});

test('purge A0/A1 are old/new roles, not filament positions',()=>{
 const i={materials:['PETG','PLA'],usedFilamentPositions:[],maxNozzleTemperature:270};
 const a=auditTemperatures('M620.10 A0 T270 P245\nM620.10 A1 T270 P245',{},i);
 assert.ok(a.temperature_commands.every(e=>e.filament===undefined));
 const b=auditTemperatures('T1\nM620 S0A\nM620.10 A0 T250 P230\nM620.10 A1 T270 P245',{},i);
 assert.deepEqual(b.temperature_commands.map(e=>e.filament),[1,1,0,0]);
});
