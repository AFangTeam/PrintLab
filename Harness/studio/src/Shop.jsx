import React,{useEffect,useState} from 'react';
import {ShoppingBag,ArrowUpRight,ArrowLeft,Copy,Check,Search,Package} from 'lucide-react';

const statusNames={unverified:'待核实',needed:'待购',owned:'已有',purchased:'已购',settled:'已用 / 余料'};
const supplierNames={available:'创客宝库 · 可购买',unavailable:'创客宝库 · 不可购买',unverified:'创客宝库 · 尚未核实'};
const qty=(n,unit)=>n==null?'待核实':`${n} ${unit}`;
const safeLink=url=>{try{const u=new URL(url);return u.protocol==='https:'&&!u.username&&!u.password?u.href:null}catch{return null}};

export default function Shop({projectId,onNavigate}){
 const [data,setData]=useState(null),[error,setError]=useState(''),[query,setQuery]=useState(''),[filter,setFilter]=useState('all'),[copied,setCopied]=useState(null),[copyText,setCopyText]=useState('');
 useEffect(()=>{let active=true;setData(null);setError('');const load=()=>fetch('/api/shop'+(projectId?'?project='+encodeURIComponent(projectId):''),{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('购物清单暂时无法读取');return r.json()}).then(d=>{if(active){setData(d);setError('')}}).catch(e=>active&&setError(e.message));load();addEventListener('printlab:refresh',load);return()=>{active=false;removeEventListener('printlab:refresh',load)}},[projectId]);
 async function copy(item){const prompt=`请加载 当前 PrintLab 项目根目录的 AGENTS.md 和 printlab shop list。我要更新配件 ${item.id}（${item.name}）的库存或购买记录。请先向我核对具体数量，再通过共享 shop 命令保存；已有与已购不重复计数，不下单、不打印。`;try{await navigator.clipboard.writeText(prompt);setCopied(item.id)}catch{setCopyText(prompt)}}
 const rows=(data?.items||[]).filter(r=>(filter==='all'||r.status===filter)&&`${r.name} ${JSON.stringify(r.specification)} ${r.sources.map(s=>s.project_name).join(' ')}`.toLowerCase().includes(query.toLowerCase()));
 const project=projectId?data?.projects?.[projectId]:null;
 return <div className="shop-page">{projectId&&<button className="breadcrumb" onClick={()=>onNavigate('shop')}><ArrowLeft size={16}/>全部购物清单</button>}
 <header className="page-heading"><div><span className="eyebrow">SHOP LIST</span><h1>{projectId?'项目配件':'购物清单'}</h1><p>{projectId?(project?.name||projectId):'把确定要做的作品所需配件，攒在一起买。'}</p></div><span className="heading-count">{data?.items?.length??'—'}<small>种配件</small></span></header>
 <div className="shop-intro"><ShoppingBag size={24}/><div><strong>规格相同，合并采购</strong><p>已有与已购只计算一次；库存不清楚时先核实。制作决定会加入清单，打印仍需单独确认。</p></div></div>
 {projectId&&!project&&data&&<div className="quiet-empty">尚未记录这个项目的制作决定。明确要做以后，Agent 会检查配件并同步到这里。</div>}
 {Object.values(data?.projects||{}).filter(p=>!p.parts_reviewed).map(p=><div className="shop-pending" key={p.id}><span>{p.name} · 已决定制作，配件待梳理</span><button className="text-link" onClick={()=>onNavigate(`projects/${p.id}`)}>查看项目<ArrowUpRight size={16}/></button></div>)}
 <div className="collection-toolbar"><div className="filter-tabs scroll-tabs" role="group" aria-label="购物状态"><button aria-pressed={filter==='all'} className={filter==='all'?'selected':''} onClick={()=>setFilter('all')}>全部</button>{Object.entries(statusNames).map(([value,name])=><button key={value} aria-pressed={filter===value} className={filter===value?'selected':''} onClick={()=>setFilter(value)}>{name}{data?.counts?.[value]>0?` ${data.counts[value]}`:''}</button>)}</div><label className="search-box"><Search size={18}/><input aria-label="搜索配件" value={query} onChange={e=>setQuery(e.target.value)} placeholder="配件、规格或项目"/></label></div>
 {error&&<div role="alert" className="shop-pending">{error}。{data?'当前保留上次读取的记录。':'请稍后刷新。'}</div>}
 {!data&&!error?<p className="muted">正在读取购物清单…</p>:rows.length?<div className="shop-list">{rows.map(item=>{const url=item.supplier.status==='available'?safeLink(item.supplier.url):null;return <article className="shop-card" key={item.id}>
 <div className="shop-card-heading"><div><span className="section-eyebrow">{item.category}</span><h2>{item.name}</h2></div><span className={`status ${item.status==='needed'?'accent':''}`}>{statusNames[item.status]}</span></div>
 <dl className="shop-numbers"><div><dt>共需</dt><dd>{item.unknown_quantities>0?(item.required>0?`已知 ${qty(item.required,item.unit)}`:'待核实'):qty(item.required,item.unit)}{item.unknown_quantities>0&&<small>另有 {item.unknown_quantities} 项数量待核实</small>}</dd></div><div><dt>已有 · 未用</dt><dd>{qty(item.existing,item.unit)}</dd></div><div><dt>已购 · 未用</dt><dd>{qty(item.purchased,item.unit)}</dd></div><div><dt>还需购买</dt><dd>{qty(item.to_buy,item.unit)}</dd></div></dl>
 <details className="shop-detail"><summary>规格、来源与购买链接<ArrowUpRight size={16}/></summary><div className="shop-detail-body">
 <div><h3>具体规格 {item.spec_verified?'':'· 待核实'}</h3>{Object.keys(item.specification).length?<dl className="shop-spec">{Object.entries(item.specification).map(([key,value])=><div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl>:<p className="muted">尚未确认规格，不合并、不猜测型号。</p>}</div>
 <div><h3>来源项目</h3>{item.sources.length?item.sources.map(s=><div className="shop-source" key={`${s.project_id}-${s.requirement_id}`}>{s.project_id==='general'?<strong>{s.project_name}</strong>:<button className="text-link" onClick={()=>onNavigate(`projects/${s.project_id}`)}>{s.project_name}<ArrowUpRight size={16}/></button>}<span>{qty(s.quantity,item.unit)} · {s.active?(s.project_id==='general'?'采购需求':'待装配'):'已使用'}</span>{s.note&&<p>{s.note}</p>}</div>):<p className="muted">暂无待制作项目使用这份余料。</p>}<p className="shop-caption">数量始终按全部项目汇总，避免跨项目重复采购。</p></div>
 <div className="shop-supplier"><h3>{supplierNames[item.supplier.status]||supplierNames.unverified}</h3>{url?<a className="button secondary" href={url} target="_blank" rel="noopener noreferrer">查看匹配规格的商品<ArrowUpRight size={16}/></a>:<p className="muted">{item.supplier.status==='unavailable'?'已记录不可购买的核查结果，需另找来源。':'具体商品尚未核实，暂不提供购买链接。'}</p>}{item.supplier.evidence&&<p className="shop-caption">{item.supplier.evidence}</p>}{item.supplier.checked_at&&<p className="shop-caption">核查于 {new Date(item.supplier.checked_at).toLocaleDateString('zh-CN')}，下单前复核规格与库存。</p>}</div>
 {item.stock_note&&<p className="shop-caption">库存依据：{item.stock_note}</p>}
 </div></details><div className="shop-card-footer"><span>已购包含在途配件，不代表已到货。</span><button className="text-link" onClick={()=>copy(item)}>{copied===item.id?<Check size={16}/>:<Copy size={16}/>} {copied===item.id?'已复制，粘贴到对话':'在对话中更新库存'}</button></div>
 </article>})}</div>:data&&<div className="empty-state"><Package size={40} strokeWidth={1.2}/><h3>{query||filter!=='all'?'没有匹配的配件':'还没有需要采购的配件'}</h3><p>{query||filter!=='all'?'换一个关键词或状态试试。':'明确决定制作后，Agent 会把非打印配件加入这里。讨论中的想法不会自动加入。'}</p></div>}
 {copyText&&<label className="field shop-copy">复制到对话<textarea readOnly value={copyText} rows={5} onFocus={e=>e.target.select()}/></label>}
 <p className="shop-caption shop-endnote">购物清单由各个 PrintLab 会话共同维护。这里只查看、整理需求；不会下单或启动打印。</p>
 </div>
}
