import { useState } from 'react';
import { Edit3, ImageIcon, Plus, Scale, Trash2 } from 'lucide-react';
import { api } from '../../api';
import { EmptyLine, Field, InlineLoading, Modal, ModuleHero } from '../../components/ui';
import { useSubmitting } from '../../hooks/useSubmitting';
import type { Attachment, ComparisonItem, ComparisonQuote } from '../../types';
import { money } from '../../utils/format';

export function ComparisonsScreen({
  projectId,
  token,
  items,
  loading,
  onRefresh,
}: {
  projectId: number;
  token: string;
  items: ComparisonItem[];
  loading: boolean;
  onRefresh: () => Promise<void>;
}) {
  const [openItem, setOpenItem] = useState(false);
  const [quoteItem, setQuoteItem] = useState<ComparisonItem | null>(null);
  const [editingItem, setEditingItem] = useState<ComparisonItem | null>(null);
  const [editingQuote, setEditingQuote] = useState<{ item: ComparisonItem; quote: ComparisonQuote } | null>(null);
  const [preview, setPreview] = useState<Attachment | null>(null);

  async function deleteItem(item: ComparisonItem) {
    if (!window.confirm(`确认删除「${item.name}」及其所有报价？`)) return;
    await api.deleteComparisonItem(token, projectId, item.id);
    await onRefresh();
  }

  async function deleteQuote(item: ComparisonItem, quote: ComparisonQuote) {
    if (!window.confirm(`确认删除「${quote.vendor}」报价？`)) return;
    await api.deleteQuote(token, projectId, item.id, quote.id);
    await onRefresh();
  }

  return (
    <div className="space-y-3">
      <ModuleHero icon={<Scale />} title="物品比价" subtitle="厨房油烟机、京东/淘宝/线下价格和截图集中比较。" />
      {loading && <InlineLoading text="比价数据加载中..." />}
      <div className="grid grid-cols-[1fr_auto] items-center gap-2 rounded-2xl bg-white p-3 shadow-sm">
        <div>
          <p className="font-display text-lg font-bold">比价清单</p>
          <p className="text-xs text-ink/45">{items.length} 个物品，{items.reduce((sum, item) => sum + item.quotes.length, 0)} 条报价</p>
        </div>
        <button onClick={() => setOpenItem(true)} className="primary-button px-3 py-2">
          <Plus className="h-4 w-4" /> 物品
        </button>
      </div>
      <div className="space-y-2">
        {items.map((item) => {
          const best = item.quotes.reduce<number | null>((min, quote) => {
            const price = Number(quote.price);
            return min === null || price < min ? price : min;
          }, null);
          return (
            <div key={item.id} className="rounded-2xl bg-white p-3 shadow-sm">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-xs font-semibold text-moss">{item.space}</p>
                  <p className="font-semibold leading-5">{item.name}</p>
                  <p className="mt-1 text-xs text-ink/45">最低价：{best === null ? '暂无报价' : money(best)}</p>
                </div>
                <div className="flex shrink-0 gap-1">
                  <button onClick={() => setQuoteItem(item)} className="rounded-full bg-sand px-2.5 py-1 text-xs font-semibold">
                    加价
                  </button>
                  <button onClick={() => setEditingItem(item)} className="rounded-full bg-sand px-2 py-1 text-xs">
                    <Edit3 className="h-3.5 w-3.5" />
                  </button>
                  <button onClick={() => deleteItem(item)} className="rounded-full bg-clay/10 px-2 py-1 text-xs text-clay">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
              <div className="mt-2 grid gap-2">
                {item.quotes.map((quote) => (
                  <div key={quote.id} className="rounded-xl bg-sand px-3 py-2">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold">{quote.vendor}</p>
                        <p className="font-display text-lg font-black text-clay">{money(quote.price)}</p>
                      </div>
                      <div className="flex gap-1">
                        {quote.screenshot && (
                          <button onClick={() => setPreview(quote.screenshot || null)} className="rounded-full bg-white px-2 py-1 text-moss">
                            <ImageIcon className="h-3.5 w-3.5" />
                          </button>
                        )}
                        <button onClick={() => setEditingQuote({ item, quote })} className="rounded-full bg-white px-2 py-1">
                          <Edit3 className="h-3.5 w-3.5" />
                        </button>
                        <button onClick={() => deleteQuote(item, quote)} className="rounded-full bg-white px-2 py-1 text-clay">
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </div>
                    {quote.note && <p className="mt-1 text-xs leading-5 text-ink/55">{quote.note}</p>}
                  </div>
                ))}
                {item.quotes.length === 0 && <p className="px-3 py-2 text-xs text-ink/45">暂无报价</p>}
              </div>
            </div>
          );
        })}
        {items.length === 0 && <EmptyLine text="还没有比价物品" />}
      </div>
      {openItem && (
        <ComparisonItemForm
          token={token}
          projectId={projectId}
          onClose={() => setOpenItem(false)}
          onCreated={onRefresh}
        />
      )}
      {editingItem && (
        <ComparisonItemForm
          token={token}
          projectId={projectId}
          item={editingItem}
          onClose={() => setEditingItem(null)}
          onCreated={onRefresh}
        />
      )}
      {quoteItem && (
        <QuoteForm
          token={token}
          projectId={projectId}
          item={quoteItem}
          onClose={() => setQuoteItem(null)}
          onCreated={onRefresh}
        />
      )}
      {editingQuote && (
        <QuoteForm
          token={token}
          projectId={projectId}
          item={editingQuote.item}
          quote={editingQuote.quote}
          onClose={() => setEditingQuote(null)}
          onCreated={onRefresh}
        />
      )}
      {preview && <AttachmentPreview attachment={preview} onClose={() => setPreview(null)} />}
    </div>
  );
}

function AttachmentPreview({ attachment, onClose }: { attachment: Attachment; onClose: () => void }) {
  const isImage = attachment.content_type?.startsWith('image/');

  return (
    <Modal title="报价截图" onClose={onClose}>
      <div className="space-y-4">
        {isImage ? (
          <img src={attachment.url} alt={attachment.file_name} className="max-h-[65vh] w-full rounded-2xl bg-white object-contain" />
        ) : (
          <div className="rounded-2xl bg-white p-5 text-sm text-ink/60">该附件不是图片文件，可在新窗口查看。</div>
        )}
        <div className="flex gap-2">
          <a href={attachment.url} target="_blank" rel="noreferrer" className="secondary-button flex-1">
            新窗口打开
          </a>
          <button onClick={onClose} className="primary-button flex-1">
            关闭
          </button>
        </div>
      </div>
    </Modal>
  );
}

function ComparisonItemForm({
  token,
  projectId,
  onClose,
  onCreated,
  item,
}: {
  token: string;
  projectId: number;
  onClose: () => void;
  onCreated: () => Promise<void>;
  item?: ComparisonItem;
}) {
  const [space, setSpace] = useState(item?.space || '');
  const [name, setName] = useState(item?.name || '');
  const [note, setNote] = useState(item?.note || '');
  const { submitting, guard } = useSubmitting();

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    await guard(async () => {
      if (item) {
        await api.updateComparisonItem(token, projectId, item.id, { space, name, note });
      } else {
        await api.createComparisonItem(token, projectId, { space, name, note });
      }
      await onCreated();
      onClose();
    });
  }

  return (
    <Modal title={item ? '编辑比价物品' : '新增比价物品'} onClose={onClose}>
      <form onSubmit={submit}>
        <Field label="空间">
          <input value={space} onChange={(event) => setSpace(event.target.value)} placeholder="厨房" required className="input" />
        </Field>
        <Field label="物品">
          <input value={name} onChange={(event) => setName(event.target.value)} placeholder="油烟机" required className="input" />
        </Field>
        <Field label="备注">
          <textarea value={note} onChange={(event) => setNote(event.target.value)} className="input min-h-20" />
        </Field>
        <button disabled={submitting} className="primary-button w-full">
          {submitting ? '保存中...' : item ? '保存修改' : '保存'}
        </button>
      </form>
    </Modal>
  );
}

function QuoteForm({
  token,
  projectId,
  item,
  onClose,
  onCreated,
  quote,
}: {
  token: string;
  projectId: number;
  item: ComparisonItem;
  onClose: () => void;
  onCreated: () => Promise<void>;
  quote?: ComparisonQuote;
}) {
  const [vendor, setVendor] = useState(quote?.vendor || '');
  const [price, setPrice] = useState(quote?.price || '');
  const [note, setNote] = useState(quote?.note || '');
  const [file, setFile] = useState<File | null>(null);
  const { submitting, guard } = useSubmitting();

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    await guard(async () => {
      let attachment: Attachment | null = null;
      if (file) {
        attachment = await api.upload(token, projectId, file);
      }
      const payload = {
        vendor,
        price,
        note,
        screenshot_attachment_id: attachment?.id || quote?.screenshot_attachment_id || null,
      };
      if (quote) {
        await api.updateQuote(token, projectId, item.id, quote.id, payload);
      } else {
        await api.createQuote(token, projectId, item.id, payload);
      }
      await onCreated();
      onClose();
    });
  }

  return (
    <Modal title={`${quote ? '编辑' : '新增'}报价：${item.name}`} onClose={onClose}>
      <form onSubmit={submit}>
        <Field label="平台/渠道">
          <input value={vendor} onChange={(event) => setVendor(event.target.value)} placeholder="京东 / 淘宝 / 本地店" required className="input" />
        </Field>
        <Field label="价格">
          <input type="number" value={price} onChange={(event) => setPrice(event.target.value)} required className="input" />
        </Field>
        <Field label="截图">
          <input type="file" accept="image/*" onChange={(event) => setFile(event.target.files?.[0] || null)} className="file-input" />
          {quote?.screenshot && !file && (
            <p className="mt-2 text-xs text-ink/45">当前截图：{quote.screenshot.file_name}</p>
          )}
        </Field>
        <Field label="备注">
          <textarea value={note} onChange={(event) => setNote(event.target.value)} className="input min-h-20" />
        </Field>
        <button disabled={submitting} className="primary-button w-full">
          {submitting ? '保存中...' : quote ? '保存修改' : '保存'}
        </button>
      </form>
    </Modal>
  );
}
