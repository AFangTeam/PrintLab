import React,{useEffect,useState} from 'react';
import {Clock3,CheckCircle2,AlertCircle,Printer} from 'lucide-react';
import {estimateDuration,estimateWeight} from './presentation';
import './print-status.css';

const phase={dispatching:'正在下发',submitted:'已接受 · 等待设备确认',preparing:'准备 / 加热中',running:'运行中 · 首层未核实',printing:'设备报告打印进度',paused:'已暂停',awaiting_physical_review:'设备完成 · 待实物验收',failed:'本次任务失败',cancelled:'本次任务取消',dispatch_unknown:'执行结果待核对',awaiting_approval:'待确认打印',approved:'已确认 · 尚未下发',awaiting_configuration:'试切片 · 待配置'};
const date=t=>t?new Date(t).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit'}):'尚无记录';

export function CurrentAttempt({record:r}){
 if(!r)return null;
 const observation=r.reconciliation,uncertain=observation&&observation.state!=='current',p=r.printer_progress;
 return <section className="current-attempt" aria-label="当前打印任务"><div className="attempt-title"><Printer size={22}/><div><span className="section-eyebrow">当前打印尝试</span><h2>{uncertain?'状态待核对':phase[r.state]||r.state}</h2></div></div><p>{r.execution_phase||(r.trial_only?'配置核对完成后再确认打印。':'与下方历史任务分开记录。')}</p>{p&&<p>设备进度 {p.progress??'未知'}% · 层数 {p.layer_num??'未知'} / {p.total_layers??'未知'}</p>}{uncertain&&<p className="attempt-warning">{observation.message||'当前显示上次状态；没有重发任务。'}</p>}<div className="attempt-meta"><span>{r.id}</span><span>{r.mapping?.transport==='bambu_native'?'原生通道 · 内部存储':'打印管理队列'}</span><span>更新 {date(r.last_reconciled_at||r.updated_at||r.created_at)}</span></div></section>
}

export function ConfirmationCard({projectId}){
 const [card,setCard]=useState(null),[error,setError]=useState('');
 useEffect(()=>{let alive=true;const load=()=>fetch(`/api/projects/${encodeURIComponent(projectId)}/confirmation`,{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('确认信息暂时无法读取');return r.json()}).then(c=>{if(alive){setCard(c);setError('')}}).catch(e=>alive&&setError(e.message));load();addEventListener('printlab:refresh',load);return()=>{alive=false;removeEventListener('printlab:refresh',load)}},[projectId]);
 if(error)return <p className="attempt-warning" role="alert">{error}，刷新后重试。</p>;if(!card)return null;
 const rows=[['模型',`${card.project_name} · ${card.revision||'版本待确认'}`],['打印板',card.plate_type||'板型待核实'],['预计耗时',estimateDuration(card.estimates?.prediction_seconds)||'尚未估算'],['预计用料',estimateWeight(card.estimates?.weight_grams)||'尚未估算']];
 const facts=card.facts||{},names={design_selected:'造型已选定',colors_selected:'配色已确认',material_loaded:'装料已确认',plate_clear:'本次打印板已清空',print_authorized:'具体任务已获授权'};
 return <section className="confirmation-card" aria-label="打印确认卡"><div className="section-heading"><div><span className="eyebrow">{card.already_dispatched?'TASK RECORD':'READY TO REVIEW'}</span><h2>{card.already_dispatched?'这次任务的确认记录':'打印确认卡'}</h2></div></div><dl className="confirmation-specs">{rows.map(([key,value])=><div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl>
 {card.routes?.length>0&&<div className="confirmation-routes">{card.routes.map((r,i)=><div key={i}><strong>AMS {String.fromCharCode(65+(r.ams_id||0))} · 槽 {r.slot_number}</strong><span>{r.english_label||r.material||'Material not identified'}{r.material_number?` (${r.material_number})`:''}</span><span>{r.route_text||(r.physical_extruder==null?'喷嘴路线待核实':`→ 喷嘴 ${r.physical_extruder+1}`)}</span></div>)}</div>}
 <div className="confirmation-facts">{Object.entries(facts).map(([key,f])=><p key={key}>{f.value?<CheckCircle2 size={16}/>:<AlertCircle size={16}/>}<span>{names[key]||key}{!f.value?' · 已撤回':!card.already_dispatched&&f.fresh===false?' · 已过期，需更新':''}<small>{date(f.recorded_at)}</small></span></p>)}</div>
 {(card.validation_alerts||[]).map((a,i)=><p className="attempt-warning" key={i}><AlertCircle size={18}/><span>{a.message}</span></p>)}
 {card.already_dispatched?<p className="confirmation-caption">这次任务已经下发，保留提交时的确认；这里不会重复发送。</p>:card.missing?.length>0?<div className="confirmation-missing"><h3>还缺这些信息</h3><ul>{card.missing.map((m,i)=><li key={i}>{m.label}{m.needs_user?'':' · 由工作流核查'}</li>)}</ul></div>:<p className="confirmation-caption">已记录的回答会沿用；下发前仍需核对实时设备及准确文件。</p>}
 <p className="confirmation-caption"><Clock3 size={15}/>读取 {date(card.observed_at)} · 耗时与用料是切片估算。板型长期保存，本次清板另行记录。</p></section>
}
