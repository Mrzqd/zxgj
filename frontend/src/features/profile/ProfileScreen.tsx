import { useEffect, useState } from 'react';
import { Copy, Edit3, Link, LogOut, Plus, Trash2, Users } from 'lucide-react';
import { api } from '../../api';
import { Card, Field, InlineLoading, Modal, ModuleHero, Tip } from '../../components/ui';
import { useSubmitting } from '../../hooks/useSubmitting';
import type { ActivityLog, Expense, Project, ProjectInviteLink, ProjectMember, ProjectProgress, ProjectStage, User } from '../../types';
import { dateText, labelOf } from '../../utils/format';

export function ProfileScreen({
  token,
  project,
  projects,
  currentProjectId,
  onProjectChange,
  user,
  members,
  activity,
  stages,
  progress,
  expenses,
  loading,
  onInvite,
  onRefreshProgress,
  onRefreshStages,
  onLogout,
}: {
  token: string;
  project: Project;
  projects: Project[];
  currentProjectId: number;
  onProjectChange: (id: number) => void;
  user: User;
  members: ProjectMember[];
  activity: ActivityLog[];
  stages: ProjectStage[];
  progress: ProjectProgress | null;
  expenses: Expense[];
  loading: {
    progress: boolean;
    stages: boolean;
    members: boolean;
    activity: boolean;
  };
  onInvite: () => Promise<void>;
  onRefreshProgress: () => Promise<void>;
  onRefreshStages: () => Promise<void>;
  onLogout: () => void;
}) {
  const [message, setMessage] = useState<string | null>(null);
  const [inviteLinks, setInviteLinks] = useState<ProjectInviteLink[]>([]);
  const [inviteExpiresInHours, setInviteExpiresInHours] = useState('72');
  const [inviteMaxAccepts, setInviteMaxAccepts] = useState('1');
  const [generatedInviteUrl, setGeneratedInviteUrl] = useState('');
  const [progressStage, setProgressStage] = useState(progress?.current_stage || stages[0]?.value || 'design');
  const [progressNote, setProgressNote] = useState(progress?.note || '');
  const [stageModalOpen, setStageModalOpen] = useState(false);
  const [editingStage, setEditingStage] = useState<ProjectStage | null>(null);
  const [stagesExpanded, setStagesExpanded] = useState(false);
  const [activityExpanded, setActivityExpanded] = useState(false);
  const inviteSubmit = useSubmitting();
  const progressSubmit = useSubmitting();
  const stageDeleteSubmit = useSubmitting();
  const visibleStages = stagesExpanded ? stages : stages.slice(0, 3);
  const visibleActivity = activityExpanded ? activity.slice(0, 20) : activity.slice(0, 3);

  useEffect(() => {
    setProgressStage(progress?.current_stage || stages[0]?.value || 'design');
    setProgressNote(progress?.note || '');
  }, [progress?.current_stage, progress?.note, stages]);

  useEffect(() => {
    api.listProjectInviteLinks(token, project.id)
      .then(setInviteLinks)
      .catch(() => setInviteLinks([]));
  }, [token, project.id]);

  async function createInviteLink(event: React.FormEvent) {
    event.preventDefault();
    await inviteSubmit.guard(async () => {
      try {
        setMessage(null);
        const invite = await api.createProjectInviteLink(token, project.id, {
          role: 'editor',
          expires_in_hours: Number(inviteExpiresInHours),
          max_accepts: Number(inviteMaxAccepts),
        });
        setGeneratedInviteUrl(inviteUrl(invite.token));
        const links = await api.listProjectInviteLinks(token, project.id);
        setInviteLinks(links);
        await onInvite();
        setMessage('邀请链接已生成');
      } catch (error) {
        setMessage(error instanceof Error ? error.message : '邀请链接生成失败');
      }
    });
  }

  async function copyInviteUrl(url: string) {
    try {
      await navigator.clipboard.writeText(url);
      setMessage('邀请链接已复制');
    } catch {
      setMessage(url);
    }
  }

  function inviteUrl(inviteToken: string) {
    return `${window.location.origin}${window.location.pathname}?invite=${encodeURIComponent(inviteToken)}`;
  }

  async function saveProgress() {
    await progressSubmit.guard(async () => {
      await api.updateProgress(token, project.id, {
        current_stage: progressStage,
        note: progressNote,
      });
      await onRefreshProgress();
    });
  }

  async function deleteStage(stage: ProjectStage) {
    if (!window.confirm(`确认删除装修阶段「${stage.label}」？`)) return;
    await stageDeleteSubmit.guard(async () => {
      await api.deleteProjectStage(token, project.id, stage.id);
      await onRefreshStages();
    });
  }

  function stageCost(stageValue: string) {
    return expenses
      .filter((expense) => expense.stage === stageValue)
      .reduce((sum, expense) => sum + Number(expense.amount), 0);
  }

  function stageActualDays(stage: ProjectStage) {
    if (!stage.started_at) return '-';
    const end = stage.completed_at ? new Date(stage.completed_at) : new Date();
    return Math.max(1, Math.floor((end.getTime() - new Date(stage.started_at).getTime()) / 86_400_000) + 1);
  }

  return (
    <div className="space-y-3">
      <ModuleHero icon={<Users />} title="我的" subtitle="管理项目成员、装修进度、阶段节奏和操作日志。" />
      <Card title="当前项目" action={project.name}>
        <select
          className="input"
          value={currentProjectId}
          onChange={(event) => onProjectChange(Number(event.target.value))}
        >
          {projects.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
      </Card>
      <Card title="装修进度管理" action={labelOf(stages, progressStage)}>
        {loading.progress && <InlineLoading text="装修进度加载中..." />}
        <div className="space-y-2">
          <select value={progressStage} onChange={(event) => setProgressStage(event.target.value)} className="input">
            {stages.map((stage) => (
              <option key={stage.id} value={stage.value}>
                {stage.label}
              </option>
            ))}
          </select>
          <input
            value={progressNote}
            onChange={(event) => setProgressNote(event.target.value)}
            placeholder="进度备注，例如：瓦工本周进场"
            className="input"
          />
          <button disabled={progressSubmit.submitting} onClick={saveProgress} className="secondary-button w-full">
            {progressSubmit.submitting ? '保存中...' : '保存当前进度'}
          </button>
        </div>
      </Card>
      <Card
        title="装修阶段"
        action={
          <button onClick={() => setStageModalOpen(true)} className="inline-flex items-center gap-1 rounded-full bg-clay px-2.5 py-1 text-xs font-bold text-white">
            <Plus className="h-3.5 w-3.5" /> 阶段
          </button>
        }
      >
        {loading.stages && <InlineLoading text="装修阶段加载中..." />}
        <div className="space-y-2">
          {visibleStages.map((stage) => (
            <div key={stage.id} className="rounded-xl bg-sand px-3 py-2">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="font-semibold">{stage.label}</p>
                  <p className="text-xs text-ink/50">
                    计划 {stage.planned_days} 天 · 已用 {stageActualDays(stage)} 天 · 用钱 ¥{stageCost(stage.value).toLocaleString('zh-CN')}
                  </p>
                  <p className="text-xs text-ink/40">
                    开始 {dateText(stage.started_at)} · 完成 {dateText(stage.completed_at)}
                  </p>
                </div>
                <div className="flex shrink-0 gap-1">
                  <button onClick={() => setEditingStage(stage)} className="rounded-full bg-white px-2 py-1">
                    <Edit3 className="h-3.5 w-3.5" />
                  </button>
                  <button
                    disabled={stageDeleteSubmit.submitting}
                    onClick={() => deleteStage(stage)}
                    className="rounded-full bg-white px-2 py-1 text-clay disabled:opacity-50"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            </div>
          ))}
          {stages.length > 3 && (
            <button
              type="button"
              onClick={() => setStagesExpanded((current) => !current)}
              className="w-full rounded-xl bg-sand/70 px-3 py-2 text-xs font-bold text-ink/55"
            >
              {stagesExpanded ? '收起装修阶段' : `展开全部 ${stages.length} 个阶段`}
            </button>
          )}
        </div>
      </Card>
      <Card title="当前账号" action={user.email}>
        <p className="font-semibold">{user.name}</p>
      </Card>
      <Card title="项目成员" action={`${members.length} 人`}>
        {loading.members && <InlineLoading text="项目成员加载中..." />}
        <div className="space-y-2">
          {members.map((member) => (
            <div key={member.id} className="flex items-center justify-between rounded-xl bg-sand px-3 py-2">
              <div>
                <p className="font-semibold">{member.user.name}</p>
                <p className="text-xs text-ink/50">{member.user.email}</p>
              </div>
              <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold">{member.role}</span>
            </div>
          ))}
        </div>
      </Card>
      <Card title="邀请成员" action="链接">
        <form onSubmit={createInviteLink} className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <Field label="有效期">
              <select
                value={inviteExpiresInHours}
                onChange={(event) => setInviteExpiresInHours(event.target.value)}
                className="input"
              >
                <option value="24">24 小时</option>
                <option value="72">3 天</option>
                <option value="168">7 天</option>
                <option value="720">30 天</option>
              </select>
            </Field>
            <Field label="接收次数">
              <input
                type="number"
                min={1}
                max={100}
                value={inviteMaxAccepts}
                onChange={(event) => setInviteMaxAccepts(event.target.value)}
                required
                className="input"
              />
            </Field>
          </div>
          <Tip message={message} onClose={() => setMessage(null)} tone="info" />
          <button disabled={inviteSubmit.submitting} className="secondary-button w-full">
            <Link className="h-4 w-4" />
            {inviteSubmit.submitting ? '生成中...' : '生成邀请链接'}
          </button>
        </form>
        {generatedInviteUrl && (
          <div className="mt-3 rounded-xl bg-sand p-3">
            <p className="mb-2 break-all text-xs font-semibold text-ink/65">{generatedInviteUrl}</p>
            <button onClick={() => copyInviteUrl(generatedInviteUrl)} className="primary-button w-full py-2.5">
              <Copy className="h-4 w-4" />
              复制链接
            </button>
          </div>
        )}
        {inviteLinks.length > 0 && (
          <div className="mt-3 space-y-2">
            {inviteLinks.slice(0, 3).map((invite) => {
              const remaining = Math.max(0, invite.max_accepts - invite.accepted_count);
              const expired = new Date(invite.expires_at).getTime() <= Date.now();
              return (
                <div key={invite.id} className="rounded-xl bg-sand px-3 py-2">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-xs font-bold text-ink/70">
                        {expired ? '已过期' : `剩余 ${remaining} 次`} · {new Date(invite.expires_at).toLocaleString('zh-CN')}
                      </p>
                      <p className="mt-1 truncate text-xs text-ink/40">{inviteUrl(invite.token)}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => copyInviteUrl(inviteUrl(invite.token))}
                      className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-white text-ink/60"
                      aria-label="复制邀请链接"
                    >
                      <Copy className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Card>
      <Card title="操作日志" action={`${activity.length} 条`}>
        {loading.activity && <InlineLoading text="操作日志加载中..." />}
        <div className="space-y-2">
          {visibleActivity.map((log) => (
            <div key={log.id} className="rounded-xl bg-sand px-3 py-2">
              <div className="flex items-start justify-between gap-3">
                <p className="text-sm font-semibold">{log.message}</p>
                <span className="shrink-0 rounded-full bg-white px-2 py-1 text-[11px] font-semibold text-ink/50">
                  {log.actor.name}
                </span>
              </div>
              <p className="mt-1 text-xs text-ink/45">{new Date(log.created_at).toLocaleString('zh-CN')}</p>
            </div>
          ))}
          {activity.length === 0 && <p className="py-4 text-center text-sm text-ink/45">暂无操作日志</p>}
          {activity.length > 3 && (
            <button
              type="button"
              onClick={() => setActivityExpanded((current) => !current)}
              className="w-full rounded-xl bg-sand/70 px-3 py-2 text-xs font-bold text-ink/55"
            >
              {activityExpanded ? '收起操作日志' : `展开最近 ${Math.min(activity.length, 20)} 条日志`}
            </button>
          )}
        </div>
      </Card>
      <button onClick={onLogout} className="flex w-full items-center justify-center gap-2 rounded-2xl bg-ink px-4 py-3 font-semibold text-white">
        <LogOut className="h-4 w-4" /> 退出登录
      </button>
      {stageModalOpen && (
        <ProjectStageModal
          token={token}
          projectId={project.id}
          onClose={() => setStageModalOpen(false)}
          onRefresh={onRefreshStages}
        />
      )}
      {editingStage && (
        <ProjectStageModal
          token={token}
          projectId={project.id}
          stage={editingStage}
          onClose={() => setEditingStage(null)}
          onRefresh={onRefreshStages}
        />
      )}
    </div>
  );
}

function ProjectStageModal({
  token,
  projectId,
  stage,
  onClose,
  onRefresh,
}: {
  token: string;
  projectId: number;
  stage?: ProjectStage;
  onClose: () => void;
  onRefresh: () => Promise<void>;
}) {
  const [label, setLabel] = useState(stage?.label || '');
  const [plannedDays, setPlannedDays] = useState(String(stage?.planned_days || 7));
  const [sortOrder, setSortOrder] = useState(String(stage?.sort_order ?? ''));
  const [startedAt, setStartedAt] = useState(stage?.started_at || '');
  const [completedAt, setCompletedAt] = useState(stage?.completed_at || '');
  const { submitting, guard } = useSubmitting();

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    await guard(async () => {
      const payload = {
        label,
        planned_days: Number(plannedDays),
        sort_order: sortOrder === '' ? undefined : Number(sortOrder),
        started_at: startedAt || null,
        completed_at: completedAt || null,
      };
      if (stage) {
        await api.updateProjectStage(token, projectId, stage.id, payload);
      } else {
        await api.createProjectStage(token, projectId, payload);
      }
      await onRefresh();
      onClose();
    });
  }

  return (
    <Modal title={stage ? '编辑装修阶段' : '新增装修阶段'} onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <Field label="阶段名称">
          <input value={label} onChange={(event) => setLabel(event.target.value)} required className="input" />
        </Field>
        <div className="grid grid-cols-2 gap-2">
          <Field label="计划天数">
            <input type="number" min={1} value={plannedDays} onChange={(event) => setPlannedDays(event.target.value)} required className="input" />
          </Field>
          <Field label="排序">
            <input type="number" value={sortOrder} onChange={(event) => setSortOrder(event.target.value)} className="input" />
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Field label="开始日期">
            <input type="date" value={startedAt} onChange={(event) => setStartedAt(event.target.value)} className="input" />
          </Field>
          <Field label="完成日期">
            <input type="date" value={completedAt} onChange={(event) => setCompletedAt(event.target.value)} className="input" />
          </Field>
        </div>
        <button disabled={submitting} className="primary-button w-full">
          {submitting ? '保存中...' : stage ? '保存修改' : '新增阶段'}
        </button>
      </form>
    </Modal>
  );
}
