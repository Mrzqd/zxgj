import { FormEvent, ReactNode, useEffect, useRef, useState } from 'react';
import { Bot, Download, FileText, Pencil, RefreshCw, Search, Send, Settings, Trash2, UploadCloud, UserRound } from 'lucide-react';
import { api } from '../../api';
import { EmptyLine, Field, Modal, Tip } from '../../components/ui';
import { useSubmitting } from '../../hooks/useSubmitting';
import type { KnowledgeAnswer, KnowledgeChatHistoryMessage, KnowledgeDocument, KnowledgeSource } from '../../types';

type ChatMessage = {
  id: string;
  role: 'assistant' | 'user';
  content: string;
  sources?: KnowledgeSource[];
};

const WELCOME_MESSAGE: ChatMessage = {
  id: 'welcome',
  role: 'assistant',
  content: '我是装修助手。可以问验收、采购、预算、工期和注意事项。我会优先检索知识库，并附上引用来源。',
};

const MAX_STORED_MESSAGES = 60;
const MAX_HISTORY_MESSAGES = 10;

const QUICK_QUESTIONS = [
  '卫生间闭水试验怎么验收？',
  '水电打压要注意什么？',
  '瓦工验收怎么看空鼓和坡度？',
  '装修付款和增项怎么控制风险？',
];

export function AssistantScreen({ token, projectId }: { token: string; projectId: number }) {
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [question, setQuestion] = useState('');
  const [chatState, setChatState] = useState(() => ({
    projectId,
    messages: loadStoredMessages(projectId),
  }));
  const [notice, setNotice] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const [streamStatus, setStreamStatus] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [editingDocument, setEditingDocument] = useState<KnowledgeDocument | null>(null);
  const [previewSource, setPreviewSource] = useState<KnowledgeSource | null>(null);
  const { submitting, guard } = useSubmitting();
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const messages = chatState.messages;

  function setMessages(next: ChatMessage[] | ((current: ChatMessage[]) => ChatMessage[])) {
    setChatState((current) => ({
      ...current,
      messages: typeof next === 'function' ? next(current.messages) : next,
    }));
  }

  async function refreshDocuments() {
    const result = await api.listKnowledgeDocuments(token, projectId);
    setDocuments(result);
  }

  useEffect(() => {
    refreshDocuments().catch((error) => {
      setNotice(error instanceof Error ? error.message : '知识库加载失败');
    });
  }, [token, projectId]);

  useEffect(() => {
    setChatState({
      projectId,
      messages: loadStoredMessages(projectId),
    });
    setNotice(null);
  }, [projectId]);

  useEffect(() => {
    if (chatState.projectId !== projectId) return;
    saveStoredMessages(projectId, chatState.messages);
  }, [projectId, chatState]);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, asking]);

  async function ask(nextQuestion = question) {
    const trimmed = nextQuestion.trim();
    if (!trimmed) {
      setNotice('先输入一个装修问题');
      return;
    }

    await guard(async () => {
      setNotice(null);
      setQuestion('');
      setAsking(true);
      setStreamStatus('正在理解问题...');
      const history = toRequestHistory(messages);
      const assistantMessageId = `a-${Date.now()}`;
      setMessages((current) => [
        ...trimStoredMessages(current),
        { id: `q-${Date.now()}`, role: 'user', content: trimmed },
        { id: assistantMessageId, role: 'assistant', content: '' },
      ]);
      try {
        await api.streamKnowledgeAnswer(token, projectId, trimmed, history, (event) => {
          if (event.event === 'status') {
            setStreamStatus(event.data.message);
            return;
          }
          if (event.event === 'sources') {
            setMessages((current) => updateMessage(current, assistantMessageId, { sources: event.data.sources }));
            return;
          }
          if (event.event === 'delta') {
            setMessages((current) => appendMessageContent(current, assistantMessageId, event.data.text));
            return;
          }
          if (event.event === 'done') {
            setStreamStatus(null);
            setMessages((current) => updateMessage(current, assistantMessageId, { content: event.data.answer }));
            return;
          }
        });
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : '助手请求失败';
        setMessages((current) => updateMessage(current, assistantMessageId, { content: `请求失败：${errorMessage}` }));
      } finally {
        setAsking(false);
        setStreamStatus(null);
      }
    });
  }

  async function uploadDocument(file: File | null) {
    if (!file) return;
    await guard(async () => {
      setNotice(null);
      await api.uploadKnowledgeDocument(token, projectId, file);
      await refreshDocuments();
      setNotice('知识库文件已上传并入库');
    });
  }

  async function buildUnreadyIndex() {
    await guard(async () => {
      setNotice(null);
      const result = await api.triggerKnowledgeIndex(token, projectId);
      await refreshDocuments();
      if (result.failed > 0) {
        setNotice(`已提交 ${result.queued} 个索引任务，${result.failed} 个提交失败`);
        return;
      }
      if (result.queued > 0) {
        setNotice(`已提交 ${result.queued} 个索引任务，${result.skipped} 个正在索引中`);
        return;
      }
      setNotice(result.skipped > 0 ? '未索引文档已在索引中' : '没有待构建索引的文档');
    });
  }

  async function removeDocument(document: KnowledgeDocument) {
    if (document.source_type !== 'upload') {
      setNotice('内置知识库不允许删除');
      return;
    }
    if (!window.confirm(`删除知识库文件「${document.title}」？`)) return;
    await guard(async () => {
      setNotice(null);
      await api.deleteKnowledgeDocument(token, projectId, document.id);
      await refreshDocuments();
      setNotice('知识库文件已删除');
    });
  }

  async function openEditor(document: KnowledgeDocument) {
    if (document.source_type !== 'upload') {
      setNotice('内置知识库不允许编辑');
      return;
    }
    await guard(async () => {
      const detail = await api.getKnowledgeDocument(token, projectId, document.id);
      setEditingDocument(detail);
    });
  }

  async function saveDocument(documentId: number, payload: { title: string; filename: string; content: string }) {
    await guard(async () => {
      await api.updateKnowledgeDocument(token, projectId, documentId, {
        ...payload,
        content_type: payload.filename.endsWith('.txt') ? 'text/plain' : 'text/markdown',
      });
      setEditingDocument(null);
      await refreshDocuments();
      setNotice('知识库文件已更新');
    });
  }

  async function downloadDocument(path: string, filename: string) {
    await guard(async () => {
      const blob = await api.downloadKnowledgeFile(token, path);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    });
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    ask();
  }

  function clearMessages() {
    if (!window.confirm('确认清空当前项目的聊天记录？')) return;
    setMessages([WELCOME_MESSAGE]);
  }

  return (
    <div className="flex h-[calc(100dvh-6.25rem)] min-h-0 flex-col overflow-hidden rounded-[1.75rem] bg-[#f7f1e6] shadow-sm">
      <header className="shrink-0 border-b border-ink/10 bg-[#f7f1e6]/95 px-3 py-3 backdrop-blur">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="grid h-9 w-9 place-items-center rounded-2xl bg-ink text-white">
              <Bot className="h-4 w-4" />
            </span>
            <div>
              <h2 className="font-display text-lg font-black leading-tight">AI 装修助手</h2>
              <p className="text-[11px] font-semibold text-ink/45">RAG 知识库问答</p>
            </div>
          </div>
          <div className="flex gap-1.5">
            <button
              onClick={clearMessages}
              className="grid h-9 w-9 place-items-center rounded-2xl bg-white text-ink/45 shadow-sm"
              aria-label="清空聊天记录"
            >
              <Trash2 className="h-4 w-4" />
            </button>
            <button
              onClick={() => setSettingsOpen(true)}
              className="grid h-9 w-9 place-items-center rounded-2xl bg-white text-ink shadow-sm"
              aria-label="知识库设置"
            >
              <Settings className="h-4 w-4" />
            </button>
          </div>
        </div>
        <Tip message={notice} onClose={() => setNotice(null)} tone="info" className="mt-2" />
      </header>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain px-3 py-3">
        {messages.map((message) => (
          <ChatBubble
            key={message.id}
            message={message}
            onPreview={setPreviewSource}
          />
        ))}
        {asking && <AssistantTyping status={streamStatus} />}
        <div ref={scrollRef} />
      </div>

      <div className="shrink-0 border-t border-ink/10 bg-[#f7f1e6] p-3">
        <div className="mb-2 flex gap-1.5 overflow-x-auto pb-1">
          {QUICK_QUESTIONS.map((item) => (
            <button
              key={item}
              onClick={() => ask(item)}
              disabled={submitting}
              className="shrink-0 rounded-full bg-white px-3 py-1.5 text-xs font-bold text-ink/60 shadow-sm"
            >
              {item}
            </button>
          ))}
        </div>
        <form onSubmit={submit} className="flex items-end gap-2 rounded-[1.35rem] bg-white p-2 shadow-sm">
          <textarea
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            rows={1}
            className="max-h-28 min-h-10 flex-1 resize-none rounded-2xl bg-sand/70 px-3 py-2.5 text-sm outline-none"
            placeholder="输入装修问题..."
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                ask();
              }
            }}
          />
          <button
            disabled={submitting || !question.trim()}
            className="grid h-10 w-10 shrink-0 place-items-center rounded-2xl bg-clay text-white disabled:opacity-50"
            aria-label="发送"
          >
            <Send className="h-4 w-4" />
          </button>
        </form>
      </div>

      {settingsOpen && (
        <KnowledgeSettingsModal
          documents={documents}
          submitting={submitting}
          onClose={() => setSettingsOpen(false)}
          onUpload={uploadDocument}
          onBuildIndex={buildUnreadyIndex}
          onEdit={openEditor}
          onRemove={removeDocument}
          onDownload={downloadDocument}
        />
      )}

      {editingDocument && (
        <DocumentEditorModal
          document={editingDocument}
          submitting={submitting}
          onClose={() => setEditingDocument(null)}
          onSave={saveDocument}
        />
      )}

      {previewSource && (
        <SourcePreviewModal
          source={previewSource}
          onClose={() => setPreviewSource(null)}
          onDownload={(path, filename) => downloadDocument(path, filename)}
        />
      )}
    </div>
  );
}

function chatStorageKey(projectId: number) {
  return `renovation_assistant_messages_${projectId}`;
}

function isChatMessage(value: unknown): value is ChatMessage {
  if (!value || typeof value !== 'object') return false;
  const item = value as Partial<ChatMessage>;
  return (
    typeof item.id === 'string'
    && (item.role === 'assistant' || item.role === 'user')
    && typeof item.content === 'string'
  );
}

function loadStoredMessages(projectId: number): ChatMessage[] {
  try {
    const raw = localStorage.getItem(chatStorageKey(projectId));
    if (!raw) return [WELCOME_MESSAGE];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [WELCOME_MESSAGE];
    const messages = parsed.filter(isChatMessage).slice(-MAX_STORED_MESSAGES);
    return messages.length ? messages : [WELCOME_MESSAGE];
  } catch {
    return [WELCOME_MESSAGE];
  }
}

function saveStoredMessages(projectId: number, messages: ChatMessage[]) {
  const nextMessages = trimStoredMessages(messages);
  localStorage.setItem(chatStorageKey(projectId), JSON.stringify(nextMessages));
}

function trimStoredMessages(messages: ChatMessage[]) {
  const welcome = messages.find((message) => message.id === WELCOME_MESSAGE.id) || WELCOME_MESSAGE;
  const rest = messages.filter((message) => message.id !== WELCOME_MESSAGE.id).slice(-(MAX_STORED_MESSAGES - 1));
  return [welcome, ...rest];
}

function updateMessage(messages: ChatMessage[], id: string, patch: Partial<ChatMessage>) {
  return trimStoredMessages(
    messages.map((message) => (message.id === id ? { ...message, ...patch } : message)),
  );
}

function appendMessageContent(messages: ChatMessage[], id: string, text: string) {
  return trimStoredMessages(
    messages.map((message) => (
      message.id === id ? { ...message, content: `${message.content}${text}` } : message
    )),
  );
}

function toRequestHistory(messages: ChatMessage[]): KnowledgeChatHistoryMessage[] {
  return messages
    .filter((message) => message.id !== WELCOME_MESSAGE.id && (message.role === 'user' || message.role === 'assistant'))
    .slice(-MAX_HISTORY_MESSAGES)
    .map((message) => ({
      role: message.role,
      content: message.content,
    }));
}

function ChatBubble({
  message,
  onPreview,
}: {
  message: ChatMessage;
  onPreview: (source: KnowledgeSource) => void;
}) {
  const isUser = message.role === 'user';
  return (
    <div className={`flex gap-2 ${isUser ? 'justify-end' : 'justify-start'}`}>
      {!isUser && <Avatar icon={<Bot className="h-4 w-4" />} tone="dark" />}
      <div className={`max-w-[82%] ${isUser ? 'order-first' : ''}`}>
        <div
          className={
            isUser
              ? 'rounded-[1.35rem] rounded-tr-md bg-clay px-3 py-2.5 text-sm leading-6 text-white'
              : 'rounded-[1.35rem] rounded-tl-md bg-white px-3 py-2.5 text-sm leading-6 text-ink shadow-sm'
          }
        >
          <MarkdownText content={message.content} />
        </div>
        {!isUser && message.sources && message.sources.length > 0 && (
          <div className="mt-2 space-y-1.5">
            {message.sources.slice(0, 3).map((source) => (
              <button
                key={source.id}
                onClick={() => onPreview(source)}
                className="block w-full rounded-2xl border border-ink/10 bg-white/80 px-3 py-2 text-left text-xs shadow-sm"
              >
                <span className="block font-bold text-ink">{source.heading}</span>
                <span className="mt-0.5 block truncate text-ink/45">{source.document_title} · 点击预览引用片段</span>
              </button>
            ))}
          </div>
        )}
      </div>
      {isUser && <Avatar icon={<UserRound className="h-4 w-4" />} tone="light" />}
    </div>
  );
}

function Avatar({ icon, tone }: { icon: ReactNode; tone: 'dark' | 'light' }) {
  return (
    <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-2xl ${tone === 'dark' ? 'bg-ink text-white' : 'bg-white text-clay'}`}>
      {icon}
    </span>
  );
}

function AssistantTyping({ status }: { status: string | null }) {
  return (
    <div className="flex items-center gap-2">
      <Avatar icon={<Bot className="h-4 w-4" />} tone="dark" />
      <div className="flex items-center gap-2 rounded-2xl bg-white px-3 py-3 text-xs font-bold text-ink/50 shadow-sm">
        <span className="assistant-search-icon" aria-hidden="true">
          <Search className="h-3.5 w-3.5" />
        </span>
        <span>{status || '正在处理...'}</span>
      </div>
    </div>
  );
}

function SourcePreviewModal({
  source,
  onClose,
  onDownload,
}: {
  source: KnowledgeSource;
  onClose: () => void;
  onDownload: (path: string, filename: string) => void;
}) {
  return (
    <Modal title="参考资料片段" onClose={onClose}>
      <div className="space-y-3">
        <div className="rounded-2xl bg-white p-3 shadow-sm">
          <p className="text-xs font-bold text-moss">{source.document_title}</p>
          <h3 className="mt-1 font-display text-lg font-black">{source.heading}</h3>
          <p className="mt-1 text-xs font-semibold text-ink/40">相关度 {source.score}</p>
        </div>
        <div className="max-h-[48vh] overflow-y-auto rounded-2xl bg-sand p-3 text-sm leading-7 text-ink/75">
          <MarkdownText content={source.text} />
        </div>
        <button
          onClick={() => onDownload(source.download_url, `${source.document_title}.md`)}
          className="secondary-button w-full"
        >
          <Download className="h-4 w-4" />
          下载完整资料
        </button>
      </div>
    </Modal>
  );
}

function KnowledgeSettingsModal({
  documents,
  submitting,
  onClose,
  onUpload,
  onBuildIndex,
  onEdit,
  onRemove,
  onDownload,
}: {
  documents: KnowledgeDocument[];
  submitting: boolean;
  onClose: () => void;
  onUpload: (file: File | null) => void;
  onBuildIndex: () => void;
  onEdit: (document: KnowledgeDocument) => void;
  onRemove: (document: KnowledgeDocument) => void;
  onDownload: (path: string, filename: string) => void;
}) {
  const builtinDocuments = documents.filter((document) => document.source_type === 'builtin');
  const uploadDocuments = documents.filter((document) => document.source_type === 'upload');
  const unreadyCount = documents.filter((document) => document.index_status !== 'ready').length;
  const failedCount = documents.filter((document) => document.index_status === 'failed').length;

  return (
    <Modal title="知识库设置" onClose={onClose}>
      <div className="space-y-3">
        <button
          onClick={onBuildIndex}
          disabled={submitting || unreadyCount === 0}
          className="flex w-full items-center gap-3 rounded-2xl bg-ink px-3 py-3 text-left text-white shadow-sm disabled:bg-ink/20 disabled:text-ink/40"
        >
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-white/12">
            <RefreshCw className={`h-5 w-5 ${submitting ? 'animate-spin' : ''}`} />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-sm font-black">构建未索引文档索引</span>
            <span className="mt-0.5 block text-xs text-white/65">
              {unreadyCount > 0
                ? `${unreadyCount} 份未就绪${failedCount > 0 ? `，其中 ${failedCount} 份失败可重试` : ''}`
                : '全部知识库文件已就绪'}
            </span>
          </span>
        </button>

        <label className="flex cursor-pointer items-center gap-3 rounded-2xl border border-dashed border-ink/20 bg-white px-3 py-4">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-sand text-clay">
            <UploadCloud className="h-5 w-5" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-sm font-bold">上传 Markdown / TXT</span>
            <span className="mt-0.5 block text-xs text-ink/45">用户新增的知识库可编辑、删除</span>
          </span>
          <input
            type="file"
            accept=".md,.txt,text/markdown,text/plain"
            className="hidden"
            disabled={submitting}
            onChange={(event) => {
              onUpload(event.target.files?.[0] || null);
              event.currentTarget.value = '';
            }}
          />
        </label>

        <KnowledgeGroup
          title="用户知识库"
          empty="还没有上传项目资料"
          documents={uploadDocuments}
          editable
          onEdit={onEdit}
          onRemove={onRemove}
          onDownload={onDownload}
        />
        <KnowledgeGroup
          title="内置知识库"
          empty="暂无内置资料"
          documents={builtinDocuments}
          editable={false}
          onEdit={onEdit}
          onRemove={onRemove}
          onDownload={onDownload}
        />
      </div>
    </Modal>
  );
}

function KnowledgeGroup({
  title,
  empty,
  documents,
  editable,
  onEdit,
  onRemove,
  onDownload,
}: {
  title: string;
  empty: string;
  documents: KnowledgeDocument[];
  editable: boolean;
  onEdit: (document: KnowledgeDocument) => void;
  onRemove: (document: KnowledgeDocument) => void;
  onDownload: (path: string, filename: string) => void;
}) {
  function statusLabel(document: KnowledgeDocument) {
    if (document.index_status === 'ready') return '已就绪';
    if (document.index_status === 'failed') return '索引失败';
    if (document.index_status === 'queued') return '排队中';
    if (document.index_status === 'indexing') return '索引中';
    if (document.index_error) return '等待重试';
    return '待索引';
  }

  function statusClass(document: KnowledgeDocument) {
    if (document.index_status === 'ready') return 'bg-moss/10 text-moss';
    if (document.index_status === 'failed') return 'bg-clay/10 text-clay';
    if (document.index_error) return 'bg-clay/10 text-clay';
    return 'bg-amber-100 text-amber-700';
  }

  return (
    <section className="rounded-2xl bg-sand/60 p-2">
      <div className="mb-2 flex items-center justify-between px-1">
        <h3 className="text-sm font-black">{title}</h3>
        <span className="text-xs font-bold text-ink/40">{documents.length} 份</span>
      </div>
      {documents.length === 0 ? (
        <EmptyLine text={empty} />
      ) : (
        <div className="space-y-2">
          {documents.map((document) => (
            <div key={document.id} className="rounded-2xl bg-white px-3 py-2.5 shadow-sm">
              <div className="flex gap-2">
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-sand text-clay">
                  <FileText className="h-4 w-4" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="min-w-0 flex-1 truncate text-sm font-bold">{document.title}</p>
                    <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-black ${statusClass(document)}`}>
                      {statusLabel(document)}
                    </span>
                  </div>
                  <p className="mt-0.5 line-clamp-2 text-xs leading-4 text-ink/45">{document.summary || document.filename}</p>
                  {document.index_error ? (
                    <p className="mt-1 line-clamp-2 text-[11px] leading-4 text-clay">{document.index_error}</p>
                  ) : null}
                </div>
              </div>
              <div className="mt-2 flex gap-2">
                <button onClick={() => onDownload(document.download_url, document.filename)} className="flex-1 rounded-xl bg-sand px-2 py-2 text-xs font-bold text-ink/65">
                  <Download className="mr-1 inline h-3.5 w-3.5" />
                  下载
                </button>
                {editable ? (
                  <>
                    <button onClick={() => onEdit(document)} className="flex-1 rounded-xl bg-moss px-2 py-2 text-xs font-bold text-white">
                      <Pencil className="mr-1 inline h-3.5 w-3.5" />
                      编辑
                    </button>
                    <button onClick={() => onRemove(document)} className="rounded-xl bg-clay/10 px-3 py-2 text-xs font-bold text-clay">
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </>
                ) : (
                  <span className="flex-1 rounded-xl bg-ink/5 px-2 py-2 text-center text-xs font-bold text-ink/35">只读</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function DocumentEditorModal({
  document,
  submitting,
  onClose,
  onSave,
}: {
  document: KnowledgeDocument;
  submitting: boolean;
  onClose: () => void;
  onSave: (documentId: number, payload: { title: string; filename: string; content: string }) => void;
}) {
  const [title, setTitle] = useState(document.title);
  const [filename, setFilename] = useState(document.filename);
  const [content, setContent] = useState(document.content || '');

  function submit(event: FormEvent) {
    event.preventDefault();
    const trimmedFilename = filename.trim();
    if (!trimmedFilename.endsWith('.md') && !trimmedFilename.endsWith('.txt')) {
      window.alert('文件名必须以 .md 或 .txt 结尾');
      return;
    }
    onSave(document.id, { title: title.trim(), filename: trimmedFilename, content });
  }

  return (
    <Modal title="编辑知识库文件" onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <Field label="标题">
          <input value={title} onChange={(event) => setTitle(event.target.value)} required className="input" />
        </Field>
        <Field label="文件名">
          <input value={filename} onChange={(event) => setFilename(event.target.value)} required className="input" placeholder="example.md" />
        </Field>
        <Field label="Markdown / TXT 内容">
          <textarea
            value={content}
            onChange={(event) => setContent(event.target.value)}
            required
            className="input min-h-[42vh] resize-y font-mono text-xs leading-5"
          />
        </Field>
        <button disabled={submitting || !title.trim() || !filename.trim() || !content.trim()} className="primary-button w-full">
          保存并重新入库
        </button>
      </form>
    </Modal>
  );
}

function MarkdownText({ content }: { content: string }) {
  return <div className="space-y-2">{parseMarkdown(content).map((node, index) => renderMarkdownNode(node, index))}</div>;
}

type MarkdownNode =
  | { type: 'heading'; level: number; text: string }
  | { type: 'list'; items: string[] }
  | { type: 'code'; text: string }
  | { type: 'paragraph'; text: string };

function parseMarkdown(markdown: string): MarkdownNode[] {
  const lines = markdown.split('\n');
  const nodes: MarkdownNode[] = [];
  let paragraph: string[] = [];
  let list: string[] = [];
  let code: string[] = [];
  let inCode = false;

  function flushParagraph() {
    if (paragraph.length) {
      nodes.push({ type: 'paragraph', text: paragraph.join(' ') });
      paragraph = [];
    }
  }

  function flushList() {
    if (list.length) {
      nodes.push({ type: 'list', items: list });
      list = [];
    }
  }

  for (const line of lines) {
    if (line.trim().startsWith('```')) {
      if (inCode) {
        nodes.push({ type: 'code', text: code.join('\n') });
        code = [];
        inCode = false;
      } else {
        flushParagraph();
        flushList();
        inCode = true;
      }
      continue;
    }
    if (inCode) {
      code.push(line);
      continue;
    }
    if (!line.trim()) {
      flushParagraph();
      flushList();
      continue;
    }
    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      flushList();
      nodes.push({ type: 'heading', level: heading[1].length, text: heading[2] });
      continue;
    }
    const bullet = line.match(/^\s*(?:[-*]|\d+\.)\s+(.+)$/);
    if (bullet) {
      flushParagraph();
      list.push(bullet[1]);
      continue;
    }
    flushList();
    paragraph.push(line.trim());
  }
  flushParagraph();
  flushList();
  if (code.length) nodes.push({ type: 'code', text: code.join('\n') });
  return nodes.length ? nodes : [{ type: 'paragraph', text: markdown }];
}

function renderMarkdownNode(node: MarkdownNode, index: number) {
  if (node.type === 'heading') {
    const size = node.level === 1 ? 'text-base' : node.level === 2 ? 'text-sm' : 'text-xs';
    return <h3 key={index} className={`${size} font-black leading-6`}>{renderInlineMarkdown(node.text)}</h3>;
  }
  if (node.type === 'list') {
    return (
      <ul key={index} className="ml-4 list-disc space-y-1">
        {node.items.map((item, itemIndex) => (
          <li key={itemIndex}>{renderInlineMarkdown(item)}</li>
        ))}
      </ul>
    );
  }
  if (node.type === 'code') {
    return <pre key={index} className="overflow-x-auto rounded-xl bg-ink/90 p-3 text-xs leading-5 text-white">{node.text}</pre>;
  }
  return <p key={index}>{renderInlineMarkdown(node.text)}</p>;
}

function renderInlineMarkdown(text: string) {
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).filter(Boolean);
  return parts.map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return <code key={index} className="rounded bg-ink/10 px-1 py-0.5 text-[0.9em]">{part.slice(1, -1)}</code>;
    }
    return <span key={index}>{part}</span>;
  });
}
