import { useState } from 'react';
import { api } from '../../api';
import { Field, Tip } from '../../components/ui';
import { useSubmitting } from '../../hooks/useSubmitting';
import type { User } from '../../types';

export function AuthScreen({
  onAuth,
  message,
  setMessage,
  invitePending,
}: {
  onAuth: (token: string, user: User) => void;
  message: string | null;
  setMessage: (message: string | null) => void;
  invitePending?: boolean;
}) {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const { submitting, guard } = useSubmitting();

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    await guard(async () => {
      setMessage(null);
      try {
        const response =
          mode === 'login'
            ? await api.login({ email, password })
            : await api.register({ email, name, password });
        onAuth(response.access_token, response.user);
      } catch (error) {
        setMessage(error instanceof Error ? error.message : '登录失败');
      }
    });
  }

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,#f9d08e,transparent_36%),linear-gradient(160deg,#fffaf0,#ead7bd)] px-6 py-10 text-ink">
      <div className="mx-auto flex min-h-[calc(100vh-5rem)] max-w-md flex-col justify-between">
        <div>
          <div className="mb-10">
            <p className="text-sm font-semibold tracking-[0.28em] text-moss">RENOVATION</p>
            <h1 className="mt-3 font-display text-5xl font-black leading-tight">装修管家</h1>
            <p className="mt-4 text-base leading-7 text-ink/70">
              {invitePending
                ? '登录或注册后即可接收项目邀请，加入后共同管理装修事项。'
                : '一套给家装现场用的协作账本：记钱、排事项、验收、比价和待办集中管理。'}
            </p>
          </div>
          <form onSubmit={submit} className="rounded-[2rem] border border-white/70 bg-white/65 p-5 shadow-card backdrop-blur">
            <div className="mb-5 grid grid-cols-2 rounded-full bg-sand p-1 text-sm font-semibold">
              <button
                type="button"
                onClick={() => setMode('login')}
                className={`rounded-full py-2 ${mode === 'login' ? 'bg-ink text-white' : 'text-ink/60'}`}
              >
                登录
              </button>
              <button
                type="button"
                onClick={() => setMode('register')}
                className={`rounded-full py-2 ${mode === 'register' ? 'bg-ink text-white' : 'text-ink/60'}`}
              >
                注册
              </button>
            </div>
            {mode === 'register' && (
              <Field label="昵称">
                <input value={name} onChange={(event) => setName(event.target.value)} required className="input" />
              </Field>
            )}
            <Field label="邮箱">
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
                className="input"
              />
            </Field>
            <Field label="密码">
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
                minLength={8}
                className="input"
              />
            </Field>
            <Tip message={message} onClose={() => setMessage(null)} tone="error" className="mb-4" />
            <button disabled={submitting} className="primary-button w-full">
              {submitting ? '处理中...' : mode === 'login' ? '进入管家' : '创建账号'}
            </button>
          </form>
        </div>
      </div>
    </main>
  );
}
