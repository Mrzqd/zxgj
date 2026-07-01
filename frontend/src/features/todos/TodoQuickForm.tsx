import { useState } from 'react';
import { api } from '../../api';
import { Modal } from '../../components/ui';
import { useSubmitting } from '../../hooks/useSubmitting';
import type { Todo } from '../../types';
import { datetimeLocalToIso } from '../../utils/format';
import { TODO_IMPORTANCE_OPTIONS } from '../../utils/todo';

function toDatetimeLocal(value?: string | null) {
  if (!value) return '';
  const date = new Date(value);
  const offsetMs = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

export function TodoFormModal({
  token,
  projectId,
  onRefresh,
  onClose,
  todo,
}: {
  token: string;
  projectId: number;
  onRefresh: () => Promise<void>;
  onClose: () => void;
  todo?: Todo;
}) {
  const [title, setTitle] = useState(todo?.title || '');
  const [description, setDescription] = useState(todo?.description || '');
  const [dueAt, setDueAt] = useState(toDatetimeLocal(todo?.due_at));
  const [importance, setImportance] = useState(todo?.importance || 3);
  const [status, setStatus] = useState(todo?.status || 'open');
  const { submitting, guard } = useSubmitting();

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    await guard(async () => {
      const payload = {
        title,
        description,
        due_at: datetimeLocalToIso(dueAt),
        importance,
        status,
      };
      if (todo) {
        await api.updateTodo(token, projectId, todo.id, payload);
      } else {
        await api.createTodo(token, projectId, payload);
      }
      setTitle('');
      setDescription('');
      setDueAt('');
      setImportance(3);
      setStatus('open');
      await onRefresh();
      onClose();
    });
  }

  return (
    <Modal title={todo ? '编辑待办' : '新增待办'} onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="油烟机止逆阀购买"
          required
          className="input"
        />
        <textarea
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          placeholder="说明，可选"
          className="input min-h-20"
        />
        <div className="grid grid-cols-2 gap-3">
          <input type="datetime-local" value={dueAt} onChange={(event) => setDueAt(event.target.value)} className="input" />
          <select value={importance} onChange={(event) => setImportance(Number(event.target.value))} className="input">
            {TODO_IMPORTANCE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <select value={status} onChange={(event) => setStatus(event.target.value)} className="input">
          <option value="open">待处理</option>
          <option value="doing">处理中</option>
          <option value="done">已完成</option>
        </select>
        <button disabled={submitting} className="secondary-button w-full">
          {submitting ? '提交中...' : todo ? '保存修改' : '添加待办'}
        </button>
      </form>
    </Modal>
  );
}
