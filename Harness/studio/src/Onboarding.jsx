import React, {useEffect, useState} from 'react';
import {Check, Copy, ArrowRight} from 'lucide-react';
import './onboarding.css';

const roleStates = {
  pending: '待建立',
  creating: '创建结果待核对',
  created: '已建立，等待首次介绍',
  introduced: '已介绍并读取共同资料',
};

export default function Onboarding({onNavigate, onDocument}) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);
  const [copyText, setCopyText] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const response = await fetch('/api/onboarding', {cache: 'no-store', signal: controller.signal});
        if (!response.ok) throw new Error(`配置读取失败（${response.status}）`);
        setData(await response.json());
        setError('');
      } catch (failure) {
        if (failure.name !== 'AbortError') setError(failure.message);
      }
    }
    load();
    window.addEventListener('printlab:refresh', load);
    return () => {
      controller.abort();
      window.removeEventListener('printlab:refresh', load);
    };
  }, []);

  async function copySetup() {
    const text = `请继续配置我的 PrintLab，工作空间为 ${data.workspace}。先读取 AGENTS.md、docs/ONBOARDING.md 和 printlab onboarding status，接续已完成的步骤。核对已有角色聊天后，自动建立尚缺的 Mike 和 Sarah 两个独立聊天，让它们读取同一工作空间并分别介绍自己。读取设备和已装材料，再帮我登记其他耗材，按我的设备与使用目标引导第一件作品。`;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      setCopyText(text);
    }
  }

  function openDocument(row) {
    onDocument({title: row.name, path: row.path, url: '/api/documents/' + row.path});
  }

  return <div className="onboarding-page">
    <header className="page-heading">
      <div><h1>配置与队伍</h1><p>共同设备、使用习惯和项目进度，供每个会话接续。</p></div>
      {data && <button className="button primary" onClick={copySetup}>
        {copied ? <Check size={17}/> : <Copy size={17}/>}
        {copied ? '已复制，粘贴到配置会话' : '让 Agent 接着配置'}
      </button>}
    </header>
    {error && <div role="alert" className="inline-error">{error}。{data ? '保留上次读取的资料。' : '请刷新重试。'}</div>}
    {!data && !error && <p className="muted">正在读取共同配置…</p>}
    {data && <>
      <section className="onboarding-panel">
        <h2>接下来</h2>
        {data.next_actions.length > 0 ? <ul>{data.next_actions.map((action, index) =>
          <li key={`${action.kind}-${index}`}>{action.text}</li>
        )}</ul> : <p>基础配置已记录，可以继续自己的作品。</p>}
        {data.questions.length > 0 && <details>
          <summary>首次会话需要补齐的信息</summary>
          <ul>{data.questions.map(question => <li key={question.id}>{question.text}</li>)}</ul>
        </details>}
      </section>
      <div className="onboarding-roles">
        {data.roles.map(role => <section className="onboarding-panel" key={role.role}>
          <h2>{role.title}</h2>
          <p className="muted">{roleStates[role.status] || role.status}</p>
          {role.first_reply && <details><summary>首次介绍</summary><p className="role-reply">{role.first_reply}</p></details>}
          {role.thread_id && <dl><dt>聊天标识</dt><dd>{role.thread_id}</dd><dt>运行位置</dt><dd>{role.host_id}</dd></dl>}
          {role.status === 'creating' && <p>先由配置会话核对宿主中的创建结果，再继续登记。</p>}
        </section>)}
      </div>
      <section className="onboarding-panel">
        <h2>我的设备与材料</h2>
        <p>{data.device_card?.model || '机型待确认'} · {data.device?.message || '实时连接待检查'}</p>
        <p>{data.inventory?.state === 'online' ? `库存已读取，当前有 ${data.inventory.items.length} 条料卷记录。` : '库存尚未读取。'}</p>
        <button className="text-link" onClick={() => onNavigate('device')}>查看设备、已装材料与库存<ArrowRight size={16}/></button>
      </section>
      <section className="onboarding-panel">
        <h2>共同资料</h2>
        <div className="onboarding-documents">{data.shared_documents.filter(row => row.sha256).map(row =>
          <button className="text-link" key={row.name} onClick={() => openDocument(row)}>{row.path}<ArrowRight size={16}/></button>
        )}</div>
        <p className="muted onboarding-path">{data.workspace}</p>
      </section>
    </>}
    {copyText && <label className="field">复制到配置会话<textarea readOnly value={copyText} rows={6} onFocus={event => event.target.select()}/></label>}
  </div>;
}
