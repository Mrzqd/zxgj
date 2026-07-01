import type {
  ComparisonItem,
  Expense,
  Inspection,
  ActivityLog,
  MetaOptions,
  ProjectMember,
  ProjectProgress,
  ProjectStage,
  StageTask,
  Todo,
} from '../types';

export const emptyMeta: MetaOptions = {
  renovation_stages: [],
  amount_categories: [],
  task_statuses: [],
  inspection_statuses: [],
};

export type Tab = 'home' | 'expenses' | 'tasks' | 'comparisons' | 'inspections' | 'assistant' | 'profile';

export type AppData = {
  expenses: Expense[];
  stageTasks: StageTask[];
  comparisons: ComparisonItem[];
  inspections: Inspection[];
  todos: Todo[];
  members: ProjectMember[];
  activity: ActivityLog[];
  progress: ProjectProgress | null;
  stages: ProjectStage[];
};

export const initialData: AppData = {
  expenses: [],
  stageTasks: [],
  comparisons: [],
  inspections: [],
  todos: [],
  members: [],
  activity: [],
  progress: null,
  stages: [],
};
