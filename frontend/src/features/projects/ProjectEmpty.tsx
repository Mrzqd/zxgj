import { useState } from 'react';
import { api } from '../../api';
import { Field } from '../../components/ui';
import { useSubmitting } from '../../hooks/useSubmitting';

export function ProjectEmpty({ token, onCreated }: { token: string; onCreated: () => Promise<void> }) {
  const [name, setName] = useState('');
  const [address, setAddress] = useState('');
  const { submitting, guard } = useSubmitting();

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    await guard(async () => {
      await api.createProject(token, { name, address });
      setName('');
      setAddress('');
      await onCreated();
    });
  }

  return (
    <section className="px-4 py-8">
      <div className="rounded-[2rem] bg-white p-5 shadow-card">
        <h2 className="font-display text-3xl font-bold">创建第一个装修项目</h2>
        <p className="mt-2 text-sm leading-6 text-ink/60">项目是多人共管、记账、比价和验收的统一空间。</p>
        <form onSubmit={submit} className="mt-6">
          <Field label="项目名称">
            <input value={name} onChange={(event) => setName(event.target.value)} required className="input" />
          </Field>
          <Field label="房屋地址">
            <input value={address} onChange={(event) => setAddress(event.target.value)} className="input" />
          </Field>
          <button disabled={submitting} className="primary-button w-full">
            {submitting ? '创建中...' : '创建项目'}
          </button>
        </form>
      </div>
    </section>
  );
}
