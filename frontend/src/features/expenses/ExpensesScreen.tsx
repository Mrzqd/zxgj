import { useState } from 'react';
import { Edit3, Plus, ReceiptText } from 'lucide-react';
import { api } from '../../api';
import { EmptyLine, Field, InlineLoading, Modal, ModuleHero, SelectField, StatCard } from '../../components/ui';
import { useSubmitting } from '../../hooks/useSubmitting';
import type { Attachment, Expense, MetaOptions, ProjectStage } from '../../types';
import { labelOf, money } from '../../utils/format';

export function ExpensesScreen({
  projectId,
  token,
  meta,
  stages,
  expenses,
  loading,
  onRefresh,
}: {
  projectId: number;
  token: string;
  meta: MetaOptions;
  stages: ProjectStage[];
  expenses: Expense[];
  loading: boolean;
  onRefresh: () => Promise<void>;
}) {
  const total = expenses.reduce((sum, item) => sum + Number(item.amount), 0);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Expense | null>(null);
  const [preview, setPreview] = useState<Attachment | null>(null);

  return (
    <div className="space-y-4">
      <ModuleHero icon={<ReceiptText />} title="装修记账" subtitle="阶段、款项、子项、凭证和备注放在同一条记录里。" />
      {loading && <InlineLoading text="记账数据加载中..." />}
      <div className="grid grid-cols-2 gap-3">
        <StatCard label="总支出" value={money(total)} />
        <StatCard label="记录数" value={`${expenses.length} 条`} />
      </div>
      <button onClick={() => setOpen(true)} className="primary-button w-full">
        <Plus className="h-4 w-4" /> 新增记账
      </button>
      <div className="space-y-3">
        {expenses.map((item) => (
          <div key={item.id} className="rounded-[1.5rem] bg-white p-4 shadow-sm">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-semibold">{item.sub_item}</p>
                <p className="mt-1 text-xs text-ink/55">
                  {labelOf(stages, item.stage)} · {labelOf(meta.amount_categories, item.category)}
                </p>
              </div>
              <p className="font-display text-xl font-black text-clay">{money(item.amount)}</p>
            </div>
            {item.note && <p className="mt-3 rounded-2xl bg-sand px-3 py-2 text-sm text-ink/65">{item.note}</p>}
            <div className="mt-3 flex gap-2">
              <button
                onClick={() => setEditing(item)}
                className="inline-flex items-center gap-1 rounded-full bg-sand px-3 py-2 text-xs font-semibold text-ink"
              >
                <Edit3 className="h-3.5 w-3.5" /> 编辑
              </button>
              {item.attachment && (
                <button
                  onClick={() => setPreview(item.attachment || null)}
                  className="rounded-full bg-moss/10 px-3 py-2 text-xs font-semibold text-moss"
                >
                  查看付款凭证
                </button>
              )}
            </div>
          </div>
        ))}
        {expenses.length === 0 && <EmptyLine text="还没有记账记录" />}
      </div>
      {open && (
        <ExpenseForm
          projectId={projectId}
          token={token}
          meta={meta}
          stages={stages}
          onClose={() => setOpen(false)}
          onCreated={onRefresh}
        />
      )}
      {editing && (
        <ExpenseForm
          projectId={projectId}
          token={token}
          meta={meta}
          stages={stages}
          expense={editing}
          onClose={() => setEditing(null)}
          onCreated={onRefresh}
        />
      )}
      {preview && <AttachmentPreview attachment={preview} onClose={() => setPreview(null)} />}
    </div>
  );
}

function ExpenseForm({
  projectId,
  token,
  meta,
  stages,
  onClose,
  onCreated,
  expense,
}: {
  projectId: number;
  token: string;
  meta: MetaOptions;
  stages: ProjectStage[];
  onClose: () => void;
  onCreated: () => Promise<void>;
  expense?: Expense;
}) {
  const [stage, setStage] = useState(expense?.stage || stages[0]?.value || 'design');
  const [category, setCategory] = useState(expense?.category || meta.amount_categories[0]?.value || 'full');
  const [subItem, setSubItem] = useState(expense?.sub_item || '');
  const [amount, setAmount] = useState(expense?.amount || '');
  const [paidAt, setPaidAt] = useState(expense?.paid_at || '');
  const [note, setNote] = useState(expense?.note || '');
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
        stage,
        category,
        sub_item: subItem,
        amount,
        paid_at: paidAt || null,
        note,
        attachment_id: attachment?.id || expense?.attachment_id || null,
      };
      if (expense) {
        await api.updateExpense(token, projectId, expense.id, payload);
      } else {
        await api.createExpense(token, projectId, payload);
      }
      await onCreated();
      onClose();
    });
  }

  return (
    <Modal title={expense ? '编辑记账' : '新增记账'} onClose={onClose}>
      <form onSubmit={submit}>
        <SelectField label="装修阶段" value={stage} onChange={setStage} options={stages} />
        <SelectField label="金额类别" value={category} onChange={setCategory} options={meta.amount_categories} />
        <Field label="子项">
          <input
            value={subItem}
            onChange={(event) => setSubItem(event.target.value)}
            placeholder="家具-中央空调 / 门窗-主卧门"
            required
            className="input"
          />
        </Field>
        <Field label="金额">
          <input type="number" value={amount} onChange={(event) => setAmount(event.target.value)} required className="input" />
        </Field>
        <Field label="付款日期">
          <input type="date" value={paidAt} onChange={(event) => setPaidAt(event.target.value)} className="input" />
        </Field>
        <Field label="付款凭证">
          <input type="file" accept="image/*,.pdf" onChange={(event) => setFile(event.target.files?.[0] || null)} className="file-input" />
          {expense?.attachment && !file && (
            <p className="mt-2 text-xs text-ink/45">当前凭证：{expense.attachment.file_name}</p>
          )}
        </Field>
        <Field label="备注">
          <textarea value={note} onChange={(event) => setNote(event.target.value)} className="input min-h-24" />
        </Field>
        <button disabled={submitting} className="primary-button w-full">
          {submitting ? '保存中...' : expense ? '保存修改' : '保存'}
        </button>
      </form>
    </Modal>
  );
}

function AttachmentPreview({ attachment, onClose }: { attachment: Attachment; onClose: () => void }) {
  const isImage = attachment.content_type?.startsWith('image/');

  return (
    <Modal title="付款凭证" onClose={onClose}>
      <div className="space-y-4">
        {isImage ? (
          <img src={attachment.url} alt={attachment.file_name} className="max-h-[65vh] w-full rounded-2xl object-contain bg-white" />
        ) : (
          <div className="rounded-2xl bg-white p-5 text-sm text-ink/60">
            该凭证不是图片文件，可在新窗口查看。
          </div>
        )}
        <div className="flex gap-2">
          <a
            href={attachment.url}
            target="_blank"
            rel="noreferrer"
            className="secondary-button flex-1"
          >
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
