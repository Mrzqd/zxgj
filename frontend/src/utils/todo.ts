export const TODO_IMPORTANCE_OPTIONS = [
  { value: 5, label: '紧急' },
  { value: 4, label: '重要' },
  { value: 3, label: '普通' },
  { value: 2, label: '较低' },
  { value: 1, label: '可延后' },
];

export function todoImportanceLabel(value: number) {
  return TODO_IMPORTANCE_OPTIONS.find((option) => option.value === value)?.label || '普通';
}

