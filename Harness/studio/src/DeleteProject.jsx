import React, {useRef, useState} from 'react';
import {ExternalLink, Trash2} from 'lucide-react';
import {requestJson} from './request-json';

export default function DeleteProject({project, onDeleted}) {
  const dialog = useRef(null);
  const submitting = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  if (window.top !== window.self) {
    return <a className="button secondary" href={location.href} target="_blank" rel="noopener noreferrer">
      独立打开以删除项目<ExternalLink size={16}/>
    </a>;
  }

  async function confirmDeletion() {
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError('');
    try {
      const session = await requestJson('/api/prepared/session');
      const result = await requestJson(`/api/projects/${encodeURIComponent(project.id)}`, {
        method: 'DELETE',
        headers: {'Content-Type': 'application/json', 'X-PrintLab-CSRF': session.csrf_token},
        body: JSON.stringify({confirm_id: project.id}),
      });
      if (result.deleted !== true || result.project_id !== project.id) {
        throw new Error('未收到这个项目的删除回执，请刷新项目图册核对。');
      }
      dialog.current?.close();
      onDeleted(project);
    } catch (cause) {
      setError(cause instanceof TypeError ? '连接中断，请刷新项目图册核对删除结果。' : cause.message);
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }

  return <>
    <button className="button secondary" onClick={() => {setError(''); dialog.current.showModal();}}>
      <Trash2 size={16}/>删除项目
    </button>
    <dialog ref={dialog} className="modal delete-project-dialog" aria-labelledby="delete-project-title"
      aria-describedby="delete-project-scope" onCancel={event => {if (submitting.current) event.preventDefault();}}>
      <h2 id="delete-project-title">删除这个项目？</h2>
      <div id="delete-project-scope">
        <p className="delete-project-name"><strong>{project.name}</strong> · {project.id}</p>
        <p>将永久删除此项目的本地文件夹，包括模型、切片和会话记录，同时移除它的待打印任务和购物需求。此操作无法撤销。</p>
      </div>
      {error && <p className="delete-project-error" role="alert">{error}</p>}
      <div className="delete-project-buttons">
        <button className="button secondary" autoFocus disabled={busy} onClick={() => dialog.current.close()}>取消</button>
        <button className="button delete-project-confirm" disabled={busy} onClick={confirmDeletion}>
          {busy ? '正在删除…' : '永久删除'}
        </button>
      </div>
    </dialog>
  </>;
}
