import type { ReactNode } from 'react';
import type { Option } from '../types';

export function Modal({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-ink/45 px-3">
      <div className="max-h-[88vh] w-full max-w-md overflow-y-auto rounded-t-[1.5rem] bg-linen p-4 shadow-card">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-display text-xl font-black">{title}</h2>
          <button onClick={onClose} className="rounded-full bg-sand px-3 py-1.5 text-xs font-semibold">
            关闭
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="mb-3 block">
      <span className="mb-1.5 block text-xs font-semibold text-ink/70">{label}</span>
      {children}
    </label>
  );
}

export function SelectField({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Option[];
}) {
  return (
    <Field label={label}>
      <select value={value} onChange={(event) => onChange(event.target.value)} className="input">
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </Field>
  );
}

export function Card({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="rounded-2xl bg-white p-3 shadow-sm">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="font-display text-lg font-bold">{title}</h2>
        {action && <span className="text-xs font-semibold text-ink/45">{action}</span>}
      </div>
      {children}
    </section>
  );
}

export function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-xl bg-white/10 px-2 py-2">
      <p className="font-display text-xl font-black">{value}</p>
      <p className="mt-1 text-xs text-white/55">{label}</p>
    </div>
  );
}

export function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-white p-3 shadow-sm">
      <p className="text-xs font-semibold text-ink/45">{label}</p>
      <p className="mt-1 font-display text-xl font-black">{value}</p>
    </div>
  );
}

export function ModuleHero({ icon, title, subtitle }: { icon: ReactNode; title: string; subtitle: string }) {
  return (
    <div className="flex items-center gap-3 rounded-2xl bg-[linear-gradient(135deg,#15120d,#4d3827)] p-3 text-white shadow-sm">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white/15 [&>svg]:h-4 [&>svg]:w-4">
        {icon}
      </div>
      <div>
        <h2 className="font-display text-xl font-black">{title}</h2>
        <p className="mt-0.5 text-xs leading-4 text-white/65">{subtitle}</p>
      </div>
    </div>
  );
}

export function EmptyLine({ text }: { text: string }) {
  return <p className="rounded-2xl border border-dashed border-ink/15 px-4 py-8 text-center text-sm text-ink/45">{text}</p>;
}

export function ShellLoader() {
  return (
    <main className="grid min-h-screen place-items-center bg-sand text-ink">
      <p className="font-display text-2xl font-black">装修管家加载中...</p>
    </main>
  );
}

export function InlineLoading({ text }: { text: string }) {
  return (
    <div className="rounded-2xl bg-white px-3 py-2 text-xs font-semibold text-ink/45 shadow-sm">
      <span className="mr-2 inline-block h-3 w-3 animate-spin rounded-full border-2 border-clay/20 border-t-clay align-[-2px]" />
      {text}
    </div>
  );
}
