import { useState } from 'react';
import { CheckCircle2, ClipboardList, Edit3, Plus, RotateCcw, Trash2 } from 'lucide-react';
import { api } from '../../api';
import { EmptyLine, Field, InlineLoading, Modal, ModuleHero, SelectField, Tip } from '../../components/ui';
import { useSubmitting } from '../../hooks/useSubmitting';
import type { ProjectProgress, StageTask, Option } from '../../types';
import type { ProjectStage } from '../../types';
import { dateText, datetimeLocalToIso, labelOf } from '../../utils/format';

export function StageTasksScreen({
  projectId,
  token,
  stages,
  tasks,
  loading,
  onRefresh,
}: {
  projectId: number;
  token: string;
  stages: ProjectStage[];
  tasks: StageTask[];
  progress: ProjectProgress | null;
  loading: boolean;
  onRefresh: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<StageTask | null>(null);
  const [stageFilter, setStageFilter] = useState('all');
  const [busyTaskId, setBusyTaskId] = useState<number | null>(null);
  const [deletingTaskId, setDeletingTaskId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const stageOptions: Option[] = [{ value: 'all', label: '全部阶段' }, ...stages];
  const filteredTasks = tasks.filter((task) => stageFilter === 'all' || task.stage === stageFilter);
  const openCount = tasks.filter((task) => task.status !== 'done').length;
  const doneCount = tasks.length - openCount;

  async function toggleTask(task: StageTask) {
    setBusyTaskId(task.id);
    try {
      setActionError(null);
      await api.updateStageTask(token, projectId, task.id, { status: task.status === 'done' ? 'open' : 'done' });
      await onRefresh();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : '阶段事项更新失败');
    } finally {
      setBusyTaskId(null);
    }
  }

  async function deleteTask(task: StageTask) {
    if (!window.confirm(`确认删除阶段事项「${task.title}」？`)) return;
    setDeletingTaskId(task.id);
    try {
      setActionError(null);
      await api.deleteStageTask(token, projectId, task.id);
      await onRefresh();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : '阶段事项删除失败');
    } finally {
      setDeletingTaskId(null);
    }
  }

  return (
    <div className="space-y-4">
      <ModuleHero icon={<ClipboardList />} title="阶段事项" subtitle="把瓦工开工前的海棠角、归方、找平等现场事项提前排好。" />
      {loading && <InlineLoading text="阶段事项加载中..." />}
      <Tip message={actionError} onClose={() => setActionError(null)} tone="error" />
      <div className="grid grid-cols-3 gap-2">
        <SummaryPill label="全部" value={tasks.length} />
        <SummaryPill label="未完成" value={openCount} />
        <SummaryPill label="已完成" value={doneCount} />
      </div>
      <SelectField label="阶段筛选" value={stageFilter} onChange={setStageFilter} options={stageOptions} />
      <button onClick={() => setOpen(true)} className="primary-button w-full">
        <Plus className="h-4 w-4" /> 新增事项
      </button>
      <div className="space-y-3">
        {filteredTasks.map((task) => (
          <div key={task.id} className="rounded-[1.5rem] bg-white p-4 shadow-sm">
            <div className="flex items-center justify-between">
              <span className="rounded-full bg-moss/10 px-3 py-1 text-xs font-semibold text-moss">
                {labelOf(stages, task.stage)}
              </span>
              <span className={`rounded-full px-3 py-1 text-xs font-semibold ${task.status === 'done' ? 'bg-moss/10 text-moss' : 'bg-sand text-ink/55'}`}>
                {task.status === 'done' ? '已完成' : '待处理'}
              </span>
            </div>
            <p className="mt-3 font-semibold">{task.title}</p>
            {task.description && <p className="mt-2 text-sm leading-6 text-ink/60">{task.description}</p>}
            <p className="mt-3 text-xs text-ink/45">截止 {dateText(task.due_at)} · 创建 {dateText(task.created_at)}</p>
            <div className="mt-3 grid grid-cols-3 gap-2">
              <button
                disabled={busyTaskId === task.id}
                className="inline-flex items-center justify-center gap-1 rounded-full bg-moss/10 px-3 py-2 text-xs font-semibold text-moss disabled:opacity-50"
                onClick={() => toggleTask(task)}
              >
                {task.status === 'done' ? <RotateCcw className="h-3.5 w-3.5" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
                {busyTaskId === task.id ? '处理中' : task.status === 'done' ? '重开' : '完成'}
              </button>
              <button
                onClick={() => setEditing(task)}
                className="inline-flex items-center justify-center gap-1 rounded-full bg-sand px-3 py-2 text-xs font-semibold text-ink"
              >
                <Edit3 className="h-3.5 w-3.5" /> 编辑
              </button>
              <button
                disabled={deletingTaskId === task.id}
                onClick={() => deleteTask(task)}
                className="inline-flex items-center justify-center gap-1 rounded-full bg-clay/10 px-3 py-2 text-xs font-semibold text-clay disabled:opacity-50"
              >
                <Trash2 className="h-3.5 w-3.5" />
                {deletingTaskId === task.id ? '删除中' : '删除'}
              </button>
            </div>
          </div>
        ))}
        {filteredTasks.length === 0 && <EmptyLine text={tasks.length === 0 ? '还没有阶段事项' : '当前筛选下没有阶段事项'} />}
      </div>
      {open && (
        <StageTaskForm
          token={token}
          projectId={projectId}
          stages={stages}
          onClose={() => setOpen(false)}
          onSaved={onRefresh}
        />
      )}
      {editing && (
        <StageTaskForm
          token={token}
          projectId={projectId}
          stages={stages}
          task={editing}
          onClose={() => setEditing(null)}
          onSaved={onRefresh}
        />
      )}
    </div>
  );
}

function SummaryPill({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-2xl bg-white p-3 shadow-sm">
      <p className="font-display text-xl font-black">{value}</p>
      <p className="text-xs font-semibold text-ink/45">{label}</p>
    </div>
  );
}

export function StageTaskForm({
  projectId,
  token,
  stages,
  onClose,
  onSaved,
  task,
}: {
  projectId: number;
  token: string;
  stages: ProjectStage[];
  onClose: () => void;
  onSaved: () => Promise<void>;
  task?: StageTask;
}) {
  const [stage, setStage] = useState(task?.stage || stages[0]?.value || 'design');
  const [title, setTitle] = useState(task?.title || '');
  const [description, setDescription] = useState(task?.description || '');
  const [status, setStatus] = useState(task?.status || 'open');
  const [dueAt, setDueAt] = useState(toDatetimeLocal(task?.due_at));
  const { submitting, guard } = useSubmitting();

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    await guard(async () => {
      const payload = {
        stage,
        title,
        description,
        due_at: datetimeLocalToIso(dueAt),
        status,
      };
      if (task) {
        await api.updateStageTask(token, projectId, task.id, payload);
      } else {
        await api.createStageTask(token, projectId, payload);
      }
      await onSaved();
      onClose();
    });
  }

  return (
    <Modal title={task ? '编辑阶段事项' : '新增阶段事项'} onClose={onClose}>
      <form onSubmit={submit}>
        <SelectField label="装修阶段" value={stage} onChange={setStage} options={stages} />
        <Field label="事项">
          <input value={title} onChange={(event) => setTitle(event.target.value)} required className="input" />
        </Field>
        <Field label="说明">
          <textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="例如：瓦工开工前确认海棠角、归方、找平"
            className="input min-h-24"
          />
        </Field>
        <SelectField
          label="状态"
          value={status}
          onChange={setStatus}
          options={[
            { value: 'open', label: '待处理' },
            { value: 'doing', label: '进行中' },
            { value: 'done', label: '已完成' },
          ]}
        />
        <Field label="截止时间">
          <input type="datetime-local" value={dueAt} onChange={(event) => setDueAt(event.target.value)} className="input" />
        </Field>
        <button disabled={submitting} className="primary-button w-full">
          {submitting ? '保存中...' : task ? '保存修改' : '保存'}
        </button>
      </form>
    </Modal>
  );
}

function toDatetimeLocal(value?: string | null) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const offsetMs = date.getTimezoneOffset() * 60 * 1000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}
