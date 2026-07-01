import { useEffect, useState } from 'react';
import { api, ApiError } from '../api';
import { BottomNav } from '../components/layout/BottomNav';
import { ShellLoader } from '../components/ui';
import { AuthScreen } from '../features/auth/AuthScreen';
import { AssistantScreen } from '../features/assistant/AssistantScreen';
import { ComparisonsScreen } from '../features/comparisons/ComparisonsScreen';
import { ExpensesScreen } from '../features/expenses/ExpensesScreen';
import { HomeScreen } from '../features/home/HomeScreen';
import { InspectionsScreen } from '../features/inspections/InspectionsScreen';
import { ProfileScreen } from '../features/profile/ProfileScreen';
import { ProjectEmpty } from '../features/projects/ProjectEmpty';
import { StageTasksScreen } from '../features/stageTasks/StageTasksScreen';
import type { MetaOptions, Project, User } from '../types';
import { emptyMeta, initialData, type AppData, type Tab } from './types';

type DataLoadingKey =
  | 'expenses'
  | 'stageTasks'
  | 'progress'
  | 'stages'
  | 'comparisons'
  | 'inspections'
  | 'todos'
  | 'members'
  | 'activity';

type DataLoading = Record<DataLoadingKey, boolean>;

const emptyDataLoading: DataLoading = {
  expenses: false,
  stageTasks: false,
  progress: false,
  stages: false,
  comparisons: false,
  inspections: false,
  todos: false,
  members: false,
  activity: false,
};

const allDataLoadingKeys = Object.keys(emptyDataLoading) as DataLoadingKey[];

export function App() {
  const [token, setToken] = useState(() => localStorage.getItem('renovation_token'));
  const [user, setUser] = useState<User | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<number | null>(() => {
    const saved = localStorage.getItem('renovation_project_id');
    return saved ? Number(saved) : null;
  });
  const [meta, setMeta] = useState<MetaOptions>(emptyMeta);
  const [data, setData] = useState<AppData>(initialData);
  const [tab, setTab] = useState<Tab>('home');
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [dataLoading, setDataLoading] = useState<DataLoading>(emptyDataLoading);

  const currentProject = projects.find((project) => project.id === projectId) || null;

  async function withErrorHandling(action: () => Promise<void>) {
    try {
      setMessage(null);
      await action();
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        localStorage.removeItem('renovation_token');
        setToken(null);
      }
      setMessage(error instanceof Error ? error.message : '操作失败');
    }
  }

  async function refreshProjects(activeToken = token) {
    if (!activeToken) return;
    const [projectList, metaOptions] = await Promise.all([
      api.listProjects(activeToken),
      api.meta(activeToken),
    ]);
    setProjects(projectList);
    setMeta(metaOptions);
    if (!projectId && projectList[0]) {
      setProjectId(projectList[0].id);
      localStorage.setItem('renovation_project_id', String(projectList[0].id));
    }
  }

  async function withDataLoading(keys: DataLoadingKey[], action: () => Promise<void>) {
    setDataLoading((current) => {
      const next = { ...current };
      keys.forEach((key) => {
        next[key] = true;
      });
      return next;
    });
    try {
      await action();
    } finally {
      setDataLoading((current) => {
        const next = { ...current };
        keys.forEach((key) => {
          next[key] = false;
        });
        return next;
      });
    }
  }

  async function refreshProjectData(activeProjectId = projectId) {
    if (!token || !activeProjectId) return;
    await withDataLoading(allDataLoadingKeys, async () => {
      const [expenses, stageTasks, progress, stages, comparisons, inspections, todos, members, activity] = await Promise.all([
        api.listExpenses(token, activeProjectId),
        api.listStageTasks(token, activeProjectId),
        api.getProgress(token, activeProjectId),
        api.listProjectStages(token, activeProjectId),
        api.listComparisons(token, activeProjectId),
        api.listInspections(token, activeProjectId),
        api.listTodos(token, activeProjectId),
        api.listMembers(token, activeProjectId),
        api.listActivity(token, activeProjectId),
      ]);
      setData({ expenses, stageTasks, progress, stages, comparisons, inspections, todos, members, activity });
    });
  }

  async function refreshExpenses(activeProjectId = projectId) {
    if (!token || !activeProjectId) return;
    await withDataLoading(['expenses'], async () => {
      const expenses = await api.listExpenses(token, activeProjectId);
      setData((current) => ({ ...current, expenses }));
    });
  }

  async function refreshStageTasks(activeProjectId = projectId) {
    if (!token || !activeProjectId) return;
    await withDataLoading(['stageTasks'], async () => {
      const stageTasks = await api.listStageTasks(token, activeProjectId);
      setData((current) => ({ ...current, stageTasks }));
    });
  }

  async function refreshComparisons(activeProjectId = projectId) {
    if (!token || !activeProjectId) return;
    await withDataLoading(['comparisons'], async () => {
      const comparisons = await api.listComparisons(token, activeProjectId);
      setData((current) => ({ ...current, comparisons }));
    });
  }

  async function refreshInspections(activeProjectId = projectId) {
    if (!token || !activeProjectId) return;
    await withDataLoading(['inspections'], async () => {
      const inspections = await api.listInspections(token, activeProjectId);
      setData((current) => ({ ...current, inspections }));
    });
  }

  async function refreshTodos(activeProjectId = projectId) {
    if (!token || !activeProjectId) return;
    await withDataLoading(['todos'], async () => {
      const todos = await api.listTodos(token, activeProjectId);
      setData((current) => ({ ...current, todos }));
    });
  }

  async function refreshMembersAndActivity(activeProjectId = projectId) {
    if (!token || !activeProjectId) return;
    await withDataLoading(['members', 'activity'], async () => {
      const [members, activity] = await Promise.all([
        api.listMembers(token, activeProjectId),
        api.listActivity(token, activeProjectId),
      ]);
      setData((current) => ({ ...current, members, activity }));
    });
  }

  async function refreshProgress(activeProjectId = projectId) {
    if (!token || !activeProjectId) return;
    await withDataLoading(['progress'], async () => {
      const progress = await api.getProgress(token, activeProjectId);
      setData((current) => ({ ...current, progress }));
    });
  }

  async function refreshStagesAndProgress(activeProjectId = projectId) {
    if (!token || !activeProjectId) return;
    await withDataLoading(['stages', 'progress'], async () => {
      const [progress, stages] = await Promise.all([
        api.getProgress(token, activeProjectId),
        api.listProjectStages(token, activeProjectId),
      ]);
      setData((current) => ({ ...current, progress, stages }));
    });
  }

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    withErrorHandling(async () => {
      const profile = await api.me(token);
      setUser(profile);
      await refreshProjects(token);
    }).finally(() => setLoading(false));
  }, [token]);

  useEffect(() => {
    if (!token || !projectId) return;
    localStorage.setItem('renovation_project_id', String(projectId));
    setData(initialData);
    withErrorHandling(() => refreshProjectData(projectId));
  }, [token, projectId]);

  function handleAuth(authToken: string, profile: User) {
    localStorage.setItem('renovation_token', authToken);
    setToken(authToken);
    setUser(profile);
  }

  function logout() {
    localStorage.removeItem('renovation_token');
    localStorage.removeItem('renovation_project_id');
    setToken(null);
    setUser(null);
    setProjects([]);
    setProjectId(null);
    setData(initialData);
  }

  if (!token || !user) {
    return <AuthScreen onAuth={handleAuth} message={message} setMessage={setMessage} />;
  }

  if (loading) {
    return <ShellLoader />;
  }

  return (
    <main className="min-h-screen bg-sand text-ink">
      <div className="mx-auto min-h-screen max-w-md bg-linen shadow-card">
        {message && (
          <div className="mx-3 mt-3 rounded-2xl border border-clay/30 bg-clay/10 px-4 py-3 text-sm text-clay">
            {message}
          </div>
        )}
        {!currentProject ? (
          <ProjectEmpty token={token} onCreated={refreshProjects} />
        ) : (
          <section className="px-3 pb-24 pt-3">
            {tab === 'home' && (
              <HomeScreen
                data={data}
                project={currentProject}
                loading={{
                  overview: dataLoading.expenses || dataLoading.members,
                  progress: dataLoading.progress || dataLoading.stages,
                  todos: dataLoading.todos,
                  stageTasks: dataLoading.stageTasks || dataLoading.progress || dataLoading.stages,
                }}
                onRefreshTodos={refreshTodos}
                onRefreshStageTasks={refreshStageTasks}
                token={token}
              />
            )}
            {tab === 'expenses' && (
              <ExpensesScreen
                projectId={currentProject.id}
                token={token}
                meta={meta}
                stages={data.stages}
                expenses={data.expenses}
                loading={dataLoading.expenses}
                onRefresh={refreshExpenses}
              />
            )}
            {tab === 'tasks' && (
              <StageTasksScreen
                projectId={currentProject.id}
                token={token}
                stages={data.stages}
                tasks={data.stageTasks}
                progress={data.progress}
                loading={dataLoading.stageTasks}
                onRefresh={refreshStageTasks}
              />
            )}
            {tab === 'comparisons' && (
              <ComparisonsScreen
                projectId={currentProject.id}
                token={token}
                items={data.comparisons}
                loading={dataLoading.comparisons}
                onRefresh={refreshComparisons}
              />
            )}
            {tab === 'inspections' && (
              <InspectionsScreen
                projectId={currentProject.id}
                token={token}
                meta={meta}
                stages={data.stages}
                inspections={data.inspections}
                loading={dataLoading.inspections}
                onRefresh={refreshInspections}
              />
            )}
            {tab === 'assistant' && <AssistantScreen token={token} projectId={currentProject.id} />}
            {tab === 'profile' && (
              <ProfileScreen
                token={token}
                project={currentProject}
                projects={projects}
                currentProjectId={currentProject.id}
                onProjectChange={setProjectId}
                user={user}
                members={data.members}
                activity={data.activity}
                stages={data.stages}
                progress={data.progress}
                expenses={data.expenses}
                loading={{
                  progress: dataLoading.progress,
                  stages: dataLoading.stages || dataLoading.expenses,
                  members: dataLoading.members,
                  activity: dataLoading.activity,
                }}
                onInvite={refreshMembersAndActivity}
                onRefreshProgress={refreshProgress}
                onRefreshStages={refreshStagesAndProgress}
                onLogout={logout}
              />
            )}
          </section>
        )}
        <BottomNav tab={tab} setTab={setTab} />
      </div>
    </main>
  );
}
