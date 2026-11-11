import React,{useEffect,useState} from 'react';
import {Box,ArrowUpRight,Search} from 'lucide-react';
import './gallery.css';

const when=t=>t&&!Number.isNaN(+new Date(t))?new Intl.DateTimeFormat('zh-CN',{year:'numeric',month:'short',day:'numeric'}).format(new Date(t)):'时间未知';
const state={completed:'设备报告完成',failed:'打印失败',printing:'打印中',paused:'已暂停',unresolved:'状态待核对',cancelled:'已取消'};
export default function Gallery({onNavigate}){
 const [data,setData]=useState(null),[error,setError]=useState(''),[query,setQuery]=useState('');
 useEffect(()=>{let live=true;const load=()=>fetch('/api/history',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('记录暂不可用');return r.json()}).then(d=>{if(live){setData(d);setError('')}}).catch(()=>live&&setError('无法读取打印记录'));load();addEventListener('printlab:refresh',load);return()=>{live=false;removeEventListener('printlab:refresh',load)}},[]);
 const rows=(data?.items||[]).filter(r=>r.is_print_event).filter(r=>`${r.name} ${r.project_name||''}`.toLowerCase().includes(query.toLowerCase()));
 return <section className="gallery-section" aria-label="打印模型图册"><div className="section-heading gallery-heading"><div><span className="eyebrow">PRINTED MODELS</span><h2>我的打印图册</h2><p>从最近一次开始，向下浏览打印记录。</p></div><label className="search-box"><Search size={18}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="搜索模型" aria-label="搜索打印模型"/></label></div>
 <p className="gallery-note">优先展示当次切片模型；“原模型参考”未核实当次配色或修改。{data?.coverage?.cloud_history_synced===false?' Handy 云端完整历史尚未接通。':''}{data?.stale?' 连接中断，显示上次记录。':''}</p>
 {error?<div className="quiet-empty">{error}</div>:!data?<div className="quiet-empty">正在读取打印记录…</div>:rows.length?<div className="gallery-grid">{rows.map(r=><article className="gallery-card" key={r.id}><div className="gallery-cover">{r.model_preview?.url?<img src={r.model_preview.url} loading="lazy" alt={`${r.name}的切片模型预览`}/>:<div className="gallery-missing"><Box size={30} strokeWidth={1.2}/><span>模型预览待找回</span></div>}<span className="gallery-badge">{r.model_preview?.kind?.startsWith('reference')?'原模型参考':r.model_preview?'切片模型预览':'无模型预览'}</span></div><div className="gallery-card-content"><h3>{r.project_name||r.name}</h3>{r.project_name&&r.name!==r.project_name&&<p className="gallery-job">{r.name}</p>}<p>{when(r.started_at||r.created_at)} · {state[r.status]||r.status||'状态未知'}</p><div className="gallery-links">{r.project_id&&<button onClick={()=>onNavigate(`projects/${r.project_id}`)}>查看项目 <ArrowUpRight size={15}/></button>}{r.makerworld_url&&<a href={r.makerworld_url} target="_blank" rel="noreferrer">原模型页面 <ArrowUpRight size={15}/></a>}</div></div></article>)}</div>:<div className="quiet-empty">{query?'没有找到符合条件的打印记录。':(data?.state === 'unconfigured' ? data.message : '还没有捕获到打印记录。')}</div>}</section>
}
