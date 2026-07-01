import type {
  Attachment,
  ActivityLog,
  AuthResponse,
  ComparisonItem,
  ComparisonQuote,
  Expense,
  Inspection,
  KnowledgeAnswer,
  KnowledgeChatHistoryMessage,
  KnowledgeDocument,
  KnowledgeIndexTrigger,
  KnowledgeSource,
  MetaOptions,
  Project,
  ProjectMember,
  ProjectProgress,
  ProjectStage,
  StageTask,
  Todo,
  User,
} from './types';

const API_BASE = import.meta.env.VITE_API_BASE || '/api';

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

type RequestOptions = RequestInit & {
  token?: string | null;
};

function buildHeaders(options: RequestOptions = {}) {
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }
  if (options.token) {
    headers.set('Authorization', `Bearer ${options.token}`);
  }
  return headers;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = buildHeaders(options);

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    throw new ApiError(response.status, typeof detail === 'string' ? detail : '请求失败');
  }
  return data as T;
}

async function download(path: string, token: string): Promise<Blob> {
  const headers = buildHeaders({ token });
  headers.delete('Content-Type');
  const response = await fetch(`${API_BASE}${path}`, { headers });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    const detail = data?.detail;
    throw new ApiError(response.status, typeof detail === 'string' ? detail : '下载失败');
  }
  return response.blob();
}

type KnowledgeStreamEvent =
  | { event: 'status'; data: { message: string } }
  | { event: 'sources'; data: { sources: KnowledgeSource[] } }
  | { event: 'delta'; data: { text: string } }
  | { event: 'done'; data: { answer: string } }
  | { event: 'error'; data: { message: string } };

async function streamRequest(
  path: string,
  options: RequestOptions,
  onEvent: (event: KnowledgeStreamEvent) => void,
) {
  const headers = buildHeaders(options);
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });
  if (!response.ok || !response.body) {
    const data = await response.json().catch(() => null);
    const detail = data?.detail;
    throw new ApiError(response.status, typeof detail === 'string' ? detail : '请求失败');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  function flushEvent(rawEvent: string) {
    const lines = rawEvent.split('\n');
    const eventName = lines.find((line) => line.startsWith('event:'))?.slice(6).trim();
    const dataLines = lines
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trimStart());
    if (!eventName || dataLines.length === 0) return;
    const data = JSON.parse(dataLines.join('\n'));
    if (eventName === 'error') {
      throw new ApiError(502, typeof data?.message === 'string' ? data.message : '助手请求失败');
    }
    onEvent({ event: eventName, data } as KnowledgeStreamEvent);
  }

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const events = buffer.split('\n\n');
    buffer = events.pop() || '';
    events.forEach(flushEvent);
    if (done) break;
  }
  if (buffer.trim()) {
    flushEvent(buffer);
  }
}

export const api = {
  register(payload: { email: string; name: string; password: string }) {
    return request<AuthResponse>('/auth/register', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },
  login(payload: { email: string; password: string }) {
    return request<AuthResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },
  me(token: string) {
    return request<User>('/auth/me', { token });
  },
  meta(token: string) {
    return request<MetaOptions>('/meta/options', { token });
  },
  listProjects(token: string) {
    return request<Project[]>('/projects', { token });
  },
  createProject(token: string, payload: { name: string; address?: string; notes?: string }) {
    return request<Project>('/projects', {
      method: 'POST',
      token,
      body: JSON.stringify(payload),
    });
  },
  listMembers(token: string, projectId: number) {
    return request<ProjectMember[]>(`/projects/${projectId}/members`, { token });
  },
  inviteMember(token: string, projectId: number, payload: { email: string; role: string }) {
    return request<ProjectMember>(`/projects/${projectId}/members`, {
      method: 'POST',
      token,
      body: JSON.stringify(payload),
    });
  },
  upload(token: string, projectId: number, file: File) {
    const form = new FormData();
    form.append('file', file);
    return request<Attachment>(`/projects/${projectId}/uploads`, {
      method: 'POST',
      token,
      body: form,
    });
  },
  listExpenses(token: string, projectId: number) {
    return request<Expense[]>(`/projects/${projectId}/expenses`, { token });
  },
  createExpense(token: string, projectId: number, payload: Record<string, unknown>) {
    return request<Expense>(`/projects/${projectId}/expenses`, {
      method: 'POST',
      token,
      body: JSON.stringify(payload),
    });
  },
  updateExpense(token: string, projectId: number, expenseId: number, payload: Record<string, unknown>) {
    return request<Expense>(`/projects/${projectId}/expenses/${expenseId}`, {
      method: 'PATCH',
      token,
      body: JSON.stringify(payload),
    });
  },
  listStageTasks(token: string, projectId: number) {
    return request<StageTask[]>(`/projects/${projectId}/stage-tasks`, { token });
  },
  getProgress(token: string, projectId: number) {
    return request<ProjectProgress>(`/projects/${projectId}/progress`, { token });
  },
  updateProgress(token: string, projectId: number, payload: Record<string, unknown>) {
    return request<ProjectProgress>(`/projects/${projectId}/progress`, {
      method: 'PATCH',
      token,
      body: JSON.stringify(payload),
    });
  },
  listProjectStages(token: string, projectId: number) {
    return request<ProjectStage[]>(`/projects/${projectId}/stages`, { token });
  },
  createProjectStage(token: string, projectId: number, payload: Record<string, unknown>) {
    return request<ProjectStage>(`/projects/${projectId}/stages`, {
      method: 'POST',
      token,
      body: JSON.stringify(payload),
    });
  },
  updateProjectStage(token: string, projectId: number, stageId: number, payload: Record<string, unknown>) {
    return request<ProjectStage>(`/projects/${projectId}/stages/${stageId}`, {
      method: 'PATCH',
      token,
      body: JSON.stringify(payload),
    });
  },
  deleteProjectStage(token: string, projectId: number, stageId: number) {
    return request<void>(`/projects/${projectId}/stages/${stageId}`, {
      method: 'DELETE',
      token,
    });
  },
  createStageTask(token: string, projectId: number, payload: Record<string, unknown>) {
    return request<StageTask>(`/projects/${projectId}/stage-tasks`, {
      method: 'POST',
      token,
      body: JSON.stringify(payload),
    });
  },
  updateStageTask(token: string, projectId: number, taskId: number, payload: Record<string, unknown>) {
    return request<StageTask>(`/projects/${projectId}/stage-tasks/${taskId}`, {
      method: 'PATCH',
      token,
      body: JSON.stringify(payload),
    });
  },
  deleteStageTask(token: string, projectId: number, taskId: number) {
    return request<void>(`/projects/${projectId}/stage-tasks/${taskId}`, {
      method: 'DELETE',
      token,
    });
  },
  listComparisons(token: string, projectId: number) {
    return request<ComparisonItem[]>(`/projects/${projectId}/comparisons`, { token });
  },
  createComparisonItem(token: string, projectId: number, payload: Record<string, unknown>) {
    return request<ComparisonItem>(`/projects/${projectId}/comparisons`, {
      method: 'POST',
      token,
      body: JSON.stringify(payload),
    });
  },
  updateComparisonItem(token: string, projectId: number, itemId: number, payload: Record<string, unknown>) {
    return request<ComparisonItem>(`/projects/${projectId}/comparisons/${itemId}`, {
      method: 'PATCH',
      token,
      body: JSON.stringify(payload),
    });
  },
  deleteComparisonItem(token: string, projectId: number, itemId: number) {
    return request<void>(`/projects/${projectId}/comparisons/${itemId}`, {
      method: 'DELETE',
      token,
    });
  },
  createQuote(token: string, projectId: number, itemId: number, payload: Record<string, unknown>) {
    return request<ComparisonQuote>(`/projects/${projectId}/comparisons/${itemId}/quotes`, {
      method: 'POST',
      token,
      body: JSON.stringify(payload),
    });
  },
  updateQuote(token: string, projectId: number, itemId: number, quoteId: number, payload: Record<string, unknown>) {
    return request<ComparisonQuote>(`/projects/${projectId}/comparisons/${itemId}/quotes/${quoteId}`, {
      method: 'PATCH',
      token,
      body: JSON.stringify(payload),
    });
  },
  deleteQuote(token: string, projectId: number, itemId: number, quoteId: number) {
    return request<void>(`/projects/${projectId}/comparisons/${itemId}/quotes/${quoteId}`, {
      method: 'DELETE',
      token,
    });
  },
  listInspections(token: string, projectId: number) {
    return request<Inspection[]>(`/projects/${projectId}/inspections`, { token });
  },
  createInspection(token: string, projectId: number, payload: Record<string, unknown>) {
    return request<Inspection>(`/projects/${projectId}/inspections`, {
      method: 'POST',
      token,
      body: JSON.stringify(payload),
    });
  },
  updateInspection(token: string, projectId: number, inspectionId: number, payload: Record<string, unknown>) {
    return request<Inspection>(`/projects/${projectId}/inspections/${inspectionId}`, {
      method: 'PATCH',
      token,
      body: JSON.stringify(payload),
    });
  },
  listTodos(token: string, projectId: number) {
    return request<Todo[]>(`/projects/${projectId}/todos`, { token });
  },
  createTodo(token: string, projectId: number, payload: Record<string, unknown>) {
    return request<Todo>(`/projects/${projectId}/todos`, {
      method: 'POST',
      token,
      body: JSON.stringify(payload),
    });
  },
  updateTodo(token: string, projectId: number, todoId: number, payload: Record<string, unknown>) {
    return request<Todo>(`/projects/${projectId}/todos/${todoId}`, {
      method: 'PATCH',
      token,
      body: JSON.stringify(payload),
    });
  },
  deleteTodo(token: string, projectId: number, todoId: number) {
    return request<void>(`/projects/${projectId}/todos/${todoId}`, {
      method: 'DELETE',
      token,
    });
  },
  listActivity(token: string, projectId: number) {
    return request<ActivityLog[]>(`/projects/${projectId}/activity`, { token });
  },
  listKnowledgeDocuments(token: string, projectId: number) {
    return request<KnowledgeDocument[]>(`/projects/${projectId}/knowledge/documents`, { token });
  },
  triggerKnowledgeIndex(token: string, projectId: number) {
    return request<KnowledgeIndexTrigger>(`/projects/${projectId}/knowledge/index`, {
      method: 'POST',
      token,
    });
  },
  getKnowledgeDocument(token: string, projectId: number, documentId: number) {
    return request<KnowledgeDocument>(`/projects/${projectId}/knowledge/documents/${documentId}`, { token });
  },
  askKnowledge(token: string, projectId: number, question: string, history: KnowledgeChatHistoryMessage[] = []) {
    return request<KnowledgeAnswer>(`/projects/${projectId}/knowledge/ask`, {
      method: 'POST',
      token,
      body: JSON.stringify({ question, history }),
    });
  },
  streamKnowledgeAnswer(
    token: string,
    projectId: number,
    question: string,
    history: KnowledgeChatHistoryMessage[] = [],
    onEvent: (event: KnowledgeStreamEvent) => void,
  ) {
    return streamRequest(
      `/projects/${projectId}/knowledge/ask/stream`,
      {
        method: 'POST',
        token,
        body: JSON.stringify({ question, history }),
      },
      onEvent,
    );
  },
  uploadKnowledgeDocument(token: string, projectId: number, file: File) {
    const form = new FormData();
    form.append('file', file);
    return request<KnowledgeDocument>(`/projects/${projectId}/knowledge/documents`, {
      method: 'POST',
      token,
      body: form,
    });
  },
  updateKnowledgeDocument(token: string, projectId: number, documentId: number, payload: Record<string, unknown>) {
    return request<KnowledgeDocument>(`/projects/${projectId}/knowledge/documents/${documentId}`, {
      method: 'PATCH',
      token,
      body: JSON.stringify(payload),
    });
  },
  deleteKnowledgeDocument(token: string, projectId: number, documentId: number) {
    return request<void>(`/projects/${projectId}/knowledge/documents/${documentId}`, {
      method: 'DELETE',
      token,
    });
  },
  downloadKnowledgeFile(token: string, path: string) {
    return download(path, token);
  },
};
