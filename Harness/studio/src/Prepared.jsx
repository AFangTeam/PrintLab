import React,{lazy,Suspense,useEffect,useRef,useState} from 'react';
import {Box,CheckCircle2,AlertCircle,Clock3,RefreshCw,Printer} from 'lucide-react';
import {estimateDuration,estimateWeight,materialDisplayColor} from './presentation';
const ModelViewer=lazy(()=>import('./ModelViewer'));
import './prepared.css';

const arr=x=>Array.isArray(x)?x:[];
function requestId(){if(globalThis.crypto?.randomUUID)return globalThis.crypto.randomUUID();if(!globalThis.crypto?.getRandomValues)throw Error('浏览器不支持安全随机数，无法启动');const bytes=crypto.getRandomValues(new Uint8Array(16));bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;const hex=Array.from(bytes,x=>x.toString(16).padStart(2,'0')).join('');return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;}
const path=(p,j)=>`/api/prepared/${encodeURIComponent(p)}/${encodeURIComponent(j)}`;
async function json(url,options){const response=await fetch(url,{cache:'no-store',...options});let data={};try{data=await response.json()}catch{}if(!response.ok)throw new Error(data.detail||data.message||data.error||`请求失败 (${response.status})`);return data}
const sameOriginUrl=value=>{if(!value)return null;try{const u=new URL(value,location.origin);return u.origin===location.origin?u.href:null}catch{return null}};
const detail=x=>typeof x==='string'?x:(x?.message||x?.label||x?.name||'待核实');

export default function Prepared(){
 const [items,setItems]=useState(null),[error,setError]=useState('');
 useEffect(()=>{let live=true;const load=()=>json('/api/prepared').then(d=>{if(live){setItems(arr(d.items));setError('')}}).catch(e=>live&&setError(e.message));load();addEventListener('printlab:refresh',load);return()=>{live=false;removeEventListener('printlab:refresh',load)}},[]);
 return <div className="prepared-page"><header className="page-heading"><div><span className="eyebrow">PREPARED PRINTS</span><h1>待打印</h1><p>准备好的任务会留在这里。启动前再核对设备和材料。</p></div></header>
 <SenderSetup/>
 {error&&<p className="prepared-alert" role="alert"><AlertCircle size={20}/>{error}</p>}
 {!items&&!error?<p className="muted">正在读取待打印任务…</p>:items?.length?<div className="prepared-list">{items.map((item,i)=><PreparedCard key={`${item.project_id||item.pid}-${item.job_id||item.jid}-${i}`} item={item}/>)}</div>:items&&<div className="empty-state"><Box size={32}/><h3>还没有待打印任务</h3><p>准备好的任务会显示在这里。</p></div>}
 </div>
}
function SenderSetup(){
 const [cap,setCap]=useState(null),[error,setError]=useState(''),[confirm,setConfirm]=useState(false),[busy,setBusy]=useState(false),[notice,setNotice]=useState('');
 const topLevel=window.top===window.self;
 async function refresh(){try{const result=await json('/api/prepared/sender/capability');setCap(result);setError('')}catch(e){setError(`发送助手状态暂不可用：${e.message}`)}}
 useEffect(()=>{refresh()},[]);
 async function enable(){if(!topLevel||busy)return;setBusy(true);setError('');try{const session=await json('/api/prepared/session');const result=await json('/api/prepared/sender/enable',{method:'POST',headers:{'Content-Type':'application/json','X-PrintLab-CSRF':session.csrf_token},body:JSON.stringify({request_permissions:true})});setNotice(result.message||'请在 macOS 系统设置中检查并勾选 PrintLab发送助手，然后刷新权限状态。');setConfirm(false);await refresh()}catch(e){setError(`暂时无法启用发送助手：${e.message}`)}finally{setBusy(false)}}
 if(!cap&&!error)return null;
 if(cap?.available===true&&!cap?.setup_required&&!notice&&!error)return null;
 const permission=value=>value===true?'已授权':value===false?'待授权':'待核实';
 return <section className="sender-setup" aria-label="发送助手设置"><div className="sender-setup-title"><div><span className="section-eyebrow">一次性设置</span><h2>启用 PrintLab发送助手</h2></div></div>
 <p>{cap?.message||'发送助手状态暂不可用，请稍后刷新。'}</p>
 {cap?.setup_required&&<p>macOS 需要为“PrintLab发送助手”授予辅助功能和屏幕读取权限，只用于核对和操作 Studio 发送窗口。请在系统设置中勾选这两项权限。</p>}
 {cap?.permissions&&<div className="sender-permissions"><span>辅助功能 · {permission(cap.permissions.accessibility)}</span><span>屏幕读取 · {permission(cap.permissions.screen_capture)}</span></div>}
 {arr(cap?.limitations).map((entry,i)=><p className="sender-note" key={i}>{detail(entry)}</p>)}{notice&&<p className="sender-note" role="status">{notice}</p>}{error&&<p className="prepared-alert" role="alert"><AlertCircle size={18}/>{error}</p>}
 {!topLevel&&<p className="sender-note">请独立打开工作台后启用发送助手。</p>}
 {confirm&&<div className="sender-confirm" role="group" aria-label="确认权限用途"><p>将请求辅助功能和屏幕读取权限，用于核对和操作 Studio 发送窗口。你仍需在 macOS 系统设置中勾选“PrintLab发送助手”。</p><div className="sender-actions"><button className="button primary" disabled={!topLevel||busy} onClick={enable}>{busy?'正在请求…':'确认并请求权限'}</button><button className="button secondary" disabled={busy} onClick={()=>setConfirm(false)}>取消</button></div></div>}
 {!confirm&&<div className="sender-actions">{cap?.setup_required&&<button className="button primary" disabled={!topLevel||busy} onClick={()=>setConfirm(true)}>启用发送助手</button>}<button className="button secondary" disabled={busy} onClick={refresh}><RefreshCw size={17}/>刷新权限状态</button></div>}
 </section>
}
function PreparedCard({item}){
 const pid=item.project_id||item.pid,jid=item.job_id||item.jid;
 const topLevel=window.top===window.self;
 const storageKey=`printlab-prepared:${pid}:${jid}`;
 const saved=(()=>{try{return JSON.parse(sessionStorage.getItem(storageKey)||'null')}catch{return null}})();
 const [check,setCheck]=useState(null),[clear,setClear]=useState(false),[busy,setBusy]=useState(''),[error,setError]=useState(''),[operation,setOperation]=useState(item.operation||saved?.operation||null),[uncertain,setUncertain]=useState(!!saved?.uncertain),[now,setNow]=useState(Date.now());
 const lock=useRef(false),opId=operation?.id||operation?.operation_id;
 useEffect(()=>{const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer)},[]);
 useEffect(()=>{if(!opId)return;let live=true,timer;const poll=async()=>{try{await json('/api/prepared/session');const data=await json(`/api/prepared/operations/${encodeURIComponent(opId)}`);if(!live)return;setOperation(data.operation||data);const s=(data.operation||data).state||(data.operation||data).status;if(['checking','queued','pending','running','dispatching','starting'].includes(s))timer=setTimeout(poll,2500)}catch{if(live)setUncertain(true)}};poll();return()=>{live=false;clearTimeout(timer)}},[opId]);
 useEffect(()=>{try{if(operation||uncertain)sessionStorage.setItem(storageKey,JSON.stringify({operation,uncertain}));else sessionStorage.removeItem(storageKey)}catch{}},[operation,uncertain,storageKey]);
 const expires=check?.expires_at?new Date(check.expires_at).getTime():NaN;
 const checksPass=arr(check?.checks).every(c=>['ok','pass','passed','ready'].includes(c.status));
 const valid=check?.ready===true&&checksPass&&arr(check?.blockers).length===0&&!!check?.check_token&&Number.isFinite(expires)&&expires>now;
 async function verify(){if(!topLevel||lock.current)return;lock.current=true;setBusy('check');setCheck(null);setClear(false);setError('');try{const session=await json('/api/prepared/session');const result=await json(`${path(pid,jid)}/check`,{method:'POST',headers:{'X-PrintLab-CSRF':session.csrf_token}});setCheck(result)}catch(e){setError(e.message)}finally{lock.current=false;setBusy('')}}
 async function start(){if(!topLevel||lock.current||!valid||!clear||operation||uncertain)return;lock.current=true;setBusy('start');setError('');try{const session=await json('/api/prepared/session');const result=await json(`${path(pid,jid)}/start`,{method:'POST',headers:{'Content-Type':'application/json','X-PrintLab-CSRF':session.csrf_token},body:JSON.stringify({check_token:check.check_token,plate_clear:true,request_id:requestId()})});setOperation(result.operation||result);setCheck(null)}catch(e){setCheck(null);setUncertain(true);setError(`提交结果待核对：${e.message}。请勿重复发送。`)}finally{lock.current=false;setBusy('')}}
 async function reconcile(){if(!topLevel||lock.current||!opId)return;lock.current=true;setBusy('reconcile');setError('');try{const session=await json('/api/prepared/session');const result=await json(`/api/prepared/operations/${encodeURIComponent(opId)}/reconcile`,{method:'POST',headers:{'X-PrintLab-CSRF':session.csrf_token}});setOperation(result.operation||result);setUncertain(false)}catch(e){setError(`设备核对失败：${e.message}。不会重新发送。`)}finally{lock.current=false;setBusy('')}}
 const preview=sameOriginUrl(item.preview_url||item.cover_url||'');const model=sameOriginUrl(item.model_url||'');const name=item.title||item.name||item.project_name||'待打印模型';const mats=arr(item.materials);const duration=estimateDuration(item.estimates?.prediction_seconds??item.prediction_seconds),weight=estimateWeight(item.estimates?.weight_grams??item.weight_grams);const state=operation?.state||operation?.status;
 return <article className="prepared-card"><div className="prepared-visual">{preview?<img src={preview} alt={`${name}预览`}/>:model?<Suspense fallback={<div className="cover-empty">正在载入模型…</div>}><ModelViewer url={model} name={name} interactive={false}/></Suspense>:<div className="cover-empty"><Box size={40}/><span>预览待生成</span></div>}</div><div className="prepared-content"><div className="prepared-heading"><div><span className="section-eyebrow">{item.project_name||pid} · {item.revision||'版本待核实'}</span><h2>{name}</h2>{(item.part_name||arr(item.parts).length>0)&&<p>部件：{item.part_name||arr(item.parts).join('、')}</p>}{item.note&&<p>{item.note}</p>}</div><span className="prepared-tag">{item.state_label||'待打印'}</span></div>
 {item.registration_issue&&<p className="prepared-alert"><AlertCircle size={18}/>{item.registration_issue}</p>}<div className="prepared-specs"><div><Clock3 size={17}/><span>{duration||item.duration||'耗时待核实'}</span></div><div><Box size={17}/><span>{weight||'用料待核实'}</span></div></div>
 <div className="prepared-materials">{mats.length?mats.map((m,i)=>{const c=typeof m==='object'?materialDisplayColor(m):null;return <span key={i}>{c&&<i style={{background:c.hex}}/>}{typeof m==='string'?m:[m.slot_label,m.name||m.series||m.material,m.required_grams!=null?`约 ${m.required_grams} g`:null].filter(Boolean).join(' · ')}</span>}):<span>材料待核实</span>}</div>
 {!topLevel&&<p className="prepared-alert" role="alert"><AlertCircle size={18}/>请独立打开工作台，再核验或启动打印。</p>}
 {!operation&&!uncertain&&<button className="button secondary prepared-check-button" disabled={!topLevel||!!busy||!pid||!jid} onClick={verify}><RefreshCw size={17}/>{busy==='check'?'正在核验…':'核验设备与材料'}</button>}
 {error&&<p className="prepared-alert" role="alert"><AlertCircle size={18}/>{error}</p>}
 {check&&<section className="prepared-check" aria-live="polite"><h3>{valid?'核验通过':check.ready?'核验已过期':'暂时不能启动'}</h3><ul>{arr(check.checks).map((c,i)=><li key={c.id||i} className={['ok','pass','passed','ready'].includes(c.status)?'good':'attention'}>{['ok','pass','passed','ready'].includes(c.status)?<CheckCircle2 size={17}/>:<AlertCircle size={17}/>}<span>{c.label}{c.message?`：${c.message}`:''}</span></li>)}{arr(check.blockers).filter(b=>!arr(check.checks).some(c=>c.id&&c.id===b.id)).map((b,i)=><li className="attention" key={`b${i}`}><AlertCircle size={17}/><span>{detail(b)}</span></li>)}</ul>{arr(check.materials).length>0&&<div className="prepared-quantities">{arr(check.materials).map((m,i)=><p key={i}><strong>{m.slot_label||'槽位待核实'}</strong> · 需 {m.required_grams??'未知'} g，预留 {m.reserve_grams??'未知'} g · {m.reported_remaining_percent!=null?`设备报告 ${m.reported_remaining_percent}%`:'设备余量未知'}{m.estimated_available_grams!=null?`，估算 ${m.estimated_available_grams} g`:''}。{m.message}</p>)}<p>余量按设备百分比和匹配料卷估算，可能滞后，并非称重。</p></div>}{valid&&<div className="prepared-start"><label><input type="checkbox" checked={clear} onChange={e=>setClear(e.target.checked)}/>我确认本次打印板已清洁并空置。</label><button className="button primary" disabled={!topLevel||!clear||!!busy} onClick={start}><Printer size={17}/>{busy==='start'?'正在提交…':'启动打印'}</button></div>}{check.ready&&!valid&&<p>请重新核验后再启动。</p>}</section>}
 {(operation||uncertain)&&<div className="prepared-operation" role="status"><strong>{uncertain?'提交结果待核对':({checking:'正在再次核验，尚未发送',blocked:'核验未通过，未发送',observed:'设备已读回匹配任务',queued:'等待处理',pending:'等待处理',running:'正在处理发送',dispatching:'正在发送',submitted:'已提交，等待设备确认',started:'设备已确认启动',printing:'设备报告打印中',unknown:'发送结果待核对',dispatch_unknown:'发送结果待核对',failed:'本次发送失败'}[state]||'正在核对提交状态')}</strong><p>{operation?.message||'请查看设备状态；不要重复发送。'}</p>{opId&&['unknown','submitted','observed'].includes(state)&&<button className="button secondary" disabled={!topLevel||!!busy} onClick={reconcile}>{busy==='reconcile'?'正在核对…':'核对设备结果'}</button>}{state==='blocked'&&!uncertain&&<button className="button secondary" onClick={()=>{setOperation(null);setCheck(null);setClear(false)}}>重新核验</button>}</div>}
 </div></article>
}
