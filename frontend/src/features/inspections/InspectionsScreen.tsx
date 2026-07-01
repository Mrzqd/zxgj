import { useMemo, useState } from 'react';
import { ListTodo, Plus } from 'lucide-react';
import { api } from '../../api';
import { Card, EmptyLine, Field, InlineLoading, Modal, ModuleHero, SelectField } from '../../components/ui';
import { useSubmitting } from '../../hooks/useSubmitting';
import type { Attachment, Inspection, MetaOptions, ProjectStage } from '../../types';
import { labelOf } from '../../utils/format';

export function InspectionsScreen({
  projectId,
  token,
  meta,
  stages,
  inspections,
  loading,
  onRefresh,
}: {
  projectId: number;
  token: string;
  meta: MetaOptions;
  stages: ProjectStage[];
  inspections: Inspection[];
  loading: boolean;
  onRefresh: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [busyInspectionId, setBusyInspectionId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const grouped = useMemo(() => {
    return inspections.reduce<Record<string, Inspection[]>>((acc, item) => {
      acc[item.stage] ||= [];
      acc[item.stage].push(item);
      return acc;
    }, {});
  }, [inspections]);

  async function updateInspectionStatus(item: Inspection, status: string) {
    setBusyInspectionId(item.id);
    try {
      setActionError(null);
      await api.updateInspection(token, projectId, item.id, { status });
      await onRefresh();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : '验收状态更新失败');
    } finally {
      setBusyInspectionId(null);
    }
  }

  return (
    <div className="space-y-4">
      <ModuleHero icon={<ListTodo />} title="验收清单" subtitle="瓦工验收、卫生间流水坡度、厨房阴阳角归方逐项记录。" />
      {loading && <InlineLoading text="验收数据加载中..." />}
      {actionError && <p className="rounded-2xl bg-clay/10 px-3 py-2 text-xs font-semibold text-clay">{actionError}</p>}
      <button onClick={() => setOpen(true)} className="primary-button w-full">
        <Plus className="h-4 w-4" /> 新增验收项
      </button>
      <div className="space-y-4">
        {Object.entries(grouped).map(([stage, items]) => (
          <Card key={stage} title={labelOf(stages, stage)} action={`${items.length} 项`}>
            <div className="space-y-3">
              {items.map((item) => (
                <div key={item.id} className="rounded-2xl bg-sand p-3">
                  <div className="flex items-center justify-between">
                    <p className="font-semibold">{item.item}</p>
                    <select
                      value={item.status}
                      disabled={busyInspectionId === item.id}
                      onChange={(event) => updateInspectionStatus(item, event.target.value)}
                      className="rounded-full bg-white px-2 py-1 text-xs disabled:opacity-50"
                    >
                      {meta.inspection_statuses.map((status) => (
                        <option key={status.value} value={status.value}>
                          {status.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <p className="mt-2 text-sm leading-6 text-ink/60">{item.standard}</p>
                </div>
              ))}
            </div>
          </Card>
        ))}
        {inspections.length === 0 && <EmptyLine text="还没有验收清单" />}
      </div>
      {open && (
        <InspectionForm
          projectId={projectId}
          token={token}
          meta={meta}
          stages={stages}
          onClose={() => setOpen(false)}
          onCreated={onRefresh}
        />
      )}
    </div>
  );
}

function InspectionForm({
  projectId,
  token,
  meta,
  stages,
  onClose,
  onCreated,
}: {
  projectId: number;
  token: string;
  meta: MetaOptions;
  stages: ProjectStage[];
  onClose: () => void;
  onCreated: () => Promise<void>;
}) {
  const [stage, setStage] = useState(stages[0]?.value || 'design');
  const [item, setItem] = useState('');
  const [standard, setStandard] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const { submitting, guard } = useSubmitting();

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    await guard(async () => {
      let attachment: Attachment | null = null;
      if (file) {
        attachment = await api.upload(token, projectId, file);
      }
      await api.createInspection(token, projectId, {
        stage,
        item,
        standard,
        status: 'pending',
        attachment_id: attachment?.id || null,
      });
      await onCreated();
      onClose();
    });
  }

  return (
    <Modal title="新增验收项" onClose={onClose}>
      <form onSubmit={submit}>
        <SelectField label="装修阶段" value={stage} onChange={setStage} options={stages} />
        <Field label="检查项">
          <input value={item} onChange={(event) => setItem(event.target.value)} required className="input" />
        </Field>
        <Field label="验收标准">
          <textarea
            value={standard}
            onChange={(event) => setStandard(event.target.value)}
            placeholder="例如：卫生间应有流水坡度，厨房阴阳角应归方"
            required
            className="input min-h-24"
          />
        </Field>
        <Field label="现场图片">
          <input type="file" accept="image/*" onChange={(event) => setFile(event.target.files?.[0] || null)} className="file-input" />
        </Field>
        <button disabled={submitting} className="primary-button w-full">
          {submitting ? '保存中...' : '保存'}
        </button>
      </form>
    </Modal>
  );
}
