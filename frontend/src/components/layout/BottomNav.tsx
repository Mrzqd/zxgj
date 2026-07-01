import type { ReactNode } from 'react';
import { Bot, ClipboardList, Home, ListTodo, ReceiptText, Scale, Users } from 'lucide-react';
import type { Tab } from '../../app/types';

export function BottomNav({ tab, setTab }: { tab: Tab; setTab: (tab: Tab) => void }) {
  const items: { id: Tab; label: string; icon: ReactNode }[] = [
    { id: 'home', label: '首页', icon: <Home /> },
    { id: 'expenses', label: '记账', icon: <ReceiptText /> },
    { id: 'tasks', label: '事项', icon: <ClipboardList /> },
    { id: 'comparisons', label: '比价', icon: <Scale /> },
    { id: 'inspections', label: '验收', icon: <ListTodo /> },
    { id: 'assistant', label: '助手', icon: <Bot /> },
    { id: 'profile', label: '我的', icon: <Users /> },
  ];

  return (
    <nav className="fixed bottom-0 left-1/2 z-30 grid w-full max-w-md -translate-x-1/2 grid-cols-7 border-t border-ink/10 bg-linen/95 px-1.5 pb-4 pt-2 backdrop-blur">
      {items.map((item) => (
        <button
          key={item.id}
          onClick={() => setTab(item.id)}
          className={`flex flex-col items-center gap-1 rounded-2xl py-2 text-[10px] font-semibold ${
            tab === item.id ? 'bg-ink text-white' : 'text-ink/55'
          }`}
        >
          <span className="[&>svg]:h-4 [&>svg]:w-4">{item.icon}</span>
          {item.label}
        </button>
      ))}
    </nav>
  );
}
