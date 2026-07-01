export type Option = {
  value: string;
  label: string;
};

export type User = {
  id: number;
  email: string;
  name: string;
  created_at: string;
};

export type AuthResponse = {
  access_token: string;
  token_type: string;
  user: User;
};

export type Project = {
  id: number;
  name: string;
  address?: string | null;
  notes?: string | null;
  owner_id: number;
  created_at: string;
};

export type ProjectMember = {
  id: number;
  project_id: number;
  role: string;
  user: User;
};

export type Attachment = {
  id: number;
  project_id: number;
  object_key: string;
  url: string;
  file_name: string;
  content_type?: string | null;
  size_bytes: number;
  created_at: string;
};

export type Expense = {
  id: number;
  project_id: number;
  stage: string;
  category: string;
  sub_item: string;
  amount: string;
  paid_at?: string | null;
  note?: string | null;
  attachment_id?: number | null;
  attachment?: Attachment | null;
  created_at: string;
};

export type StageTask = {
  id: number;
  project_id: number;
  stage: string;
  title: string;
  description?: string | null;
  status: string;
  assignee_id?: number | null;
  due_at?: string | null;
  created_at: string;
};

export type ComparisonQuote = {
  id: number;
  item_id: number;
  vendor: string;
  price: string;
  screenshot_attachment_id?: number | null;
  screenshot?: Attachment | null;
  note?: string | null;
  created_at: string;
};

export type ComparisonItem = {
  id: number;
  project_id: number;
  space: string;
  name: string;
  note?: string | null;
  quotes: ComparisonQuote[];
  created_at: string;
};

export type Inspection = {
  id: number;
  project_id: number;
  stage: string;
  item: string;
  standard: string;
  status: string;
  note?: string | null;
  attachment_id?: number | null;
  attachment?: Attachment | null;
  created_at: string;
};

export type Todo = {
  id: number;
  project_id: number;
  title: string;
  description?: string | null;
  due_at?: string | null;
  importance: number;
  status: string;
  assignee_id?: number | null;
  created_at: string;
};

export type ActivityLog = {
  id: number;
  project_id: number;
  actor_id: number;
  action: string;
  target_type: string;
  target_id?: number | null;
  message: string;
  created_at: string;
  actor: User;
};

export type ProjectProgress = {
  id: number;
  project_id: number;
  current_stage: string;
  note?: string | null;
  updated_at: string;
};

export type ProjectStage = {
  id: number;
  project_id: number;
  value: string;
  label: string;
  planned_days: number;
  sort_order: number;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
};

export type MetaOptions = {
  renovation_stages: Option[];
  amount_categories: Option[];
  task_statuses: Option[];
  inspection_statuses: Option[];
};

export type KnowledgeDocument = {
  id: number;
  project_id?: number | null;
  source_type: string;
  title: string;
  filename: string;
  download_url: string;
  summary?: string | null;
  content?: string | null;
  index_status: string;
  indexed_at?: string | null;
  index_error?: string | null;
  created_at: string;
};

export type KnowledgeIndexTrigger = {
  queued: number;
  skipped: number;
  failed: number;
  total_unready: number;
};

export type KnowledgeSource = {
  id: number;
  document_id: number;
  document_title: string;
  heading: string;
  text: string;
  download_url: string;
  score: number;
};

export type KnowledgeAnswer = {
  answer: string;
  sources: KnowledgeSource[];
  documents: KnowledgeDocument[];
};

export type KnowledgeChatHistoryMessage = {
  role: 'user' | 'assistant';
  content: string;
};
