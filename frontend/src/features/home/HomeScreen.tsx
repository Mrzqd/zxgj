import { CheckCircle2, CheckSquare, ChevronDown, Edit3, Plus, RotateCcw, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { api } from '../../api';
import type { AppData } from '../../app/types';
import { Card, EmptyLine, InlineLoading, Metric, Tip } from '../../components/ui';
import type { Project, StageTask, Todo } from '../../types';
import { dateText, labelOf, money } from '../../utils/format';
import { todoImportanceLabel } from '../../utils/todo';
import { StageTaskForm } from '../stageTasks/StageTasksScreen';
import { TodoFormModal } from '../todos/TodoQuickForm';

export function HomeScreen({
  data,
  project,
  token,
  loading,
  onRefreshTodos,
  onRefreshStageTasks,
}: {
  data: AppData;
  project: Project;
  token: string;
  loading: {
    overview: boolean;
    progress: boolean;
    todos: boolean;
    stageTasks: boolean;
  };
  onRefreshTodos: () => Promise<void>;
  onRefreshStageTasks: () => Promise<void>;
}) {
  const total = data.expenses.reduce((sum, item) => sum + Number(item.amount), 0);
  const openTodos = data.todos.filter((todo) => todo.status !== 'done');
  const currentStage = data.progress?.current_stage || data.stages[0]?.value || 'design';
  const currentStageIndex = Math.max(0, data.stages.findIndex((stage) => stage.value === currentStage));
  const currentStageDetail = data.stages.find((stage) => stage.value === currentStage);
  const currentStageStartedAt = currentStageDetail?.started_at || data.progress?.updated_at;
  const currentStageDays = currentStageStartedAt
    ? Math.max(1, Math.floor((Date.now() - new Date(currentStageStartedAt).getTime()) / 86_400_000) + 1)
    : 0;
  const [todoModalOpen, setTodoModalOpen] = useState(false);
  const [editingTodo, setEditingTodo] = useState<Todo | null>(null);
  const [editingStageTask, setEditingStageTask] = useState<StageTask | null>(null);
  const [todoFilter, setTodoFilter] = useState<'open' | 'done' | 'all'>('open');
  const [todosExpanded, setTodosExpanded] = useState(false);
  const [tasksExpanded, setTasksExpanded] = useState(false);
  const [busyTodoId, setBusyTodoId] = useState<number | null>(null);
  const [busyStageTaskId, setBusyStageTaskId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [stageTaskError, setStageTaskError] = useState<string | null>(null);
  const sortedStageTasks = data.stageTasks
    .filter((task) => task.status !== 'done' && task.stage === currentStage)
    .sort((a, b) => compareOptionalDate(a.due_at, b.due_at));
  const visibleStageTasks = tasksExpanded ? sortedStageTasks : sortedStageTasks.slice(0, 3);
  const filteredTodos = data.todos
    .filter((todo) => {
      if (todoFilter === 'all') return true;
      if (todoFilter === 'done') return todo.status === 'done';
      return todo.status !== 'done';
    })
    .sort(compareTodos);
  const visibleTodos = todosExpanded ? filteredTodos : filteredTodos.slice(0, 3);

  async function toggleTodo(todo: Todo) {
    if (todo.status !== 'done' && !window.confirm(`确认完成待办「${todo.title}」？`)) return;
    setBusyTodoId(todo.id);
    try {
      setActionError(null);
      await api.updateTodo(token, project.id, todo.id, { status: todo.status === 'done' ? 'open' : 'done' });
      await onRefreshTodos();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : '待办更新失败');
    } finally {
      setBusyTodoId(null);
    }
  }

  async function deleteTodo(todo: Todo) {
    if (!window.confirm(`确认删除待办「${todo.title}」？`)) return;
    setBusyTodoId(todo.id);
    try {
      setActionError(null);
      await api.deleteTodo(token, project.id, todo.id);
      await onRefreshTodos();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : '待办删除失败');
    } finally {
      setBusyTodoId(null);
    }
  }

  async function toggleStageTask(task: StageTask) {
    setBusyStageTaskId(task.id);
    try {
      setStageTaskError(null);
      await api.updateStageTask(token, project.id, task.id, { status: task.status === 'done' ? 'open' : 'done' });
      await onRefreshStageTasks();
    } catch (error) {
      setStageTaskError(error instanceof Error ? error.message : '阶段事项更新失败');
    } finally {
      setBusyStageTaskId(null);
    }
  }

  async function deleteStageTask(task: StageTask) {
    if (!window.confirm(`确认删除阶段事项「${task.title}」？`)) return;
    setBusyStageTaskId(task.id);
    try {
      setStageTaskError(null);
      await api.deleteStageTask(token, project.id, task.id);
      await onRefreshStageTasks();
    } catch (error) {
      setStageTaskError(error instanceof Error ? error.message : '阶段事项删除失败');
    } finally {
      setBusyStageTaskId(null);
    }
  }

  return (
    <div className="space-y-4">
      <div className="overflow-hidden rounded-[2rem] bg-ink p-5 text-white shadow-card">
        <p className="text-sm text-white/60">
          {[project.address, project.name].filter(Boolean).join(' · ') || '家的装修现场'}
        </p>
        <div className="mt-7">
          <p className="text-sm text-white/60">累计支出</p>
          <p className="mt-1 font-display text-4xl font-black">{money(total)}</p>
        </div>
        <div className="mt-6 grid grid-cols-3 gap-3 text-center text-sm">
          <Metric label="待办" value={openTodos.length} />
          <Metric label="事项" value={data.stageTasks.length} />
          <Metric label="成员" value={data.members.length} />
        </div>
      </div>
      {loading.overview && <InlineLoading text="首页统计加载中..." />}
      <Card title="装修进度" action={labelOf(data.stages, currentStage)}>
        {loading.progress && <InlineLoading text="装修进度加载中..." />}
        <div className="space-y-2">
          <div className="h-2 overflow-hidden rounded-full bg-sand">
            <div
              className="h-full rounded-full bg-moss"
              style={{
                width: `${data.stages.length > 1 ? ((currentStageIndex + 1) / data.stages.length) * 100 : 0}%`,
              }}
            />
          </div>
          <div className="flex items-center justify-between text-xs text-ink/50">
            <span>{labelOf(data.stages, currentStage)}已持续 {currentStageDays} 天</span>
            <span>计划 {currentStageDetail?.planned_days || '-'} 天 · {currentStageIndex + 1}/{data.stages.length}</span>
          </div>
          {data.progress?.note && <p className="rounded-xl bg-sand px-3 py-2 text-xs text-ink/60">{data.progress.note}</p>}
        </div>
      </Card>
      <Card
        title="待办"
        action={
          <button
            onClick={() => setTodoModalOpen(true)}
            className="inline-flex items-center gap-1 rounded-full bg-clay px-2.5 py-1 text-xs font-bold text-white"
          >
            <Plus className="h-3.5 w-3.5" /> {openTodos.length}
          </button>
        }
      >
        {loading.todos && <InlineLoading text="待办数据加载中..." />}
        <Tip message={actionError} onClose={() => setActionError(null)} tone="error" />
        <div className="mb-2 grid grid-cols-3 gap-2 text-xs font-semibold">
          {[
            ['open', `待处理 ${openTodos.length}`],
            ['done', `已完成 ${data.todos.length - openTodos.length}`],
            ['all', `全部 ${data.todos.length}`],
          ].map(([value, label]) => (
            <button
              key={value}
              onClick={() => setTodoFilter(value as 'open' | 'done' | 'all')}
              className={`rounded-full px-2 py-1.5 ${todoFilter === value ? 'bg-ink text-white' : 'bg-sand text-ink/60'}`}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="space-y-2">
          {visibleTodos.map((todo) => (
            <div
              key={todo.id}
              className="rounded-2xl bg-sand px-3 py-2"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className={`font-semibold leading-5 ${todo.status === 'done' ? 'text-ink/45 line-through' : ''}`}>
                    {todo.title}
                  </p>
                  <p className="text-xs text-ink/55">截止 {dateText(todo.due_at)} · {todoImportanceLabel(todo.importance)}</p>
                  {todo.description && <p className="mt-1 line-clamp-2 text-xs text-ink/45">{todo.description}</p>}
                </div>
                <div className="flex shrink-0 gap-1">
                  <button
                    disabled={busyTodoId === todo.id}
                    onClick={() => toggleTodo(todo)}
                    className="rounded-full bg-white px-2 py-1 text-moss disabled:opacity-50"
                  >
                    {todo.status === 'done' ? <RotateCcw className="h-3.5 w-3.5" /> : <CheckSquare className="h-3.5 w-3.5" />}
                  </button>
                  <button onClick={() => setEditingTodo(todo)} className="rounded-full bg-white px-2 py-1">
                    <Edit3 className="h-3.5 w-3.5" />
                  </button>
                  <button
                    disabled={busyTodoId === todo.id}
                    onClick={() => deleteTodo(todo)}
                    className="rounded-full bg-white px-2 py-1 text-clay disabled:opacity-50"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            </div>
          ))}
          {visibleTodos.length === 0 && <EmptyLine text="暂无待办" />}
        </div>
        {filteredTodos.length > 3 && (
          <button
            onClick={() => setTodosExpanded((value) => !value)}
            className="mt-2 flex w-full items-center justify-center gap-1 rounded-xl bg-white px-3 py-2 text-xs font-semibold text-ink/55"
          >
            <ChevronDown className={`h-4 w-4 transition ${todosExpanded ? 'rotate-180' : ''}`} />
            {todosExpanded ? '收起' : `展开 ${filteredTodos.length - 3} 条`}
          </button>
        )}
      </Card>
      {todoModalOpen && (
        <TodoFormModal
          token={token}
          projectId={project.id}
          onRefresh={onRefreshTodos}
          onClose={() => setTodoModalOpen(false)}
        />
      )}
      {editingTodo && (
        <TodoFormModal
          token={token}
          projectId={project.id}
          todo={editingTodo}
          onRefresh={onRefreshTodos}
          onClose={() => setEditingTodo(null)}
        />
      )}
      <Card title="当前阶段事项" action={labelOf(data.stages, currentStage)}>
        {loading.stageTasks && <InlineLoading text="当前阶段事项加载中..." />}
        <Tip message={stageTaskError} onClose={() => setStageTaskError(null)} tone="error" />
        <div className="space-y-3">
          {visibleStageTasks.map((task) => (
            <div key={task.id} className="rounded-2xl border border-ink/10 bg-white px-4 py-3">
              <p className="font-semibold">{task.title}</p>
              <p className="mt-1 text-xs text-ink/55">
                {labelOf(data.stages, task.stage)} · {dateText(task.due_at)}
              </p>
              {task.description && <p className="mt-2 line-clamp-2 text-xs text-ink/45">{task.description}</p>}
              <div className="mt-3 flex gap-1">
                <button
                  disabled={busyStageTaskId === task.id}
                  onClick={() => toggleStageTask(task)}
                  className="rounded-full bg-moss/10 px-2 py-1 text-moss disabled:opacity-50"
                  aria-label={task.status === 'done' ? '重开阶段事项' : '完成阶段事项'}
                >
                  {task.status === 'done' ? <RotateCcw className="h-3.5 w-3.5" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
                </button>
                <button
                  onClick={() => setEditingStageTask(task)}
                  className="rounded-full bg-sand px-2 py-1"
                  aria-label="编辑阶段事项"
                >
                  <Edit3 className="h-3.5 w-3.5" />
                </button>
                <button
                  disabled={busyStageTaskId === task.id}
                  onClick={() => deleteStageTask(task)}
                  className="rounded-full bg-clay/10 px-2 py-1 text-clay disabled:opacity-50"
                  aria-label="删除阶段事项"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          ))}
          {visibleStageTasks.length === 0 && <EmptyLine text="当前阶段暂无未完成事项" />}
        </div>
        {sortedStageTasks.length > 3 && (
          <button
            onClick={() => setTasksExpanded((value) => !value)}
            className="mt-2 flex w-full items-center justify-center gap-1 rounded-xl bg-sand px-3 py-2 text-xs font-semibold text-ink/55"
          >
            <ChevronDown className={`h-4 w-4 transition ${tasksExpanded ? 'rotate-180' : ''}`} />
            {tasksExpanded ? '收起' : `展开 ${sortedStageTasks.length - 3} 条`}
          </button>
        )}
      </Card>
      {editingStageTask && (
        <StageTaskForm
          token={token}
          projectId={project.id}
          stages={data.stages}
          task={editingStageTask}
          onSaved={onRefreshStageTasks}
          onClose={() => setEditingStageTask(null)}
        />
      )}
    </div>
  );
}

function compareTodos(a: Todo, b: Todo) {
  const statusWeight = (todo: Todo) => (todo.status === 'done' ? 1 : 0);
  const statusDiff = statusWeight(a) - statusWeight(b);
  if (statusDiff !== 0) return statusDiff;
  const importanceDiff = b.importance - a.importance;
  if (importanceDiff !== 0) return importanceDiff;
  return compareOptionalDate(a.due_at, b.due_at);
}

function compareOptionalDate(a?: string | null, b?: string | null) {
  if (!a && !b) return 0;
  if (!a) return 1;
  if (!b) return -1;
  return new Date(a).getTime() - new Date(b).getTime();
}
