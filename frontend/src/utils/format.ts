import type { Option } from '../types';

export function labelOf(options: Option[], value: string) {
  return options.find((item) => item.value === value)?.label || value;
}

export function money(value: string | number) {
  return Number(value || 0).toLocaleString('zh-CN', {
    style: 'currency',
    currency: 'CNY',
    maximumFractionDigits: 0,
  });
}

export function dateText(value?: string | null) {
  if (!value) return '未设置';
  return new Date(value).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
}

export function datetimeLocalToIso(value: string) {
  return value ? new Date(value).toISOString() : null;
}

